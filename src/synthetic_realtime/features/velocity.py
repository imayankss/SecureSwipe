"""Transaction velocity feature family: 1m/1h/24h counts by account, device,
payment method, and merchant.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_velocity_features`` - the
computation reads ``event`` back out of the store's own history so that
"including this event" is naturally satisfied by a single data source.

The same illustrative count threshold is applied uniformly across all four
entity dimensions and all three window sizes for simplicity and
transparency at this plumbing layer; a production system would likely tune
these independently per dimension. Thresholds below are illustrative
synthetic constants, not tuned fraud thresholds, and this module never
produces a fraud probability.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.synthetic_realtime.contracts import SyntheticEvent, TriggeredSignal
from src.synthetic_realtime.store import SyntheticEventStore
from src.synthetic_realtime.windows import WINDOW_DURATIONS, WindowSize, window_counts

VELOCITY_ENTITY_EXTRACTORS: dict[str, Callable[[SyntheticEvent], str]] = {
    "account": lambda event: event.account_id,
    "device": lambda event: event.device_id,
    "payment_method": lambda event: event.payment_method_id,
    "merchant": lambda event: event.merchant_id,
}

# Illustrative synthetic thresholds, not tuned fraud values.
VELOCITY_COUNT_THRESHOLDS: dict[WindowSize, int] = {"1m": 3, "1h": 10, "24h": 50}

VELOCITY_SIGNAL_CONTRIBUTION = 0.25


@dataclass(frozen=True)
class VelocityFeatures:
    """Velocity-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_velocity_features(
    *, store: SyntheticEventStore, event: SyntheticEvent
) -> VelocityFeatures:
    """Compute per-entity 1m/1h/24h velocity signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["24h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {}

    for entity_label, extractor in VELOCITY_ENTITY_EXTRACTORS.items():
        entity_value = extractor(event)
        entity_events = [
            candidate for candidate in candidates if extractor(candidate) == entity_value
        ]
        counts = window_counts(entity_events, as_of=event.event_time)
        window_count_by_size: dict[WindowSize, int] = {
            "1m": counts.count_1m,
            "1h": counts.count_1h,
            "24h": counts.count_24h,
        }

        for window, window_count in window_count_by_size.items():
            window_features[f"velocity_{entity_label}_{window}_count"] = float(window_count)

            threshold = VELOCITY_COUNT_THRESHOLDS[window]
            if window_count > threshold:
                triggered_signals.append(
                    TriggeredSignal(
                        reason_code=f"velocity_{entity_label}_{window}_count_high",
                        description=(
                            f"This {entity_label} had {window_count} synthetic transactions "
                            f"in the last {window}, above the illustrative baseline of "
                            f"{threshold}."
                        ),
                        contribution=VELOCITY_SIGNAL_CONTRIBUTION,
                    )
                )

    return VelocityFeatures(triggered_signals=triggered_signals, window_features=window_features)
