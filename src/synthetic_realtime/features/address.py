"""Address pattern feature family.

Three illustrative, deterministic signals:

- **address newness**: whether this address_id has been paired with this
  account_id before, anywhere in the retained history prior to now.
- **address fan-out**: how many distinct synthetic accounts have used this
  address_id within the last 24h.
- **billing/shipping mismatch**: surfaces the event's own
  ``billing_shipping_match`` flag as a signal when it is False.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_address_features`` - the
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
from src.synthetic_realtime.windows import WINDOW_DURATIONS, distinct_count

ADDRESS_FAN_OUT_LOOKBACK_HOURS = 24
ADDRESS_FAN_OUT_ACCOUNT_THRESHOLD = 3  # illustrative synthetic threshold, not a tuned fraud value

NEW_ADDRESS_CONTRIBUTION = 0.2
ADDRESS_FAN_OUT_CONTRIBUTION = 0.3
BILLING_SHIPPING_MISMATCH_CONTRIBUTION = 0.15


@dataclass(frozen=True)
class AddressFeatures:
    """Address-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_address_features(
    *, store: SyntheticEventStore, event: SyntheticEvent
) -> AddressFeatures:
    """Compute address newness/fan-out/mismatch signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["24h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)
    address_events = [
        candidate for candidate in candidates if candidate.address_id == event.address_id
    ]

    prior_events_for_account = [
        candidate
        for candidate in address_events
        if candidate.account_id == event.account_id and candidate.event_id != event.event_id
    ]
    is_new_address_for_account = len(prior_events_for_account) == 0

    distinct_accounts = distinct_count(address_events, key=lambda candidate: candidate.account_id)

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {
        "address_new_to_account": 1.0 if is_new_address_for_account else 0.0,
        "address_fan_out_distinct_accounts_24h": float(distinct_accounts),
        "address_billing_shipping_mismatch": 0.0 if event.billing_shipping_match else 1.0,
    }

    if is_new_address_for_account:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="address_new_to_account",
                description=(
                    "This address has not been paired with this account before, in the "
                    "synthetic history available."
                ),
                contribution=NEW_ADDRESS_CONTRIBUTION,
            )
        )

    if distinct_accounts > ADDRESS_FAN_OUT_ACCOUNT_THRESHOLD:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="address_fan_out_high",
                description=(
                    f"This address has been used by {distinct_accounts} distinct synthetic "
                    f"accounts in the last {ADDRESS_FAN_OUT_LOOKBACK_HOURS}h, above the "
                    f"illustrative baseline of {ADDRESS_FAN_OUT_ACCOUNT_THRESHOLD}."
                ),
                contribution=ADDRESS_FAN_OUT_CONTRIBUTION,
            )
        )

    if not event.billing_shipping_match:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="address_billing_shipping_mismatch",
                description=(
                    "Billing and shipping addresses do not match for this synthetic transaction."
                ),
                contribution=BILLING_SHIPPING_MISMATCH_CONTRIBUTION,
            )
        )

    return AddressFeatures(triggered_signals=triggered_signals, window_features=window_features)
