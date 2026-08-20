"""Atomic deterministic evidence tests for the legacy stage wrapper."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.run_reference_stage as reference_script
from scripts import (
    run_day2_eda,
    run_day3_preprocessing,
    run_day4_baseline_models,
    run_day5_advanced_models,
    run_day6_threshold_tuning,
    run_day7_explainability,
)
from scripts.run_reference_stage import run_reference_stage
from src.preprocessing.feature_config import REQUIRED_COLUMNS


def _write_dataset(path: Path) -> Path:
    rows = 20
    values: dict[str, np.ndarray] = {"Time": np.arange(rows, dtype=float)}
    for index in range(1, 29):
        values[f"V{index}"] = np.arange(rows, dtype=float) + index / 100
    values["Amount"] = np.arange(rows, dtype=float) + 1
    values["Class"] = np.array([0] * 16 + [1] * 4)
    pd.DataFrame(values, columns=REQUIRED_COLUMNS).to_csv(path, index=False)
    return path


def test_day2_reference_stage_is_atomic_manifested_and_byte_deterministic(
    tmp_path: Path,
) -> None:
    dataset = _write_dataset(tmp_path / "synthetic.csv")
    first = run_reference_stage(
        stage="day2",
        output_dir=tmp_path / "first",
        data_path=dataset,
        skip_figures=True,
    )
    second = run_reference_stage(
        stage="day2",
        output_dir=tmp_path / "second",
        data_path=dataset,
        skip_figures=True,
    )

    assert set(first) == set(second)
    for logical_name in first:
        assert first[logical_name].read_bytes() == second[logical_name].read_bytes(), logical_name
    manifest = json.loads(first["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["run_kind"] == "legacy_day2_reference"
    assert manifest["evaluation_scope"] == "data_characterization"
    assert manifest["data_fingerprint"] == manifest["inputs"]["dataset"]["sha256"]
    assert set(manifest["outputs"]) == {"reports/day2_eda_summary.md"}


def test_reference_stage_failure_leaves_no_apparently_complete_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _write_dataset(tmp_path / "synthetic.csv")
    target = tmp_path / "failed"
    monkeypatch.setattr(
        reference_script,
        "_dispatch_stage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected stage failure")),
    )
    with pytest.raises(RuntimeError, match="injected stage failure"):
        run_reference_stage(
            stage="day2",
            output_dir=target,
            data_path=dataset,
            skip_figures=True,
        )
    assert not target.exists()
    assert not list(tmp_path.glob(".failed.*"))


def test_reference_stage_never_overwrites_even_an_empty_target(tmp_path: Path) -> None:
    dataset = _write_dataset(tmp_path / "synthetic.csv")
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(FileExistsError, match="Refusing to overwrite evidence target"):
        run_reference_stage(
            stage="day2",
            output_dir=target,
            data_path=dataset,
            skip_figures=True,
        )


@pytest.mark.parametrize("stage", ["test", "historical", "final_test"])
def test_reference_stage_rejects_test_or_historical_stage_names(
    tmp_path: Path, stage: str
) -> None:
    with pytest.raises(ValueError, match="stage must be one of"):
        run_reference_stage(stage=stage, output_dir=tmp_path / stage)


@pytest.mark.parametrize(
    "module",
    [
        run_day2_eda,
        run_day3_preprocessing,
        run_day4_baseline_models,
        run_day5_advanced_models,
        run_day6_threshold_tuning,
        run_day7_explainability,
    ],
)
def test_direct_legacy_cli_refuses_unmanifested_execution(module: object) -> None:
    with pytest.raises(SystemExit) as caught:
        module.main()  # type: ignore[attr-defined]
    assert caught.value.code == 2
