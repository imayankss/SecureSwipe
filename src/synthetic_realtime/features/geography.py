"""Geography/IP/VPN feature family.

Three illustrative, deterministic signals:

- **country mismatch**: the event's own ``account_country`` and
  ``event_country`` disagree.
- **VPN/proxy**: surfaces the event's own ``vpn_or_proxy`` flag as a signal
  when True.
- **IP fan-out**: how many distinct synthetic accounts have used this
  ip_id within the last 24h.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_geography_features`` - the
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

IP_FAN_OUT_LOOKBACK_HOURS = 24
IP_FAN_OUT_ACCOUNT_THRESHOLD = 3  # illustrative synthetic threshold, not a tuned fraud value

COUNTRY_MISMATCH_CONTRIBUTION = 0.2
VPN_OR_PROXY_CONTRIBUTION = 0.25
IP_FAN_OUT_CONTRIBUTION = 0.3


@dataclass(frozen=True)
class GeographyFeatures:
    """Geography-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_geography_features(
    *, store: SyntheticEventStore, event: SyntheticEvent
) -> GeographyFeatures:
    """Compute country-mismatch/VPN/IP-fan-out signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["24h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)
    ip_events = [candidate for candidate in candidates if candidate.ip_id == event.ip_id]
    distinct_accounts = distinct_count(ip_events, key=lambda candidate: candidate.account_id)

    country_mismatch = event.account_country != event.event_country

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {
        "geography_country_mismatch": 1.0 if country_mismatch else 0.0,
        "geography_vpn_or_proxy": 1.0 if event.vpn_or_proxy else 0.0,
        "geography_ip_fan_out_distinct_accounts_24h": float(distinct_accounts),
    }

    if country_mismatch:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="geography_country_mismatch",
                description=(
                    "The synthetic account's home country and this transaction's event "
                    "country do not match."
                ),
                contribution=COUNTRY_MISMATCH_CONTRIBUTION,
            )
        )

    if event.vpn_or_proxy:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="geography_vpn_or_proxy",
                description="This synthetic transaction is flagged as originating via VPN or proxy.",
                contribution=VPN_OR_PROXY_CONTRIBUTION,
            )
        )

    if distinct_accounts > IP_FAN_OUT_ACCOUNT_THRESHOLD:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="geography_ip_fan_out_high",
                description=(
                    f"This IP has been used by {distinct_accounts} distinct synthetic "
                    f"accounts in the last {IP_FAN_OUT_LOOKBACK_HOURS}h, above the "
                    f"illustrative baseline of {IP_FAN_OUT_ACCOUNT_THRESHOLD}."
                ),
                contribution=IP_FAN_OUT_CONTRIBUTION,
            )
        )

    return GeographyFeatures(triggered_signals=triggered_signals, window_features=window_features)
