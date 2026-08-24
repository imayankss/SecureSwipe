"""Tests for the merchant-specific behavior feature family."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import Outcome, SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.features.merchant import (
    MERCHANT_FAILURE_RATE_CONTRIBUTION,
    MERCHANT_FAILURE_RATE_THRESHOLD,
    MERCHANT_MIN_SAMPLE_SIZE,
    NEW_MERCHANT_CONTRIBUTION,
    compute_merchant_features,
)
from src.synthetic_realtime.store import SyntheticEventStore

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    event_time: datetime,
    account_id: str = "syn_acct_001",
    merchant_id: str = "syn_mer_001",
    outcome: Outcome = "success",
) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        account_id=account_id,
        device_id="syn_dev_001",
        payment_method_id="syn_pm_001",
        merchant_id=merchant_id,
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
        retry_group_id=None,
    )


def _store(retention: timedelta = timedelta(hours=48)) -> SyntheticEventStore:
    return SyntheticEventStore(clock=FixedClock(current=AS_OF), retention=retention)


def _reason_codes(signals: Sequence[TriggeredSignal]) -> set[str]:
    return {signal.reason_code for signal in signals}


def test_first_ever_merchant_account_pairing_is_new() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_merchant_features(store=store, event=event)

    assert features.window_features["merchant_new_to_account"] == 1.0
    assert "merchant_new_to_account" in _reason_codes(features.triggered_signals)


def test_repeated_merchant_account_pairing_is_not_new() -> None:
    store = _store()
    first = _event(event_id="evt_1", event_time=AS_OF - timedelta(minutes=10))
    second = _event(event_id="evt_2", event_time=AS_OF)
    store.record(first)
    store.record(second)

    features = compute_merchant_features(store=store, event=second)

    assert features.window_features["merchant_new_to_account"] == 0.0
    assert "merchant_new_to_account" not in _reason_codes(features.triggered_signals)


def test_new_merchant_signal_has_expected_contribution() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_merchant_features(store=store, event=event)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "merchant_new_to_account"
    )
    assert signal.contribution == NEW_MERCHANT_CONTRIBUTION


def test_failure_rate_below_sample_size_reports_rate_but_does_not_trigger() -> None:
    store = _store()
    assert MERCHANT_MIN_SAMPLE_SIZE > 2
    store.record(
        _event(event_id="evt_1", event_time=AS_OF - timedelta(minutes=1), outcome="failed")
    )
    current = _event(event_id="evt_2", event_time=AS_OF, outcome="failed")
    store.record(current)

    features = compute_merchant_features(store=store, event=current)

    assert features.window_features["merchant_transaction_count_24h"] == 2.0
    assert features.window_features["merchant_failure_rate_24h"] == pytest.approx(1.0)
    assert "merchant_failure_rate_high" not in _reason_codes(features.triggered_signals)


def test_failure_rate_not_triggered_exactly_at_threshold() -> None:
    store = _store()
    total = MERCHANT_MIN_SAMPLE_SIZE
    failures = round(total * MERCHANT_FAILURE_RATE_THRESHOLD)
    current = None
    for index in range(total):
        outcome: Outcome = "failed" if index < failures else "success"
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=total - 1 - index),
            outcome=outcome,
        )
        store.record(current)
    assert current is not None

    features = compute_merchant_features(store=store, event=current)

    assert features.window_features["merchant_failure_rate_24h"] == pytest.approx(failures / total)
    assert "merchant_failure_rate_high" not in _reason_codes(features.triggered_signals)


def test_failure_rate_triggered_above_threshold_with_sufficient_sample() -> None:
    store = _store()
    total = MERCHANT_MIN_SAMPLE_SIZE
    current = None
    for index in range(total):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=total - 1 - index),
            outcome="failed",
        )
        store.record(current)
    assert current is not None

    features = compute_merchant_features(store=store, event=current)

    assert features.window_features["merchant_failure_rate_24h"] == pytest.approx(1.0)
    assert "merchant_failure_rate_high" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "merchant_failure_rate_high"
    )
    assert signal.contribution == MERCHANT_FAILURE_RATE_CONTRIBUTION


def test_failure_rate_ignores_other_merchants() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_other",
            event_time=AS_OF - timedelta(minutes=1),
            merchant_id="syn_mer_other",
            outcome="failed",
        )
    )
    current = _event(event_id="evt_current", event_time=AS_OF, outcome="success")
    store.record(current)

    features = compute_merchant_features(store=store, event=current)

    assert features.window_features["merchant_transaction_count_24h"] == 1.0
    assert features.window_features["merchant_failure_rate_24h"] == 0.0


def test_ignores_events_outside_24h_lookback() -> None:
    store = _store()
    store.record(
        _event(event_id="evt_old", event_time=AS_OF - timedelta(hours=25), outcome="failed")
    )
    current = _event(event_id="evt_current", event_time=AS_OF, outcome="success")
    store.record(current)

    features = compute_merchant_features(store=store, event=current)

    assert features.window_features["merchant_transaction_count_24h"] == 1.0
    assert features.window_features["merchant_failure_rate_24h"] == 0.0


def test_window_features_keys_are_exactly_the_expected_set() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_merchant_features(store=store, event=event)

    assert set(features.window_features.keys()) == {
        "merchant_new_to_account",
        "merchant_transaction_count_24h",
        "merchant_failure_rate_24h",
    }
