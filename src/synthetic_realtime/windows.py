"""Event-time window aggregation for the synthetic real-time layer.

Generic, entity-agnostic primitives over an already-filtered sequence of
``SyntheticEvent`` objects: window-boundary computation for the three
canonical window sizes (1m/1h/24h), event selection within a window, and a
small set of reusable numeric aggregates. This module does not know about
account_id/device_id/etc. entity filtering - that is each feature module's
job (added in a later implementation step); this module only does the
time-bucketing math those feature modules build on. It must never import
the historical XGBoost model, SHAP, thresholds, metrics, or Bundle v3 code.

Window semantics: a window is the closed interval
``[as_of - duration, as_of]`` - inclusive at both ends, matching
``SyntheticEventStore.events_in_range``'s inclusive-both-ends convention so
the two layers never disagree about a boundary event.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.synthetic_realtime.clock import require_timezone_aware
from src.synthetic_realtime.contracts import SyntheticEvent

WindowSize = Literal["1m", "1h", "24h"]

WINDOW_DURATIONS: dict[WindowSize, timedelta] = {
    "1m": timedelta(minutes=1),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
}


@dataclass(frozen=True)
class WindowBounds:
    """The inclusive ``[start, end]`` instants for one window at one ``as_of``."""

    start: datetime
    end: datetime


def window_bounds(as_of: datetime, window: WindowSize) -> WindowBounds:
    """Compute the inclusive time bounds for ``window`` ending at ``as_of``."""
    require_timezone_aware(as_of, field_name="as_of")
    if window not in WINDOW_DURATIONS:
        raise ValueError(f"Unknown window {window!r}. Known windows: {tuple(WINDOW_DURATIONS)}.")
    duration = WINDOW_DURATIONS[window]
    return WindowBounds(start=as_of - duration, end=as_of)


def select_window_events(
    events: Sequence[SyntheticEvent], *, as_of: datetime, window: WindowSize
) -> list[SyntheticEvent]:
    """Return the subset of ``events`` within ``window`` ending at ``as_of``, time-sorted.

    ``events`` is not assumed to be pre-sorted or pre-filtered to any
    particular entity; typically the caller fetches a broad 24h superset
    once (e.g. from ``SyntheticEventStore.events_in_range``) and calls this
    once per window size against that same list.
    """
    bounds = window_bounds(as_of, window)
    matching = [event for event in events if bounds.start <= event.event_time <= bounds.end]
    matching.sort(key=lambda event: event.event_time)
    return matching


@dataclass(frozen=True)
class WindowCounts:
    """Event counts across all three canonical windows for one ``as_of``."""

    count_1m: int
    count_1h: int
    count_24h: int


def window_counts(events: Sequence[SyntheticEvent], *, as_of: datetime) -> WindowCounts:
    """Compute 1m/1h/24h event counts in one pass over ``events``."""
    require_timezone_aware(as_of, field_name="as_of")
    return WindowCounts(
        count_1m=count(select_window_events(events, as_of=as_of, window="1m")),
        count_1h=count(select_window_events(events, as_of=as_of, window="1h")),
        count_24h=count(select_window_events(events, as_of=as_of, window="24h")),
    )


def count(events: Sequence[SyntheticEvent]) -> int:
    return len(events)


def sum_amount(events: Sequence[SyntheticEvent]) -> float:
    return sum(event.amount for event in events)


def mean_amount(events: Sequence[SyntheticEvent]) -> float:
    """Mean amount, or 0.0 for an empty window (documented, not a division error)."""
    if not events:
        return 0.0
    return sum_amount(events) / len(events)


def max_amount(events: Sequence[SyntheticEvent]) -> float:
    """Maximum amount, or 0.0 for an empty window (documented, not a ValueError)."""
    if not events:
        return 0.0
    return max(event.amount for event in events)


def distinct_count(events: Sequence[SyntheticEvent], key: Callable[[SyntheticEvent], str]) -> int:
    """Count of distinct values of ``key`` across ``events``."""
    return len({key(event) for event in events})
