"""Numerical boundary tests for the review-signal policy."""

from __future__ import annotations

import math

import pytest

from src.inference.risk_scoring import threshold_decision


def test_threshold_decision_includes_the_threshold_in_review() -> None:
    assert threshold_decision(0.529999, 0.53) == "pass"
    assert threshold_decision(0.53, 0.53) == "review"
    assert threshold_decision(0.9, 0.53) == "review"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.1, 1.1])
def test_threshold_decision_rejects_invalid_score(value: float) -> None:
    with pytest.raises(ValueError, match="score"):
        threshold_decision(value, 0.5)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.1, 1.1])
def test_threshold_decision_rejects_invalid_threshold(value: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        threshold_decision(0.5, value)
