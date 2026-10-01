"""Focused tests for the explicitly limited recovered-demo packager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from scripts.package_recovered_demo_bundle import (
    MODEL_VERSION,
    package_recovered_demo_bundle,
)
from src.artifacts.bundle import load_model_bundle, sha256_file
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor

SOURCE_URL = "https://github.com/imayankss/Credit-Card-Fraud-Detection.git"
SOURCE_SHA = "a" * 40


def _write_synthetic_recovered_components(
    directory: Path, *, model_order: list[str] | None = None
) -> tuple[Path, Path, Path]:
    rng = np.random.default_rng(7)
    frame = pd.DataFrame(rng.normal(size=(48, len(ALL_FEATURES))), columns=ALL_FEATURES)
    frame["Time"] = np.arange(len(frame), dtype=float)
    frame["Amount"] = np.abs(frame["Amount"])
    labels = np.array([0, 1] * 24)
    preprocessor = fit_preprocessor(frame, build_preprocessor())
    preprocessor.set_output(transform="pandas")
    transformed_names = [
        str(name).split("__")[-1] for name in preprocessor.get_feature_names_out()
    ]
    transformed = pd.DataFrame(
        preprocessor.transform(frame), columns=model_order or transformed_names
    )
    model = LogisticRegression(random_state=42, max_iter=1_000).fit(transformed, labels)

    preprocessor_path = directory / "recovered_preprocessor.joblib"
    model_path = directory / "recovered_model.joblib"
    source_csv_path = directory / "recovered_source.csv"
    joblib.dump(preprocessor, preprocessor_path)
    joblib.dump(model, model_path)
    source_csv_path.write_text("Time,V1,Amount,Class\n0,0,1,0\n", encoding="utf-8")
    return model_path, preprocessor_path, source_csv_path


def test_packages_hash_verified_recovered_demo_with_limited_provenance(tmp_path: Path) -> None:
    model_path, preprocessor_path, source_csv_path = _write_synthetic_recovered_components(tmp_path)
    output = tmp_path / "bundle"

    manifest_path = package_recovered_demo_bundle(
        model_path=model_path,
        preprocessor_path=preprocessor_path,
        source_csv_path=source_csv_path,
        output_dir=output,
        source_repository_url=SOURCE_URL,
        source_repository_sha=SOURCE_SHA,
        acknowledge_trusted_local_joblib=True,
    )

    bundle = load_model_bundle(manifest_path, trusted_root=tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    provenance = manifest["recovery_provenance"]
    assert bundle.model_version == MODEL_VERSION
    assert bundle.score_type == "raw_score"
    assert bundle.training_data_fingerprint == sha256_file(source_csv_path)
    assert provenance["evidence_category"] == "genuine_demo_inference"
    assert provenance["metric_linkage"] == "unverified"
    assert provenance["historical_metrics_claimed"] is False
    assert provenance["threshold_provenance"] == {
        "value": 0.53,
        "source": "historical validation-selected threshold",
        "recovered_component_linkage": "unverified",
        "purpose": "demo human-review policy only",
        "calibrated": False,
        "cost_optimal": False,
        "razorpay_approved": False,
        "production_approved": False,
    }
    assert provenance["component_hash_scope"] == (
        "SHA-256 hashes establish component identity, not independent authenticity."
    )
    assert provenance["component_sources"]["model"] == {
        "filename": model_path.name,
        "sha256": sha256_file(model_path),
    }
    assert provenance["source_dataset"]["filename"] == source_csv_path.name
    assert "training split" in provenance["source_dataset"]["fingerprint_scope"]
    assert str(tmp_path) not in manifest_path.read_text(encoding="utf-8")


def test_rejects_transformed_feature_order_mismatch(tmp_path: Path) -> None:
    model_path, preprocessor_path, source_csv_path = _write_synthetic_recovered_components(
        tmp_path, model_order=list(reversed(["Time", "Amount", *[f"V{i}" for i in range(1, 29)]]))
    )

    with pytest.raises(ValueError, match="transformed feature order"):
        package_recovered_demo_bundle(
            model_path=model_path,
            preprocessor_path=preprocessor_path,
            source_csv_path=source_csv_path,
            output_dir=tmp_path / "bundle",
            source_repository_url=SOURCE_URL,
            source_repository_sha=SOURCE_SHA,
            acknowledge_trusted_local_joblib=True,
        )


def test_rejects_invalid_preprocessor_raw_schema(tmp_path: Path) -> None:
    model_path, preprocessor_path, source_csv_path = _write_synthetic_recovered_components(tmp_path)
    preprocessor = joblib.load(preprocessor_path)
    preprocessor.feature_names_in_ = np.array([*ALL_FEATURES[:-1], "Unexpected"])
    joblib.dump(preprocessor, preprocessor_path)

    with pytest.raises(ValueError, match="raw feature set"):
        package_recovered_demo_bundle(
            model_path=model_path,
            preprocessor_path=preprocessor_path,
            source_csv_path=source_csv_path,
            output_dir=tmp_path / "bundle",
            source_repository_url=SOURCE_URL,
            source_repository_sha=SOURCE_SHA,
            acknowledge_trusted_local_joblib=True,
        )


def test_refuses_to_deserialize_without_trusted_local_acknowledgement(tmp_path: Path) -> None:
    model_path, preprocessor_path, source_csv_path = _write_synthetic_recovered_components(tmp_path)

    with patch("scripts.package_recovered_demo_bundle.joblib.load") as deserialize:
        with pytest.raises(ValueError, match="Explicit acknowledgement"):
            package_recovered_demo_bundle(
                model_path=model_path,
                preprocessor_path=preprocessor_path,
                source_csv_path=source_csv_path,
                output_dir=tmp_path / "bundle",
                source_repository_url=SOURCE_URL,
                source_repository_sha=SOURCE_SHA,
            )
        deserialize.assert_not_called()


@pytest.mark.parametrize(
    ("source_repository_sha", "score_type", "message"),
    [
        ("not-a-git-sha", "raw_score", "40-character lowercase Git SHA"),
        (SOURCE_SHA, "calibrated_probability", "uncalibrated raw_score"),
    ],
)
def test_rejects_invalid_provenance_or_calibrated_score_claim(
    tmp_path: Path, source_repository_sha: str, score_type: str, message: str
) -> None:
    model_path, preprocessor_path, source_csv_path = _write_synthetic_recovered_components(tmp_path)

    with pytest.raises(ValueError, match=message):
        package_recovered_demo_bundle(
            model_path=model_path,
            preprocessor_path=preprocessor_path,
            source_csv_path=source_csv_path,
            output_dir=tmp_path / "bundle",
            source_repository_url=SOURCE_URL,
            source_repository_sha=source_repository_sha,
            acknowledge_trusted_local_joblib=True,
            score_type=score_type,
        )
