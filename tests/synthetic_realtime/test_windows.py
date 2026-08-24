"""Tests for event-time window aggregation, with explicit boundary coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.synthetic_realtime.contracts import SyntheticEvent
from src.synthetic_realtime.windows import (
    WINDOW_DURATIONS,
    count,
    distinct_count,
    max_amount,
    mean_amount,
    select_window_events,
    sum_amount,
    window_bounds,
    window_counts,
)

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    event_time: datetime,
    amount: float = 100.0,
    device_id: str = "syn_dev_001",
) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        account_id="syn_acct_001",
        device_id=device_id,
        payment_method_id="syn_pm_001",
        merchant_id="syn_mer_001",
        address_id="syn_addr_001",
        ip_id="syn_ip_001",
        amount=amount,
        currency="INR",
        outcome="success",
        account_country="IN",
        event_country="IN",
        event_region="APAC",
        billing_shipping_match=True,
        vpn_or_proxy=False,
        retry_group_id=None,
    )


# --- window_bounds -----------------------------------------------------------------


@pytest.mark.parametrize("window", ["1m", "1h", "24h"])
def test_window_bounds_end_equals_as_of(window: str) -> None:
    bounds = window_bounds(AS_OF, window)  # type: ignore[arg-type]
    assert bounds.end == AS_OF


@pytest.mark.parametrize("window", ["1m", "1h", "24h"])
def test_window_bounds_start_is_as_of_minus_duration(window: str) -> None:
    bounds = window_bounds(AS_OF, window)  # type: ignore[arg-type]
    assert bounds.start == AS_OF - WINDOW_DURATIONS[window]  # type: ignore[index]


def test_window_bounds_rejects_unknown_window() -> None:
    with pytest.raises(ValueError, match="Unknown window"):
        window_bounds(AS_OF, "7d")  # type: ignore[arg-type]


def test_window_bounds_rejects_naive_as_of() -> None:
    naive = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        window_bounds(naive, "1m")


# --- select_window_events: boundary-timestamp behavior -------------------------------


@pytest.mark.parametrize("window", ["1m", "1h", "24h"])
def test_event_exactly_at_window_start_is_included(window: str) -> None:
    duration = WINDOW_DURATIONS[window]  # type: ignore[index]
    boundary_event = _event(event_id="evt_boundary", event_time=AS_OF - duration)
    selected = select_window_events([boundary_event], as_of=AS_OF, window=window)  # type: ignore[arg-type]
    assert [event.event_id for event in selected] == ["evt_boundary"]


@pytest.mark.parametrize("window", ["1m", "1h", "24h"])
def test_event_one_microsecond_before_window_start_is_excluded(window: str) -> None:
    duration = WINDOW_DURATIONS[window]  # type: ignore[index]
    just_outside = _event(
        event_id="evt_outside", event_time=AS_OF - duration - timedelta(microseconds=1)
    )
    selected = select_window_events([just_outside], as_of=AS_OF, window=window)  # type: ignore[arg-type]
    assert selected == []


def test_event_exactly_at_as_of_is_included() -> None:
    at_as_of = _event(event_id="evt_now", event_time=AS_OF)
    selected = select_window_events([at_as_of], as_of=AS_OF, window="1m")
    assert [event.event_id for event in selected] == ["evt_now"]


def test_event_after_as_of_is_excluded() -> None:
    future_event = _event(event_id="evt_future", event_time=AS_OF + timedelta(microseconds=1))
    selected = select_window_events([future_event], as_of=AS_OF, window="24h")
    assert selected == []


def test_select_window_events_returns_time_sorted_results() -> None:
    events = [
        _event(event_id="evt_late", event_time=AS_OF - timedelta(seconds=5)),
        _event(event_id="evt_early", event_time=AS_OF - timedelta(seconds=50)),
        _event(event_id="evt_mid", event_time=AS_OF - timedelta(seconds=20)),
    ]
    selected = select_window_events(events, as_of=AS_OF, window="1m")
    assert [event.event_id for event in selected] == ["evt_early", "evt_mid", "evt_late"]


def test_select_window_events_ignores_unrelated_out_of_bounds_events() -> None:
    events = [
        _event(event_id="evt_in", event_time=AS_OF - timedelta(seconds=10)),
        _event(event_id="evt_out", event_time=AS_OF - timedelta(hours=2)),
    ]
    selected = select_window_events(events, as_of=AS_OF, window="1m")
    assert [event.event_id for event in selected] == ["evt_in"]


# --- window_counts -------------------------------------------------------------------


def test_window_counts_computes_all_three_sizes_in_one_pass() -> None:
    events = [
        _event(event_id="evt_1", event_time=AS_OF - timedelta(seconds=10)),  # in all 3
        _event(event_id="evt_2", event_time=AS_OF - timedelta(minutes=30)),  # in 1h, 24h only
        _event(event_id="evt_3", event_time=AS_OF - timedelta(hours=12)),  # in 24h only
        _event(event_id="evt_4", event_time=AS_OF - timedelta(hours=48)),  # in none
    ]
    counts = window_counts(events, as_of=AS_OF)
    assert counts.count_1m == 1
    assert counts.count_1h == 2
    assert counts.count_24h == 3


def test_window_counts_handles_empty_input() -> None:
    counts = window_counts([], as_of=AS_OF)
    assert counts.count_1m == 0
    assert counts.count_1h == 0
    assert counts.count_24h == 0


def test_window_counts_rejects_naive_as_of() -> None:
    naive = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        window_counts([], as_of=naive)


# --- generic aggregates --------------------------------------------------------------


def test_count_matches_length() -> None:
    events = [
        _event(event_id="evt_1", event_time=AS_OF),
        _event(event_id="evt_2", event_time=AS_OF),
    ]
    assert count(events) == 2


def test_sum_amount_adds_amounts() -> None:
    events = [
        _event(event_id="evt_1", event_time=AS_OF, amount=100.0),
        _event(event_id="evt_2", event_time=AS_OF, amount=250.5),
    ]
    assert sum_amount(events) == pytest.approx(350.5)


def test_mean_amount_averages_amounts() -> None:
    events = [
        _event(event_id="evt_1", event_time=AS_OF, amount=100.0),
        _event(event_id="evt_2", event_time=AS_OF, amount=200.0),
    ]
    assert mean_amount(events) == pytest.approx(150.0)


def test_mean_amount_is_zero_for_empty_window() -> None:
    assert mean_amount([]) == 0.0


def test_max_amount_returns_largest_value() -> None:
    events = [
        _event(event_id="evt_1", event_time=AS_OF, amount=100.0),
        _event(event_id="evt_2", event_time=AS_OF, amount=999.0),
        _event(event_id="evt_3", event_time=AS_OF, amount=50.0),
    ]
    assert max_amount(events) == pytest.approx(999.0)


def test_max_amount_is_zero_for_empty_window() -> None:
    assert max_amount([]) == 0.0


def test_distinct_count_counts_unique_keys() -> None:
    events = [
        _event(event_id="evt_1", event_time=AS_OF, device_id="syn_dev_001"),
        _event(event_id="evt_2", event_time=AS_OF, device_id="syn_dev_002"),
        _event(event_id="evt_3", event_time=AS_OF, device_id="syn_dev_001"),
    ]
    assert distinct_count(events, key=lambda event: event.device_id) == 2


def test_distinct_count_is_zero_for_empty_window() -> None:
    assert distinct_count([], key=lambda event: event.device_id) == 0
