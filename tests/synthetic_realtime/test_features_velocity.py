"""Tests for the transaction velocity feature family."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.features.velocity import (
    VELOCITY_COUNT_THRESHOLDS,
    VELOCITY_SIGNAL_CONTRIBUTION,
    compute_velocity_features,
)
from src.synthetic_realtime.store import SyntheticEventStore

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
DEFAULT_IDS = {
    "account_id": "syn_acct_001",
    "device_id": "syn_dev_001",
    "payment_method_id": "syn_pm_001",
    "merchant_id": "syn_mer_001",
}


def _event(*, event_id: str, event_time: datetime, **overrides: str) -> SyntheticEvent:
    ids = {**DEFAULT_IDS, **overrides}
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        address_id="syn_addr_001",
        ip_id="syn_ip_001",
        amount=100.0,
        currency="INR",
        outcome="success",
        account_country="IN",
        event_country="IN",
        event_region="APAC",
        billing_shipping_match=True,
        vpn_or_proxy=False,
        retry_group_id=None,
        **ids,
    )


def _store(retention: timedelta = timedelta(hours=48)) -> SyntheticEventStore:
    return SyntheticEventStore(clock=FixedClock(current=AS_OF), retention=retention)


def _reason_codes(signals: Sequence[TriggeredSignal]) -> set[str]:
    return {signal.reason_code for signal in signals}


def test_single_event_has_count_one_in_every_window_and_dimension() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_velocity_features(store=store, event=event)

    for entity in ("account", "device", "payment_method", "merchant"):
        for window in ("1m", "1h", "24h"):
            assert features.window_features[f"velocity_{entity}_{window}_count"] == 1.0
    assert features.triggered_signals == []


def test_window_features_have_exactly_twelve_keys() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_velocity_features(store=store, event=event)

    assert len(features.window_features) == 12


def test_account_velocity_not_triggered_exactly_at_threshold() -> None:
    store = _store()
    threshold = VELOCITY_COUNT_THRESHOLDS["1m"]
    current = None
    for index in range(threshold):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=threshold - 1 - index),
            device_id=f"syn_dev_{index:03d}",
            payment_method_id=f"syn_pm_{index:03d}",
            merchant_id=f"syn_mer_{index:03d}",
        )
        store.record(current)
    assert current is not None

    features = compute_velocity_features(store=store, event=current)

    assert features.window_features["velocity_account_1m_count"] == float(threshold)
    assert "velocity_account_1m_count_high" not in _reason_codes(features.triggered_signals)


def test_account_velocity_triggered_above_threshold() -> None:
    store = _store()
    threshold = VELOCITY_COUNT_THRESHOLDS["1m"]
    total = threshold + 1
    current = None
    for index in range(total):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=total - 1 - index),
            device_id=f"syn_dev_{index:03d}",
            payment_method_id=f"syn_pm_{index:03d}",
            merchant_id=f"syn_mer_{index:03d}",
        )
        store.record(current)
    assert current is not None

    features = compute_velocity_features(store=store, event=current)

    assert features.window_features["velocity_account_1m_count"] == float(threshold + 1)
    assert "velocity_account_1m_count_high" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "velocity_account_1m_count_high"
    )
    assert signal.contribution == VELOCITY_SIGNAL_CONTRIBUTION


def test_triggering_one_dimension_does_not_trigger_unrelated_dimensions() -> None:
    store = _store()
    threshold = VELOCITY_COUNT_THRESHOLDS["1m"]
    total = threshold + 1
    current = None
    for index in range(total):
        current = _event(
            event_id=f"evt_{index}",
            event_time=AS_OF - timedelta(seconds=total - 1 - index),
            device_id=f"syn_dev_{index:03d}",
            payment_method_id=f"syn_pm_{index:03d}",
            merchant_id=f"syn_mer_{index:03d}",
        )
        store.record(current)
    assert current is not None

    features = compute_velocity_features(store=store, event=current)
    reason_codes = _reason_codes(features.triggered_signals)

    assert "velocity_account_1m_count_high" in reason_codes
    assert "velocity_device_1m_count_high" not in reason_codes
    assert "velocity_payment_method_1m_count_high" not in reason_codes
    assert "velocity_merchant_1m_count_high" not in reason_codes


def test_velocity_ignores_events_outside_24h_lookback() -> None:
    store = _store()
    store.record(_event(event_id="evt_old", event_time=AS_OF - timedelta(hours=25)))
    current = _event(event_id="evt_current", event_time=AS_OF)
    store.record(current)

    features = compute_velocity_features(store=store, event=current)

    assert features.window_features["velocity_account_24h_count"] == 1.0


def test_1h_window_counts_events_outside_1m_but_inside_1h() -> None:
    store = _store()
    store.record(_event(event_id="evt_older", event_time=AS_OF - timedelta(minutes=30)))
    current = _event(event_id="evt_current", event_time=AS_OF)
    store.record(current)

    features = compute_velocity_features(store=store, event=current)

    assert features.window_features["velocity_account_1m_count"] == 1.0
    assert features.window_features["velocity_account_1h_count"] == 2.0
    assert features.window_features["velocity_account_24h_count"] == 2.0
