"""Run the locked Day 7 final test-set evaluation.

This script is the only place in the project that evaluates the held-out
test split. It does not tune thresholds, choose models, retrain anything,
or change preprocessing. The model is the Day 5 champion XGBoost artifact,
and the operating threshold is the Day 6 validation-selected
``recall_target`` threshold.

Run from the repository root:

    python3 -m scripts.run_final_evaluation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.final_evaluation import (  # noqa: E402
    build_final_evaluation_summary,
    evaluate_locked_model,
    save_final_evaluation,
    write_final_evaluation_report,
)
from src.artifacts.bundle import load_verified_joblib  # noqa: E402

DEFAULT_MODEL_PATH = Path("artifacts/models/xgboost_baseline.joblib")
DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_THRESHOLDS_PATH = Path("reports/threshold_tuning/selected_thresholds.json")
DEFAULT_OUTPUT_JSON = Path("reports/final/final_model_evaluation.json")
DEFAULT_OUTPUT_REPORT = Path("reports/final/final_evaluation_report.md")
LOCKED_THRESHOLD_NAME = "recall_target"
MODEL_NAME = "xgboost_baseline"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run final locked evaluation on the held-out test split."
    )
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--thresholds-path", type=Path, default=DEFAULT_THRESHOLDS_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_REPORT)
    return parser.parse_args()


def load_locked_threshold(thresholds_path: Path) -> float:
    """Load the Day 6 validation-selected recall-target threshold."""
    if not thresholds_path.exists():
        raise FileNotFoundError(
            f"Selected thresholds file not found at {thresholds_path}. "
            "Run Day 6 first: python3 -m scripts.run_day6_threshold_tuning"
        )

    with thresholds_path.open("r", encoding="utf-8") as fh:
        thresholds = json.load(fh)

    if LOCKED_THRESHOLD_NAME not in thresholds:
        raise ValueError(
            f"Expected '{LOCKED_THRESHOLD_NAME}' in {thresholds_path}, "
            f"found keys: {sorted(thresholds)}"
        )

    threshold = thresholds[LOCKED_THRESHOLD_NAME].get("threshold")
    if threshold is None:
        raise ValueError(
            f"'{LOCKED_THRESHOLD_NAME}' in {thresholds_path} has no threshold value."
        )

    return float(threshold)


def load_test_data(processed_dir: Path) -> tuple[pd.DataFrame, pd.Series]:
    """Load the held-out Day 3 processed test split."""
    x_test_path = processed_dir / "X_test_processed.parquet"
    y_test_path = processed_dir / "y_test.parquet"

    if not x_test_path.exists():
        raise FileNotFoundError(f"Missing test features: {x_test_path}")
    if not y_test_path.exists():
        raise FileNotFoundError(f"Missing test labels: {y_test_path}")

    x_test = pd.read_parquet(x_test_path)
    y_test_df = pd.read_parquet(y_test_path)

    if "Class" not in y_test_df.columns:
        raise ValueError(f"Expected 'Class' column in {y_test_path}.")
    if "Class" in x_test.columns:
        raise ValueError("Target column 'Class' must not be present in X_test.")

    y_test = y_test_df["Class"]
    if len(x_test) != len(y_test):
        raise ValueError(
            f"X_test/y_test row mismatch: {len(x_test)} vs {len(y_test)}."
        )
    if set(y_test.unique().tolist()) != {0, 1}:
        raise ValueError("y_test must contain both classes 0 and 1.")

    return x_test, y_test


def run_final_evaluation(
    model_path: Path = DEFAULT_MODEL_PATH,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    output_report: Path = DEFAULT_OUTPUT_REPORT,
) -> dict[str, Any]:
    """Run the locked final evaluation workflow."""
    print("Final locked evaluation started")
    print("No tuning is performed in this script.")

    if not model_path.exists():
        raise FileNotFoundError(
            f"Champion model not found at {model_path}. "
            "Run Day 5 first: python3 -m scripts.run_day5_advanced_models"
        )

    threshold = load_locked_threshold(thresholds_path)
    print(f"Loaded locked threshold from Day 6 validation: {threshold:.2f}")

    model = load_verified_joblib(
        model_path,
        trusted_root=PROJECT_ROOT / "artifacts",
        required_attributes=("predict_proba",),
    )
    x_test, y_test = load_test_data(processed_dir)
    print(f"Loaded test rows: {len(x_test)}")

    if not hasattr(model, "predict_proba"):
        raise AttributeError("Champion model must expose predict_proba.")
    y_test_proba = model.predict_proba(x_test)[:, 1]
    print("Generated test probabilities")

    metrics = evaluate_locked_model(y_test, y_test_proba, threshold=threshold)
    summary = build_final_evaluation_summary(
        metrics=metrics,
        model_name=MODEL_NAME,
        threshold=threshold,
        split_name="test",
    )

    json_path = save_final_evaluation(summary, output_json)
    report_path = write_final_evaluation_report(summary, output_report)

    print(f"Saved final evaluation JSON: {json_path}")
    print(f"Saved final evaluation report: {report_path}")
    print("Final locked evaluation completed")

    return {
        "summary": summary,
        "json_path": json_path,
        "report_path": report_path,
    }


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    try:
        run_final_evaluation(
            model_path=args.model_path,
            processed_dir=args.processed_dir,
            thresholds_path=args.thresholds_path,
            output_json=args.output_json,
            output_report=args.output_report,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Final evaluation failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
