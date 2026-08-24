"""Merchant-specific behavior feature family.

Two illustrative, deterministic signals over the last 24h:

- **merchant newness**: whether this merchant_id has been paired with this
  account_id before, anywhere in the retained history prior to now.
- **merchant failure rate**: the proportion of this merchant's transactions
  that were ``declined``/``failed``, computed only once the merchant has at
  least ``MERCHANT_MIN_SAMPLE_SIZE`` transactions in the window - below that,
  the rate is still reported honestly in ``window_features`` but never
  triggers a signal, since a rate from a tiny sample is noise, not a
  pattern.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_merchant_features`` - the
computation reads ``event`` back out of the store's own history so that
"including this event" is naturally satisfied by a single data source.

Thresholds below are illustrative synthetic constants for demonstrating
plumbing, not tuned fraud thresholds, and this module never produces a
fraud probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.store import SyntheticEventStore
from src.synthetic_realtime.windows import WINDOW_DURATIONS

MERCHANT_LOOKBACK_HOURS = 24
FAILED_OUTCOMES = frozenset({"declined", "failed"})

# Illustrative synthetic thresholds, not tuned fraud values.
MERCHANT_MIN_SAMPLE_SIZE = 5
MERCHANT_FAILURE_RATE_THRESHOLD = 0.5

NEW_MERCHANT_CONTRIBUTION = 0.2
MERCHANT_FAILURE_RATE_CONTRIBUTION = 0.3


@dataclass(frozen=True)
class MerchantFeatures:
    """Merchant-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_merchant_features(
    *, store: SyntheticEventStore, event: SyntheticEvent
) -> MerchantFeatures:
    """Compute merchant newness/failure-rate signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["24h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)
    merchant_events = [
        candidate for candidate in candidates if candidate.merchant_id == event.merchant_id
    ]

    prior_events_for_account = [
        candidate
        for candidate in merchant_events
        if candidate.account_id == event.account_id and candidate.event_id != event.event_id
    ]
    is_new_merchant_for_account = len(prior_events_for_account) == 0

    total_count = len(merchant_events)
    failure_count = len(
        [candidate for candidate in merchant_events if candidate.outcome in FAILED_OUTCOMES]
    )
    has_sufficient_sample = total_count >= MERCHANT_MIN_SAMPLE_SIZE
    failure_rate = (failure_count / total_count) if total_count > 0 else 0.0

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {
        "merchant_new_to_account": 1.0 if is_new_merchant_for_account else 0.0,
        "merchant_transaction_count_24h": float(total_count),
        "merchant_failure_rate_24h": failure_rate,
    }

    if is_new_merchant_for_account:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="merchant_new_to_account",
                description=(
                    "This merchant has not been paired with this account before, in the "
                    "synthetic history available."
                ),
                contribution=NEW_MERCHANT_CONTRIBUTION,
            )
        )

    if has_sufficient_sample and failure_rate > MERCHANT_FAILURE_RATE_THRESHOLD:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="merchant_failure_rate_high",
                description=(
                    f"This merchant had a {failure_rate:.0%} synthetic decline/failure rate "
                    f"over {total_count} transactions in the last {MERCHANT_LOOKBACK_HOURS}h, "
                    f"above the illustrative baseline of {MERCHANT_FAILURE_RATE_THRESHOLD:.0%}."
                ),
                contribution=MERCHANT_FAILURE_RATE_CONTRIBUTION,
            )
        )

    return MerchantFeatures(triggered_signals=triggered_signals, window_features=window_features)
