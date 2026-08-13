"""Generate calibration, threshold, uncertainty, and cost evidence from development scores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.calibration import apply_calibrator, compare_calibrators, evaluate_calibration
from src.evaluation.cost_analysis import CostScenario, analyze_cost_scenarios
from src.evaluation.statistical_metrics import classification_wilson_intervals
from src.evaluation.threshold_tuning import (
    build_threshold_metrics_table,
    select_best_f1_threshold,
)
from src.utils.evidence_directory import (
    atomic_evidence_directory,
    require_absent_evidence_target,
)
from src.utils.run_manifest import build_run_manifest, write_run_manifest

REQUIRED_SCORE_COLUMNS = ["row_id", "partition", "y_true", "raw_score"]
ALLOWED_PARTITIONS = {"calibration_train", "development_validation"}


def _native_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _native_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native_json(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _json_write(payload: Any, path: Path) -> Path:
    path.write_text(
        json.dumps(_native_json(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_development_scores(path: str | Path) -> pd.DataFrame:
    """Load only explicit development partitions; reject test-like namespaces."""
    frame = pd.read_csv(path)
    if list(frame.columns) != REQUIRED_SCORE_COLUMNS:
        raise ValueError(f"Score CSV columns must be exactly {REQUIRED_SCORE_COLUMNS}.")
    if frame.empty or frame["row_id"].isna().any() or frame["row_id"].duplicated().any():
        raise ValueError("Score CSV must have non-empty, globally unique row_id values.")
    if set(frame["partition"]) != ALLOWED_PARTITIONS:
        raise ValueError(
            "Score CSV must contain exactly calibration_train and development_validation; "
            "historical/test partitions are prohibited."
        )
    labels = frame["y_true"].to_numpy()
    scores = frame["raw_score"].to_numpy(dtype=float)
    if not np.isfinite(scores).all() or np.logical_or(scores < 0.0, scores > 1.0).any():
        raise ValueError("raw_score must be finite and in [0, 1].")
    if not set(np.unique(labels)).issubset({0, 1}):
        raise ValueError("y_true must contain only 0 and 1.")
    for partition, group in frame.groupby("partition", sort=True):
        if set(group["y_true"]) != {0, 1}:
            raise ValueError(f"Partition {partition} must contain both classes.")
    return frame


def load_cost_scenarios(path: str | Path) -> list[CostScenario]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("scenarios"), list):
        raise ValueError("Cost configuration must contain a scenarios list.")
    allowed = {
        "name",
        "false_positive_cost",
        "false_negative_cost",
        "review_cost",
        "fraud_recovery_rate",
    }
    scenarios: list[CostScenario] = []
    for item in payload["scenarios"]:
        if not isinstance(item, dict) or set(item) != allowed:
            raise ValueError(f"Every cost scenario must contain exactly {sorted(allowed)}.")
        scenario = CostScenario(**item)
        scenario.validate()
        scenarios.append(scenario)
    if not scenarios or len({item.name for item in scenarios}) != len(scenarios):
        raise ValueError("Cost scenarios must be non-empty and uniquely named.")
    return scenarios


def run_development_analysis(
    *,
    scores_path: Path,
    scenarios_path: Path,
    output_dir: Path,
    minimum_brier_improvement: float,
) -> dict[str, Path]:
    """Compute first, then atomically publish deterministic development evidence."""
    output_dir = require_absent_evidence_target(output_dir)
    scores = load_development_scores(scores_path)
    scenarios = load_cost_scenarios(scenarios_path)
    train = scores[scores["partition"] == "calibration_train"]
    validation = scores[scores["partition"] == "development_validation"]

    comparison, calibrator, selected_method = compare_calibrators(
        train["raw_score"].to_numpy(),
        train["y_true"].to_numpy(),
        validation["raw_score"].to_numpy(),
        validation["y_true"].to_numpy(),
        calibration_train_row_ids=train["row_id"].astype(str).tolist(),
        evaluation_row_ids=validation["row_id"].astype(str).tolist(),
        minimum_brier_improvement=minimum_brier_improvement,
    )
    decision_scores = (
        apply_calibrator(calibrator, validation["raw_score"].to_numpy())
        if calibrator is not None
        else validation["raw_score"].to_numpy(dtype=float)
    )
    labels = validation["y_true"].to_numpy(dtype=int)
    threshold_table = build_threshold_metrics_table(labels, decision_scores)
    best_f1 = select_best_f1_threshold(threshold_table)
    predictions = (decision_scores >= float(best_f1["threshold"])).astype(int)
    intervals = classification_wilson_intervals(labels, predictions)
    calibration_metrics = evaluate_calibration(labels, decision_scores)
    cost_table, cost_selections = analyze_cost_scenarios(labels, decision_scores, scenarios)

    filenames = {
        "calibration_comparison": "calibration_comparison.csv",
        "calibration_metrics": "calibration_metrics.json",
        "cost_sensitivity": "cost_sensitivity.csv",
        "selected_operating_points": "selected_operating_points.json",
        "threshold_metrics": "threshold_metrics.csv",
    }
    with atomic_evidence_directory(output_dir) as temporary:
        temporary_outputs = {
            logical_name: temporary / filename
            for logical_name, filename in filenames.items()
        }
        comparison.to_csv(temporary_outputs["calibration_comparison"], index=False)
        threshold_table.to_csv(temporary_outputs["threshold_metrics"], index=False)
        cost_table.to_csv(temporary_outputs["cost_sensitivity"], index=False)
        _json_write(calibration_metrics, temporary_outputs["calibration_metrics"])
        _json_write(
            {
                "calibration_method": selected_method,
                "cost_scenarios": cost_selections,
                "evaluation_scope": "development_validation",
                "score_type": (
                    "calibrated_probability" if calibrator is not None else "raw_score"
                ),
                "threshold_best_f1": best_f1,
                "wilson_intervals": intervals,
            },
            temporary_outputs["selected_operating_points"],
        )
        manifest = build_run_manifest(
            run_kind="development_score_analysis",
            evaluation_scope="development_validation",
            repository=PROJECT_ROOT,
            inputs={"cost_scenarios": scenarios_path, "development_scores": scores_path},
            outputs=temporary_outputs,
            parameters={
                "calibration_methods": ["identity", "platt", "isotonic"],
                "minimum_brier_improvement": minimum_brier_improvement,
                "threshold_grid": {"minimum": 0.01, "maximum": 0.99, "step": 0.01},
            },
            seeds={"calibration_logistic_regression": 42},
            packages=["numpy", "pandas", "pyyaml", "scikit-learn"],
        )
        write_run_manifest(manifest, temporary / "run_manifest.json")
    return {
        **{name: output_dir / filename for name, filename in filenames.items()},
        "run_manifest": output_dir / "run_manifest.json",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze development-only scores; historical/test partitions are rejected."
    )
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--cost-scenarios", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--minimum-brier-improvement", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_development_analysis(
        scores_path=args.scores.resolve(strict=True),
        scenarios_path=args.cost_scenarios.resolve(strict=True),
        output_dir=args.output_dir.resolve(),
        minimum_brier_improvement=args.minimum_brier_improvement,
    )
    print(json.dumps({name: str(path) for name, path in sorted(outputs.items())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
