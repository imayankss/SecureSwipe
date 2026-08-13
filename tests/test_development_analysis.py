"""End-to-end deterministic development-score evidence tests."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.run_development_analysis as development_script

from scripts.curate_dataset import curate_dataset
from scripts.run_development_analysis import (
    load_development_scores,
    run_development_analysis,
)
from src.data.curation import row_content_fingerprints
from src.preprocessing.feature_config import REQUIRED_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def _write_inputs(directory: Path) -> tuple[Path, dict[str, Path]]:
    train_count = 60
    selection_count = 40
    evaluation_count = 40
    train_labels = np.array([0] * 45 + [1] * 15)
    selection_labels = np.array([0] * 30 + [1] * 10)
    evaluation_labels = np.array([0] * 30 + [1] * 10)
    total = train_count + selection_count + evaluation_count
    indices = np.arange(total, dtype=float)
    dataset_values: dict[str, np.ndarray] = {
        "Time": indices,
        "Amount": indices + 1,
    }
    for feature in range(1, 29):
        dataset_values[f"V{feature}"] = indices + feature / 100
    all_labels = np.concatenate([train_labels, selection_labels, evaluation_labels])
    dataset_values["Class"] = all_labels
    dataset = pd.DataFrame(dataset_values, columns=REQUIRED_COLUMNS)
    source = directory / "source.csv"
    dataset.to_csv(source, index=False)
    curated = curate_dataset(
        source_path=source,
        output_dir=directory / "curated",
        source_kind="new_authorized_development",
        source_reference="development-analysis-fixture-v1",
    )
    curated_frame = pd.read_csv(curated["curated_dataset"])
    frame = pd.DataFrame(
        {
            "row_fingerprint": row_content_fingerprints(curated_frame),
            "partition": ["calibration_fit"] * train_count
            + ["operating_point_selection"] * selection_count
            + ["untouched_development_evaluation"] * evaluation_count,
            "y_true": all_labels,
            "raw_score": np.concatenate(
                [
                    np.where(train_labels == 1, 0.65, 0.35),
                    np.where(selection_labels == 1, 0.62, 0.38),
                    np.where(evaluation_labels == 1, 0.60, 0.40),
                ]
            ),
        }
    )
    path = directory / "scores.csv"
    frame.to_csv(path, index=False)
    return path, curated


def test_development_analysis_is_deterministic_and_manifested(tmp_path: Path) -> None:
    scores, curated = _write_inputs(tmp_path)
    scenarios = ROOT / "configs" / "cost_scenarios.example.yaml"
    first = run_development_analysis(
        scores_path=scores,
        curated_path=curated["curated_dataset"],
        curation_record_path=curated["curation_record"],
        scenarios_path=scenarios,
        output_dir=tmp_path / "first",
        minimum_brier_improvement=0.001,
    )
    second = run_development_analysis(
        scores_path=scores,
        curated_path=curated["curated_dataset"],
        curation_record_path=curated["curation_record"],
        scenarios_path=scenarios,
        output_dir=tmp_path / "second",
        minimum_brier_improvement=0.001,
    )

    assert set(first) == set(second)
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes(), name
    manifest = json.loads(first["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["run_kind"] == "development_score_analysis"
    assert manifest["evaluation_scope"] == "three_way_development"
    assert set(manifest["inputs"]) == {
        "cost_scenarios",
        "curated_dataset",
        "curation_record",
        "development_scores",
    }
    assert set(manifest["outputs"]) == set(first) - {"run_manifest"}
    selected = json.loads(first["selected_operating_points"].read_text(encoding="utf-8"))
    assert selected["evaluation_scope"] == "operating_point_selection"
    assert selected["score_type"] == "calibrated_probability"
    assert len(selected["cost_scenarios"]) == 3
    assert (
        selected["untouched_evaluation"]["evaluation_scope"]
        == "untouched_development_evaluation"
    )


def test_development_analysis_refuses_to_overwrite_outputs(tmp_path: Path) -> None:
    scores, curated = _write_inputs(tmp_path)
    output = tmp_path / "output"
    run_development_analysis(
        scores_path=scores,
        curated_path=curated["curated_dataset"],
        curation_record_path=curated["curation_record"],
        scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
        output_dir=output,
        minimum_brier_improvement=0.0,
    )
    with pytest.raises(FileExistsError, match="Refusing to overwrite evidence target"):
        run_development_analysis(
            scores_path=scores,
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=output,
            minimum_brier_improvement=0.0,
        )


def test_development_analysis_write_failure_publishes_no_partial_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scores, curated = _write_inputs(tmp_path)
    output = tmp_path / "failed"
    monkeypatch.setattr(
        development_script,
        "write_run_manifest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected write failure")),
    )
    with pytest.raises(OSError, match="injected write failure"):
        run_development_analysis(
            scores_path=scores,
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=output,
            minimum_brier_improvement=0.0,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".failed.*"))


def test_historical_or_test_partition_is_rejected(tmp_path: Path) -> None:
    scores, _curated = _write_inputs(tmp_path)
    frame = pd.read_csv(scores)
    frame.loc[0, "partition"] = "historical_reported_test"
    frame.to_csv(scores, index=False)
    with pytest.raises(ValueError, match="historical/test partitions are prohibited"):
        load_development_scores(scores)


def test_renamed_or_duplicate_row_fingerprint_is_rejected(tmp_path: Path) -> None:
    scores, _curated = _write_inputs(tmp_path)
    frame = pd.read_csv(scores)
    frame.loc[1, "row_fingerprint"] = frame.loc[0, "row_fingerprint"]
    frame.to_csv(scores, index=False)
    with pytest.raises(ValueError, match="globally unique SHA-256"):
        load_development_scores(scores)


def test_valid_but_renamed_fingerprint_outside_curated_lineage_is_rejected(
    tmp_path: Path,
) -> None:
    scores, curated = _write_inputs(tmp_path)
    frame = pd.read_csv(scores)
    frame.loc[0, "row_fingerprint"] = hashlib.sha256(b"attacker-renamed-row").hexdigest()
    frame.to_csv(scores, index=False)
    with pytest.raises(ValueError, match="outside the verified curated data"):
        run_development_analysis(
            scores_path=scores,
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=tmp_path / "output",
            minimum_brier_improvement=0.0,
        )


def test_partition_rename_cannot_break_chronology_or_source_labels(tmp_path: Path) -> None:
    scores, curated = _write_inputs(tmp_path)
    frame = pd.read_csv(scores)
    frame.loc[0, "partition"] = "operating_point_selection"
    frame.loc[60, "partition"] = "calibration_fit"
    frame.to_csv(scores, index=False)
    with pytest.raises(ValueError, match="strictly chronological"):
        run_development_analysis(
            scores_path=scores,
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=tmp_path / "chronology-output",
            minimum_brier_improvement=0.0,
        )

    frame = pd.read_csv(scores)
    frame.loc[0, "partition"] = "calibration_fit"
    frame.loc[60, "partition"] = "operating_point_selection"
    frame.loc[0, "y_true"] = 1 - int(frame.loc[0, "y_true"])
    frame.to_csv(scores, index=False)
    with pytest.raises(ValueError, match="labels do not match"):
        run_development_analysis(
            scores_path=scores,
            curated_path=curated["curated_dataset"],
            curation_record_path=curated["curation_record"],
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=tmp_path / "label-output",
            minimum_brier_improvement=0.0,
        )
