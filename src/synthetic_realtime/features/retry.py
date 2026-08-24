"""Retry/failure behavior feature family.

Two illustrative, deterministic signals over a 1h lookback (short relative
to the other families' 24h fan-out/velocity windows, since retry behavior
is a rapid-fire pattern by nature):

- **retry group size**: how many synthetic events share this event's
  ``retry_group_id`` within the last 1h. Events without a ``retry_group_id``
  have no group to measure.
- **account failure count**: how many ``declined``/``failed`` synthetic
  outcomes this account has had within the last 1h.

Precondition: ``event`` must already have been recorded via
``store.record(event)`` before calling ``compute_retry_features`` - the
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

RETRY_LOOKBACK_HOURS = 1
FAILED_OUTCOMES = frozenset({"declined", "failed"})

# Illustrative synthetic thresholds, not tuned fraud values.
RETRY_GROUP_SIZE_THRESHOLD = 3
ACCOUNT_FAILURE_COUNT_THRESHOLD = 3

RETRY_GROUP_SIZE_CONTRIBUTION = 0.25
ACCOUNT_FAILURE_COUNT_CONTRIBUTION = 0.25


@dataclass(frozen=True)
class RetryFeatures:
    """Retry-family signals and bounded window features for one event."""

    triggered_signals: list[TriggeredSignal] = field(default_factory=list)
    window_features: dict[str, float] = field(default_factory=dict)


def compute_retry_features(*, store: SyntheticEventStore, event: SyntheticEvent) -> RetryFeatures:
    """Compute retry-group-size/account-failure-count signals for ``event``.

    Assumes ``event`` has already been recorded via ``store.record()``.
    """
    lookback_start = event.event_time - WINDOW_DURATIONS["1h"]
    candidates = store.events_in_range(start=lookback_start, end=event.event_time)

    has_retry_group = event.retry_group_id is not None
    if has_retry_group:
        retry_group_size = len(
            [
                candidate
                for candidate in candidates
                if candidate.retry_group_id == event.retry_group_id
            ]
        )
    else:
        retry_group_size = 0

    account_failure_count = len(
        [
            candidate
            for candidate in candidates
            if candidate.account_id == event.account_id and candidate.outcome in FAILED_OUTCOMES
        ]
    )

    triggered_signals: list[TriggeredSignal] = []
    window_features: dict[str, float] = {
        "retry_has_group": 1.0 if has_retry_group else 0.0,
        "retry_group_size_1h": float(retry_group_size),
        "retry_account_failure_count_1h": float(account_failure_count),
    }

    if has_retry_group and retry_group_size > RETRY_GROUP_SIZE_THRESHOLD:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="retry_group_size_high",
                description=(
                    f"This synthetic retry group has {retry_group_size} attempts in the last "
                    f"{RETRY_LOOKBACK_HOURS}h, above the illustrative baseline of "
                    f"{RETRY_GROUP_SIZE_THRESHOLD}."
                ),
                contribution=RETRY_GROUP_SIZE_CONTRIBUTION,
            )
        )

    if account_failure_count > ACCOUNT_FAILURE_COUNT_THRESHOLD:
        triggered_signals.append(
            TriggeredSignal(
                reason_code="retry_account_failure_count_high",
                description=(
                    f"This account had {account_failure_count} declined or failed synthetic "
                    f"attempts in the last {RETRY_LOOKBACK_HOURS}h, above the illustrative "
                    f"baseline of {ACCOUNT_FAILURE_COUNT_THRESHOLD}."
                ),
                contribution=ACCOUNT_FAILURE_COUNT_CONTRIBUTION,
            )
        )

    return RetryFeatures(triggered_signals=triggered_signals, window_features=window_features)
