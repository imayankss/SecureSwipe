"""Focused non-database checks for the gated P1-S2 scale substrate."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression

from api.main import ApiSettings, create_app
from api.postgres_idempotency import PostgresIdempotencyStore
from api.scale_config import (
    PostgresScaleSettings,
    ScaleConfigurationError,
    state_backend_from_environment,
    validate_test_dsn,
)
from api.scale_response import (
    BoundedResponseIntegrityError,
    build_bounded_prediction_response,
    canonical_response_bytes,
)
from api.schemas import TransactionFeatures
from api.service import ModelService
from src.artifacts.bundle import (
    ModelBundle,
    data_role_metadata,
    intended_use_metadata,
    threshold_provenance_metadata,
    training_provenance_metadata,
)
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor

_SCALE_ENVIRONMENT = (
    "SECURESWIPE_STATE_BACKEND",
    "SECURESWIPE_POSTGRES_DSN",
    "SECURESWIPE_POSTGRES_SCHEMA",
    "SECURESWIPE_POSTGRES_POOL_MIN_SIZE",
    "SECURESWIPE_POSTGRES_POOL_MAX_SIZE",
    "SECURESWIPE_POSTGRES_CONNECT_TIMEOUT_SECONDS",
    "SECURESWIPE_IDEMPOTENCY_HMAC_SECRET",
    "SECURESWIPE_AUDIT_LOG",
)


@pytest.fixture(scope="module")
def scale_bundle() -> ModelBundle:
    rng = np.random.default_rng(20260830)
    frame = pd.DataFrame(rng.normal(size=(40, len(ALL_FEATURES))), columns=ALL_FEATURES)
    frame["Time"] = np.arange(40, dtype=float)
    frame["Amount"] = np.abs(frame["Amount"] * 10)
    labels = np.array([0, 1] * 20)
    preprocessor = fit_preprocessor(frame, build_preprocessor())
    preprocessor.set_output(transform="pandas")
    model = LogisticRegression(random_state=42).fit(preprocessor.transform(frame), labels)
    role = data_role_metadata(
        fingerprint_sha256="b" * 64,
        total_row_count=40,
        fraud_row_count=20,
        duplicate_row_count=0,
    )
    training = training_provenance_metadata(
        producer_policy="synthetic_api_smoke_v1",
        model_fit=role,
        calibrator_fit=None,
        threshold_selection=None,
        evaluation=None,
        quarantine=None,
    )
    return ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=training.data_roles_sha256,
        model_version="synthetic-smoke-1",
        intended_use=intended_use_metadata("synthetic_api_smoke_v1"),
        threshold_provenance=threshold_provenance_metadata(
            producer_policy="synthetic_api_smoke_v1", value=0.53, calibrated=False
        ),
        training_provenance=training,
        model_artifact_sha256="a" * 64,
    )


@pytest.fixture(scope="module")
def transaction() -> TransactionFeatures:
    values = {feature: float(index) / 10.0 for index, feature in enumerate(ALL_FEATURES)}
    values["Time"] = 10.0
    values["Amount"] = 19.95
    return TransactionFeatures.model_validate(values)


def test_default_profile_has_no_scale_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SCALE_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    assert state_backend_from_environment() == "local-default"
    settings = ApiSettings.from_environment()
    assert settings.state_backend == "local-default"
    assert settings.postgres_scale is None


def test_scale_configuration_requires_every_secret_and_rejects_ambiguous_local_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in _SCALE_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECURESWIPE_STATE_BACKEND", "postgres-scale")
    with pytest.raises(ScaleConfigurationError, match="DSN is required"):
        ApiSettings.from_environment()

    monkeypatch.setenv(
        "SECURESWIPE_POSTGRES_DSN",
        "postgresql://scale_user:private-value@127.0.0.1:55432/secureswipe_p1_scale_test",
    )
    monkeypatch.setenv("SECURESWIPE_POSTGRES_SCHEMA", "secureswipe_s2_test_config")
    with pytest.raises(ScaleConfigurationError, match="HMAC_SECRET is required") as caught:
        ApiSettings.from_environment()
    assert "private-value" not in str(caught.value)

    monkeypatch.setenv("SECURESWIPE_IDEMPOTENCY_HMAC_SECRET", "x" * 32)
    settings = ApiSettings.from_environment()
    assert settings.state_backend == "postgres-scale"
    assert settings.postgres_scale is not None
    assert "private-value" not in repr(settings.postgres_scale)

    monkeypatch.setenv("SECURESWIPE_STATE_BACKEND", "local-default")
    with pytest.raises(ScaleConfigurationError, match="require.*postgres-scale"):
        ApiSettings.from_environment()


def test_test_dsn_guard_requires_loopback_and_test_database() -> None:
    validate_test_dsn("postgresql://user:secret@127.0.0.1:55432/example_test")
    with pytest.raises(ScaleConfigurationError, match="loopback"):
        validate_test_dsn("postgresql://user:secret@db.example.invalid/example_test")
    with pytest.raises(ScaleConfigurationError, match="end in _test"):
        validate_test_dsn("postgresql://user:secret@127.0.0.1:55432/example")


def test_bounded_response_uses_loaded_bundle_provenance_and_contains_no_scores(
    scale_bundle: ModelBundle, transaction: TransactionFeatures
) -> None:
    service = ModelService(scale_bundle)
    result = service.predict_one(transaction)
    bounded = build_bounded_prediction_response(service=service, result=result)
    payload = bounded.model_dump(mode="json")
    encoded = canonical_response_bytes(bounded).decode("utf-8")

    assert payload["model"]["historical_taint"] is False
    assert payload["model"]["decision_eligible"] is False
    assert payload["model"]["historical_metrics_claimed"] is False
    assert payload["model"]["evaluation_performed"] is False
    assert payload["model"]["model_artifact_sha256"] == scale_bundle.model_artifact_sha256
    assert payload["policy"]["producer_policy"] == scale_bundle.intended_use.producer_policy
    assert payload["policy"]["threshold_source"] == scale_bundle.threshold_provenance.source
    assert payload["policy"]["threshold_model_linkage"] == (
        scale_bundle.threshold_provenance.model_linkage
    )
    for forbidden in (
        "raw_score",
        "decision_score",
        "calibrated_probability",
        '"score"',
        '"request_id"',
        '"features"',
        '"payload"',
    ):
        assert forbidden not in encoded


def test_bounded_response_rejects_provenance_not_matching_loaded_bundle(
    scale_bundle: ModelBundle, transaction: TransactionFeatures
) -> None:
    service = ModelService(scale_bundle)
    result = service.predict_one(transaction)
    altered = result.model_copy(
        update={
            "provenance": result.provenance.model_copy(update={"decision_eligible": True})
        }
    )
    with pytest.raises(BoundedResponseIntegrityError, match="does not match"):
        build_bounded_prediction_response(service=service, result=altered)


def test_postgres_profile_keeps_public_v1_prediction_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scale_bundle: ModelBundle,
    transaction: TransactionFeatures,
) -> None:
    calls = 0

    class CountingService(ModelService):
        def predict_one(self, value: TransactionFeatures):
            nonlocal calls
            calls += 1
            return super().predict_one(value)

    async def fake_open(store: PostgresIdempotencyStore) -> None:
        del store

    monkeypatch.setattr(PostgresIdempotencyStore, "open", fake_open)
    postgres = PostgresScaleSettings(
        dsn="postgresql://user:secret@127.0.0.1:55432/secureswipe_p1_scale_test",
        schema="secureswipe_s2_test_api_gate",
        hmac_secret=b"x" * 32,
    )
    settings = ApiSettings(
        artifact_root=tmp_path,
        bundle_manifest=None,
        cors_origins=(),
        state_backend="postgres-scale",
        postgres_scale=postgres,
    )
    with TestClient(create_app(service=CountingService(scale_bundle), settings=settings)) as client:
        ready = client.get("/health/ready")
        prediction = client.post(
            "/v1/predict",
            json=transaction.model_dump(mode="json"),
            headers={"X-Request-ID": "scale-gate-1"},
        )
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert prediction.status_code == 503
    assert prediction.json()["error"]["code"] == "scale_profile_requires_v2"
    assert calls == 0


def test_configuration_never_serializes_secrets() -> None:
    settings = PostgresScaleSettings(
        dsn="postgresql://user:do-not-print@127.0.0.1:55432/secureswipe_p1_scale_test",
        schema="secureswipe_s2_test_redaction",
        hmac_secret=b"do-not-print-this-secret-value!!",
    )
    serialized = json.dumps({"settings": repr(settings)})
    assert "do-not-print" not in serialized
