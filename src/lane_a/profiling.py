"""Aggregate-only column profiling for Lane A.

Emits dtype, missingness, cardinality and invalid-value counts. It never
retains, returns, or logs a cell value, an identifier, or an example, so its
output is safe to publish while its input is not.

Cardinality is exact up to ``CARDINALITY_CAP`` distinct values and reported as
capped beyond that, which bounds memory on wide, high-cardinality inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

CARDINALITY_CAP = 2_000
MISSING_TOKENS = frozenset({"", "NaN", "nan", "NA", "N/A", "null", "None"})


class ProfilingError(RuntimeError):
    """Raised when profiling is asked to do something unsafe."""


@dataclass
class ColumnAccumulator:
    """Streaming, value-free accumulator for one column."""

    name: str
    non_negative_expected: bool = False
    _present: int = 0
    _missing: int = 0
    _int_like: int = 0
    _float_like: int = 0
    _text_like: int = 0
    _negative: int = 0
    _non_finite: int = 0
    _distinct: set[str] = field(default_factory=set)
    _capped: bool = False

    def update(self, raw: str) -> None:
        if raw is None or raw.strip() in MISSING_TOKENS:
            self._missing += 1
            return
        value = raw.strip()
        self._present += 1
        if not self._capped:
            self._distinct.add(value)
            if len(self._distinct) > CARDINALITY_CAP:
                self._capped = True
                self._distinct = set()
        try:
            number = float(value)
        except ValueError:
            self._text_like += 1
            return
        if math.isnan(number) or math.isinf(number):
            self._non_finite += 1
            return
        if float(value).is_integer() and "." not in value and "e" not in value.lower():
            self._int_like += 1
        else:
            self._float_like += 1
        if number < 0.0:
            self._negative += 1

    @property
    def total(self) -> int:
        return self._present + self._missing

    def dtype_inferred(self) -> str:
        kinds = {
            "integer": self._int_like,
            "float": self._float_like,
            "text": self._text_like,
        }
        populated = {key: count for key, count in kinds.items() if count}
        if not populated:
            return "empty"
        if len(populated) > 1:
            if set(populated) == {"integer", "float"}:
                return "float"
            return "mixed"
        return next(iter(populated))

    def finalize(self) -> Mapping[str, object]:
        """Return a value-free profile. Contains counts and rates only."""
        total = self.total
        profile: dict[str, object] = {
            "column": self.name,
            "dtype_inferred": self.dtype_inferred(),
            "rows_seen": total,
            "present_count": self._present,
            "missing_count": self._missing,
            "missing_rate": round(self._missing / total, 6) if total else None,
            "cardinality": (
                f">={CARDINALITY_CAP}" if self._capped else len(self._distinct)
            ),
            "cardinality_capped": self._capped,
            "invalid_non_finite_count": self._non_finite,
            "invalid_negative_count": self._negative if self.non_negative_expected else 0,
            "negative_count": self._negative,
            "mixed_type_observed": self.dtype_inferred() == "mixed",
        }
        violations: list[str] = []
        if self._non_finite:
            violations.append("non_finite_values_present")
        if self.non_negative_expected and self._negative:
            violations.append("negative_values_where_non_negative_expected")
        if profile["mixed_type_observed"]:
            violations.append("mixed_types_observed")
        profile["invalid_value_violations"] = violations
        return profile


def new_accumulators(
    columns: tuple[str, ...], non_negative: frozenset[str] = frozenset()
) -> dict[str, ColumnAccumulator]:
    """Build one accumulator per column, refusing any label column."""
    from src.lane_a.feature_contract import LABEL_COLUMN

    if LABEL_COLUMN in columns:
        raise ProfilingError(
            f"Refusing to profile the label column {LABEL_COLUMN!r}; "
            "Lane A profiling must never read it."
        )
    return {
        name: ColumnAccumulator(name=name, non_negative_expected=name in non_negative)
        for name in columns
    }


def profile_is_publishable(profile: Mapping[str, object]) -> bool:
    """True when a profile carries only counts, rates and flags."""
    permitted = {
        "column",
        "dtype_inferred",
        "rows_seen",
        "present_count",
        "missing_count",
        "missing_rate",
        "cardinality",
        "cardinality_capped",
        "invalid_non_finite_count",
        "invalid_negative_count",
        "negative_count",
        "mixed_type_observed",
        "invalid_value_violations",
    }
    return set(profile) == permitted
