"""New-data training, untouched evaluation, and real-bundle integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from scripts.curate_dataset import curate_dataset
from scripts.run_development_training import run_development_training
from src.artifacts.bundle import load_model_bundle
from src.preprocessing.feature_config import REQUIRED_COLUMNS


def _authorized_source(path: Path) -> Path:
    rows = 200
    indices = np.arange(rows, dtype=float)
    values: dict[str, np.ndarray] = {
        "Time": indices,
        "Amount": 1.0 + indices % 31,
    }
    for feature in range(1, 29):
        values[f"V{feature}"] = (
            np.sin(indices * (feature + 1) / 23.0) + indices / 10_000
        )
    values["Class"] = ((indices.astype(int) % 7) == 0).astype(int)
    pd.DataFrame(values, columns=REQUIRED_COLUMNS).to_csv(path, index=False)
    return path


def _factories():
    return {
        "simple_logistic": lambda _labels: LogisticRegression(
            class_weight="balanced", random_state=42, max_iter=1_000, C=1.0
        ),
        "complex_logistic": lambda _labels: LogisticRegression(
            class_weight="balanced", random_state=42, max_iter=1_000, C=2.0
        ),
    }


def test_new_authorized_data_reaches_verified_bundle_with_service_parity(
    tmp_path: Path,
) -> None:
    source = _authorized_source(tmp_path / "new-source.csv")
    curated = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "curated",
        source_kind="new_authorized_development",
        source_reference="synthetic-new-source-v1",
    )
    outputs = run_development_training(
        curated_path=curated["curated_dataset"],
        curation_record_path=curated["curation_record"],
        output_dir=tmp_path / "training-run",
        candidate_factories=_factories(),
        bootstrap_resamples=100,
    )
    second = run_development_training(
        curated_path=curated["curated_dataset"],
        curation_record_path=curated["curation_record"],
        output_dir=tmp_path / "training-run-second",
        candidate_factories=_factories(),
        bootstrap_resamples=100,
    )

    bundle = load_model_bundle(
        outputs["bundle_manifest"], trusted_root=tmp_path / "training-run"
    )
    assert bundle.model_version.startswith("development-")
    selection = json.loads(outputs["selection"].read_text(encoding="utf-8"))
    assert selection["evaluation_was_untouched_during_selection"] is True
    assert selection["selected_model"] in _factories()
    evaluation = json.loads(outputs["evaluation"].read_text(encoding="utf-8"))
    assert evaluation["evaluation_scope"] == "untouched_development_evaluation"
    parity = json.loads(outputs["golden_parity"].read_text(encoding="utf-8"))
    assert parity["maximum_absolute_difference"] <= parity["tolerance"]
    assert parity["raw_score_sha256"] == parity["service_raw_score_sha256"]
    manifest = json.loads(outputs["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["evaluation_scope"] == "new_authorized_three_way_development"
    assert "bundle/manifest.json" in manifest["outputs"]
    first_files = {
        path.relative_to(tmp_path / "training-run"): path.read_bytes()
        for path in (tmp_path / "training-run").rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(tmp_path / "training-run-second"): path.read_bytes()
        for path in (tmp_path / "training-run-second").rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    assert second["bundle_manifest"].is_file()


def test_reference_only_curation_cannot_create_decision_bundle(tmp_path: Path) -> None:
    source = _authorized_source(tmp_path / "reference.csv")
    curated = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "curated",
        source_kind="historical_kaggle_reference",
        source_reference="historical-reference-fixture",
    )
    with pytest.raises(ValueError, match="genuinely new authorized development data"):
        run_development_training(
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            output_dir=tmp_path / "training-run",
            candidate_factories=_factories(),
            bootstrap_resamples=100,
        )
