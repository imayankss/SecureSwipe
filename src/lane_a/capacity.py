"""Merchant-configurable review-capacity policy for Lane A.

The v1 universal "100 reviews/day" assumption is withdrawn as unsupported: real
merchants differ by orders of magnitude in review staffing, so a single global
number was never defensible. The frozen operating policy is this
capacity-to-allocation function, **not** a single universal threshold.

The policy ranks transactions by risk score and spends a merchant-configured
review budget on the highest-risk ones. It is a human-review prioritisation
system: it never approves, blocks, declines, or steps up anything.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

POLICY_VERSION = "lane_a_capacity_policy_v2"

#: The only decision vocabulary this policy may emit.
BELOW_REVIEW_THRESHOLD = "below_review_threshold"
HUMAN_REVIEW = "human_review"
UNAVAILABLE_FAIL_CLOSED = "unavailable_fail_closed"
DECISIONS: tuple[str, ...] = (BELOW_REVIEW_THRESHOLD, HUMAN_REVIEW, UNAVAILABLE_FAIL_CLOSED)

#: Illustrative development tiers. Not merchant defaults, not a recommendation.
ILLUSTRATIVE_CAPACITY_TIERS: tuple[int, ...] = (100, 250, 500, 1_000, 2_000)

ILLUSTRATIVE_LABEL = (
    "Illustrative development scenario - not Razorpay economics, not a "
    "production SLO, and not a universal merchant policy."
)


class CapacityPolicyError(RuntimeError):
    """Raised when a capacity configuration is invalid."""


@dataclass(frozen=True)
class MerchantCapacityConfig:
    """Merchant-supplied review capacity. No default is provided on purpose."""

    daily_review_capacity: int
    evaluation_period_days: float

    def __post_init__(self) -> None:
        if not isinstance(self.daily_review_capacity, int) or isinstance(
            self.daily_review_capacity, bool
        ):
            raise CapacityPolicyError("daily_review_capacity must be an int.")
        if self.daily_review_capacity < 0:
            raise CapacityPolicyError("daily_review_capacity must be non-negative.")
        if not math.isfinite(self.evaluation_period_days) or self.evaluation_period_days <= 0:
            raise CapacityPolicyError("evaluation_period_days must be positive and finite.")

    @property
    def review_budget(self) -> int:
        """floor(daily_capacity x evaluation_period_days)."""
        return int(math.floor(self.daily_review_capacity * self.evaluation_period_days))


def allocate_reviews(
    scores: Sequence[float] | np.ndarray,
    config: MerchantCapacityConfig,
    *,
    scores_available: bool = True,
) -> dict[str, object]:
    """Allocate the review budget to the highest-scoring transactions.

    Ties are resolved by ascending source position, a deterministic non-label
    field, so the allocation is reproducible. Source positions are used only
    internally and are never returned or published.
    """
    if not scores_available:
        return {
            "policy_version": POLICY_VERSION,
            "decision_for_all": UNAVAILABLE_FAIL_CLOSED,
            "selected_count": 0,
            "review_budget": config.review_budget,
            "reason": "scores unavailable; failing closed to human-review-unavailable",
        }
    values = np.asarray(scores, dtype=float)
    if values.ndim != 1:
        raise CapacityPolicyError("scores must be one-dimensional.")
    if not np.all(np.isfinite(values)):
        raise CapacityPolicyError("scores must be finite.")
    total = len(values)
    budget = min(config.review_budget, total)

    # Descending score, ascending source position for ties: lexsort on the
    # negated score with position as the stable secondary key.
    positions = np.arange(total)
    order = np.lexsort((positions, -values))
    selected = order[:budget]
    decisions = np.full(total, BELOW_REVIEW_THRESHOLD, dtype=object)
    decisions[selected] = HUMAN_REVIEW

    minimum_selected_score = float(values[selected].min()) if budget else None
    return {
        "policy_version": POLICY_VERSION,
        "decisions": decisions,
        "selected_mask": np.isin(positions, selected),
        "selected_count": int(budget),
        "review_budget": config.review_budget,
        "population": total,
        "capacity_utilisation": (
            float(budget / config.review_budget) if config.review_budget else None
        ),
        "minimum_selected_score": minimum_selected_score,
        "tie_handling": "descending score, ascending stable source position",
    }


def frontier_row(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    config: MerchantCapacityConfig,
) -> Mapping[str, object]:
    """One capacity tier's aggregate outcome. Counts and rates only."""
    from src.evaluation.statistical_metrics import wilson_interval

    labels_array = np.asarray(labels).astype(int)
    allocation = allocate_reviews(scores, config)
    selected = np.asarray(allocation["selected_mask"], dtype=bool)

    tp = int(np.sum(selected & (labels_array == 1)))
    fp = int(np.sum(selected & (labels_array == 0)))
    fn = int(np.sum(~selected & (labels_array == 1)))
    tn = int(np.sum(~selected & (labels_array == 0)))
    reviews = tp + fp
    precision = tp / reviews if reviews else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "daily_review_capacity": config.daily_review_capacity,
        "evaluation_period_days": round(config.evaluation_period_days, 4),
        "review_budget": config.review_budget,
        "alerts_selected": reviews,
        "average_reviews_per_day": reviews / config.evaluation_period_days,
        "alert_rate": reviews / len(labels_array),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "precision_wilson": wilson_interval(tp, reviews) if reviews else None,
        "recall_wilson": wilson_interval(tp, tp + fn) if (tp + fn) else None,
        "capacity_utilisation": allocation["capacity_utilisation"],
        "minimum_selected_score": allocation["minimum_selected_score"],
        "reaches_recall_80": recall >= 0.80,
        "label": ILLUSTRATIVE_LABEL,
    }


def workload_for_recall(
    labels: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    *,
    target_recall: float = 0.80,
    evaluation_period_days: float,
) -> Mapping[str, object]:
    """Minimum review workload reaching ``target_recall``.

    This is a **derived coverage reference**, not a merchant capacity and not a
    recommended default.
    """
    labels_array = np.asarray(labels).astype(int)
    values = np.asarray(scores, dtype=float)
    positives = int(labels_array.sum())
    if positives == 0:
        raise CapacityPolicyError("No positives present.")
    order = np.lexsort((np.arange(len(values)), -values))
    ranked_labels = labels_array[order]
    cumulative = np.cumsum(ranked_labels)
    needed = math.ceil(target_recall * positives)
    reached = np.flatnonzero(cumulative >= needed)
    if len(reached) == 0:
        return {"reachable": False, "target_recall": target_recall}
    workload = int(reached[0]) + 1
    return {
        "reachable": True,
        "target_recall": target_recall,
        "minimum_reviews": workload,
        "implied_reviews_per_day": workload / evaluation_period_days,
        "achieved_recall": float(cumulative[reached[0]] / positives),
        "achieved_precision": float(cumulative[reached[0]] / workload),
        "note": (
            "derived coverage reference only; NOT a merchant capacity, NOT a "
            "recommended default, and NOT adopted as a policy setting"
        ),
    }
