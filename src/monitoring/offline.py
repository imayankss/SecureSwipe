"""Deterministic offline schema, drift, score, and delayed-label monitoring."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.artifacts.bundle import ModelBundle
from src.data.data_loader import validate_dataset_schema
from src.evaluation.calibration import evaluate_calibration
from src.evaluation.classification_metrics import calculate_binary_classification_metrics
from src.inference.batch_scoring import score_bundle_frame
from src.preprocessing.feature_config import ALL_FEATURES, REQUIRED_COLUMNS
from src.utils.run_manifest import runtime_provenance

MONITORING_REPORT_VERSION = "1"


@dataclass(frozen=True)
class DriftThresholds:
    """Operational signal thresholds; these are not statistical significance tests."""

    population_stability_index: float = 0.2
    ks_statistic: float = 0.2
    histogram_bins: int = 10

    def __post_init__(self) -> None:
        if not math.isfinite(self.population_stability_index) or not (
            0.0 < self.population_stability_index
        ):
            raise ValueError("population_stability_index must be finite and positive.")
        if not math.isfinite(self.ks_statistic) or not 0.0 < self.ks_statistic <= 1.0:
            raise ValueError("ks_statistic must be finite and in (0, 1].")
        if not isinstance(self.histogram_bins, int) or not 2 <= self.histogram_bins <= 100:
            raise ValueError("histogram_bins must be an integer from 2 to 100.")


def _frame_fingerprint(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode("utf-8"))
    digest.update(b"\x00")
    digest.update("\x1f".join(map(str, frame.dtypes)).encode("utf-8"))
    digest.update(b"\x00")
    row_hashes = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    digest.update(row_hashes.to_numpy(dtype="uint64", copy=False).tobytes())
    return digest.hexdigest()


def audit_batch(frame: pd.DataFrame, *, max_rows: int = 1_000_000) -> dict[str, Any]:
    """Report contract violations without exposing any row values."""
    if not isinstance(max_rows, int) or max_rows < 1:
        raise ValueError("max_rows must be a positive integer.")
    columns = list(frame.columns)
    expected = list(REQUIRED_COLUMNS) if "Class" in columns else list(ALL_FEATURES)
    missing = [column for column in expected if column not in columns]
    unexpected = [column for column in columns if column not in expected]
    missingness = {
        column: int(frame[column].isna().sum())
        for column in expected
        if column in frame and frame[column].isna().any()
    }
    violations: list[dict[str, Any]] = []
    if frame.empty:
        violations.append({"code": "empty_batch", "count": 0})
    if len(frame) > max_rows:
        violations.append({"code": "row_limit_exceeded", "count": len(frame)})
    if len(columns) != len(set(columns)):
        violations.append({"code": "duplicate_columns"})
    if missing:
        violations.append({"code": "missing_columns", "columns": missing})
    if unexpected:
        violations.append({"code": "unexpected_columns", "columns": unexpected})
    if not missing and not unexpected and columns != expected:
        violations.append({"code": "incorrect_column_order"})
    if missingness:
        violations.append({"code": "missing_values", "counts": missingness})

    if not violations:
        candidate = frame if "Class" in frame else frame.assign(Class=0)
        try:
            validate_dataset_schema(candidate)
        except ValueError as exc:
            violations.append({"code": "dataset_contract", "message": str(exc)})

    return {
        "column_count": int(frame.shape[1]),
        "expected_columns": expected,
        "fingerprint": _frame_fingerprint(frame),
        "has_delayed_labels": "Class" in frame,
        "missingness": missingness,
        "row_count": int(frame.shape[0]),
        "valid": not violations,
        "violations": violations,
    }


def _ks_statistic(reference: np.ndarray, current: np.ndarray) -> float:
    points = np.sort(np.unique(np.concatenate([reference, current])))
    reference_sorted = np.sort(reference)
    current_sorted = np.sort(current)
    reference_cdf = np.searchsorted(reference_sorted, points, side="right") / len(reference)
    current_cdf = np.searchsorted(current_sorted, points, side="right") / len(current)
    return float(np.max(np.abs(reference_cdf - current_cdf)))


def _population_stability_index(
    reference: np.ndarray,
    current: np.ndarray,
    *,
    bins: int,
) -> float:
    internal_edges = np.unique(np.quantile(reference, np.linspace(0.0, 1.0, bins + 1)[1:-1]))
    if len(internal_edges) == 1 and np.all(reference == internal_edges[0]):
        value = internal_edges[0]
        edges = np.array([-np.inf, np.nextafter(value, -np.inf), np.nextafter(value, np.inf), np.inf])
    else:
        edges = np.concatenate(([-np.inf], internal_edges, [np.inf]))
    reference_counts = np.histogram(reference, bins=edges)[0].astype(float)
    current_counts = np.histogram(current, bins=edges)[0].astype(float)
    epsilon = 1e-6
    reference_share = np.maximum(reference_counts / len(reference), epsilon)
    current_share = np.maximum(current_counts / len(current), epsilon)
    reference_share /= reference_share.sum()
    current_share /= current_share.sum()
    return float(np.sum((current_share - reference_share) * np.log(current_share / reference_share)))


def _distribution_summary(values: np.ndarray) -> dict[str, float | int]:
    return {
        "count": int(len(values)),
        "mean": float(np.mean(values)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
        "standard_deviation": float(np.std(values)),
    }


def _drift_record(
    reference: np.ndarray,
    current: np.ndarray,
    thresholds: DriftThresholds,
) -> dict[str, Any]:
    psi = _population_stability_index(reference, current, bins=thresholds.histogram_bins)
    ks = _ks_statistic(reference, current)
    return {
        "current": _distribution_summary(current),
        "drift_signal": bool(
            psi >= thresholds.population_stability_index or ks >= thresholds.ks_statistic
        ),
        "ks_statistic": ks,
        "population_stability_index": psi,
        "reference": _distribution_summary(reference),
    }


def _performance(labels: pd.Series, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    values = labels.to_numpy(dtype=int, copy=False)
    if set(np.unique(values)) != {0, 1}:
        return {
            "available": False,
            "reason": "Both delayed-label classes are required for performance diagnostics.",
        }
    predicted = (scores >= threshold).astype(int)
    metrics = calculate_binary_classification_metrics(values, predicted, scores)
    calibration = evaluate_calibration(
        values,
        scores,
        n_bins=min(10, len(values)),
        strategy="quantile",
    )
    return {
        "available": True,
        "average_precision": metrics["average_precision"],
        "brier_score_diagnostic": calibration["brier_score"],
        "expected_calibration_error": calibration["expected_calibration_error"],
        "false_negatives": metrics["false_negatives"],
        "false_positives": metrics["false_positives"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "true_negatives": metrics["true_negatives"],
        "true_positives": metrics["true_positives"],
    }


def monitor_batches(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    bundle: ModelBundle | None,
    thresholds: DriftThresholds = DriftThresholds(),
    max_rows: int = 1_000_000,
) -> dict[str, Any]:
    """Compare two batches; invalid schemas are reported and never scored."""
    reference_audit = audit_batch(reference, max_rows=max_rows)
    current_audit = audit_batch(current, max_rows=max_rows)
    report: dict[str, Any] = {
        "interpretation": {
            "drift_is_model_failure": False,
            "guidance": (
                "A drift signal requests investigation; it does not by itself prove model "
                "failure, fraud-pattern change, or customer harm."
            ),
        },
        "monitoring_report_version": MONITORING_REPORT_VERSION,
        "runtime": runtime_provenance(
            ["joblib", "numpy", "pandas", "scikit-learn"]
        ),
        "schema": {"current": current_audit, "reference": reference_audit},
        "status": "invalid" if not reference_audit["valid"] or not current_audit["valid"] else "valid",
        "thresholds": {
            "histogram_bins": thresholds.histogram_bins,
            "ks_statistic": thresholds.ks_statistic,
            "population_stability_index": thresholds.population_stability_index,
        },
    }
    if report["status"] == "invalid":
        report["signals"] = {
            "feature_drift": None,
            "schema_violation": True,
            "score_drift": None,
        }
        return report
    if bundle is None:
        raise ValueError("A verified ModelBundle is required to score valid batches.")

    reference_features = reference.loc[:, ALL_FEATURES]
    current_features = current.loc[:, ALL_FEATURES]
    reference_scored = score_bundle_frame(bundle, reference_features)
    current_scored = score_bundle_frame(bundle, current_features)
    feature_records = {
        feature: _drift_record(
            reference_features[feature].to_numpy(dtype=float, copy=False),
            current_features[feature].to_numpy(dtype=float, copy=False),
            thresholds,
        )
        for feature in ALL_FEATURES
    }
    feature_drift = any(record["drift_signal"] for record in feature_records.values())
    score_drift = _drift_record(
        reference_scored.decision_scores,
        current_scored.decision_scores,
        thresholds,
    )
    report["model"] = {
        "model_version": bundle.model_version,
        "operating_threshold": bundle.operating_threshold,
        "score_type": bundle.score_type,
        "training_data_fingerprint": bundle.training_data_fingerprint,
    }
    report["feature_drift"] = {
        "drifted_feature_count": sum(
            int(record["drift_signal"]) for record in feature_records.values()
        ),
        "features": feature_records,
    }
    report["score_drift"] = score_drift
    report["performance"] = {
        "calibrated_probability_claim": bundle.score_type == "calibrated_probability",
        "current": (
            _performance(current["Class"], current_scored.decision_scores, bundle.operating_threshold)
            if "Class" in current
            else {"available": False, "reason": "Delayed labels were not supplied."}
        ),
        "reference": (
            _performance(
                reference["Class"],
                reference_scored.decision_scores,
                bundle.operating_threshold,
            )
            if "Class" in reference
            else {"available": False, "reason": "Delayed labels were not supplied."}
        ),
    }
    report["signals"] = {
        "feature_drift": feature_drift,
        "schema_violation": False,
        "score_drift": score_drift["drift_signal"],
    }
    return report
