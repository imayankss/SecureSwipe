"""Export verified SecureSwipe reports into a deployment-safe web payload.

This script reads only tracked, precomputed evaluation artifacts. It does not
load transaction data, deserialize model files, run inference, or train models.

Run from the repository root:

    python3 scripts/export_web_data.py

Use ``--check`` in CI to verify that the committed payload is current.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "web/public/data/dashboard.json"

EDA_REPORT = PROJECT_ROOT / "reports/day2_eda_summary.md"
SPLIT_REPORT = PROJECT_ROOT / "reports/day3_preprocessing_summary.md"
MODEL_COMPARISON = (
    PROJECT_ROOT / "reports/model_comparison/validation_model_comparison.json"
)
THRESHOLD_METRICS = PROJECT_ROOT / "reports/threshold_tuning/threshold_metrics.csv"
SELECTED_THRESHOLDS = (
    PROJECT_ROOT / "reports/threshold_tuning/selected_thresholds.json"
)
FINAL_EVALUATION = PROJECT_ROOT / "reports/final/final_model_evaluation.json"
SHAP_FEATURES = PROJECT_ROOT / "reports/explainability/shap_top_features.json"

SOURCE_FILES = (
    EDA_REPORT,
    SPLIT_REPORT,
    MODEL_COMPARISON,
    THRESHOLD_METRICS,
    SELECTED_THRESHOLDS,
    FINAL_EVALUATION,
    SHAP_FEATURES,
)

PUBLIC_FIGURES = (
    "precision_recall_curve.png",
    "roc_curve.png",
    "confusion_matrix_default_threshold.png",
    "confusion_matrix_best_f1_threshold.png",
    "confusion_matrix_recall_target_threshold.png",
    "shap_summary_bar.png",
    "shap_top_features.png",
)

MODEL_DISPLAY_NAMES = {
    "dummy_baseline": "Dummy baseline",
    "logistic_regression": "Logistic Regression",
    "random_forest": "Random Forest",
    "xgboost_baseline": "XGBoost",
}


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Required report is missing: {path}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(_read_text(path), parse_constant=_reject_json_constant)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant is not allowed: {value}")


def _required_match(pattern: str, text: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not parse {label} from its verified report.")
    return match


def _parse_dataset_summary() -> dict[str, Any]:
    report = _read_text(EDA_REPORT)
    total = int(
        _required_match(r"\| Total transactions \| (\d+) \|", report, "total rows").group(1)
    )
    legitimate_match = _required_match(
        r"\| Legitimate transactions \| (\d+) \(([\d.]+)%\) \|",
        report,
        "legitimate count",
    )
    fraud_match = _required_match(
        r"\| Fraudulent transactions \| (\d+) \(([\d.]+)%\) \|",
        report,
        "fraud count",
    )
    ratio = float(
        _required_match(
            r"\| Imbalance ratio \(legitimate:fraud\) \| ([\d.]+):1 \|",
            report,
            "imbalance ratio",
        ).group(1)
    )
    majority_accuracy = float(
        _required_match(
            r"\| Majority-class accuracy baseline \| ([\d.]+)% \|",
            report,
            "majority baseline",
        ).group(1)
    )

    legitimate = int(legitimate_match.group(1))
    fraud = int(fraud_match.group(1))
    fraud_prevalence = float(fraud_match.group(2))
    if total != legitimate + fraud:
        raise ValueError("Dataset class counts do not sum to the reported total.")

    return {
        "totalTransactions": total,
        "legitimateTransactions": legitimate,
        "fraudTransactions": fraud,
        "fraudPrevalencePercent": fraud_prevalence,
        "imbalanceRatio": ratio,
        "majorityClassAccuracyPercent": majority_accuracy,
        "source": "reports/day2_eda_summary.md",
    }


def _parse_split_summary() -> list[dict[str, Any]]:
    report = _read_text(SPLIT_REPORT)
    rows: list[dict[str, Any]] = []
    for name in ("Train", "Validation", "Test"):
        pattern = rf"\| {name} \| (\d+) \| (\d+) \| (\d+) \| ([\d.]+)% \| ([\d.]+)% \|"
        match = _required_match(pattern, report, f"{name.lower()} split")
        rows.append(
            {
                "name": name.lower(),
                "rows": int(match.group(1)),
                "legitimate": int(match.group(2)),
                "fraud": int(match.group(3)),
                "legitimatePercent": float(match.group(4)),
                "fraudPercent": float(match.group(5)),
            }
        )

    if sum(row["rows"] for row in rows) != 284_807:
        raise ValueError("Train, validation, and test rows do not sum to 284,807.")
    return rows


def _number(row: Mapping[str, str], field: str, *, integer: bool = False) -> int | float:
    raw = row.get(field)
    if raw is None or raw == "":
        raise ValueError(f"Threshold metrics are missing required field: {field}")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"Threshold field {field} contains a non-finite value.")
    return int(value) if integer else value


def _parse_threshold_points(validation_rows: int, validation_frauds: int) -> list[dict[str, Any]]:
    with THRESHOLD_METRICS.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        points = [
            {
                "threshold": _number(row, "threshold"),
                "precision": _number(row, "precision"),
                "recall": _number(row, "recall"),
                "f1": _number(row, "f1"),
                "truePositives": _number(row, "tp", integer=True),
                "falsePositives": _number(row, "fp", integer=True),
                "falseNegatives": _number(row, "fn", integer=True),
                "trueNegatives": _number(row, "tn", integer=True),
                "fraudCaught": _number(row, "fraud_caught", integer=True),
                "fraudMissed": _number(row, "fraud_missed", integer=True),
                "falseAlerts": _number(row, "false_alerts", integer=True),
                "reviewWorkload": _number(row, "predicted_frauds", integer=True),
                "predictedLegitimate": _number(row, "predicted_legitimate", integer=True),
            }
            for row in reader
        ]

    if not points:
        raise ValueError("Threshold metrics table is empty.")
    for point in points:
        confusion_total = (
            point["truePositives"]
            + point["falsePositives"]
            + point["falseNegatives"]
            + point["trueNegatives"]
        )
        if confusion_total != validation_rows:
            raise ValueError("A threshold confusion matrix does not match validation rows.")
        if point["truePositives"] + point["falseNegatives"] != validation_frauds:
            raise ValueError("A threshold point does not match validation fraud count.")
    return points


def _normalise_selected_thresholds(raw: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    labels = {
        "default": "Default 0.50",
        "best_f1": "Best validation F1",
        "recall_target": "Selected operating point",
    }
    return [
        {
            "key": key,
            "label": labels[key],
            "threshold": values["threshold"],
            "precision": values["precision"],
            "recall": values["recall"],
            "f1": values["f1"],
            "truePositives": values["tp"],
            "falsePositives": values["fp"],
            "falseNegatives": values["fn"],
            "trueNegatives": values["tn"],
        }
        for key, values in raw.items()
        if key in labels
    ]


def _source_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(SOURCE_FILES):
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sanitize_for_json(value: Any) -> Any:
    """Convert common scientific values into strict, portable JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        converted = float(value)
        return converted if math.isfinite(converted) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_for_json(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        return sanitize_for_json(item_method())
    isoformat_method = getattr(value, "isoformat", None)
    if callable(isoformat_method):
        return isoformat_method()
    raise TypeError(f"Unsupported value for web JSON export: {type(value).__name__}")


def build_web_payload() -> dict[str, Any]:
    dataset = _parse_dataset_summary()
    splits = _parse_split_summary()
    model_comparison = _read_json(MODEL_COMPARISON)
    selected_thresholds_raw = _read_json(SELECTED_THRESHOLDS)
    final_evaluation = _read_json(FINAL_EVALUATION)
    shap_features = _read_json(SHAP_FEATURES)

    if not isinstance(model_comparison, list) or not model_comparison:
        raise ValueError("Validation model comparison must be a non-empty list.")
    if not isinstance(selected_thresholds_raw, dict):
        raise ValueError("Selected threshold data must be a JSON object.")
    if not isinstance(shap_features, list) or not shap_features:
        raise ValueError("SHAP feature importance must be a non-empty list.")

    champion = model_comparison[0]
    if champion["model_name"] != final_evaluation["model_name"]:
        raise ValueError("Validation champion and final evaluated model do not match.")

    validation_split = next(row for row in splits if row["name"] == "validation")
    test_split = next(row for row in splits if row["name"] == "test")
    if champion["validation_rows"] != validation_split["rows"]:
        raise ValueError("Model comparison row count does not match the validation split.")
    if champion["validation_frauds"] != validation_split["fraud"]:
        raise ValueError("Model comparison fraud count does not match the validation split.")
    if final_evaluation["total_samples"] != test_split["rows"]:
        raise ValueError("Final evaluation row count does not match the test split.")

    threshold_points = _parse_threshold_points(
        validation_split["rows"], validation_split["fraud"]
    )
    selected_thresholds = _normalise_selected_thresholds(selected_thresholds_raw)
    for selected in selected_thresholds:
        matching = next(
            (
                point
                for point in threshold_points
                if math.isclose(point["threshold"], selected["threshold"], abs_tol=1e-12)
            ),
            None,
        )
        if matching is None:
            raise ValueError(f"Selected threshold {selected['threshold']} is absent from sweep.")

    comparison_rows = [
        {
            **row,
            "displayName": MODEL_DISPLAY_NAMES.get(row["model_name"], row["model_name"]),
        }
        for row in model_comparison
    ]

    payload = {
        "schemaVersion": 1,
        "project": {
            "name": "SecureSwipe",
            "subtitle": "Fraud detection and transaction risk analytics",
            "repository": "https://github.com/imayankss/SecureSwipe",
            "deploymentMode": "precomputed-demonstration",
            "artifactGeneratedAt": final_evaluation["generated_at"],
            "sourceDigestSha256": _source_digest(),
            "disclaimer": (
                "Educational portfolio system—not a bank production authorization, "
                "compliance, or payment-processing service."
            ),
        },
        "dataset": {**dataset, "splits": splits},
        "modelSelection": {
            "modelName": champion["model_name"],
            "displayName": MODEL_DISPLAY_NAMES.get(
                champion["model_name"], champion["model_name"]
            ),
            "selectedBy": "Highest validation PR-AUC",
            "selectionSplit": "validation",
            "validationMetrics": champion,
        },
        "finalEvaluation": {
            **final_evaluation,
            "displayName": MODEL_DISPLAY_NAMES.get(
                final_evaluation["model_name"], final_evaluation["model_name"]
            ),
        },
        "modelComparison": comparison_rows,
        "thresholdAnalysis": {
            "modelName": champion["model_name"],
            "split": "validation",
            "validationRows": validation_split["rows"],
            "validationFrauds": validation_split["fraud"],
            "points": threshold_points,
            "selected": selected_thresholds,
            "costAnalysisAvailable": False,
            "costAnalysisNote": (
                "No defensible fraud-loss or manual-review cost assumptions are tracked, "
                "so the dashboard does not claim an economic optimum."
            ),
        },
        "explainability": {
            "method": "SHAP mean absolute feature importance",
            "split": "validation sample",
            "features": shap_features,
            "caveat": (
                "V1-V28 are anonymized PCA components. SHAP describes model behavior "
                "and does not assign real-world business meaning or causality."
            ),
        },
        "curves": {
            "split": "validation",
            "precisionRecall": {
                "image": "/images/precision_recall_curve.png",
                "auc": champion["pr_auc"],
            },
            "roc": {
                "image": "/images/roc_curve.png",
                "auc": champion["roc_auc"],
            },
        },
        "methodology": {
            "splitStrategy": "70% train / 15% validation / 15% test, stratified by Class",
            "preprocessing": (
                "StandardScaler fitted on training Time and Amount only; V1-V28 passed "
                "through; the target was excluded."
            ),
            "imbalanceHandling": (
                "Logistic Regression used class weighting; XGBoost scale_pos_weight was "
                "derived only from the training labels."
            ),
            "selection": (
                "Models were compared by validation PR-AUC. The 0.53 operating threshold "
                "was selected on validation data as the highest-precision point with "
                "recall of at least 0.80."
            ),
            "finalTest": (
                "The held-out test split was evaluated once after model and threshold lock."
            ),
        },
        "limitations": [
            "No trained model or preprocessor is shipped with the web application.",
            "No original or user-submitted transaction data is served, stored, or logged.",
            "Dashboard interactions use precomputed validation and test artifacts, not live inference.",
            "The historical, anonymized dataset does not represent current bank traffic or policy.",
            "The XGBoost score has not been calibrated as a real-world fraud probability.",
        ],
        "sources": [str(path.relative_to(PROJECT_ROOT)) for path in SOURCE_FILES],
    }
    return sanitize_for_json(payload)


def sync_public_figures() -> None:
    source_dir = PROJECT_ROOT / "reports/figures"
    target_dir = PROJECT_ROOT / "web/public/images"
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in PUBLIC_FIGURES:
        source = source_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Required verified figure is missing: {source}")
        destination = target_dir / filename
        if not destination.exists() or source.read_bytes() != destination.read_bytes():
            shutil.copy2(source, destination)


def export_web_data(output_path: Path = DEFAULT_OUTPUT, *, sync_assets: bool = True) -> Path:
    payload = build_web_payload()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if sync_assets:
        sync_public_figures()
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the existing output differs from the verified source artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload_text = json.dumps(
        build_web_payload(), indent=2, ensure_ascii=False, allow_nan=False
    ) + "\n"
    output_path = args.output.resolve()

    if args.check:
        if not output_path.is_file() or output_path.read_text(encoding="utf-8") != payload_text:
            raise SystemExit(
                "Web data is stale. Run `python3 scripts/export_web_data.py` and commit the result."
            )
        sync_public_figures()
        print(f"Verified current web data: {output_path.relative_to(PROJECT_ROOT)}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload_text, encoding="utf-8")
    sync_public_figures()
    print(f"Exported verified web data: {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
