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
import sys
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.historical_lock import verify_historical_observation  # noqa: E402

DEFAULT_OUTPUT = PROJECT_ROOT / "web/public/data/dashboard.json"

EDA_REPORT = PROJECT_ROOT / "reports/day2_eda_summary.md"
SPLIT_REPORT = PROJECT_ROOT / "reports/day3_preprocessing_summary.md"
MODEL_COMPARISON = PROJECT_ROOT / "reports/model_comparison/validation_model_comparison.json"
THRESHOLD_METRICS = PROJECT_ROOT / "reports/threshold_tuning/threshold_metrics.csv"
SELECTED_THRESHOLDS = PROJECT_ROOT / "reports/threshold_tuning/selected_thresholds.json"
FINAL_EVALUATION = PROJECT_ROOT / "reports/final/final_model_evaluation.json"
HISTORICAL_LOCK = PROJECT_ROOT / "reports/final/historical_observation.lock.json"
SHAP_FEATURES = PROJECT_ROOT / "reports/explainability/shap_top_features.json"

SOURCE_FILES = (
    EDA_REPORT,
    SPLIT_REPORT,
    MODEL_COMPARISON,
    THRESHOLD_METRICS,
    SELECTED_THRESHOLDS,
    FINAL_EVALUATION,
    HISTORICAL_LOCK,
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


def _figure_pairs() -> list[tuple[Path, Path]]:
    return [
        (
            PROJECT_ROOT / "reports/figures" / filename,
            PROJECT_ROOT / "web/public/images" / filename,
        )
        for filename in PUBLIC_FIGURES
    ]


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


def _parse_split_summary(dataset_rows: int) -> list[dict[str, Any]]:
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

    if sum(row["rows"] for row in rows) != dataset_rows:
        raise ValueError("Train, validation, and test rows do not sum to the dataset total.")
    return rows


def _number(row: Mapping[str, str], field: str, *, integer: bool = False) -> int | float:
    raw = row.get(field)
    if raw is None or raw == "":
        raise ValueError(f"Threshold metrics are missing required field: {field}")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"Threshold field {field} contains a non-finite value.")
    if integer:
        if value < 0.0 or not value.is_integer():
            raise ValueError(f"Threshold field {field} must be a non-negative integer.")
        return int(value)
    return value


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _assert_close(actual: Any, expected: float, label: str) -> None:
    if not isinstance(actual, (int, float)) or not math.isfinite(float(actual)):
        raise ValueError(f"{label} must be a finite number.")
    if not math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError(f"{label} does not match its confusion-matrix value.")


def _validate_confusion_metrics(
    values: Mapping[str, Any],
    *,
    tp_key: str,
    fp_key: str,
    fn_key: str,
    tn_key: str,
    precision_key: str,
    recall_key: str,
    f1_key: str,
    context: str,
) -> None:
    counts: dict[str, int] = {}
    for key in (tp_key, fp_key, fn_key, tn_key):
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{context} {key} must be a non-negative integer.")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
            raise ValueError(f"{context} {key} must be a non-negative integer.")
        counts[key] = int(numeric)
    precision = _ratio(counts[tp_key], counts[tp_key] + counts[fp_key])
    recall = _ratio(counts[tp_key], counts[tp_key] + counts[fn_key])
    f1 = _ratio(2 * precision * recall, precision + recall)
    _assert_close(values.get(precision_key), precision, f"{context} {precision_key}")
    _assert_close(values.get(recall_key), recall, f"{context} {recall_key}")
    _assert_close(values.get(f1_key), f1, f"{context} {f1_key}")


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
    thresholds = [float(point["threshold"]) for point in points]
    if any(not 0.0 <= threshold <= 1.0 for threshold in thresholds):
        raise ValueError("Threshold sweep contains a value outside [0, 1].")
    if thresholds != sorted(thresholds) or len(thresholds) != len(set(thresholds)):
        raise ValueError("Threshold sweep must be strictly increasing and unique.")
    for point in points:
        _validate_confusion_metrics(
            point,
            tp_key="truePositives",
            fp_key="falsePositives",
            fn_key="falseNegatives",
            tn_key="trueNegatives",
            precision_key="precision",
            recall_key="recall",
            f1_key="f1",
            context=f"threshold {point['threshold']}",
        )
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
        if point["fraudCaught"] != point["truePositives"]:
            raise ValueError("fraud_caught does not equal true positives.")
        if point["fraudMissed"] != point["falseNegatives"]:
            raise ValueError("fraud_missed does not equal false negatives.")
        if point["falseAlerts"] != point["falsePositives"]:
            raise ValueError("false_alerts does not equal false positives.")
        if point["reviewWorkload"] != point["truePositives"] + point["falsePositives"]:
            raise ValueError("predicted_frauds does not match flagged rows.")
        if point["predictedLegitimate"] != point["trueNegatives"] + point["falseNegatives"]:
            raise ValueError("predicted_legitimate does not match unflagged rows.")
    return points


def _normalise_selected_thresholds(raw: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    labels = {
        "default": "Default 0.50",
        "best_f1": "Best validation F1",
        "recall_target": "Selected operating point",
    }
    if set(raw) != set(labels):
        raise ValueError(f"Selected thresholds must contain exactly {sorted(labels)}.")
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
            "fraudCaught": values["fraud_caught"],
            "fraudMissed": values["fraud_missed"],
            "falseAlerts": values["false_alerts"],
            "reviewWorkload": values["predicted_frauds"],
            "predictedLegitimate": values["predicted_legitimate"],
        }
        for key in labels
        for values in [raw[key]]
    ]


def _source_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(SOURCE_FILES):
        if not path.is_file():
            raise FileNotFoundError(f"Required report is missing: {path}")
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    for source, _ in sorted(_figure_pairs()):
        if not source.is_file():
            raise FileNotFoundError(f"Required verified figure is missing: {source}")
        digest.update(str(source.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(source.read_bytes())
    return digest.hexdigest()


def verify_public_figures() -> None:
    """Read-only verification that every published figure equals its source."""
    for source, destination in _figure_pairs():
        if not source.is_file():
            raise FileNotFoundError(f"Required verified figure is missing: {source}")
        if not destination.is_file():
            raise FileNotFoundError(f"Published figure is missing: {destination}")
        if source.read_bytes() != destination.read_bytes():
            raise ValueError(f"Published figure is stale or modified: {destination}")


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


def _validate_model_comparison(
    rows: Any, validation_rows: int, validation_frauds: int
) -> list[Mapping[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Validation model comparison must be a non-empty list.")
    names: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("Every model comparison row must be an object.")
        name = row.get("model_name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every model comparison row needs a model_name.")
        names.append(name)
        if row.get("validation_rows") != validation_rows:
            raise ValueError(f"Model comparison row {index} has the wrong validation size.")
        if row.get("validation_frauds") != validation_frauds:
            raise ValueError(f"Model comparison row {index} has the wrong fraud count.")
        for field in ("pr_auc", "roc_auc", "precision", "recall", "f1"):
            value = row.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"Model comparison {field} must be finite.")
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"Model comparison {field} must be in [0, 1].")
    if len(names) != len(set(names)):
        raise ValueError("Model comparison model names must be unique.")
    highest_average_precision = max(float(row["pr_auc"]) for row in rows)
    if not math.isclose(float(rows[0]["pr_auc"]), highest_average_precision, abs_tol=1e-12):
        raise ValueError("First model row is not the highest reported average precision.")
    return rows


def _validate_selected_thresholds(
    selected: list[dict[str, Any]], points: list[dict[str, Any]]
) -> None:
    compared_fields = (
        "precision",
        "recall",
        "f1",
        "truePositives",
        "falsePositives",
        "falseNegatives",
        "trueNegatives",
        "fraudCaught",
        "fraudMissed",
        "falseAlerts",
        "reviewWorkload",
        "predictedLegitimate",
    )
    for selected_point in selected:
        matching = next(
            (
                point
                for point in points
                if math.isclose(
                    float(point["threshold"]),
                    float(selected_point["threshold"]),
                    abs_tol=1e-12,
                )
            ),
            None,
        )
        if matching is None:
            raise ValueError(
                f"Selected threshold {selected_point['threshold']} is absent from sweep."
            )
        for field in compared_fields:
            expected = matching[field]
            actual = selected_point[field]
            if isinstance(expected, float):
                if not isinstance(actual, (int, float)) or not math.isclose(
                    float(actual), expected, rel_tol=1e-9, abs_tol=1e-12
                ):
                    raise ValueError(
                        f"Selected threshold {selected_point['key']} has stale {field}."
                    )
            elif actual != expected:
                raise ValueError(f"Selected threshold {selected_point['key']} has stale {field}.")


def _validate_final_evaluation(
    final: Any,
    *,
    test_rows: int,
    test_frauds: int,
    selected_threshold: float,
) -> Mapping[str, Any]:
    if not isinstance(final, Mapping):
        raise ValueError("Final evaluation must be a JSON object.")
    if final.get("split_name") != "test":
        raise ValueError("Final evaluation split_name must be test.")
    if final.get("total_samples") != test_rows or final.get("total_fraud") != test_frauds:
        raise ValueError("Final evaluation totals do not match the recorded test split.")
    if final.get("total_legitimate") != test_rows - test_frauds:
        raise ValueError("Final legitimate count does not match the test split.")
    threshold = final.get("threshold")
    if not isinstance(threshold, (int, float)) or not math.isclose(
        float(threshold), selected_threshold, abs_tol=1e-12
    ):
        raise ValueError("Final threshold does not match the selected validation threshold.")
    _validate_confusion_metrics(
        final,
        tp_key="true_positives",
        fp_key="false_positives",
        fn_key="false_negatives",
        tn_key="true_negatives",
        precision_key="precision",
        recall_key="recall",
        f1_key="f1_score",
        context="final evaluation",
    )
    tp = int(final["true_positives"])
    fp = int(final["false_positives"])
    fn = int(final["false_negatives"])
    tn = int(final["true_negatives"])
    if tp + fp + fn + tn != test_rows or tp + fn != test_frauds:
        raise ValueError("Final confusion counts do not match the test split.")
    exact_aliases = {
        "fraud_caught": tp,
        "fraud_missed": fn,
        "false_alerts": fp,
    }
    for field, expected in exact_aliases.items():
        if final.get(field) != expected:
            raise ValueError(f"Final {field} does not match its confusion count.")
    _assert_close(final.get("specificity"), _ratio(tn, tn + fp), "final specificity")
    _assert_close(
        final.get("false_positive_rate"),
        _ratio(fp, fp + tn),
        "final false_positive_rate",
    )
    _assert_close(
        final.get("false_negative_rate"),
        _ratio(fn, fn + tp),
        "final false_negative_rate",
    )
    for field in ("pr_auc", "roc_auc"):
        value = final.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"Final {field} must be finite.")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"Final {field} must be in [0, 1].")
    return final


def _selection_methodology(selected_threshold: float) -> str:
    if not math.isfinite(selected_threshold) or not 0.0 <= selected_threshold <= 1.0:
        raise ValueError("Selected methodology threshold must be finite and in [0, 1].")
    return (
        "Models were compared by reported validation average precision. The "
        f"historical {selected_threshold:.2f} operating point was recorded from "
        "validation data under the recall-target rule; it has no domain-approved "
        "cost model or future-performance guarantee."
    )


def build_web_payload() -> dict[str, Any]:
    verify_historical_observation(HISTORICAL_LOCK, PROJECT_ROOT)
    dataset = _parse_dataset_summary()
    splits = _parse_split_summary(dataset["totalTransactions"])
    model_comparison_raw = _read_json(MODEL_COMPARISON)
    selected_thresholds_raw = _read_json(SELECTED_THRESHOLDS)
    final_evaluation = _read_json(FINAL_EVALUATION)
    shap_features = _read_json(SHAP_FEATURES)

    if not isinstance(selected_thresholds_raw, dict):
        raise ValueError("Selected threshold data must be a JSON object.")
    if not isinstance(shap_features, list) or not shap_features:
        raise ValueError("SHAP feature importance must be a non-empty list.")

    validation_split = next(row for row in splits if row["name"] == "validation")
    test_split = next(row for row in splits if row["name"] == "test")
    model_comparison = _validate_model_comparison(
        model_comparison_raw, validation_split["rows"], validation_split["fraud"]
    )
    champion = model_comparison[0]

    threshold_points = _parse_threshold_points(validation_split["rows"], validation_split["fraud"])
    selected_thresholds = _normalise_selected_thresholds(selected_thresholds_raw)
    _validate_selected_thresholds(selected_thresholds, threshold_points)
    recall_target = next(item for item in selected_thresholds if item["key"] == "recall_target")
    final_evaluation = _validate_final_evaluation(
        final_evaluation,
        test_rows=test_split["rows"],
        test_frauds=test_split["fraud"],
        selected_threshold=float(recall_target["threshold"]),
    )
    if champion["model_name"] != final_evaluation["model_name"]:
        raise ValueError("Validation champion and final evaluated model do not match.")

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
            "displayName": MODEL_DISPLAY_NAMES.get(champion["model_name"], champion["model_name"]),
            "selectedBy": "Highest reported validation average precision (single split)",
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
                "averagePrecision": champion["pr_auc"],
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
            "selection": _selection_methodology(float(recall_target["threshold"])),
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
        "sources": [
            str(path.relative_to(PROJECT_ROOT))
            for path in (*SOURCE_FILES, *(source for source, _ in _figure_pairs()))
        ],
    }
    return sanitize_for_json(payload)


def sync_public_figures() -> None:
    (PROJECT_ROOT / "web/public/images").mkdir(parents=True, exist_ok=True)
    for source, destination in _figure_pairs():
        if not source.is_file():
            raise FileNotFoundError(f"Required verified figure is missing: {source}")
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
    payload_text = (
        json.dumps(build_web_payload(), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    output_path = args.output.resolve()

    if args.check:
        if not output_path.is_file() or output_path.read_text(encoding="utf-8") != payload_text:
            raise SystemExit(
                "Web data is stale. Run `python3 scripts/export_web_data.py` and commit the result."
            )
        verify_public_figures()
        print(f"Verified current web data: {output_path.relative_to(PROJECT_ROOT)}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload_text, encoding="utf-8")
    sync_public_figures()
    print(f"Exported verified web data: {output_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
