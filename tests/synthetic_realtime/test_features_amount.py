"""Tests for the unusual amount deviation feature family."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from src.synthetic_realtime.clock import FixedClock
from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.features.amount import (
    AMOUNT_DEVIATION_CONTRIBUTION,
    AMOUNT_DEVIATION_RATIO_CAP,
    AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER,
    compute_amount_features,
)
from src.synthetic_realtime.store import SyntheticEventStore

AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    event_time: datetime,
    amount: float,
    account_id: str = "syn_acct_001",
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


def _store(retention: timedelta = timedelta(hours=48)) -> SyntheticEventStore:
    return SyntheticEventStore(clock=FixedClock(current=AS_OF), retention=retention)


def _reason_codes(signals: Sequence[TriggeredSignal]) -> set[str]:
    return {signal.reason_code for signal in signals}


def test_no_prior_history_has_no_baseline_and_no_signal() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF, amount=500.0)
    store.record(event)

    features = compute_amount_features(store=store, event=event)

    assert features.window_features["amount_has_baseline"] == 0.0
    assert features.window_features["amount_baseline_mean_24h"] == 0.0
    assert features.window_features["amount_deviation_ratio"] == 0.0
    assert features.triggered_signals == []


def test_amount_equal_to_baseline_has_ratio_one_and_no_signal() -> None:
    store = _store()
    store.record(
        _event(event_id="evt_prior", event_time=AS_OF - timedelta(minutes=10), amount=100.0)
    )
    current = _event(event_id="evt_current", event_time=AS_OF, amount=100.0)
    store.record(current)

    features = compute_amount_features(store=store, event=current)

    assert features.window_features["amount_has_baseline"] == 1.0
    assert features.window_features["amount_baseline_mean_24h"] == pytest.approx(100.0)
    assert features.window_features["amount_deviation_ratio"] == pytest.approx(1.0)
    assert features.triggered_signals == []


def test_deviation_not_triggered_exactly_at_threshold_multiplier() -> None:
    store = _store()
    store.record(
        _event(event_id="evt_prior", event_time=AS_OF - timedelta(minutes=10), amount=100.0)
    )
    current = _event(
        event_id="evt_current",
        event_time=AS_OF,
        amount=100.0 * AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER,
    )
    store.record(current)

    features = compute_amount_features(store=store, event=current)

    assert features.window_features["amount_deviation_ratio"] == pytest.approx(
        AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER
    )
    assert "amount_unusual_deviation_high" not in _reason_codes(features.triggered_signals)


def test_deviation_triggered_above_threshold_multiplier() -> None:
    store = _store()
    store.record(
        _event(event_id="evt_prior", event_time=AS_OF - timedelta(minutes=10), amount=100.0)
    )
    current = _event(
        event_id="evt_current",
        event_time=AS_OF,
        amount=100.0 * AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER + 1.0,
    )
    store.record(current)

    features = compute_amount_features(store=store, event=current)

    assert "amount_unusual_deviation_high" in _reason_codes(features.triggered_signals)
    signal = next(
        s for s in features.triggered_signals if s.reason_code == "amount_unusual_deviation_high"
    )
    assert signal.contribution == AMOUNT_DEVIATION_CONTRIBUTION


def test_deviation_ratio_is_capped_but_signal_still_triggers_on_extreme_amounts() -> None:
    store = _store()
    store.record(_event(event_id="evt_prior", event_time=AS_OF - timedelta(minutes=10), amount=1.0))
    current = _event(event_id="evt_current", event_time=AS_OF, amount=1_000_000.0)
    store.record(current)

    features = compute_amount_features(store=store, event=current)

    assert features.window_features["amount_deviation_ratio"] == pytest.approx(
        AMOUNT_DEVIATION_RATIO_CAP
    )
    assert "amount_unusual_deviation_high" in _reason_codes(features.triggered_signals)


def test_baseline_ignores_events_from_other_accounts() -> None:
    store = _store()
    store.record(
        _event(
            event_id="evt_other",
            event_time=AS_OF - timedelta(minutes=10),
            amount=10_000.0,
            account_id="syn_acct_other",
        )
    )
    current = _event(event_id="evt_current", event_time=AS_OF, amount=100.0)
    store.record(current)

    features = compute_amount_features(store=store, event=current)

    assert features.window_features["amount_has_baseline"] == 0.0
    assert features.window_features["amount_baseline_mean_24h"] == 0.0


def test_baseline_ignores_events_outside_24h_lookback() -> None:
    store = _store()
    store.record(
        _event(event_id="evt_old", event_time=AS_OF - timedelta(hours=25), amount=10_000.0)
    )
    current = _event(event_id="evt_current", event_time=AS_OF, amount=100.0)
    store.record(current)

    features = compute_amount_features(store=store, event=current)

    assert features.window_features["amount_has_baseline"] == 0.0
    assert features.window_features["amount_baseline_mean_24h"] == 0.0


def test_window_features_keys_are_exactly_the_expected_set() -> None:
    store = _store()
    event = _event(event_id="evt_1", event_time=AS_OF, amount=100.0)
    store.record(event)

    features = compute_amount_features(store=store, event=event)

    assert set(features.window_features.keys()) == {
        "amount_has_baseline",
        "amount_baseline_mean_24h",
        "amount_deviation_ratio",
    }
