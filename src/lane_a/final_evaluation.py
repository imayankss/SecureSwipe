"""Lane A one-time final-evaluation metrics, bound to the frozen protocol.

Every constant here is predeclared in
``docs/evidence/LANE_A_FINAL_EVALUATION_PROTOCOL.md`` and may not be changed
after the protocol is frozen. This module computes aggregates only: it never
returns, logs, or exports a row-level value, identifier, score, or label.

It cannot train, refit, tune, or select anything. There is no threshold search,
no calibrator fit, and no variant comparison. Variants A-D are refused outright
on final data.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from src.evaluation.statistical_metrics import wilson_interval
from src.lane_a.capacity import (
    ILLUSTRATIVE_LABEL,
    MerchantCapacityConfig,
    frontier_row,
    workload_for_recall,
)
from src.lane_a.evaluation import Interval, _stratified_indices

#: The only variant this module will ever evaluate on final data.
SELECTED_VARIANT = "E"

#: Variants that must never touch final data.
PROHIBITED_ON_FINAL: tuple[str, ...] = ("A", "B", "C", "D")

#: Frozen capacity tiers, in reviews per day.
CAPACITY_TIERS: tuple[int, ...] = (100, 250, 500, 1_000, 2_000)

#: Frozen uncertainty procedure.
BOOTSTRAP_RESAMPLES = 2_000
BOOTSTRAP_SEED = 42
CONFIDENCE_LEVEL = 0.95

#: Frozen calibration reporting.
ECE_BINS = 15

#: Seconds per day, for the sole permitted use of ``TransactionDT``.
SECONDS_PER_DAY = 86_400.0

#: Recall target for the predeclared retrospective workload diagnostic.
RECALL_TARGET = 0.80

#: The complete predeclared aggregate metric set. Nothing may be added.
PREDECLARED_METRICS: frozenset[str] = frozenset(
    {
        "row_count",
        "positive_count",
        "negative_count",
        "prevalence",
        "average_precision",
        "roc_auc",
        "brier_score",
        "log_loss",
        "expected_calibration_error",
        "calibration_table",
    }
)

#: Metrics carrying a bootstrap confidence interval.
BOOTSTRAP_METRICS: tuple[str, ...] = (
    "average_precision",
    "roc_auc",
    "brier_score",
    "log_loss",
)

#: Terminology every public export must carry.
REQUIRED_TERMS: tuple[str, ...] = (
    "IEEE-CIS Lane A final evaluation",
    "programmatically held out",
    "evaluated exactly once",
    "Platt-calibrated benchmark output",
    "merchant-configurable illustrative review capacity",
    "not Razorpay economics",
    "not live-merchant performance",
    "not a production SLO",
    "not directly comparable with Lane B",
)

#: Claims no public export may ever make.
PROHIBITED_CLAIMS: tuple[str, ...] = (
    "human-blind",
    "human blind",
    "externally blind",
    "razorpay performance",
    "indian-payment performance",
    "indian payment performance",
    "live-merchant performance claim",
    "production fraud performance",
    "guaranteed savings",
    "roi",
    "universal threshold",
    "universal operating threshold",
    "autonomous block",
    "autonomously blocks",
)

#: Patterns that betray private or row-level content in a public export.
_PRIVATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("absolute_posix_path", re.compile(r"(?:^|[\s'\"(=])/(?:Users|home|private|var|tmp)/")),
    ("windows_path", re.compile(r"[A-Za-z]:\\\\")),
    ("home_shortcut", re.compile(r"~/")),
    ("domain_like", re.compile(r"\b[a-z0-9-]+\.(?:com|net|org|co|io|in|ru|de)\b", re.I)),
    ("device_string", re.compile(r"\b(?:SM-[A-Z0-9]+|iOS Device|Windows|MacOS|Trident|rv:)\b")),
    ("transaction_id", re.compile(r"\bTransactionID\b")),
    ("email_like", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
)


class FinalEvaluationError(RuntimeError):
    """Raised when a final-evaluation rule would be violated."""


# -- frozen-choice guards ------------------------------------------------


def assert_variant_selected(name: str) -> str:
    """Only variant E may be evaluated on final data."""
    if name in PROHIBITED_ON_FINAL:
        raise FinalEvaluationError(
            f"Variant {name} must never be evaluated on final data; only "
            f"{SELECTED_VARIANT} is authorised."
        )
    if name != SELECTED_VARIANT:
        raise FinalEvaluationError(f"Unknown variant {name!r}; only {SELECTED_VARIANT} is authorised.")
    return name


def assert_tiers_frozen(tiers: Sequence[int]) -> tuple[int, ...]:
    """The five frozen capacity tiers may not be changed, added to, or dropped."""
    if tuple(tiers) != CAPACITY_TIERS:
        raise FinalEvaluationError(
            f"Capacity tiers are frozen at {CAPACITY_TIERS}; refusing {tuple(tiers)}."
        )
    return CAPACITY_TIERS


def assert_metrics_predeclared(names: Iterable[str]) -> frozenset[str]:
    """Refuse any metric the protocol did not predeclare."""
    requested = frozenset(names)
    undeclared = requested - PREDECLARED_METRICS
    if undeclared:
        raise FinalEvaluationError(
            f"Metrics not predeclared in the frozen protocol: {sorted(undeclared)}."
        )
    return requested


# -- evaluation period ---------------------------------------------------


def evaluation_period_days(transaction_dt: Sequence[float] | np.ndarray) -> float:
    """``(max - min) / 86400`` over ``TransactionDT``.

    This is the only permitted use of ``TransactionDT``. It is never a model
    input, and it carries no calendar meaning.
    """
    values = np.asarray(transaction_dt, dtype=float)
    if values.size == 0:
        raise FinalEvaluationError("TransactionDT is empty.")
    if not np.all(np.isfinite(values)):
        raise FinalEvaluationError("TransactionDT must be finite.")
    span = (float(values.max()) - float(values.min())) / SECONDS_PER_DAY
    if span <= 0:
        raise FinalEvaluationError("Evaluation period must be positive.")
    return span


# -- calibration ---------------------------------------------------------


def expected_calibration_error(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    *,
    bins: int = ECE_BINS,
) -> dict[str, Any]:
    """ECE over exactly ``bins`` equal-width bins on ``[0, 1]``.

    Descriptive only. It never selects, rejects, or re-fits the frozen Platt
    calibrator.
    """
    if bins != ECE_BINS:
        raise FinalEvaluationError(f"ECE bin count is frozen at {ECE_BINS}; refusing {bins}.")
    label_array = np.asarray(labels).astype(int)
    score_array = np.asarray(scores, dtype=float)
    if label_array.shape != score_array.shape:
        raise FinalEvaluationError("Labels and scores must align.")
    if np.any(score_array < 0.0) or np.any(score_array > 1.0):
        raise FinalEvaluationError("Calibrated scores must lie in [0, 1].")

    edges = np.linspace(0.0, 1.0, bins + 1)
    # Right-closed on the final bin so a score of exactly 1.0 is counted.
    index = np.clip(np.digitize(score_array, edges[1:-1], right=False), 0, bins - 1)
    total = label_array.size
    table: list[dict[str, Any]] = []
    ece = 0.0
    for bin_id in range(bins):
        mask = index == bin_id
        count = int(mask.sum())
        if count:
            mean_predicted = float(score_array[mask].mean())
            observed_rate = float(label_array[mask].mean())
            ece += (count / total) * abs(observed_rate - mean_predicted)
        else:
            mean_predicted = None
            observed_rate = None
        table.append(
            {
                "bin": bin_id + 1,
                "lower_edge": round(float(edges[bin_id]), 6),
                "upper_edge": round(float(edges[bin_id + 1]), 6),
                "count": count,
                "mean_predicted": mean_predicted,
                "observed_positive_rate": observed_rate,
            }
        )
    if sum(row["count"] for row in table) != total:
        raise FinalEvaluationError("Calibration table does not reconcile with the row count.")
    return {"expected_calibration_error": float(ece), "bins": bins, "calibration_table": table}


# -- aggregate metrics ---------------------------------------------------


def _point_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    return {
        "average_precision": float(average_precision_score(labels, scores)),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "brier_score": float(brier_score_loss(labels, scores)),
        "log_loss": float(log_loss(labels, scores, labels=[0, 1])),
    }


def bootstrap_intervals(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence_level: float = CONFIDENCE_LEVEL,
) -> dict[str, Interval]:
    """Stratified percentile bootstrap for the four predeclared metrics.

    Resampling is performed independently within the positive and negative
    classes, preserving the original class counts in every resample.
    """
    if n_resamples != BOOTSTRAP_RESAMPLES:
        raise FinalEvaluationError(
            f"Bootstrap resample count is frozen at {BOOTSTRAP_RESAMPLES}."
        )
    if seed != BOOTSTRAP_SEED:
        raise FinalEvaluationError(f"Bootstrap seed is frozen at {BOOTSTRAP_SEED}.")
    if confidence_level != CONFIDENCE_LEVEL:
        raise FinalEvaluationError(f"Confidence level is frozen at {CONFIDENCE_LEVEL}.")

    label_array = np.asarray(labels).astype(int)
    score_array = np.asarray(scores, dtype=float)
    if len(np.unique(label_array)) < 2:
        raise FinalEvaluationError("Both classes must be present.")

    point = _point_metrics(label_array, score_array)
    draws: dict[str, list[float]] = {name: [] for name in BOOTSTRAP_METRICS}
    rng = np.random.default_rng(seed)
    for _ in range(n_resamples):
        index = _stratified_indices(label_array, rng)
        resampled_labels = label_array[index]
        resampled_scores = score_array[index]
        for name, value in _point_metrics(resampled_labels, resampled_scores).items():
            draws[name].append(value)

    tail = (1.0 - confidence_level) / 2.0
    intervals: dict[str, Interval] = {}
    for name in BOOTSTRAP_METRICS:
        values = np.asarray(draws[name], dtype=float)
        intervals[name] = Interval(
            point=point[name],
            lower=float(np.quantile(values, tail)),
            upper=float(np.quantile(values, 1.0 - tail)),
        )
    return intervals


def aggregate_metrics(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
) -> dict[str, Any]:
    """Every predeclared aggregate metric, with intervals. Aggregates only."""
    label_array = np.asarray(labels).astype(int)
    score_array = np.asarray(scores, dtype=float)
    if label_array.shape != score_array.shape:
        raise FinalEvaluationError("Labels and scores must align.")

    positives = int(label_array.sum())
    negatives = int(label_array.size - positives)
    intervals = bootstrap_intervals(label_array, score_array)
    calibration = expected_calibration_error(label_array, score_array)

    return {
        "row_count": int(label_array.size),
        "positive_count": positives,
        "negative_count": negatives,
        "prevalence": float(positives / label_array.size),
        **{
            name: {
                "point": interval.point,
                "ci_lower": interval.lower,
                "ci_upper": interval.upper,
                "confidence_level": CONFIDENCE_LEVEL,
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "method": "stratified percentile bootstrap",
            }
            for name, interval in intervals.items()
        },
        "expected_calibration_error": calibration["expected_calibration_error"],
        "calibration_table": calibration["calibration_table"],
        "ece_bins": calibration["bins"],
        "ece_role": "descriptive only; does not select or re-fit the frozen calibrator",
        "score_terminology": "Platt-calibrated benchmark output",
    }


# -- capacity ------------------------------------------------------------


def capacity_table(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    *,
    evaluation_period_days: float,
    tiers: Sequence[int] = CAPACITY_TIERS,
) -> list[Mapping[str, Any]]:
    """The five frozen tiers, each fully reconciled against the row counts."""
    assert_tiers_frozen(tiers)
    label_array = np.asarray(labels).astype(int)
    score_array = np.asarray(scores, dtype=float)
    total = int(label_array.size)
    positives = int(label_array.sum())
    negatives = total - positives

    rows: list[Mapping[str, Any]] = []
    for tier in tiers:
        config = MerchantCapacityConfig(
            daily_review_capacity=tier,
            evaluation_period_days=evaluation_period_days,
        )
        row = dict(frontier_row(label_array, score_array, config))
        tp, fp = int(row["tp"]), int(row["fp"])  # type: ignore[call-overload]
        fn, tn = int(row["fn"]), int(row["tn"])  # type: ignore[call-overload]
        selected = int(row["alerts_selected"])  # type: ignore[call-overload]
        budget = int(row["review_budget"])  # type: ignore[call-overload]
        if tp + fp != selected:
            raise FinalEvaluationError(f"Tier {tier}: TP+FP != selected review count.")
        if tp + fn != positives:
            raise FinalEvaluationError(f"Tier {tier}: TP+FN != total positives.")
        if tn + fp != negatives:
            raise FinalEvaluationError(f"Tier {tier}: TN+FP != total negatives.")
        if tp + fp + fn + tn != total:
            raise FinalEvaluationError(f"Tier {tier}: confusion cells do not sum to the row count.")
        if selected > budget:
            raise FinalEvaluationError(f"Tier {tier}: selected reviews exceed the frozen budget.")
        rows.append(row)
    return rows


def recall_80_workload(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    *,
    evaluation_period_days: float,
) -> Mapping[str, Any]:
    """Predeclared retrospective benchmark diagnostic. Not a recommendation."""
    result = dict(
        workload_for_recall(
            labels,
            scores,
            target_recall=RECALL_TARGET,
            evaluation_period_days=evaluation_period_days,
        )
    )
    result["diagnostic_class"] = "retrospective benchmark diagnostic"
    result["not_a_recommendation"] = True
    result["label"] = ILLUSTRATIVE_LABEL
    return result


# -- public export safety ------------------------------------------------


def _iter_strings(payload: Any) -> Iterable[str]:
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, Mapping):
        for key, value in payload.items():
            yield str(key)
            yield from _iter_strings(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _iter_strings(item)


def assert_public_export_safe(payload: Any) -> None:
    """Refuse a public export carrying private or row-level content.

    Aggregates, counts, rates, digests and predeclared labels are permitted.
    Absolute paths, domains, device strings, identifiers and e-mail-like values
    are not.
    """
    for text in _iter_strings(payload):
        for name, pattern in _PRIVATE_PATTERNS:
            if pattern.search(text):
                raise FinalEvaluationError(
                    f"Public export rejected: {name} detected in exported content."
                )
    lowered = " ".join(_iter_strings(payload)).lower()
    for claim in PROHIBITED_CLAIMS:
        if claim in lowered:
            raise FinalEvaluationError(f"Public export rejected: prohibited claim {claim!r}.")


def assert_required_terminology(document: str) -> None:
    """Every required term must appear verbatim in public evidence."""
    missing = [term for term in REQUIRED_TERMS if term not in document]
    if missing:
        raise FinalEvaluationError(f"Public evidence is missing required terminology: {missing}.")


def wilson(successes: int, total: int) -> Mapping[str, float | int]:
    """Wilson 95 % interval, exposed so capacity rows reproduce from counts."""
    return wilson_interval(successes, total, CONFIDENCE_LEVEL)


def reconcile_rate(numerator: int, denominator: int, reported: float) -> bool:
    """Confirm a reported rate reproduces from its counts."""
    if denominator == 0:
        return reported == 0.0
    return math.isclose(numerator / denominator, reported, rel_tol=1e-9, abs_tol=1e-12)
