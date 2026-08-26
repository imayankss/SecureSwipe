"""Lane A selection, calibration and threshold logic.

Reuses the project's existing, feature-agnostic statistics and calibration code
(`src/evaluation/…`) because it is scientifically compatible with either lane.
Only the Brier-difference bootstrap is added here: the accepted protocol
requires a confidence interval on
``improvement = Brier(identity) - Brier(candidate)`` and the existing bootstrap
is average-precision specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

BOOTSTRAP_RESAMPLES = 2_000
BOOTSTRAP_SEED = 42
CONFIDENCE_LEVEL = 0.95

#: Predeclared tie-break order: simplest model wins a tie.
MODEL_SIMPLICITY_ORDER: tuple[str, ...] = (
    "dummy_majority",
    "logistic_regression",
    "random_forest",
    "xgboost",
)

#: Protocol thresholds.
CALIBRATION_POSITIVE_FLOOR = 40
MINIMUM_BRIER_IMPROVEMENT = 0.005
RECALL_TARGET = 0.80
REVIEW_CAPACITY_PER_DAY = 100


class LaneAEvaluationError(RuntimeError):
    """Raised when an evaluation precondition is violated."""


@dataclass(frozen=True)
class ThresholdRow:
    """One candidate operating point. Typed so ordering cannot go wrong."""

    threshold: float
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    review_volume: int
    reviews_per_day: float
    meets_recall: bool
    within_capacity: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": self.precision,
            "recall": self.recall,
            "review_volume": self.review_volume,
            "reviews_per_day": self.reviews_per_day,
            "meets_recall": self.meets_recall,
            "within_capacity": self.within_capacity,
        }


@dataclass(frozen=True)
class Interval:
    """A percentile confidence interval."""

    point: float
    lower: float
    upper: float

    def excludes_zero_above(self) -> bool:
        return self.lower > 0.0

    def includes_zero(self) -> bool:
        return self.lower <= 0.0 <= self.upper


def confusion_counts(labels: np.ndarray, predictions: np.ndarray) -> dict[str, int]:
    labels = np.asarray(labels).astype(int)
    predictions = np.asarray(predictions).astype(int)
    return {
        "tp": int(np.sum((labels == 1) & (predictions == 1))),
        "fp": int(np.sum((labels == 0) & (predictions == 1))),
        "fn": int(np.sum((labels == 1) & (predictions == 0))),
        "tn": int(np.sum((labels == 0) & (predictions == 0))),
    }


def core_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    if labels.shape != scores.shape:
        raise LaneAEvaluationError("Labels and scores must align.")
    if len(np.unique(labels)) < 2:
        raise LaneAEvaluationError("Both classes must be present.")
    return {
        "average_precision": float(average_precision_score(labels, scores)),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "prevalence": float(np.mean(labels)),
    }


def _stratified_indices(labels: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    positives = np.flatnonzero(labels == 1)
    negatives = np.flatnonzero(labels == 0)
    return np.concatenate(
        (
            rng.choice(negatives, size=len(negatives), replace=True),
            rng.choice(positives, size=len(positives), replace=True),
        )
    )


def paired_ap_difference(
    labels: np.ndarray,
    scores_a: np.ndarray,
    scores_b: np.ndarray,
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> Interval:
    """Stratified paired bootstrap CI for ``AP(a) - AP(b)``.

    Rows are resampled once per replicate and both score vectors are evaluated on
    the identical resampled rows, so the interval reflects the paired difference.
    Stratification preserves the positive count, so no replicate can be degenerate.
    """
    labels = np.asarray(labels).astype(int)
    rng = np.random.default_rng(seed)
    point = float(
        average_precision_score(labels, scores_a) - average_precision_score(labels, scores_b)
    )
    differences = np.empty(n_resamples, dtype=float)
    for index in range(n_resamples):
        picked = _stratified_indices(labels, rng)
        picked_labels = labels[picked]
        differences[index] = average_precision_score(
            picked_labels, scores_a[picked]
        ) - average_precision_score(picked_labels, scores_b[picked])
    alpha = 1.0 - CONFIDENCE_LEVEL
    return Interval(
        point=point,
        lower=float(np.quantile(differences, alpha / 2.0)),
        upper=float(np.quantile(differences, 1.0 - alpha / 2.0)),
    )


def paired_brier_improvement(
    labels: np.ndarray,
    identity_scores: np.ndarray,
    candidate_scores: np.ndarray,
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> Interval:
    """Stratified paired bootstrap CI for ``Brier(identity) - Brier(candidate)``.

    Positive when the candidate is better, matching the protocol's definition.
    """
    labels = np.asarray(labels).astype(int)
    rng = np.random.default_rng(seed)
    point = float(
        brier_score_loss(labels, identity_scores) - brier_score_loss(labels, candidate_scores)
    )
    improvements = np.empty(n_resamples, dtype=float)
    for index in range(n_resamples):
        picked = _stratified_indices(labels, rng)
        picked_labels = labels[picked]
        improvements[index] = brier_score_loss(
            picked_labels, identity_scores[picked]
        ) - brier_score_loss(picked_labels, candidate_scores[picked])
    alpha = 1.0 - CONFIDENCE_LEVEL
    return Interval(
        point=point,
        lower=float(np.quantile(improvements, alpha / 2.0)),
        upper=float(np.quantile(improvements, 1.0 - alpha / 2.0)),
    )


def select_champion(validation_ap: Mapping[str, float]) -> tuple[str, str]:
    """Highest validation AP; ties broken toward the simpler model.

    Returns ``(champion, reason)``.
    """
    if not validation_ap:
        raise LaneAEvaluationError("No candidate models supplied.")
    best = max(validation_ap.values())
    tied = [name for name, value in validation_ap.items() if value == best]
    if len(tied) == 1:
        return tied[0], "highest validation average precision"
    for name in MODEL_SIMPLICITY_ORDER:
        if name in tied:
            return name, "tie on validation average precision, broken toward the simpler model"
    raise LaneAEvaluationError("Tie could not be broken; unknown model name.")


def select_threshold(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    partition_days: float,
    recall_target: float = RECALL_TARGET,
    review_capacity_per_day: int = REVIEW_CAPACITY_PER_DAY,
    grid: Sequence[float] | None = None,
) -> dict[str, object]:
    """Maximise precision subject to recall >= target and the review capacity.

    Returns the decision plus the reason. If no threshold satisfies both
    constraints, that outcome is reported; no rule is relaxed.
    """
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    if partition_days <= 0:
        raise LaneAEvaluationError("partition_days must be positive.")
    candidates = list(grid) if grid is not None else [i / 1000.0 for i in range(1, 1000)]
    capacity_rows = review_capacity_per_day * partition_days

    rows: list[ThresholdRow] = []
    for threshold in candidates:
        predicted = (scores >= threshold).astype(int)
        counts = confusion_counts(labels, predicted)
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        review_volume = tp + fp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        rows.append(
            ThresholdRow(
                threshold=float(threshold),
                tp=tp,
                fp=fp,
                fn=fn,
                tn=counts["tn"],
                precision=precision,
                recall=recall,
                review_volume=review_volume,
                reviews_per_day=review_volume / partition_days,
                meets_recall=recall >= recall_target,
                within_capacity=review_volume <= capacity_rows,
            )
        )

    meeting_recall = [row for row in rows if row.meets_recall]
    feasible = [row for row in meeting_recall if row.within_capacity]
    if feasible:
        chosen = max(feasible, key=lambda row: (row.precision, row.recall, -row.threshold))
        return {
            "satisfiable": True,
            "selected": chosen.as_dict(),
            "reason": "highest precision subject to recall target and review capacity",
            "capacity_rows_allowed": capacity_rows,
        }
    if meeting_recall:
        best_ignoring_capacity = max(
            meeting_recall, key=lambda row: (row.precision, row.recall, -row.threshold)
        )
        return {
            "satisfiable": False,
            "selected": None,
            "unsatisfiable_reason": "review_capacity",
            "best_meeting_recall_only": best_ignoring_capacity.as_dict(),
            "capacity_rows_allowed": capacity_rows,
            "reason": (
                "no threshold meets the recall target within the declared synthetic "
                "review capacity; the capacity constraint was NOT relaxed"
            ),
        }
    return {
        "satisfiable": False,
        "selected": None,
        "unsatisfiable_reason": "recall_target",
        "capacity_rows_allowed": capacity_rows,
        "reason": "no threshold reaches the recall target at any operating point",
    }
