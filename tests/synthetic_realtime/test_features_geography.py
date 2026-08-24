"""Tests for the geography/IP/VPN feature family."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.features.geography import (
    COUNTRY_MISMATCH_CONTRIBUTION,
    IP_FAN_OUT_ACCOUNT_THRESHOLD,
    IP_FAN_OUT_CONTRIBUTION,
    VPN_OR_PROXY_CONTRIBUTION,
    compute_geography_features,
)
from src.synthetic_realtime.store import SyntheticEventStore

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    event_time: datetime,
    account_id: str = "syn_acct_001",
    ip_id: str = "syn_ip_001",
    account_country: str = "IN",
    event_country: str = "IN",
    vpn_or_proxy: bool = False,
) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=event_id,
        event_time=event_time,
        account_id=account_id,
        device_id="syn_dev_001",
        payment_method_id="syn_pm_001",
        merchant_id="syn_mer_001",
        address_id="syn_addr_001",
        ip_id=ip_id,
        amount=100.0,
        currency="INR",
        outcome="success",
        account_country=account_country,
        event_country=event_country,
        event_region="APAC",
        billing_shipping_match=True,
        vpn_or_proxy=vpn_or_proxy,
        retry_group_id=None,
    )


def _store(retention: timedelta = timedelta(hours=48)) -> SyntheticEventStore:
    return SyntheticEventStore(clock=FixedClock(current=AS_OF), retention=retention)


def _reason_codes(signals: Sequence[TriggeredSignal]) -> set[str]:
    return {signal.reason_code for signal in signals}


def test_matching_countries_has_no_mismatch_signal() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF, account_country="IN", event_country="IN")
    store.record(event)

    features = compute_geography_features(store=store, event=event)

    assert features.window_features["geography_country_mismatch"] == 0.0
    assert "geography_country_mismatch" not in _reason_codes(features.triggered_signals)


def test_mismatched_countries_triggers_signal() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF, account_country="IN", event_country="US")
    store.record(event)

    features = compute_geography_features(store=store, event=event)

    assert features.window_features["geography_country_mismatch"] == 1.0
    assert "geography_country_mismatch" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "geography_country_mismatch"
    )
    assert signal.contribution == COUNTRY_MISMATCH_CONTRIBUTION


def test_vpn_or_proxy_false_has_no_signal() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF, vpn_or_proxy=False)
    store.record(event)

    features = compute_geography_features(store=store, event=event)

    assert features.window_features["geography_vpn_or_proxy"] == 0.0
    assert "geography_vpn_or_proxy" not in _reason_codes(features.triggered_signals)


def test_vpn_or_proxy_true_triggers_signal() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF, vpn_or_proxy=True)
    store.record(event)

    features = compute_geography_features(store=store, event=event)

    assert features.window_features["geography_vpn_or_proxy"] == 1.0
    assert "geography_vpn_or_proxy" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "geography_vpn_or_proxy"
    )
    assert signal.contribution == VPN_OR_PROXY_CONTRIBUTION


def test_ip_fan_out_not_triggered_exactly_at_threshold() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_b",
            event_time=AS_OF - timedelta(minutes=30),
            account_id="syn_acct_b",
            ip_id="syn_ip_shared",
        )
    )
    store.record(
        _event(
            event_id="evt_c",
            event_time=AS_OF - timedelta(minutes=20),
            account_id="syn_acct_c",
            ip_id="syn_ip_shared",
        )
    )
    current = _event(
        event_id="evt_a", event_time=AS_OF, account_id="syn_acct_a", ip_id="syn_ip_shared"
    )
    store.record(current)

    features = compute_geography_features(store=store, event=current)

    assert features.window_features["geography_ip_fan_out_distinct_accounts_24h"] == float(
        IP_FAN_OUT_ACCOUNT_THRESHOLD
    )
    assert "geography_ip_fan_out_high" not in _reason_codes(features.triggered_signals)


def test_ip_fan_out_triggered_above_threshold() -> None:
    store = _store()
    for index, account_id in enumerate(["syn_acct_b", "syn_acct_c", "syn_acct_d"]):
        store.record(
            _event(
                event_id=f"evt_prior_{index}",
                event_time=AS_OF - timedelta(minutes=30 - index),
                account_id=account_id,
                ip_id="syn_ip_shared",
            )
        )
    current = _event(
        event_id="evt_a", event_time=AS_OF, account_id="syn_acct_a", ip_id="syn_ip_shared"
    )
    store.record(current)

    features = compute_geography_features(store=store, event=current)

    assert features.window_features["geography_ip_fan_out_distinct_accounts_24h"] == 4.0
    assert "geography_ip_fan_out_high" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "geography_ip_fan_out_high"
    )
    assert signal.contribution == IP_FAN_OUT_CONTRIBUTION


def test_ip_fan_out_ignores_events_outside_24h_lookback() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_old",
            event_time=AS_OF - timedelta(hours=25),
            account_id="syn_acct_old",
            ip_id="syn_ip_shared",
        )
    )
    current = _event(
        event_id="evt_a", event_time=AS_OF, account_id="syn_acct_a", ip_id="syn_ip_shared"
    )
    store.record(current)

    features = compute_geography_features(store=store, event=current)

    assert features.window_features["geography_ip_fan_out_distinct_accounts_24h"] == 1.0
    assert "geography_ip_fan_out_high" not in _reason_codes(features.triggered_signals)


def test_window_features_keys_are_exactly_the_expected_set() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF)
    store.record(event)

    features = compute_geography_features(store=store, event=event)

    assert set(features.window_features.keys()) == {
        "geography_country_mismatch",
        "geography_vpn_or_proxy",
        "geography_ip_fan_out_distinct_accounts_24h",
    }
