"""End-to-end deterministic development-score evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.run_development_analysis as development_script

from scripts.run_development_analysis import (
    load_development_scores,
    run_development_analysis,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_scores(path: Path) -> Path:
    train_count = 60
    validation_count = 40
    train_labels = np.array([0] * 45 + [1] * 15)
    validation_labels = np.array([0] * 30 + [1] * 10)
    frame = pd.DataFrame(
        {
            "row_id": [f"train-{index}" for index in range(train_count)]
            + [f"validation-{index}" for index in range(validation_count)],
            "partition": ["calibration_train"] * train_count
            + ["development_validation"] * validation_count,
            "y_true": np.concatenate([train_labels, validation_labels]),
            "raw_score": np.concatenate(
                [
                    np.where(train_labels == 1, 0.65, 0.35),
                    np.where(validation_labels == 1, 0.62, 0.38),
                ]
            ),
        }
    )
    frame.to_csv(path, index=False)
    return path


def test_development_analysis_is_deterministic_and_manifested(tmp_path: Path) -> None:
    scores = _write_scores(tmp_path / "scores.csv")
    scenarios = ROOT / "configs" / "cost_scenarios.example.yaml"
    first = run_development_analysis(
        scores_path=scores,
        scenarios_path=scenarios,
        output_dir=tmp_path / "first",
        minimum_brier_improvement=0.001,
    )
    second = run_development_analysis(
        scores_path=scores,
        scenarios_path=scenarios,
        output_dir=tmp_path / "second",
        minimum_brier_improvement=0.001,
    )

    assert set(first) == set(second)
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes(), name
    manifest = json.loads(first["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["run_kind"] == "development_score_analysis"
    assert manifest["evaluation_scope"] == "development_validation"
    assert set(manifest["inputs"]) == {"cost_scenarios", "development_scores"}
    assert set(manifest["outputs"]) == set(first) - {"run_manifest"}
    selected = json.loads(first["selected_operating_points"].read_text(encoding="utf-8"))
    assert selected["evaluation_scope"] == "development_validation"
    assert selected["score_type"] == "calibrated_probability"
    assert len(selected["cost_scenarios"]) == 3


def test_development_analysis_refuses_to_overwrite_outputs(tmp_path: Path) -> None:
    scores = _write_scores(tmp_path / "scores.csv")
    output = tmp_path / "output"
    run_development_analysis(
        scores_path=scores,
        scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
        output_dir=output,
        minimum_brier_improvement=0.0,
    )
    with pytest.raises(FileExistsError, match="Refusing to overwrite evidence target"):
        run_development_analysis(
            scores_path=scores,
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=output,
            minimum_brier_improvement=0.0,
        )


def test_development_analysis_write_failure_publishes_no_partial_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scores = _write_scores(tmp_path / "scores.csv")
    output = tmp_path / "failed"
    monkeypatch.setattr(
        development_script,
        "write_run_manifest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected write failure")),
    )
    with pytest.raises(OSError, match="injected write failure"):
        run_development_analysis(
            scores_path=scores,
            scenarios_path=ROOT / "configs" / "cost_scenarios.example.yaml",
            output_dir=output,
            minimum_brier_improvement=0.0,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".failed.*"))


def test_historical_or_test_partition_is_rejected(tmp_path: Path) -> None:
    scores = _write_scores(tmp_path / "scores.csv")
    frame = pd.read_csv(scores)
    frame.loc[0, "partition"] = "historical_reported_test"
    frame.to_csv(scores, index=False)
    with pytest.raises(ValueError, match="historical/test partitions are prohibited"):
        load_development_scores(scores)
