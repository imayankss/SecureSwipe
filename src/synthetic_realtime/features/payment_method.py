"""Payment-method history feature family.

Two illustrative, deterministic signals derived from the bounded event
history in a ``SyntheticEventStore``:

- **payment-method newness**: whether this payment_method_id has been paired
  with this account_id before, anywhere in the retained history prior to
  now.
- **payment-method fan-out**: how many distinct synthetic accounts have used
  this payment_method_id within the last 24h.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_payment_method_features``
- the computation reads ``event`` back out of the store's own history so
that "including this event" is naturally satisfied by a single data
source.

Thresholds below are illustrative synthetic constants for demonstrating
plumbing, not tuned fraud thresholds, and this module never produces a
fraud probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.store import SyntheticEventStore
from src.synthetic_realtime.windows import WINDOW_DURATIONS, distinct_count

PAYMENT_METHOD_FAN_OUT_LOOKBACK_HOURS = 24
# Illustrative synthetic threshold, not a tuned fraud value.
PAYMENT_METHOD_FAN_OUT_ACCOUNT_THRESHOLD = 3

NEW_PAYMENT_METHOD_CONTRIBUTION = 0.2
PAYMENT_METHOD_FAN_OUT_CONTRIBUTION = 0.3


@dataclass(frozen=True)
class PaymentMethodFeatures:
    """Payment-method-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_payment_method_features(
    *, store: SyntheticEventStore, event: SyntheticEvent
) -> PaymentMethodFeatures:
    """Compute payment-method newness/fan-out signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["24h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)
    payment_method_events = [
        candidate
        for candidate in candidates
        if candidate.payment_method_id == event.payment_method_id
    ]

    prior_events_for_account = [
        candidate
        for candidate in payment_method_events
        if candidate.account_id == event.account_id and candidate.event_id != event.event_id
    ]
    is_new_payment_method_for_account = len(prior_events_for_account) == 0

    distinct_accounts = distinct_count(
        payment_method_events, key=lambda candidate: candidate.account_id
    )

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {
        "payment_method_new_to_account": 1.0 if is_new_payment_method_for_account else 0.0,
        "payment_method_fan_out_distinct_accounts_24h": float(distinct_accounts),
    }

    if is_new_payment_method_for_account:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="payment_method_new_to_account",
                description=(
                    "This payment method has not been paired with this account before, in "
                    "the synthetic history available."
                ),
                contribution=NEW_PAYMENT_METHOD_CONTRIBUTION,
            )
        )

    if distinct_accounts > PAYMENT_METHOD_FAN_OUT_ACCOUNT_THRESHOLD:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="payment_method_fan_out_high",
                description=(
                    f"This payment method has been used by {distinct_accounts} distinct "
                    f"synthetic accounts in the last {PAYMENT_METHOD_FAN_OUT_LOOKBACK_HOURS}h, "
                    f"above the illustrative baseline of "
                    f"{PAYMENT_METHOD_FAN_OUT_ACCOUNT_THRESHOLD}."
                ),
                contribution=PAYMENT_METHOD_FAN_OUT_CONTRIBUTION,
            )
        )

    return PaymentMethodFeatures(
        triggered_signals=triggered_signals, window_features=window_features
    )
