"""Unusual amount deviation feature family.

One illustrative, deterministic signal: how far this transaction's amount
deviates from this account's own mean amount over the prior 24h (excluding
the current event itself). With no prior same-account history in the
lookback window there is no baseline to compare against, so no signal
fires - this is documented, not an error.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_amount_features`` - the
computation reads ``event`` back out of the store's own history so that
"including this event" is naturally satisfied by a single data source.

The deviation ratio reported in ``window_features`` is capped at
``AMOUNT_DEVIATION_RATIO_CAP`` so it always stays a bounded aggregate
feature; the *trigger* decision below uses the uncapped ratio so an
extreme deviation is never silently under-reported as "borderline".
Thresholds below are illustrative synthetic constants for demonstrating
plumbing, not tuned fraud thresholds, and this module never produces a
fraud probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.store import SyntheticEventStore
from src.synthetic_realtime.windows import WINDOW_DURATIONS, mean_amount

AMOUNT_LOOKBACK_HOURS = 24
# Illustrative synthetic multiplier, not a tuned fraud value.
AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER = 3.0
AMOUNT_DEVIATION_RATIO_CAP = 100.0

AMOUNT_DEVIATION_CONTRIBUTION = 0.3


@dataclass(frozen=True)
class AmountFeatures:
    """Amount-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_amount_features(*, store: SyntheticEventStore, event: SyntheticEvent) -> AmountFeatures:
    """Compute unusual-amount-deviation signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["24h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)
    prior_account_events = [
        candidate
        for candidate in candidates
        if candidate.account_id == event.account_id and candidate.event_id != event.event_id
    ]

    has_baseline = len(prior_account_events) > 0
    baseline_mean = mean_amount(prior_account_events) if has_baseline else 0.0
    raw_ratio = event.amount / baseline_mean if has_baseline else 0.0
    deviation_ratio = min(raw_ratio, AMOUNT_DEVIATION_RATIO_CAP)

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {
        "amount_has_baseline": 1.0 if has_baseline else 0.0,
        "amount_baseline_mean_24h": baseline_mean,
        "amount_deviation_ratio": deviation_ratio,
    }

    if has_baseline and raw_ratio > AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="amount_unusual_deviation_high",
                description=(
                    f"This transaction's amount is {raw_ratio:.1f}x this account's synthetic "
                    f"{AMOUNT_LOOKBACK_HOURS}h baseline, above the illustrative multiplier of "
                    f"{AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER:.1f}x."
                ),
                contribution=AMOUNT_DEVIATION_CONTRIBUTION,
            )
        )

    return AmountFeatures(triggered_signals=triggered_signals, window_features=window_features)
