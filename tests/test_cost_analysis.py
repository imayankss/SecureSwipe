"""Explicit scenario cost-accounting tests."""

from __future__ import annotations

import pandas as pd
import pytest

from src.evaluation.cost_analysis import (
    CostScenario,
    analyze_cost_scenarios,
    evaluate_cost_scenario,
    select_minimum_cost_threshold,
)


def _threshold_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"threshold": 0.2, "tp": 8, "fp": 10, "fn": 2, "tn": 80},
            {"threshold": 0.8, "tp": 5, "fp": 1, "fn": 5, "tn": 89},
        ]
    )


def test_cost_components_follow_explicit_formula() -> None:
    scenario = CostScenario(
        name="synthetic",
        false_positive_cost=2.0,
        false_negative_cost=100.0,
        review_cost=1.0,
        fraud_recovery_rate=0.75,
    )
    row = evaluate_cost_scenario(_threshold_table(), scenario).iloc[0]
    assert row["review_cost"] == pytest.approx(18.0)
    assert row["false_positive_cost"] == pytest.approx(20.0)
    assert row["missed_fraud_cost"] == pytest.approx(200.0)
    assert row["residual_caught_fraud_cost"] == pytest.approx(200.0)
    assert row["total_cost"] == pytest.approx(438.0)
    assert row["cost_per_transaction"] == pytest.approx(4.38)


@pytest.mark.parametrize(
    "scenario",
    [
        CostScenario("", 1, 1, 1, 0.5),
        CostScenario("bad", -1, 1, 1, 0.5),
        CostScenario("bad", 1, float("inf"), 1, 0.5),
        CostScenario("bad", 1, 1, 1, 1.1),
    ],
)
def test_cost_scenario_rejects_unusable_assumptions(scenario: CostScenario) -> None:
    with pytest.raises(ValueError):
        scenario.validate()


def test_minimum_cost_tie_prefers_lower_review_then_higher_threshold() -> None:
    table = pd.DataFrame(
        [
            {"threshold": 0.4, "scenario": "s", "review_volume": 10, "total_cost": 5},
            {"threshold": 0.6, "scenario": "s", "review_volume": 8, "total_cost": 5},
            {"threshold": 0.7, "scenario": "s", "review_volume": 8, "total_cost": 5},
        ]
    )
    assert select_minimum_cost_threshold(table)["threshold"] == pytest.approx(0.7)


def test_cost_analysis_rejects_inconsistent_population_counts() -> None:
    malformed = _threshold_table()
    malformed.loc[1, "tn"] += 1
    scenario = CostScenario("synthetic", 1, 10, 1, 0.5)
    with pytest.raises(ValueError, match="same non-empty population"):
        evaluate_cost_scenario(malformed, scenario)


def test_multiple_scenarios_produce_separate_sensitivity_outputs() -> None:
    scenarios = [
        CostScenario("low_miss_ratio", 1, 10, 1, 0.5),
        CostScenario("high_miss_ratio", 1, 1_000, 1, 0.9),
    ]
    table, selections = analyze_cost_scenarios(
        [0, 0, 0, 1, 1],
        [0.1, 0.4, 0.8, 0.3, 0.9],
        scenarios,
        thresholds=[0.2, 0.5, 0.85],
    )
    assert set(table["scenario"]) == {scenario.name for scenario in scenarios}
    assert len(table) == 6
    assert {selection["scenario"] for selection in selections} == {
        scenario.name for scenario in scenarios
    }
