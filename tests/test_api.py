"""Contract, integration, and failure-mode tests for the FastAPI service."""

from __future__ import annotations

import json
import logging
import time
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression

from api.main import ApiSettings, create_app
from api.metrics import ApiMetrics
from api.schemas import TransactionFeatures
from api.service import ModelService
from src.artifacts.bundle import ModelBundle, save_model_bundle
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor


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
    model = LogisticRegression(random_state=42).fit(preprocessor.transform(training), labels)
    return ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint="b" * 64,
        model_version="api-fixture-1",
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


def test_unavailable_model_is_live_but_not_ready(
    tmp_path: Path, transaction_payload: dict[str, float]
) -> None:
    settings = ApiSettings(tmp_path, None, ())
    with TestClient(create_app(service=ModelService(), settings=settings)) as client:
        assert client.get("/health/live").status_code == 200
        readiness = client.get("/health/ready")
        assert readiness.status_code == 503
        assert readiness.json()["status"] == "not_ready"
        response = client.post("/v1/predict", json=transaction_payload)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_unavailable"


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
    assert body["calibrated_probability"] is None
    assert body["score_type"] == "raw_score"
    assert body["operating_threshold"] == 0.53
    assert body["model_version"] == "api-fixture-1"
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
    assert record["model_version"] == "api-fixture-1"
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
        def transform(self, _frame: pd.DataFrame) -> np.ndarray:
            raise RuntimeError(sentinel)

    broken = ModelBundle(
        preprocessor=ExplodingPreprocessor(),
        model=fitted_bundle.model,
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint="c" * 64,
        model_version="broken-fixture-1",
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
        json.loads(line)
        for line in output.splitlines()
        if '"event":"unhandled_error"' in line
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
        def transform(self, frame: pd.DataFrame) -> object:
            time.sleep(0.2)
            return original.transform(frame)

    slow = ModelBundle(
        preprocessor=SlowPreprocessor(),
        model=fitted_bundle.model,
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint="d" * 64,
        model_version="slow-fixture-1",
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


def test_logs_contain_request_metadata_but_not_transaction_vectors(
    ready_client: TestClient,
    transaction_payload: dict[str, float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="secureswipe.api")
    response = ready_client.post(
        "/v1/predict",
        json=transaction_payload,
        headers={"X-Request-ID": "redaction-check"},
    )
    assert response.status_code == 200
    combined = "\n".join(record.getMessage() for record in caplog.records)
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
        assert set(responses) == {"200", "413", "422", "500", "503"}
        for status in ("413", "422", "500", "503"):
            assert responses[status]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
    model_info_responses = schema["paths"]["/v1/model-info"]["get"]["responses"]
    assert set(model_info_responses) == {"200", "500", "503"}


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
