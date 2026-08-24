"""Tests for the device newness/fan-out feature family."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.features.device import (
    DEVICE_FAN_OUT_ACCOUNT_THRESHOLD,
    DEVICE_FAN_OUT_CONTRIBUTION,
    NEW_DEVICE_CONTRIBUTION,
    compute_device_features,
)
from src.synthetic_realtime.store import SyntheticEventStore

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    event_time: datetime,
    account_id: str = "syn_acct_001",
    device_id: str = "syn_dev_001",
) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        account_id=account_id,
        device_id=device_id,
        payment_method_id="syn_pm_001",
        merchant_id="syn_mer_001",
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
    )


def _store(retention: timedelta = timedelta(hours=48)) -> SyntheticEventStore:
    return SyntheticEventStore(clock=FixedClock(current=AS_OF), retention=retention)


def _reason_codes(signals: Sequence[TriggeredSignal]) -> set[str]:
    return {signal.reason_code for signal in signals}


def test_first_ever_device_account_pairing_is_new() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_device_features(store=store, event=event)

    assert features.window_features["device_new_to_account"] == 1.0
    assert "device_new_to_account" in _reason_codes(features.triggered_signals)


def test_repeated_device_account_pairing_is_not_new() -> None:
    store = _store()
    first = _event(event_id="evt_1", event_time=AS_OF - timedelta(minutes=10))
    second = _event(event_id="evt_2", event_time=AS_OF)
    store.record(first)
    store.record(second)

    features = compute_device_features(store=store, event=second)

    assert features.window_features["device_new_to_account"] == 0.0
    assert "device_new_to_account" not in _reason_codes(features.triggered_signals)


def test_new_device_signal_has_expected_contribution() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_device_features(store=store, event=event)
    signal = next(s for s in features.triggered_signals if s.reason_code == "device_new_to_account")
    assert signal.contribution == NEW_DEVICE_CONTRIBUTION


def test_fan_out_not_triggered_exactly_at_threshold() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_b",
            event_time=AS_OF - timedelta(minutes=30),
            account_id="syn_acct_b",
            device_id="syn_dev_shared",
        )
    )
    store.record(
        _event(
            event_id="evt_c",
            event_time=AS_OF - timedelta(minutes=20),
            account_id="syn_acct_c",
            device_id="syn_dev_shared",
        )
    )
    current = _event(
        event_id="evt_a",
        event_time=AS_OF,
        account_id="syn_acct_a",
        device_id="syn_dev_shared",
    )
    store.record(current)

    features = compute_device_features(store=store, event=current)

    assert features.window_features["device_fan_out_distinct_accounts_24h"] == float(
        DEVICE_FAN_OUT_ACCOUNT_THRESHOLD
    )
    assert "device_fan_out_high" not in _reason_codes(features.triggered_signals)


def test_fan_out_triggered_above_threshold() -> None:
    store = _store()
    for index, account_id in enumerate(["syn_acct_b", "syn_acct_c", "syn_acct_d"]):
        store.record(
            _event(
                event_id=f"evt_prior_{index}",
                event_time=AS_OF - timedelta(minutes=30 - index),
                account_id=account_id,
                device_id="syn_dev_shared",
            )
        )
    current = _event(
        event_id="evt_a",
        event_time=AS_OF,
        account_id="syn_acct_a",
        device_id="syn_dev_shared",
    )
    store.record(current)

    features = compute_device_features(store=store, event=current)

    assert features.window_features["device_fan_out_distinct_accounts_24h"] == 4.0
    assert "device_fan_out_high" in _reason_codes(features.triggered_signals)
    signal = next(s for s in features.triggered_signals if s.reason_code == "device_fan_out_high")
    assert signal.contribution == DEVICE_FAN_OUT_CONTRIBUTION


def test_fan_out_ignores_events_outside_24h_lookback() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_old",
            event_time=AS_OF - timedelta(hours=25),
            account_id="syn_acct_old",
            device_id="syn_dev_shared",
        )
    )
    current = _event(
        event_id="evt_a",
        event_time=AS_OF,
        account_id="syn_acct_a",
        device_id="syn_dev_shared",
    )
    store.record(current)

    features = compute_device_features(store=store, event=current)

    assert features.window_features["device_fan_out_distinct_accounts_24h"] == 1.0
    assert "device_fan_out_high" not in _reason_codes(features.triggered_signals)


def test_window_features_keys_are_exactly_the_expected_set() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_device_features(store=store, event=event)

    assert set(features.window_features.keys()) == {
        "device_new_to_account",
        "device_fan_out_distinct_accounts_24h",
    }
