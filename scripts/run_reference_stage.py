"""Atomically run a legacy Day 2-7 stage as manifested reference evidence.

These stages preserve the repository's historical random-split workflow. Their
scope is explicitly ``legacy_random_*_reference`` and they are not a path for
new model, calibration, or threshold decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import chdir
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_day2_eda import run_day2_eda  # noqa: E402
from scripts.run_day3_preprocessing import run_day3_preprocessing  # noqa: E402
from scripts.run_day4_baseline_models import run_day4_baseline_models  # noqa: E402
from scripts.run_day5_advanced_models import run_day5_advanced_models  # noqa: E402
from scripts.run_day6_threshold_tuning import run_day6_threshold_tuning  # noqa: E402
from scripts.run_day7_explainability import run_day7_explainability  # noqa: E402
from src.artifacts.bundle import sha256_file  # noqa: E402
from src.models.advanced_models import XGBOOST_PARAMS  # noqa: E402
from src.preprocessing.feature_config import RANDOM_STATE  # noqa: E402
from src.utils.config import load_project_config  # noqa: E402
from src.utils.evidence_directory import (  # noqa: E402
    atomic_evidence_directory,
    require_absent_evidence_target,
)
from src.utils.run_manifest import build_run_manifest, write_run_manifest  # noqa: E402

CONFIG = load_project_config()
STAGES = ("day2", "day3", "day4", "day5", "day6", "day7")
PROCESSED_FILES = {
    "x_train": "X_train_processed.parquet",
    "x_validation": "X_val_processed.parquet",
    "y_train": "y_train.parquet",
    "y_validation": "y_val.parquet",
}


def _require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"{label} must be a regular non-symlink file: {resolved}")
    return resolved


def _processed_inputs(directory: Path, *, training: bool) -> dict[str, Path]:
    names = PROCESSED_FILES if training else {
        "x_validation": PROCESSED_FILES["x_validation"],
        "y_validation": PROCESSED_FILES["y_validation"],
    }
    return {
        logical: _require_file(directory / filename, logical)
        for logical, filename in names.items()
    }


def _model_inputs(model_path: Path) -> dict[str, Path]:
    model = _require_file(model_path, "model")
    checksum = _require_file(model.with_suffix(model.suffix + ".sha256"), "model_checksum")
    return {"model": model, "model_checksum": checksum}


def _collect_outputs(directory: Path) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Evidence output must not be a symlink: {path}")
        if path.is_file() and path.name != "run_manifest.json":
            logical = path.relative_to(directory).as_posix()
            outputs[logical] = path
    if not outputs:
        raise RuntimeError("Reference stage produced no evidence files.")
    return outputs


def _stage_inputs(
    stage: str,
    *,
    data_path: Path,
    processed_dir: Path,
    model_path: Path,
    day4_metrics_path: Path,
) -> dict[str, Path]:
    if stage in {"day2", "day3"}:
        return {"dataset": _require_file(data_path, "dataset")}
    if stage == "day4":
        return _processed_inputs(processed_dir, training=True)
    if stage == "day5":
        return {
            **_processed_inputs(processed_dir, training=True),
            "day4_metrics": _require_file(day4_metrics_path, "day4_metrics"),
        }
    if stage in {"day6", "day7"}:
        return {
            **_processed_inputs(processed_dir, training=False),
            **_model_inputs(model_path),
        }
    raise ValueError(f"Unsupported reference stage: {stage}")


def _stage_metadata(
    stage: str, *, skip_figures: bool, min_recall: float, sample_size: int
) -> tuple[str, dict[str, Any], list[str]]:
    common = ["numpy", "pandas"]
    if stage == "day2":
        return "data_characterization", {"figures": not skip_figures}, [*common, "matplotlib"]
    if stage == "day3":
        return (
            "legacy_random_split_reference",
            {
                "duplicate_policy": "reject_exact_rows_before_split",
                "test_size": CONFIG.data.test_size,
                "validation_size": CONFIG.data.validation_size,
            },
            [*common, "joblib", "pyarrow", "scikit-learn"],
        )
    if stage == "day4":
        return (
            "legacy_random_validation_reference",
            {"models": ["dummy", "logistic_regression", "random_forest"]},
            [*common, "joblib", "pyarrow", "scikit-learn"],
        )
    if stage == "day5":
        return (
            "legacy_random_validation_reference",
            {"selection_metric": "average_precision", "xgboost": XGBOOST_PARAMS},
            [*common, "joblib", "pyarrow", "scikit-learn", "xgboost"],
        )
    if stage == "day6":
        return (
            "legacy_random_validation_reference",
            {"minimum_recall": min_recall, "threshold_grid": [0.01, 0.99, 0.01]},
            [*common, "joblib", "matplotlib", "pyarrow", "scikit-learn"],
        )
    if stage == "day7":
        return (
            "legacy_random_validation_reference",
            {
                "explanation_cohort": "fraud_high_score_and_representative",
                "model_output": "raw_margin_log_odds",
                "sample_size": sample_size,
            },
            [*common, "joblib", "matplotlib", "pyarrow", "scikit-learn", "shap", "xgboost"],
        )
    raise ValueError(f"Unsupported reference stage: {stage}")


def _dispatch_stage(
    stage: str,
    *,
    inputs: dict[str, Path],
    skip_figures: bool,
    min_recall: float,
    sample_size: int,
) -> None:
    if stage == "day2":
        run_day2_eda(
            data_path=inputs["dataset"],
            report_path="reports/day2_eda_summary.md",
            figures_dir="reports/figures",
            generate_figures=not skip_figures,
        )
    elif stage == "day3":
        run_day3_preprocessing(
            data_path=inputs["dataset"],
            interim_dir="data/interim",
            processed_dir="data/processed",
            preprocessor_path="artifacts/preprocessing/preprocessor.joblib",
            metadata_path="artifacts/preprocessing/split_metadata.json",
            report_path="reports/day3_preprocessing_summary.md",
        )
    elif stage == "day4":
        run_day4_baseline_models(
            processed_dir=inputs["x_train"].parent,
            models_dir="artifacts/models",
            metrics_dir="reports/metrics",
            report_path="reports/day4_baseline_model_summary.md",
        )
    elif stage == "day5":
        run_day5_advanced_models(
            processed_dir=inputs["x_train"].parent,
            models_dir="artifacts/models",
            metrics_dir="reports/metrics",
            comparison_dir="reports/model_comparison",
            day4_metrics_path=inputs["day4_metrics"],
        )
    elif stage == "day6":
        run_day6_threshold_tuning(
            model_path=inputs["model"],
            processed_dir=inputs["x_validation"].parent,
            threshold_dir=Path("reports/threshold_tuning"),
            figures_dir=Path("reports/figures"),
            report_path=Path("reports/threshold_tuning/day6_threshold_tuning_report.md"),
            min_recall=min_recall,
        )
    elif stage == "day7":
        run_day7_explainability(
            model_path=inputs["model"],
            processed_dir=inputs["x_validation"].parent,
            explainability_dir="reports/explainability",
            figures_dir="reports/figures",
            sample_size=sample_size,
            random_state=RANDOM_STATE,
        )
    else:  # pragma: no cover - protected by parser and metadata validation
        raise ValueError(f"Unsupported reference stage: {stage}")


def run_reference_stage(
    *,
    stage: str,
    output_dir: Path,
    data_path: Path = CONFIG.data.raw_path,
    processed_dir: Path = CONFIG.data.processed_dir,
    model_path: Path = CONFIG.artifacts.legacy_model_dir / "xgboost_baseline.joblib",
    day4_metrics_path: Path = CONFIG.reports.metrics_dir / "day4_baseline_metrics.json",
    skip_figures: bool = False,
    min_recall: float = CONFIG.evaluation.recall_target,
    sample_size: int = 1_000,
) -> dict[str, Path]:
    """Run one fixed-scope reference stage and publish it only when complete."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}.")
    if not 0 <= min_recall <= 1:
        raise ValueError("min_recall must be in [0, 1].")
    if sample_size < 1:
        raise ValueError("sample_size must be positive.")
    output_dir = require_absent_evidence_target(output_dir)
    inputs = _stage_inputs(
        stage,
        data_path=data_path,
        processed_dir=processed_dir,
        model_path=model_path,
        day4_metrics_path=day4_metrics_path,
    )
    scope, parameters, packages = _stage_metadata(
        stage,
        skip_figures=skip_figures,
        min_recall=min_recall,
        sample_size=sample_size,
    )
    with atomic_evidence_directory(output_dir) as temporary:
        with chdir(temporary):
            _dispatch_stage(
                stage,
                inputs=inputs,
                skip_figures=skip_figures,
                min_recall=min_recall,
                sample_size=sample_size,
            )
        outputs = _collect_outputs(temporary)
        manifest = build_run_manifest(
            run_kind=f"legacy_{stage}_reference",
            evaluation_scope=scope,
            repository=PROJECT_ROOT,
            inputs=inputs,
            outputs=outputs,
            parameters=parameters,
            seeds={"canonical_random_state": RANDOM_STATE},
            packages=packages,
            data_fingerprint=(sha256_file(inputs["dataset"]) if "dataset" in inputs else None),
        )
        write_run_manifest(manifest, temporary / "run_manifest.json")
    return {
        **{name: output_dir / path.relative_to(temporary) for name, path in outputs.items()},
        "run_manifest": output_dir / "run_manifest.json",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--data-path", type=Path, default=CONFIG.data.raw_path)
    parser.add_argument("--processed-dir", type=Path, default=CONFIG.data.processed_dir)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=CONFIG.artifacts.legacy_model_dir / "xgboost_baseline.joblib",
    )
    parser.add_argument(
        "--day4-metrics-path",
        type=Path,
        default=CONFIG.reports.metrics_dir / "day4_baseline_metrics.json",
    )
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--min-recall", type=float, default=CONFIG.evaluation.recall_target)
    parser.add_argument("--sample-size", type=int, default=1_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_reference_stage(
        stage=args.stage,
        output_dir=args.output_dir.resolve(),
        data_path=args.data_path,
        processed_dir=args.processed_dir,
        model_path=args.model_path,
        day4_metrics_path=args.day4_metrics_path,
        skip_figures=args.skip_figures,
        min_recall=args.min_recall,
        sample_size=args.sample_size,
    )
    print(json.dumps({name: str(path) for name, path in sorted(outputs.items())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
