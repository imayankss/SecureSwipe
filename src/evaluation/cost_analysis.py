"""Explicit, scenario-based development cost analysis for fraud review policies.

Costs are supplied by the caller in one consistent currency or unit. This module
does not claim that any built-in ratio represents a bank or payment processor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from src.evaluation.threshold_tuning import build_threshold_metrics_table


@dataclass(frozen=True)
class CostScenario:
    """Auditable assumptions for one threshold-sensitivity scenario."""

    name: str
    false_positive_cost: float
    false_negative_cost: float
    review_cost: float
    fraud_recovery_rate: float

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("CostScenario name must not be empty.")
        monetary = (
            self.false_positive_cost,
            self.false_negative_cost,
            self.review_cost,
        )
        if not all(math.isfinite(value) and value >= 0.0 for value in monetary):
            raise ValueError("Cost assumptions must be finite and non-negative.")
        if not math.isfinite(self.fraud_recovery_rate) or not (
            0.0 <= self.fraud_recovery_rate <= 1.0
        ):
            raise ValueError("fraud_recovery_rate must be finite and in [0, 1].")


def _validate_threshold_counts(threshold_table: pd.DataFrame) -> None:
    if threshold_table is None or threshold_table.empty:
        raise ValueError("threshold_table must not be empty.")
    required = {"threshold", "tp", "fp", "fn", "tn"}
    missing = required - set(threshold_table.columns)
    if missing:
        raise ValueError(f"threshold_table is missing required columns: {sorted(missing)}.")
    numeric = threshold_table[list(required)].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("threshold_table must contain only finite values.")
    if (threshold_table[["tp", "fp", "fn", "tn"]] < 0).any(axis=None):
        raise ValueError("Confusion counts must be non-negative.")
    counts = threshold_table[["tp", "fp", "fn", "tn"]].to_numpy(dtype=float)
    if not np.equal(counts, np.floor(counts)).all():
        raise ValueError("Confusion counts must be integers.")
    if np.logical_or(threshold_table["threshold"] < 0.0, threshold_table["threshold"] > 1.0).any():
        raise ValueError("Thresholds must be in [0, 1].")
    total_rows = threshold_table[["tp", "fp", "fn", "tn"]].sum(axis=1)
    fraud_rows = threshold_table[["tp", "fn"]].sum(axis=1)
    legitimate_rows = threshold_table[["fp", "tn"]].sum(axis=1)
    if (total_rows <= 0).any() or total_rows.nunique() != 1:
        raise ValueError("Every threshold must describe the same non-empty population.")
    if fraud_rows.nunique() != 1 or legitimate_rows.nunique() != 1:
        raise ValueError("Class totals must remain constant across thresholds.")


def evaluate_cost_scenario(
    threshold_table: pd.DataFrame,
    scenario: CostScenario,
) -> pd.DataFrame:
    """Add transparent cost components for every candidate threshold.

    A flagged row incurs review cost. A false positive additionally incurs the
    supplied false-positive cost. A missed fraud incurs full false-negative
    cost. A caught fraud retains the unrecovered fraction of that same loss.
    """
    scenario.validate()
    _validate_threshold_counts(threshold_table)
    output = threshold_table.copy()
    output["scenario"] = scenario.name
    output["review_volume"] = output["tp"] + output["fp"]
    output["review_cost"] = output["review_volume"] * scenario.review_cost
    output["false_positive_cost"] = output["fp"] * scenario.false_positive_cost
    output["missed_fraud_cost"] = output["fn"] * scenario.false_negative_cost
    output["residual_caught_fraud_cost"] = (
        output["tp"] * scenario.false_negative_cost * (1.0 - scenario.fraud_recovery_rate)
    )
    component_columns = [
        "review_cost",
        "false_positive_cost",
        "missed_fraud_cost",
        "residual_caught_fraud_cost",
    ]
    output["total_cost"] = output[component_columns].sum(axis=1)
    row_count = output[["tp", "fp", "fn", "tn"]].sum(axis=1)
    output["cost_per_transaction"] = output["total_cost"] / row_count
    return output


def select_minimum_cost_threshold(cost_table: pd.DataFrame) -> dict[str, object]:
    """Select minimum cost, then lower review volume, then higher threshold."""
    required = {"threshold", "scenario", "review_volume", "total_cost"}
    if cost_table is None or cost_table.empty or required - set(cost_table.columns):
        raise ValueError("cost_table is empty or missing cost-analysis columns.")
    if cost_table["scenario"].nunique() != 1:
        raise ValueError("Select one scenario at a time.")
    numeric = cost_table[["threshold", "review_volume", "total_cost"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (numeric < 0.0).any():
        raise ValueError("Cost selection values must be finite and non-negative.")
    row = cost_table.sort_values(
        ["total_cost", "review_volume", "threshold"],
        ascending=[True, True, False],
        kind="mergesort",
    ).iloc[0]
    return {
        key: value.item() if isinstance(value, np.generic) else value for key, value in row.items()
    }


def analyze_cost_scenarios(
    y_true: Sequence[int] | np.ndarray,
    scores: Sequence[float] | np.ndarray,
    scenarios: Iterable[CostScenario],
    *,
    thresholds: Sequence[float] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Return long-form sensitivity data and one selected point per scenario."""
    configured = list(scenarios)
    if not configured:
        raise ValueError("At least one explicit CostScenario is required.")
    names = [scenario.name for scenario in configured]
    if len(names) != len(set(names)):
        raise ValueError("CostScenario names must be unique.")
    threshold_table = build_threshold_metrics_table(y_true, scores, thresholds)
    scenario_tables = [evaluate_cost_scenario(threshold_table, scenario) for scenario in configured]
    selections = [select_minimum_cost_threshold(table) for table in scenario_tables]
    return pd.concat(scenario_tables, ignore_index=True), selections
