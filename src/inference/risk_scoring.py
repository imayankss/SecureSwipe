"""Pure, testable conversion from a model score to a review signal."""

from __future__ import annotations

import math
from typing import Literal


def threshold_decision(
    score: float,
    threshold: float,
) -> Literal["human_review", "below_review_threshold"]:
    """Return a review signal; never imply payment authorization."""
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("score must be finite and in [0, 1].")
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be finite and in [0, 1].")
    return "human_review" if score >= threshold else "below_review_threshold"
