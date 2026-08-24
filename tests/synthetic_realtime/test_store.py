"""Tests for the bounded synthetic event store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import SyntheticEvent
from src.synthetic_realtime.store import (
    DEFAULT_MAX_EVENTS,
    DEFAULT_RETENTION,
    DuplicateEventConflictError,
    SyntheticEventStore,
)

BASE_TIME = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(*, event_id: str, event_time: datetime, amount: float = 100.0) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        account_id="syn_acct_001",
        device_id="syn_dev_001",
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


def _store(*, clock: FixedClock | None = None, **kwargs: object) -> SyntheticEventStore:
    return SyntheticEventStore(clock=clock or FixedClock(current=BASE_TIME), **kwargs)  # type: ignore[arg-type]


# --- construction validation ------------------------------------------------------


def test_rejects_non_positive_retention() -> None:
    with pytest.raises(ValueError, match="retention"):
        SyntheticEventStore(clock=FixedClock(current=BASE_TIME), retention=timedelta(0))


def test_rejects_non_positive_max_events() -> None:
    with pytest.raises(ValueError, match="max_events"):
        SyntheticEventStore(clock=FixedClock(current=BASE_TIME), max_events=0)


def test_defaults_are_exposed_as_properties() -> None:
    store = SyntheticEventStore(clock=FixedClock(current=BASE_TIME))
    assert store.retention == DEFAULT_RETENTION
    assert store.max_events == DEFAULT_MAX_EVENTS


# --- basic recording ---------------------------------------------------------------


def test_first_event_is_new_and_in_order() -> None:
    store = _store()
    result = store.record(_event(event_id="evt_a", event_time=BASE_TIME))
    assert result.duplicate_status == "new"
    assert result.ordering_status == "in_order"
    assert len(store) == 1
    assert store.get("evt_a") is not None


def test_get_returns_none_for_unknown_event_id() -> None:
    store = _store()
    assert store.get("evt_unknown") is None


# --- idempotency -------------------------------------------------------------------


def test_resubmitting_identical_payload_is_a_no_op_duplicate() -> None:
    store = _store()
    event = _event(event_id="evt_a", event_time=BASE_TIME)
    first = store.record(event)
    second = store.record(event)
    assert first.duplicate_status == "new"
    assert second.duplicate_status == "duplicate"
    assert second.ordering_status == first.ordering_status
    assert len(store) == 1


def test_resubmitting_conflicting_payload_raises() -> None:
    store = _store()
    store.record(_event(event_id="evt_a", event_time=BASE_TIME, amount=100.0))
    with pytest.raises(DuplicateEventConflictError):
        store.record(_event(event_id="evt_a", event_time=BASE_TIME, amount=250.0))


def test_duplicate_replays_original_ordering_status_not_a_fresh_evaluation() -> None:
    store = _store()
    late_event = _event(event_id="evt_late", event_time=BASE_TIME)
    store.record(_event(event_id="evt_first", event_time=BASE_TIME + timedelta(minutes=10)))
    late_result = store.record(late_event)
    assert late_result.ordering_status == "late"

    # A later duplicate resubmission must replay "late", not re-derive it
    # against whatever the watermark has become since.
    store.record(_event(event_id="evt_second", event_time=BASE_TIME + timedelta(minutes=20)))
    replay = store.record(late_event)
    assert replay.duplicate_status == "duplicate"
    assert replay.ordering_status == "late"


def test_duplicate_submission_does_not_change_length() -> None:
    store = _store()
    event = _event(event_id="evt_a", event_time=BASE_TIME)
    store.record(event)
    store.record(event)
    store.record(event)
    assert len(store) == 1


# --- late / out-of-order policy -----------------------------------------------------


def test_events_arriving_in_time_order_are_all_in_order() -> None:
    store = _store()
    first = store.record(_event(event_id="evt_1", event_time=BASE_TIME))
    second = store.record(_event(event_id="evt_2", event_time=BASE_TIME + timedelta(minutes=1)))
    assert first.ordering_status == "in_order"
    assert second.ordering_status == "in_order"


def test_event_behind_the_watermark_is_late() -> None:
    store = _store()
    store.record(_event(event_id="evt_1", event_time=BASE_TIME + timedelta(minutes=10)))
    late = store.record(_event(event_id="evt_2", event_time=BASE_TIME))
    assert late.ordering_status == "late"


def test_equal_event_time_to_watermark_is_not_late() -> None:
    store = _store()
    store.record(_event(event_id="evt_1", event_time=BASE_TIME))
    tie = store.record(_event(event_id="evt_2", event_time=BASE_TIME))
    assert tie.ordering_status == "in_order"


# --- events_in_range ----------------------------------------------------------------


def test_events_in_range_returns_time_sorted_matches() -> None:
    store = _store()
    store.record(_event(event_id="evt_1", event_time=BASE_TIME + timedelta(minutes=5)))
    store.record(_event(event_id="evt_2", event_time=BASE_TIME))
    store.record(_event(event_id="evt_3", event_time=BASE_TIME + timedelta(minutes=10)))

    results = store.events_in_range(start=BASE_TIME, end=BASE_TIME + timedelta(minutes=10))
    assert [event.event_id for event in results] == ["evt_2", "evt_1", "evt_3"]


def test_events_in_range_excludes_outside_bounds() -> None:
    store = _store()
    store.record(_event(event_id="evt_1", event_time=BASE_TIME))
    results = store.events_in_range(
        start=BASE_TIME + timedelta(minutes=1), end=BASE_TIME + timedelta(minutes=10)
    )
    assert results == []


def test_events_in_range_rejects_start_after_end() -> None:
    store = _store()
    with pytest.raises(ValueError, match="start must not be after end"):
        store.events_in_range(start=BASE_TIME, end=BASE_TIME - timedelta(minutes=1))


def test_events_in_range_rejects_naive_bounds() -> None:
    store = _store()
    naive = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        store.events_in_range(start=naive, end=BASE_TIME)


# --- bounded memory: capacity eviction ------------------------------------------------


def test_capacity_eviction_removes_oldest_inserted_first() -> None:
    clock = FixedClock(current=BASE_TIME)
    store = SyntheticEventStore(clock=clock, max_events=2)
    store.record(_event(event_id="evt_1", event_time=BASE_TIME))
    store.record(_event(event_id="evt_2", event_time=BASE_TIME + timedelta(minutes=1)))
    store.record(_event(event_id="evt_3", event_time=BASE_TIME + timedelta(minutes=2)))

    assert len(store) == 2
    assert store.get("evt_1") is None
    assert store.get("evt_2") is not None
    assert store.get("evt_3") is not None


# --- bounded memory: time-based retention ---------------------------------------------


def test_retention_expires_old_events_on_next_record() -> None:
    clock = FixedClock(current=BASE_TIME)
    store = SyntheticEventStore(clock=clock, retention=timedelta(hours=1))
    store.record(_event(event_id="evt_old", event_time=BASE_TIME))

    clock.advance(timedelta(hours=2))
    store.record(_event(event_id="evt_new", event_time=clock.now()))

    assert store.get("evt_old") is None
    assert store.get("evt_new") is not None
    assert len(store) == 1


def test_evict_expired_can_be_called_explicitly_and_returns_count() -> None:
    clock = FixedClock(current=BASE_TIME)
    store = SyntheticEventStore(clock=clock, retention=timedelta(hours=1))
    store.record(_event(event_id="evt_old_1", event_time=BASE_TIME))
    store.record(_event(event_id="evt_old_2", event_time=BASE_TIME + timedelta(minutes=1)))

    clock.advance(timedelta(hours=2))
    evicted_count = store.evict_expired()

    assert evicted_count == 2
    assert len(store) == 0


def test_resubmitting_an_evicted_event_id_is_treated_as_new() -> None:
    clock = FixedClock(current=BASE_TIME)
    store = SyntheticEventStore(clock=clock, retention=timedelta(hours=1))
    event = _event(event_id="evt_a", event_time=BASE_TIME)
    store.record(event)

    clock.advance(timedelta(hours=2))
    store.evict_expired()
    assert store.get("evt_a") is None

    result = store.record(event)
    assert result.duplicate_status == "new"


# --- reset -------------------------------------------------------------------------


def test_reset_clears_all_records() -> None:
    store = _store()
    store.record(_event(event_id="evt_1", event_time=BASE_TIME))
    store.record(_event(event_id="evt_2", event_time=BASE_TIME + timedelta(minutes=1)))
    store.reset()
    assert len(store) == 0
    assert store.get("evt_1") is None
    assert store.get("evt_2") is None


def test_reset_clears_the_watermark_so_ordering_restarts() -> None:
    store = _store()
    store.record(_event(event_id="evt_1", event_time=BASE_TIME + timedelta(minutes=10)))
    store.reset()

    # Without the reset, this would be classified "late" relative to the
    # watermark left over from evt_1.
    result = store.record(_event(event_id="evt_2", event_time=BASE_TIME))
    assert result.ordering_status == "in_order"
