"""Tests for the synthetic scenario generators, including end-to-end checks
that each narrative scenario actually trips its corresponding feature
signal when replayed through a ``SyntheticEventStore``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.features.address import compute_address_features
from src.synthetic_realtime.features.amount import compute_amount_features
from src.synthetic_realtime.features.device import compute_device_features
from src.synthetic_realtime.features.geography import compute_geography_features
from src.synthetic_realtime.features.merchant import compute_merchant_features
from src.synthetic_realtime.features.retry import compute_retry_features
from src.synthetic_realtime.scenarios import (
    MAX_EVENT_COUNT,
    MIN_EVENT_COUNT,
    ScenarioName,
    available_scenarios,
    fixed_scenario_size,
    generate_events,
)
from src.synthetic_realtime.store import SyntheticEventStore

START = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

NARRATIVE_SCENARIOS: tuple[ScenarioName, ...] = (
    "new_device_burst",
    "address_fan_out",
    "vpn_geography_mismatch",
    "retry_storm",
    "unusual_amount",
    "merchant_deviation",
    "duplicate",
    "out_of_order",
)


def _store() -> SyntheticEventStore:
    # clock set well after any generated event so nothing expires mid-replay
    return SyntheticEventStore(
        clock=FixedClock(current=START + timedelta(days=1)), retention=timedelta(hours=48)
    )


# --- registry --------------------------------------------------------------------


def test_available_scenarios_includes_normal_baseline() -> None:
    assert "normal_baseline" in available_scenarios()


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_available_scenarios_includes_every_narrative_scenario(scenario: ScenarioName) -> None:
    assert scenario in available_scenarios()


def test_generate_events_rejects_unknown_scenario() -> None:
    with pytest.raises(ValueError, match="Unknown scenario"):
        generate_events("does_not_exist", seed=1, start=START, event_count=3)  # type: ignore[arg-type]


def test_fixed_scenario_size_rejects_unknown_scenario() -> None:
    with pytest.raises(ValueError, match="Unknown scenario"):
        fixed_scenario_size("does_not_exist")  # type: ignore[arg-type]


def test_fixed_scenario_size_is_none_for_normal_baseline() -> None:
    assert fixed_scenario_size("normal_baseline") is None


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_fixed_scenario_size_is_a_positive_int_for_narrative_scenarios(
    scenario: ScenarioName,
) -> None:
    size = fixed_scenario_size(scenario)
    assert isinstance(size, int)
    assert size > 0


@pytest.mark.parametrize("event_count", [0, -1, MAX_EVENT_COUNT + 1])
def test_generate_events_rejects_out_of_range_event_count(event_count: int) -> None:
    with pytest.raises(ValueError, match="event_count"):
        generate_events("normal_baseline", seed=1, start=START, event_count=event_count)


def test_generate_events_rejects_naive_start() -> None:
    naive_start = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        generate_events("normal_baseline", seed=1, start=naive_start, event_count=3)


# --- normal_baseline: variable length -------------------------------------------------


def test_generate_events_accepts_boundary_event_counts() -> None:
    events = generate_events("normal_baseline", seed=1, start=START, event_count=MIN_EVENT_COUNT)
    assert len(events) == MIN_EVENT_COUNT


def test_normal_baseline_is_deterministic_for_identical_arguments() -> None:
    first = generate_events("normal_baseline", seed=7, start=START, event_count=10)
    second = generate_events("normal_baseline", seed=7, start=START, event_count=10)
    assert first == second


def test_normal_baseline_differs_across_seeds() -> None:
    first = generate_events("normal_baseline", seed=1, start=START, event_count=5)
    second = generate_events("normal_baseline", seed=2, start=START, event_count=5)
    assert first != second


def test_normal_baseline_entity_tokens_are_independent_of_start_time() -> None:
    later_start = START + timedelta(days=30)
    first = generate_events("normal_baseline", seed=7, start=START, event_count=5)
    second = generate_events("normal_baseline", seed=7, start=later_start, event_count=5)

    assert [event.account_id for event in first] == [event.account_id for event in second]
    assert [event.amount for event in first] == [event.amount for event in second]
    assert [event.event_time for event in first] != [event.event_time for event in second]


def test_normal_baseline_returns_requested_count() -> None:
    events = generate_events("normal_baseline", seed=3, start=START, event_count=25)
    assert len(events) == 25


def test_normal_baseline_event_ids_are_unique() -> None:
    events = generate_events("normal_baseline", seed=3, start=START, event_count=25)
    event_ids = [event.event_id for event in events]
    assert len(set(event_ids)) == len(event_ids)


def test_normal_baseline_event_times_strictly_increase() -> None:
    events = generate_events("normal_baseline", seed=3, start=START, event_count=10)
    times = [event.event_time for event in events]
    assert times == sorted(times)
    assert len(set(times)) == len(times)


def test_normal_baseline_amounts_are_within_configured_bounds() -> None:
    events = generate_events("normal_baseline", seed=3, start=START, event_count=25)
    for event in events:
        assert 50.0 <= event.amount <= 5_000.0


def test_normal_baseline_carries_no_anomalous_signal() -> None:
    events = generate_events("normal_baseline", seed=3, start=START, event_count=25)
    for event in events:
        assert event.outcome == "success"
        assert event.vpn_or_proxy is False
        assert event.billing_shipping_match is True
        assert event.retry_group_id is None
        assert event.account_country == event.event_country


# --- narrative scenarios: shared floor/determinism behavior -----------------------------


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_narrative_scenario_rejects_event_count_below_minimum(scenario: ScenarioName) -> None:
    minimum = fixed_scenario_size(scenario)
    assert minimum is not None
    if minimum <= MIN_EVENT_COUNT:
        pytest.skip("minimum is already the lowest possible event_count")
    with pytest.raises(ValueError, match="needs at least"):
        generate_events(scenario, seed=1, start=START, event_count=minimum - 1)


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_narrative_scenario_accepts_event_count_at_minimum(scenario: ScenarioName) -> None:
    minimum = fixed_scenario_size(scenario)
    assert minimum is not None
    events = generate_events(scenario, seed=1, start=START, event_count=minimum)
    assert len(events) == minimum


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_narrative_scenario_ignores_event_count_above_minimum(scenario: ScenarioName) -> None:
    minimum = fixed_scenario_size(scenario)
    assert minimum is not None
    events = generate_events(scenario, seed=1, start=START, event_count=minimum + 50)
    assert len(events) == minimum


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_narrative_scenario_is_deterministic_for_identical_arguments(
    scenario: ScenarioName,
) -> None:
    minimum = fixed_scenario_size(scenario)
    assert minimum is not None
    first = generate_events(scenario, seed=7, start=START, event_count=minimum)
    second = generate_events(scenario, seed=7, start=START, event_count=minimum)
    assert first == second


@pytest.mark.parametrize("scenario", NARRATIVE_SCENARIOS)
def test_narrative_scenario_differs_across_seeds(scenario: ScenarioName) -> None:
    minimum = fixed_scenario_size(scenario)
    assert minimum is not None
    first = generate_events(scenario, seed=1, start=START, event_count=minimum)
    second = generate_events(scenario, seed=2, start=START, event_count=minimum)
    assert first != second


# --- narrative scenarios: end-to-end signal verification -----------------------------


def _all_reason_codes(store: SyntheticEventStore, events: list, feature_fn) -> set[str]:  # type: ignore[no-untyped-def]
    codes: set[str] = set()
    for event in events:
        store.record(event)
        features = feature_fn(store=store, event=event)
        codes |= {signal.reason_code for signal in features.triggered_signals}
    return codes


def test_new_device_burst_trips_device_new_to_account() -> None:
    store = _store()
    size = fixed_scenario_size("new_device_burst")
    assert size is not None
    events = generate_events("new_device_burst", seed=7, start=START, event_count=size)
    codes = _all_reason_codes(store, events, compute_device_features)
    assert "device_new_to_account" in codes


def test_address_fan_out_trips_address_fan_out_high() -> None:
    store = _store()
    size = fixed_scenario_size("address_fan_out")
    assert size is not None
    events = generate_events("address_fan_out", seed=7, start=START, event_count=size)
    codes = _all_reason_codes(store, events, compute_address_features)
    assert "address_fan_out_high" in codes


def test_vpn_geography_mismatch_trips_both_geography_signals() -> None:
    store = _store()
    size = fixed_scenario_size("vpn_geography_mismatch")
    assert size is not None
    events = generate_events("vpn_geography_mismatch", seed=7, start=START, event_count=size)
    codes = _all_reason_codes(store, events, compute_geography_features)
    assert "geography_country_mismatch" in codes
    assert "geography_vpn_or_proxy" in codes


def test_retry_storm_trips_both_retry_signals() -> None:
    store = _store()
    size = fixed_scenario_size("retry_storm")
    assert size is not None
    events = generate_events("retry_storm", seed=7, start=START, event_count=size)
    codes = _all_reason_codes(store, events, compute_retry_features)
    assert "retry_group_size_high" in codes
    assert "retry_account_failure_count_high" in codes


def test_unusual_amount_trips_amount_unusual_deviation_high() -> None:
    store = _store()
    size = fixed_scenario_size("unusual_amount")
    assert size is not None
    events = generate_events("unusual_amount", seed=7, start=START, event_count=size)
    codes = _all_reason_codes(store, events, compute_amount_features)
    assert "amount_unusual_deviation_high" in codes


def test_merchant_deviation_trips_merchant_failure_rate_high() -> None:
    store = _store()
    size = fixed_scenario_size("merchant_deviation")
    assert size is not None
    events = generate_events("merchant_deviation", seed=7, start=START, event_count=size)
    codes = _all_reason_codes(store, events, compute_merchant_features)
    assert "merchant_failure_rate_high" in codes


def test_duplicate_scenario_has_exactly_one_repeated_event_id() -> None:
    size = fixed_scenario_size("duplicate")
    assert size is not None
    events = generate_events("duplicate", seed=7, start=START, event_count=size)
    event_ids = [event.event_id for event in events]
    assert len(event_ids) != len(set(event_ids))
    assert len(set(event_ids)) == len(event_ids) - 1


def test_duplicate_scenario_replay_is_flagged_duplicate_by_the_store() -> None:
    store = _store()
    size = fixed_scenario_size("duplicate")
    assert size is not None
    events = generate_events("duplicate", seed=7, start=START, event_count=size)

    results = [store.record(event) for event in events]

    assert [result.duplicate_status for result in results[:-1]] == ["new"] * (len(events) - 1)
    assert results[-1].duplicate_status == "duplicate"
    assert results[-1].stored_event == events[0]


def test_out_of_order_scenario_is_not_time_sorted_in_generation_order() -> None:
    size = fixed_scenario_size("out_of_order")
    assert size is not None
    events = generate_events("out_of_order", seed=7, start=START, event_count=size)
    times = [event.event_time for event in events]
    assert times != sorted(times)


def test_out_of_order_scenario_replay_produces_a_late_classification() -> None:
    store = _store()
    size = fixed_scenario_size("out_of_order")
    assert size is not None
    events = generate_events("out_of_order", seed=7, start=START, event_count=size)

    results = [store.record(event) for event in events]

    assert "late" in [result.ordering_status for result in results]
