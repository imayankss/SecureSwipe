"""Verified post-training development diagnostics tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

import scripts.run_development_analysis as development_script
import src.data.historical_quarantine as quarantine_module
from scripts.curate_dataset import curate_dataset
from scripts.run_development_analysis import load_development_scores, run_development_analysis
from scripts.run_development_training import run_development_training
from src.artifacts.bundle import sha256_file
from src.preprocessing.feature_config import REQUIRED_COLUMNS
from tests.historical_quarantine_helpers import (
    SYNTHETIC_QUARANTINE_FRAUD,
    SYNTHETIC_QUARANTINE_ROWS,
    approved_quarantine_environment,
    write_nonoverlapping_quarantine,
)
from tests.source_approval_helpers import write_source_approval

ROOT = Path(__file__).resolve().parents[1]


def _factories():
    return {
        "simple": lambda _labels: LogisticRegression(
            class_weight="balanced", random_state=42, max_iter=1_000, C=1.0
        ),
        "complex": lambda _labels: LogisticRegression(
            class_weight="balanced", random_state=42, max_iter=1_000, C=2.0
        ),
    }


def _training_run(directory: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    rows = 200
    indices = np.arange(rows, dtype=float)
    values: dict[str, np.ndarray] = {
        "Time": indices + 0.125,
        "Amount": indices % 37 + 1.25,
    }
    for feature in range(1, 29):
        values[f"V{feature}"] = np.sin(indices * (feature + 1) / 29.0)
    values["Class"] = ((indices.astype(int) % 7) == 0).astype(int)
    source = directory / "source.csv"
    pd.DataFrame(values, columns=REQUIRED_COLUMNS).to_csv(source, index=False)
    reference = "verified-analysis-fixture-v1"
    curated = curate_dataset(
        source_path=source,
        output_dir=directory / "curated",
        source_kind="new_authorized_development",
        source_reference=reference,
        source_approval_path=write_source_approval(source, reference),
    )
    training_dir = directory / "training"
    quarantine, quarantine_anchor = write_nonoverlapping_quarantine(directory)
    with (
        patch.object(
            quarantine_module,
            "DEFAULT_HISTORICAL_QUARANTINE_ANCHOR",
            quarantine_anchor,
        ),
        patch.object(quarantine_module, "HISTORICAL_TEST_ROWS", 2),
        patch.object(quarantine_module, "HISTORICAL_TEST_FRAUD", 1),
    ):
        training = run_development_training(
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            historical_quarantine_path=quarantine,
            output_dir=training_dir,
            candidate_factories=_factories(),
            bootstrap_resamples=100,
        )
    training["scores"] = training_dir / "development_scores.csv"
    training["quarantine_anchor"] = quarantine_anchor
    return curated, training


def _analyze(
    *, directory: Path, curated: dict[str, Path], training: dict[str, Path]
) -> dict[str, Path]:
    anchor = training["quarantine_anchor"]
    with approved_quarantine_environment(
        anchor,
        anchor.parent,
        rows=SYNTHETIC_QUARANTINE_ROWS,
        fraud=SYNTHETIC_QUARANTINE_FRAUD,
    ):
        return run_development_analysis(
            scores_path=training["scores"],
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            training_run_manifest_path=training["run_manifest"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=directory,
        )


def test_verified_analysis_is_deterministic_and_post_training_only(tmp_path: Path) -> None:
    curated, training = _training_run(tmp_path)
    first = _analyze(directory=tmp_path / "first", curated=curated, training=training)
    second = _analyze(directory=tmp_path / "second", curated=curated, training=training)
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes(), name
    manifest = json.loads(first["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["run_kind"] == "verified_post_training_analysis"
    assert manifest["parameters"]["post_training_only"] is True
    selected = json.loads(first["selected_operating_points"].read_text(encoding="utf-8"))
    assert selected["evaluation_scope"] == "verified_post_training_selection_diagnostics"
    assert selected["model_version"].startswith("development-")


def test_fabricated_or_tampered_scores_are_rejected(tmp_path: Path) -> None:
    curated, training = _training_run(tmp_path)
    frame = pd.read_csv(training["scores"])
    frame["raw_score"] = frame["y_true"].astype(float)
    frame.to_csv(training["scores"], index=False)
    with pytest.raises(ValueError, match="manifest mismatch for development_scores"):
        _analyze(directory=tmp_path / "forged", curated=curated, training=training)


def test_forged_scores_fail_even_when_manifest_record_is_also_tampered(
    tmp_path: Path,
) -> None:
    curated, training = _training_run(tmp_path)
    frame = pd.read_csv(training["scores"])
    frame["raw_score"] = frame["y_true"].astype(float)
    frame.to_csv(training["scores"], index=False)
    manifest = json.loads(training["run_manifest"].read_text(encoding="utf-8"))
    score_record = manifest["outputs"]["development_scores"]
    score_record["sha256"] = sha256_file(training["scores"])
    score_record["size_bytes"] = training["scores"].stat().st_size
    training["run_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="scores recomputed from the verified bundle"):
        _analyze(directory=tmp_path / "forged-manifest", curated=curated, training=training)


def test_calibration_policy_cannot_change_after_training(tmp_path: Path) -> None:
    curated, training = _training_run(tmp_path)
    with pytest.raises(ValueError, match="cannot change the frozen"):
        run_development_analysis(
            scores_path=training["scores"],
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            training_run_manifest_path=training["run_manifest"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=tmp_path / "changed-policy",
            minimum_brier_improvement=1.0,
        )


def test_analysis_refuses_overwrite_and_partial_publication(tmp_path: Path, monkeypatch) -> None:
    curated, training = _training_run(tmp_path)
    output = tmp_path / "output"
    _analyze(directory=output, curated=curated, training=training)
    with pytest.raises(FileExistsError, match="Refusing to overwrite evidence target"):
        _analyze(directory=output, curated=curated, training=training)

    failed = tmp_path / "failed"
    monkeypatch.setattr(
        development_script,
        "write_run_manifest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected write failure")),
    )
    with pytest.raises(OSError, match="injected write failure"):
        _analyze(directory=failed, curated=curated, training=training)
    assert not failed.exists()


def test_historical_partition_and_duplicate_fingerprint_are_rejected(tmp_path: Path) -> None:
    _curated, training = _training_run(tmp_path)
    frame = pd.read_csv(training["scores"])
    frame.loc[0, "partition"] = "historical_reported_test"
    bad_partition = tmp_path / "bad-partition.csv"
    frame.to_csv(bad_partition, index=False)
    with pytest.raises(ValueError, match="historical/test partitions are prohibited"):
        load_development_scores(bad_partition)
    frame = pd.read_csv(training["scores"])
    frame.loc[1, "row_fingerprint"] = frame.loc[0, "row_fingerprint"]
    duplicate = tmp_path / "duplicate.csv"
    frame.to_csv(duplicate, index=False)
    with pytest.raises(ValueError, match="globally unique SHA-256"):
        load_development_scores(duplicate)
