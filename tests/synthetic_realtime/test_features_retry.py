"""Tests for the retry/failure behavior feature family."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import Outcome, SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.features.retry import (
    ACCOUNT_FAILURE_COUNT_CONTRIBUTION,
    ACCOUNT_FAILURE_COUNT_THRESHOLD,
    RETRY_GROUP_SIZE_CONTRIBUTION,
    RETRY_GROUP_SIZE_THRESHOLD,
    compute_retry_features,
)
from src.synthetic_realtime.store import SyntheticEventStore

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    event_time: datetime,
    account_id: str = "syn_acct_001",
    outcome: Outcome = "success",
    retry_group_id: str | None = None,
) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        account_id=account_id,
        device_id="syn_dev_001",
        payment_method_id="syn_pm_001",
        merchant_id="syn_mer_001",
        address_id="syn_addr_001",
        ip_id="syn_ip_001",
        amount=100.0,
        currency="INR",
        outcome=outcome,
        account_country="IN",
        event_country="IN",
        event_region="APAC",
        billing_shipping_match=True,
        vpn_or_proxy=False,
        retry_group_id=retry_group_id,
    )


def _store(retention: timedelta = timedelta(hours=48)) -> SyntheticEventStore:
    return SyntheticEventStore(clock=FixedClock(current=AS_OF), retention=retention)


def _reason_codes(signals: Sequence[TriggeredSignal]) -> set[str]:
    return {signal.reason_code for signal in signals}


def test_no_retry_group_and_no_failures_triggers_nothing() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_retry_features(store=store, event=event)

    assert features.window_features["retry_has_group"] == 0.0
    assert features.window_features["retry_group_size_1h"] == 0.0
    assert features.window_features["retry_account_failure_count_1h"] == 0.0
    assert features.triggered_signals == []


def test_retry_group_size_not_triggered_exactly_at_threshold() -> None:
    store = _store()
    current = None
    for index in range(RETRY_GROUP_SIZE_THRESHOLD):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=RETRY_GROUP_SIZE_THRESHOLD - 1 - index),
            retry_group_id="syn_retry_001",
        )
        store.record(current)
    assert current is not None

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_has_group"] == 1.0
    assert features.window_features["retry_group_size_1h"] == float(RETRY_GROUP_SIZE_THRESHOLD)
    assert "retry_group_size_high" not in _reason_codes(features.triggered_signals)


def test_retry_group_size_triggered_above_threshold() -> None:
    store = _store()
    total = RETRY_GROUP_SIZE_THRESHOLD + 1
    current = None
    for index in range(total):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=total - 1 - index),
            retry_group_id="syn_retry_001",
        )
        store.record(current)
    assert current is not None

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_group_size_1h"] == float(total)
    assert "retry_group_size_high" in _reason_codes(features.triggered_signals)
    signal = next(s for s in features.triggered_signals if s.reason_code == "retry_group_size_high")
    assert signal.contribution == RETRY_GROUP_SIZE_CONTRIBUTION


def test_retry_group_size_ignores_different_group_ids() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_other_group",
            event_time=AS_OF - timedelta(minutes=1),
            retry_group_id="syn_retry_other",
        )
    )
    current = _event(event_id="evt_current", event_time=AS_OF, retry_group_id="syn_retry_001")
    store.record(current)

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_group_size_1h"] == 1.0


def test_retry_group_ignores_events_outside_1h_lookback() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_old",
            event_time=AS_OF - timedelta(hours=2),
            retry_group_id="syn_retry_001",
        )
    )
    current = _event(event_id="evt_current", event_time=AS_OF, retry_group_id="syn_retry_001")
    store.record(current)

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_group_size_1h"] == 1.0


def test_account_failure_count_not_triggered_exactly_at_threshold() -> None:
    store = _store()
    current = None
    for index in range(ACCOUNT_FAILURE_COUNT_THRESHOLD):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=ACCOUNT_FAILURE_COUNT_THRESHOLD - 1 - index),
            outcome="declined",
        )
        store.record(current)
    assert current is not None

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_account_failure_count_1h"] == float(
        ACCOUNT_FAILURE_COUNT_THRESHOLD
    )
    assert "retry_account_failure_count_high" not in _reason_codes(features.triggered_signals)


def test_account_failure_count_triggered_above_threshold() -> None:
    store = _store()
    total = ACCOUNT_FAILURE_COUNT_THRESHOLD + 1
    current = None
    for index in range(total):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=total - 1 - index),
            outcome="failed",
        )
        store.record(current)
    assert current is not None

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_account_failure_count_1h"] == float(total)
    assert "retry_account_failure_count_high" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "retry_account_failure_count_high"
    )
    assert signal.contribution == ACCOUNT_FAILURE_COUNT_CONTRIBUTION


def test_success_outcomes_do_not_count_as_failures() -> None:
    store = _store()
    for index in range(5):
        store.record(
            _event(
                event_id=f"evt_{index}",
                event_time=AS_OF - timedelta(seconds=5 - index),
                outcome="success",
            )
        )
    current = _event(event_id="evt_current", event_time=AS_OF, outcome="success")
    store.record(current)

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_account_failure_count_1h"] == 0.0


def test_failure_count_ignores_other_accounts() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_other",
            event_time=AS_OF - timedelta(minutes=1),
            account_id="syn_acct_other",
            outcome="failed",
        )
    )
    current = _event(event_id="evt_current", event_time=AS_OF, outcome="success")
    store.record(current)

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_account_failure_count_1h"] == 0.0


def test_failure_count_ignores_events_outside_1h_lookback() -> None:
    store = _store()
    store.record(
        _event(event_id="evt_old", event_time=AS_OF - timedelta(hours=2), outcome="failed")
    )
    current = _event(event_id="evt_current", event_time=AS_OF, outcome="success")
    store.record(current)

    features = compute_retry_features(store=store, event=current)

    assert features.window_features["retry_account_failure_count_1h"] == 0.0


def test_window_features_keys_are_exactly_the_expected_set() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_retry_features(store=store, event=event)

    assert set(features.window_features.keys()) == {
        "retry_has_group",
        "retry_group_size_1h",
        "retry_account_failure_count_1h",
    }
