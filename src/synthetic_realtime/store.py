"""Bounded, deterministic in-memory event store for the synthetic real-time layer.

Single-process, demo/test-only in-memory state. No external database,
queue, or cache: state lives only in this process's memory and is
intentionally lost on restart (see context.md's synthetic-plumbing policy:
no external database, Kafka, Redis, or Kubernetes for this layer unless an
observed requirement proves it necessary). This module must never import
the historical XGBoost model, SHAP, thresholds, metrics, or Bundle v3 code.

This module owns three explicit policies:

- **Idempotency**: resubmitting the same ``event_id`` with the identical
  payload is a no-op that returns the original recorded outcome. Resubmitting
  the same ``event_id`` with a *different* payload is a data-integrity
  problem and raises rather than silently picking a winner.
- **Late/out-of-order**: an event whose ``event_time`` is behind the highest
  ``event_time`` already seen is classified ``"late"``, once, at first
  arrival. A later duplicate resubmission always replays that original
  classification - it is never re-evaluated against a newer watermark. This
  is what "do not silently rewrite prior emitted decisions" means at the
  store layer.
- **Bounded memory**: eviction is deterministic, not size-of-heap-driven -
  a time-based retention window relative to an injected ``Clock``, plus a
  hard capacity as a FIFO safety net. Because memory is bounded, idempotent
  duplicate detection is only guaranteed within that window: once an
  ``event_id`` has been evicted, a later resubmission is indistinguishable
  from a new event and is recorded as ``"new"``. That is an intentional,
  documented trade-off of bounded memory, not a bug.
- **Reset**: `reset()` exists for demos/tests only and must never be called
  on a live decision path.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.synthetic_realtime.clock import Clock, require_timezone_aware
from src.synthetic_realtime.contracts import DuplicateStatus, OrderingStatus, SyntheticEvent

# Matches the longest canonical feature window (24h) so windows.py can
# always find whatever look-back range it needs still present in the store.
DEFAULT_RETENTION = timedelta(hours=24)
DEFAULT_MAX_EVENTS = 100_000
MIN_MAX_EVENTS = 1


class DuplicateEventConflictError(ValueError):
    """Raised when an event_id is resubmitted with a different payload.

    A genuine idempotent retry resubmits byte-for-byte the same event. This
    error signals accidental event_id reuse; the store never silently picks
    a winner between the two conflicting payloads.
    """


@dataclass(frozen=True)
class RecordResult:
    """Outcome of submitting one event to the store."""

    duplicate_status: DuplicateStatus
    ordering_status: OrderingStatus
    stored_event: SyntheticEvent


@dataclass(frozen=True)
class _StoredRecord:
    event: SyntheticEvent
    ordering_status: OrderingStatus


class SyntheticEventStore:
    """Bounded, single-process, demo/test-only in-memory event history."""

    def __init__(
        self,
        *,
        clock: Clock,
        retention: timedelta = DEFAULT_RETENTION,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        if retention <= timedelta(0):
            raise ValueError("retention must be positive.")
        if max_events < MIN_MAX_EVENTS:
            raise ValueError(f"max_events must be at least {MIN_MAX_EVENTS}.")
        self._clock = clock
        self._retention = retention
        self._max_events = max_events
        self._records: OrderedDict[str, _StoredRecord] = OrderedDict()
        self._watermark: datetime | None = None

    @property
    def retention(self) -> timedelta:
        return self._retention

    @property
    def max_events(self) -> int:
        return self._max_events

    def __len__(self) -> int:
        return len(self._records)

    def get(self, event_id: str) -> SyntheticEvent | None:
        """Return the stored event for ``event_id``, or None if unknown/evicted."""
        record = self._records.get(event_id)
        return record.event if record is not None else None

    def events_in_range(self, *, start: datetime, end: datetime) -> list[SyntheticEvent]:
        """Return currently-retained events with ``start <= event_time <= end``, time-sorted."""
        require_timezone_aware(start, field_name="start")
        require_timezone_aware(end, field_name="end")
        if start > end:
            raise ValueError("start must not be after end.")
        matching = [
            record.event
            for record in self._records.values()
            if start <= record.event.event_time <= end
        ]
        matching.sort(key=lambda event: event.event_time)
        return matching

    def evict_expired(self) -> int:
        """Evict every record older than the retention window. Returns the count evicted."""
        cutoff = self._clock.now() - self._retention
        expired_ids = [
            event_id
            for event_id, record in self._records.items()
            if record.event.event_time < cutoff
        ]
        for event_id in expired_ids:
            del self._records[event_id]
        return len(expired_ids)

    def reset(self) -> None:
        """Clear all stored state, including the watermark. For demos/tests only."""
        self._records.clear()
        self._watermark = None

    def record(self, event: SyntheticEvent) -> RecordResult:
        """Record one event, applying idempotency, ordering, and eviction policy."""
        self.evict_expired()

        existing = self._records.get(event.event_id)
        if existing is not None:
            if existing.event != event:
                raise DuplicateEventConflictError(
                    f"event_id {event.event_id!r} was already recorded with a different payload."
                )
            return RecordResult(
                duplicate_status="duplicate",
                ordering_status=existing.ordering_status,
                stored_event=existing.event,
            )

        ordering_status: OrderingStatus = "in_order"
        if self._watermark is not None and event.event_time < self._watermark:
            ordering_status = "late"
        if self._watermark is None or event.event_time > self._watermark:
            self._watermark = event.event_time

        self._records[event.event_id] = _StoredRecord(event=event, ordering_status=ordering_status)
        self._enforce_capacity()

        return RecordResult(
            duplicate_status="new",
            ordering_status=ordering_status,
            stored_event=event,
        )

    def _enforce_capacity(self) -> None:
        while len(self._records) > self._max_events:
            self._records.popitem(last=False)
