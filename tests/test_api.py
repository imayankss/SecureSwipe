"""Contract, integration, and failure-mode tests for the FastAPI service."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import replace
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression

from api.audit import AuditLog, verify_audit_log
from api.main import ApiSettings, create_app
from api.metrics import ApiMetrics
from api.schemas import TransactionFeatures
from api.service import ModelService
from src.artifacts.bundle import (
    ModelBundle,
    data_role_metadata,
    intended_use_metadata,
    save_model_bundle,
    threshold_provenance_metadata,
    training_provenance_metadata,
)
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor


def _synthetic_training_provenance(fingerprint: str):
    return training_provenance_metadata(
        producer_policy="synthetic_api_smoke_v1",
        model_fit=data_role_metadata(
            fingerprint_sha256=fingerprint,
            total_row_count=80,
            fraud_row_count=40,
            duplicate_row_count=0,
        ),
        calibrator_fit=None,
        threshold_selection=None,
        evaluation=None,
        quarantine=None,
    )


@pytest.fixture(scope="module")
def transaction_payload() -> dict[str, float]:
    payload = {feature: float(index) / 10.0 for index, feature in enumerate(ALL_FEATURES)}
    payload["Time"] = 1234.0
    payload["Amount"] = 123.456789
    return payload


@pytest.fixture(scope="module")
def fitted_bundle() -> ModelBundle:
    rng = np.random.default_rng(42)
    training = pd.DataFrame(
        rng.normal(size=(80, len(ALL_FEATURES))),
        columns=ALL_FEATURES,
    )
    training["Time"] = np.arange(80, dtype=float)
    training["Amount"] = np.abs(training["Amount"] * 100.0)
    labels = np.array([0, 1] * 40)
    preprocessor = fit_preprocessor(training, build_preprocessor())
    preprocessor.set_output(transform="pandas")
    model = LogisticRegression(random_state=42).fit(preprocessor.transform(training), labels)
    training_provenance = _synthetic_training_provenance("b" * 64)
    return ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=training_provenance.data_roles_sha256,
        model_version="synthetic-smoke-1",
        intended_use=intended_use_metadata("synthetic_api_smoke_v1"),
        threshold_provenance=threshold_provenance_metadata(
            producer_policy="synthetic_api_smoke_v1",
            value=0.53,
            calibrated=False,
        ),
        training_provenance=training_provenance,
    )


@pytest.fixture
def ready_client(fitted_bundle: ModelBundle, tmp_path: Path) -> TestClient:
    settings = ApiSettings(
        artifact_root=tmp_path,
        bundle_manifest=None,
        cors_origins=(),
    )
    with TestClient(create_app(service=ModelService(fitted_bundle), settings=settings)) as client:
        yield client


def test_liveness_readiness_and_model_info(
    ready_client: TestClient,
    fitted_bundle: ModelBundle,
) -> None:
    live = ready_client.get("/health/live")
    ready = ready_client.get("/health/ready")
    info = ready_client.get("/v1/model-info")
    assert live.status_code == 200 and live.json()["status"] == "live"
    assert ready.status_code == 200 and ready.json()["status"] == "ready"
    assert info.status_code == 200
    assert info.json()["model_version"] == fitted_bundle.model_version
    assert info.json()["score_type"] == "raw_score"
    assert info.json()["calibrated"] is False
    assert info.json()["feature_schema"] == list(ALL_FEATURES)
    assert info.json()["evidence_category"] == "synthetic_demo_inference"
    assert info.json()["historical_taint"] is False
    assert info.json()["decision_eligible"] is False
    assert info.json()["historical_metrics_claimed"] is False
    assert info.json()["evaluation_performed"] is False


def test_unavailable_model_is_live_but_not_ready(
    tmp_path: Path, transaction_payload: dict[str, float]
) -> None:
    settings = ApiSettings(tmp_path, None, ())
    with TestClient(create_app(service=ModelService(), settings=settings)) as client:
        assert client.get("/health/live").status_code == 200
        readiness = client.get("/health/ready")
        assert readiness.status_code == 503
        assert readiness.json()["status"] == "not_ready"
        response = client.post(
            "/v1/predict",
            json=transaction_payload,
            headers={"X-Request-ID": "unavailable-fail-closed-1"},
        )
        assert response.status_code == 503
        body = response.json()
        assert body["request_id"] == "unavailable-fail-closed-1"
        assert body["error"]["code"] == "model_unavailable"
        assert "decision" not in body


@pytest.mark.parametrize(
    ("method", "path", "status", "message"),
    [
        ("GET", "/does-not-exist", 404, "Not Found"),
        ("POST", "/health/live", 405, "Method Not Allowed"),
    ],
)
def test_starlette_http_errors_use_stable_error_contract(
    ready_client: TestClient,
    method: str,
    path: str,
    status: int,
    message: str,
) -> None:
    response = ready_client.request(method, path)
    assert response.status_code == status
    assert response.json() == {
        "schema_version": "1.0",
        "request_id": response.headers["x-request-id"],
        "error": {"code": "http_error", "message": message, "details": None},
    }
    if status == 405:
        assert response.headers["allow"] == "GET"


def test_single_prediction_matches_direct_bundle_path(
    ready_client: TestClient,
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
) -> None:
    response = ready_client.post(
        "/v1/predict",
        json=transaction_payload,
        headers={"X-Request-ID": "golden-parity-1"},
    )
    assert response.status_code == 200
    body = response.json()
    direct = ModelService(fitted_bundle).predict_one(TransactionFeatures(**transaction_payload))
    assert body["raw_score"] == direct.raw_score
    assert body["decision_score"] == direct.decision_score
    assert body["decision"] == direct.decision
    assert body["calibrated_probability"] is None
    assert body["score_type"] == "raw_score"
    assert body["operating_threshold"] == 0.53
    assert body["model_version"] == "synthetic-smoke-1"
    assert body["bundle_format_version"] == "3"
    assert body["provenance"] == {
        "training_data_fingerprint": fitted_bundle.training_data_fingerprint,
        "evidence_category": "synthetic_demo_inference",
        "historical_taint": False,
        "decision_eligible": False,
        "historical_metrics_claimed": False,
        "evaluation_performed": False,
    }
    assert body["request_id"] == "golden-parity-1"
    assert response.headers["x-request-id"] == "golden-parity-1"


def test_named_json_order_is_safely_normalized(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    forward = ready_client.post("/v1/predict", json=transaction_payload).json()["raw_score"]
    reversed_payload = dict(reversed(list(transaction_payload.items())))
    reverse = ready_client.post("/v1/predict", json=reversed_payload).json()["raw_score"]
    assert reverse == forward


def test_batch_prediction_and_concurrent_determinism(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    response = ready_client.post(
        "/v1/predict/batch",
        json={"transactions": [transaction_payload, transaction_payload]},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["predictions"][0] == response.json()["predictions"][1]

    def score() -> float:
        result = ready_client.post("/v1/predict", json=transaction_payload)
        assert result.status_code == 200
        return result.json()["raw_score"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        scores = list(executor.map(lambda _: score(), range(12)))
    assert len(set(scores)) == 1


def test_single_endpoint_matches_single_item_batch_endpoint(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    single = ready_client.post(
        "/v1/predict",
        json=transaction_payload,
        headers={"X-Request-ID": "single-vs-batch-1"},
    ).json()
    batch = ready_client.post(
        "/v1/predict/batch",
        json={"transactions": [transaction_payload]},
        headers={"X-Request-ID": "single-vs-batch-2"},
    ).json()
    assert batch["count"] == 1
    batched = batch["predictions"][0]
    assert single["raw_score"] == batched["raw_score"]
    assert single["decision_score"] == batched["decision_score"]
    assert single["calibrated_probability"] == batched["calibrated_probability"]
    assert single["decision"] == batched["decision"]
    assert single["operating_threshold"] == batched["operating_threshold"]
    assert single["model_version"] == batch["model_version"] == batched["model_version"]
    assert single["bundle_format_version"] == batched["bundle_format_version"] == "3"
    assert single["provenance"] == batched["provenance"]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [("Amount", -1.0), ("Time", -1.0), ("V1", "1.0"), ("V2", True)],
)
def test_invalid_values_use_stable_redacted_error_contract(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
    field: str,
    invalid: object,
) -> None:
    payload = dict(transaction_payload)
    payload[field] = invalid  # type: ignore[assignment]
    response = ready_client.post("/v1/predict", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["error"]["code"] == "validation_error"
    assert "input" not in json.dumps(body).lower()


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_is_rejected(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
    token: str,
) -> None:
    raw = json.dumps(transaction_payload).replace("1234.0", token, 1)
    response = ready_client.post(
        "/v1/predict",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_field_and_oversized_batch_are_rejected(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    extra = dict(transaction_payload, card_number=4111111111111111)
    assert ready_client.post("/v1/predict", json=extra).status_code == 422
    response = ready_client.post(
        "/v1/predict/batch",
        json={"transactions": [transaction_payload] * 101},
    )
    assert response.status_code == 422


def test_request_body_limit_handles_stream_without_reaching_schema(
    fitted_bundle: ModelBundle,
    tmp_path: Path,
) -> None:
    settings = ApiSettings(tmp_path, None, (), max_request_bytes=1024)
    with TestClient(create_app(service=ModelService(fitted_bundle), settings=settings)) as client:
        response = client.post(
            "/v1/predict",
            content=b"{" + b"x" * 2048,
            headers={"content-type": "application/json", "X-Request-ID": "too-big-1"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert response.headers["x-request-id"] == "too-big-1"


def test_metrics_are_prometheus_compatible_and_bounded(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    ready_client.post("/v1/predict", json=transaction_payload)
    response = ready_client.get("/metrics")
    assert response.status_code == 200
    assert "secureswipe_http_requests_total" in response.text
    assert 'route="/v1/predict"' in response.text
    assert "request_id=" not in response.text
    assert "secureswipe_prediction_decision_score_bucket" in response.text


def test_metrics_normalize_attacker_controlled_methods() -> None:
    metrics = ApiMetrics()
    for index in range(500):
        metrics.observe_request(f"LOAD{index}", "/health/live", 405, 0.001)
    exposition = metrics.render()
    request_series = [
        line
        for line in exposition.splitlines()
        if line.startswith("secureswipe_http_requests_total{")
    ]
    assert request_series == [
        'secureswipe_http_requests_total{method="OTHER",route="/health/live",status="405"} 500'
    ]


def test_api_info_logging_is_enabled_and_emits_parseable_redacted_json(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("secureswipe.api")
    logger.addHandler(handler)
    try:
        response = ready_client.post(
            "/v1/predict",
            json=transaction_payload,
            headers={"X-Request-ID": "runtime-log-check"},
        )
    finally:
        logger.removeHandler(handler)
    assert response.status_code == 200
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    record = next(item for item in records if item["request_id"] == "runtime-log-check")
    assert record["method"] == "POST"
    assert record["route"] == "/v1/predict"
    assert record["status"] == 200
    assert record["model_version"] == "synthetic-smoke-1"
    assert isinstance(record["latency_ms"], float)
    assert "123.456789" not in stream.getvalue()
    assert '"V28"' not in stream.getvalue()


def test_unexpected_model_exception_log_omits_exception_message_and_features(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    sentinel = "SENSITIVE-123.456789-V1-V28"

    class ExplodingPreprocessor:
        n_features_in_ = fitted_bundle.preprocessor.n_features_in_
        feature_names_in_ = fitted_bundle.preprocessor.feature_names_in_

        def get_feature_names_out(self) -> np.ndarray:
            return fitted_bundle.preprocessor.get_feature_names_out()

        def transform(self, _frame: pd.DataFrame) -> np.ndarray:
            raise RuntimeError(sentinel)

    broken = replace(
        fitted_bundle,
        preprocessor=ExplodingPreprocessor(),
        training_data_fingerprint=_synthetic_training_provenance("c" * 64).data_roles_sha256,
        training_provenance=_synthetic_training_provenance("c" * 64),
    )
    service = ModelService(fitted_bundle)
    service._bundle = broken
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("secureswipe.api")
    logger.addHandler(handler)
    try:
        with TestClient(
            create_app(
                service=service,
                settings=ApiSettings(tmp_path, None, ()),
            ),
            raise_server_exceptions=False,
        ) as client:
            response = client.post(
                "/v1/predict",
                json=transaction_payload,
                headers={"X-Request-ID": "exception-redaction-check"},
            )
    finally:
        logger.removeHandler(handler)
    assert response.status_code == 500
    assert response.json() == {
        "schema_version": "1.0",
        "request_id": "exception-redaction-check",
        "error": {
            "code": "internal_error",
            "message": "An internal error occurred.",
            "details": None,
        },
    }
    output = stream.getvalue()
    assert sentinel not in output
    assert '"V28"' not in output
    error_record = next(
        json.loads(line) for line in output.splitlines() if '"event":"unhandled_error"' in line
    )
    assert error_record == {
        "event": "unhandled_error",
        "request_id": "exception-redaction-check",
        "error_class": "RuntimeError",
    }


def test_slow_inference_is_offloaded_so_liveness_remains_responsive(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    original = fitted_bundle.preprocessor

    class SlowPreprocessor:
        n_features_in_ = original.n_features_in_
        feature_names_in_ = original.feature_names_in_

        def get_feature_names_out(self) -> np.ndarray:
            return original.get_feature_names_out()

        def transform(self, frame: pd.DataFrame) -> object:
            time.sleep(0.3)
            return original.transform(frame)

    slow = replace(
        fitted_bundle,
        preprocessor=SlowPreprocessor(),
        training_data_fingerprint=_synthetic_training_provenance("d" * 64).data_roles_sha256,
        training_provenance=_synthetic_training_provenance("d" * 64),
    )
    with TestClient(
        create_app(service=ModelService(slow), settings=ApiSettings(tmp_path, None, ()))
    ) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            prediction = executor.submit(client.post, "/v1/predict", json=transaction_payload)
            time.sleep(0.04)
            started = time.perf_counter()
            health = client.get("/health/live")
            health_latency = time.perf_counter() - started
        assert prediction.result().status_code == 200
    assert health.status_code == 200
    assert health_latency < 0.15


def test_prediction_exceeding_deadline_returns_stable_timeout_error(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    class BlockingService(ModelService):
        def __init__(self) -> None:
            super().__init__(fitted_bundle)
            self.started = threading.Event()
            self.release = threading.Event()
            self.finished = threading.Event()

        def predict_one(self, transaction: TransactionFeatures):
            self.started.set()
            try:
                if not self.release.wait(timeout=2.0):
                    raise RuntimeError("Test worker release timed out.")
                return super().predict_one(transaction)
            finally:
                self.finished.set()

    service = BlockingService()
    settings = ApiSettings(tmp_path, None, (), prediction_timeout_seconds=0.1)
    with TestClient(create_app(service=service, settings=settings)) as client:
        started = time.perf_counter()
        response = client.post(
            "/v1/predict",
            json=transaction_payload,
            headers={"X-Request-ID": "timeout-check-1"},
        )
        elapsed = time.perf_counter() - started
        assert service.started.wait(timeout=1.0)
        service.release.set()
        assert service.finished.wait(timeout=1.0)
    assert response.status_code == 504
    body = response.json()
    assert body == {
        "schema_version": "1.0",
        "request_id": "timeout-check-1",
        "error": {
            "code": "prediction_timeout",
            "message": "Prediction exceeded the 0.1s deadline.",
            "details": None,
        },
    }
    assert "decision" not in body
    assert response.headers["x-request-id"] == "timeout-check-1"
    assert elapsed < 0.5


def test_repeated_timeouts_hold_capacity_until_prediction_workers_finish(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    class TrackingBlockingService(ModelService):
        def __init__(self) -> None:
            super().__init__(fitted_bundle)
            self.release_workers = threading.Event()
            self.worker_condition = threading.Condition()
            self.active_workers = 0
            self.max_active_workers = 0

        def predict_one(self, transaction: TransactionFeatures):
            with self.worker_condition:
                self.active_workers += 1
                self.max_active_workers = max(self.max_active_workers, self.active_workers)
                self.worker_condition.notify_all()
            try:
                if not self.release_workers.wait(timeout=2.0):
                    raise RuntimeError("Test worker release timed out.")
                return super().predict_one(transaction)
            finally:
                with self.worker_condition:
                    self.active_workers -= 1
                    self.worker_condition.notify_all()

        def wait_for_active_workers(self, expected: int) -> bool:
            with self.worker_condition:
                return self.worker_condition.wait_for(
                    lambda: self.active_workers == expected,
                    timeout=1.0,
                )

    service = TrackingBlockingService()
    settings = ApiSettings(
        tmp_path,
        None,
        (),
        prediction_timeout_seconds=0.1,
        max_concurrent_predictions=2,
    )
    with TestClient(create_app(service=service, settings=settings)) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            timed_out_requests = [
                executor.submit(
                    client.post,
                    "/v1/predict",
                    json=transaction_payload,
                    headers={"X-Request-ID": f"timeout-capacity-{index}"},
                )
                for index in range(2)
            ]
            assert service.wait_for_active_workers(2)
            timed_out_responses = [future.result(timeout=1.0) for future in timed_out_requests]

        assert [response.status_code for response in timed_out_responses] == [504, 504]
        assert client.app.state.concurrency_gate.in_flight == 2

        rejected = [
            client.post(
                "/v1/predict",
                json=transaction_payload,
                headers={"X-Request-ID": f"timeout-retry-{index}"},
            )
            for index in range(3)
        ]
        assert [response.status_code for response in rejected] == [503, 503, 503]
        assert all(response.json()["error"]["code"] == "capacity_exceeded" for response in rejected)
        assert service.active_workers == 2
        assert service.max_active_workers == settings.max_concurrent_predictions

        service.release_workers.set()
        assert service.wait_for_active_workers(0)
        deadline = time.monotonic() + 1.0
        while client.app.state.concurrency_gate.in_flight and time.monotonic() < deadline:
            time.sleep(0.001)
        assert client.app.state.concurrency_gate.in_flight == 0


def test_prediction_capacity_exceeded_fails_closed_deterministically(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    class BlockingService(ModelService):
        def __init__(self) -> None:
            super().__init__(fitted_bundle)
            self.started = threading.Event()
            self.release = threading.Event()

        def predict_one(self, transaction: TransactionFeatures):
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise RuntimeError("Test worker release timed out.")
            return super().predict_one(transaction)

    service = BlockingService()
    settings = ApiSettings(tmp_path, None, (), max_concurrent_predictions=1)
    with TestClient(create_app(service=service, settings=settings)) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                client.post,
                "/v1/predict",
                json=transaction_payload,
                headers={"X-Request-ID": "capacity-first"},
            )
            assert service.started.wait(timeout=1.0)
            second = client.post(
                "/v1/predict",
                json=transaction_payload,
                headers={"X-Request-ID": "capacity-second"},
            )
            service.release.set()
            first_response = first.result(timeout=1.0)
        assert client.app.state.concurrency_gate.in_flight == 0
        recovered = client.post(
            "/v1/predict",
            json=transaction_payload,
            headers={"X-Request-ID": "capacity-recovered"},
        )
    assert first_response.status_code == 200
    assert second.status_code == 503
    second_body = second.json()
    assert second_body["error"]["code"] == "capacity_exceeded"
    assert second_body["request_id"] == "capacity-second"
    assert "decision" not in second_body
    assert recovered.status_code == 200
    assert recovered.json()["decision"] in {"human_review", "below_review_threshold"}


def test_logs_contain_request_metadata_but_not_transaction_vectors(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("secureswipe.api")
    logger.addHandler(handler)
    try:
        response = ready_client.post(
            "/v1/predict",
            json=transaction_payload,
            headers={"X-Request-ID": "redaction-check"},
        )
    finally:
        logger.removeHandler(handler)
    assert response.status_code == 200
    combined = stream.getvalue()
    assert "redaction-check" in combined
    assert "123.456789" not in combined
    assert '"V28"' not in combined


def test_openapi_contains_versioned_contracts(ready_client: TestClient) -> None:
    schema = ready_client.get("/openapi.json").json()
    assert schema["info"]["version"] == "1.0"
    for path in (
        "/health/live",
        "/health/ready",
        "/v1/model-info",
        "/v1/predict",
        "/v1/predict/batch",
    ):
        assert path in schema["paths"]
    transaction_schema = schema["components"]["schemas"]["TransactionFeatures"]
    assert transaction_schema["additionalProperties"] is False
    assert set(transaction_schema["required"]) == set(ALL_FEATURES)
    for path in ("/v1/predict", "/v1/predict/batch"):
        responses = schema["paths"][path]["post"]["responses"]
        assert set(responses) == {"200", "409", "413", "422", "500", "503", "504"}
        for status in ("409", "413", "422", "500", "503", "504"):
            assert responses[status]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
    model_info_responses = schema["paths"]["/v1/model-info"]["get"]["responses"]
    assert set(model_info_responses) == {"200", "500", "503"}


def test_duplicate_prediction_replays_without_rescoring_or_duplicate_audit_event(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    class CountingService(ModelService):
        def __init__(self, bundle: ModelBundle) -> None:
            super().__init__(bundle)
            self.calls = 0

        def predict_one(self, transaction: TransactionFeatures):
            self.calls += 1
            time.sleep(0.05)
            return super().predict_one(transaction)

    audited_bundle = replace(fitted_bundle, model_artifact_sha256="a" * 64)
    service = CountingService(audited_bundle)
    audit_path = tmp_path / "prediction-events.ndjson"
    settings = ApiSettings(tmp_path, None, (), audit_log_path=audit_path)
    headers = {
        "X-Request-ID": "idempotent-prediction-1",
        "Authorization": "Bearer do-not-record-this-secret",
        "X-Api-Key": "do-not-record-this-api-key",
        "Cookie": "session=do-not-record-this-cookie",
    }
    with TestClient(create_app(service=service, settings=settings)) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [
                executor.submit(
                    client.post,
                    "/v1/predict",
                    json=transaction_payload,
                    headers=headers,
                )
                for _ in range(2)
            ]
            first, replay = [attempt.result(timeout=2.0) for attempt in attempts]

        conflicting_payload = dict(transaction_payload)
        conflicting_payload["Amount"] += 1.0
        conflict = client.post("/v1/predict", json=conflicting_payload, headers=headers)

        rejected_payload = {
            **transaction_payload,
            "PAN": "4111111111111111",
            "CVV": "999",
            "secret": "payload-secret",
            "customer_email": "person@example.invalid",
        }
        rejected = client.post(
            "/v1/predict",
            json=rejected_payload,
            headers={"X-Request-ID": "privacy-rejection-1"},
        )

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert sorted(
        response.headers.get("x-idempotent-replay", "false") for response in (first, replay)
    ) == ["false", "true"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert rejected.status_code == 422
    assert service.calls == 1

    verified = verify_audit_log(audit_path)
    assert verified.event_count == 1
    event = json.loads(audit_path.read_text(encoding="ascii"))
    assert event["request_id"] == "idempotent-prediction-1"
    assert event["model_fingerprint_sha256"] == "a" * 64
    assert event["model_version"] == "synthetic-smoke-1"
    assert event["score"] == first.json()["decision_score"]
    assert event["threshold"] == 0.53
    assert event["decision"] in {"human_review", "below_review_threshold"}

    encoded = audit_path.read_text(encoding="ascii")
    for forbidden in (
        "4111111111111111",
        "999",
        "payload-secret",
        "person@example.invalid",
        "do-not-record-this-secret",
        "do-not-record-this-api-key",
        "do-not-record-this-cookie",
        "123.456789",
        '"V28"',
        '"Amount"',
    ):
        assert forbidden not in encoded


def test_transient_audit_sink_failure_fails_closed_then_recovers_without_sleeping(
    fitted_bundle: ModelBundle,
    transaction_payload: dict[str, float],
    tmp_path: Path,
) -> None:
    sentinel = "SENSITIVE-INJECTED-AUDIT-FAILURE"

    class CountingService(ModelService):
        def __init__(self, bundle: ModelBundle) -> None:
            super().__init__(bundle)
            self.calls = 0

        def predict_one(self, transaction: TransactionFeatures):
            self.calls += 1
            return super().predict_one(transaction)

    class FailOnceAuditSink:
        def __init__(self, delegate: AuditLog) -> None:
            self.delegate = delegate
            self.attempts = 0

        def append_inference(self, **kwargs: object) -> tuple[str, ...]:
            self.attempts += 1
            if self.attempts == 1:
                raise OSError(sentinel)
            return self.delegate.append_inference(**kwargs)

    audited_bundle = replace(fitted_bundle, model_artifact_sha256="a" * 64)
    service = CountingService(audited_bundle)
    audit_path = tmp_path / "prediction-events.ndjson"
    settings = ApiSettings(tmp_path, None, (), audit_log_path=audit_path)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("secureswipe.api")
    logger.addHandler(handler)
    started = time.perf_counter()
    try:
        with TestClient(create_app(service=service, settings=settings)) as client:
            sink = FailOnceAuditSink(client.app.state.audit_log)
            client.app.state.audit_log = sink
            headers = {"X-Request-ID": "audit-recovery-1"}
            failed = client.post("/v1/predict", json=transaction_payload, headers=headers)
            recovered = client.post("/v1/predict", json=transaction_payload, headers=headers)
            replay = client.post("/v1/predict", json=transaction_payload, headers=headers)
    finally:
        logger.removeHandler(handler)
    elapsed = time.perf_counter() - started

    assert failed.status_code == 503
    assert failed.json() == {
        "schema_version": "1.0",
        "request_id": "audit-recovery-1",
        "error": {
            "code": "audit_unavailable",
            "message": "Audit evidence is unavailable; no inference result was released.",
            "details": None,
        },
    }
    assert "decision" not in failed.json()
    assert recovered.status_code == replay.status_code == 200
    assert recovered.json() == replay.json()
    assert replay.headers["x-idempotent-replay"] == "true"
    assert recovered.json()["decision"] in {"human_review", "below_review_threshold"}
    assert service.calls == 2
    assert sink.attempts == 2
    assert verify_audit_log(audit_path).event_count == 1
    assert sentinel not in stream.getvalue()
    assert elapsed < 20.0


def test_configured_corrupt_bundle_refuses_startup(
    fitted_bundle: ModelBundle,
    tmp_path: Path,
) -> None:
    trusted_root = tmp_path / "artifacts"
    manifest = save_model_bundle(fitted_bundle, trusted_root / "api-fixture-1")
    model_path = manifest.parent / "model.joblib"
    model_path.write_bytes(model_path.read_bytes() + b"corrupt")
    settings = ApiSettings(
        artifact_root=trusted_root,
        bundle_manifest=manifest,
        cors_origins=(),
    )
    with pytest.raises(RuntimeError, match="failed verification"):
        with TestClient(create_app(settings=settings)):
            pass


def test_cors_uses_explicit_allowlist(fitted_bundle: ModelBundle, tmp_path: Path) -> None:
    settings = ApiSettings(tmp_path, None, ("https://demo.example",))
    with TestClient(create_app(service=ModelService(fitted_bundle), settings=settings)) as client:
        allowed = client.options(
            "/v1/predict",
            headers={
                "Origin": "https://demo.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        denied = client.options(
            "/v1/predict",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert allowed.headers["access-control-allow-origin"] == "https://demo.example"
    assert "access-control-allow-origin" not in denied.headers
