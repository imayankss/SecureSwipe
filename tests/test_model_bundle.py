"""Trust-boundary and round-trip tests for versioned ModelBundle artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from src.artifacts.bundle import (
    ArtifactVerificationError,
    ModelBundle,
    load_model_bundle,
    load_verified_joblib,
    save_model_bundle,
    write_checksum_sidecar,
)
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor


def _training_fixture() -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(42)
    values = rng.normal(size=(40, len(ALL_FEATURES)))
    frame = pd.DataFrame(values, columns=ALL_FEATURES)
    frame["Time"] = np.arange(len(frame), dtype=float)
    frame["Amount"] = np.abs(frame["Amount"])
    labels = np.array([0, 1] * 20)
    return frame, labels


def _bundle() -> tuple[ModelBundle, pd.DataFrame]:
    frame, labels = _training_fixture()
    preprocessor = fit_preprocessor(frame, build_preprocessor())
    processed = preprocessor.transform(frame)
    model = LogisticRegression(random_state=42).fit(processed, labels)
    return (
        ModelBundle(
            preprocessor=preprocessor,
            model=model,
            calibrator=None,
            operating_threshold=0.53,
            feature_schema=tuple(ALL_FEATURES),
            training_data_fingerprint="a" * 64,
            model_version="fixture-1",
        ),
        frame,
    )


def test_model_bundle_roundtrip_preserves_golden_scores(tmp_path: Path) -> None:
    bundle, frame = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    loaded = load_model_bundle(manifest, trusted_root=tmp_path / "trusted")

    expected = bundle.model.predict_proba(bundle.preprocessor.transform(frame.iloc[:3]))[:, 1]
    actual = loaded.model.predict_proba(loaded.preprocessor.transform(frame.iloc[:3]))[:, 1]
    np.testing.assert_array_equal(actual, expected)
    assert loaded.operating_threshold == pytest.approx(0.53)
    assert loaded.score_type == "raw_score"


def test_corrupt_bundle_fails_before_any_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    model_path = manifest.parent / "model.joblib"
    model_path.write_bytes(model_path.read_bytes() + b"corruption")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="size|checksum"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_manifest_schema_mismatch_fails_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["feature_schema"] = list(reversed(payload["feature_schema"]))
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="schema"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_verified_joblib_rejects_untrusted_path(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside.joblib"
    joblib.dump({"value": 1}, outside)
    write_checksum_sidecar(outside)
    with pytest.raises(ArtifactVerificationError, match="outside trusted root"):
        load_verified_joblib(outside, trusted_root=trusted)


def test_verified_joblib_requires_checksum_before_deserialization(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    artifact = trusted / "model.joblib"
    joblib.dump({"value": 1}, artifact)
    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Missing checksum"):
            load_verified_joblib(artifact, trusted_root=trusted)
        deserialize.assert_not_called()
