"""Deterministic clock and seed primitives for the synthetic real-time layer.

Every consumer that needs "now" or randomness takes an explicit, injectable
primitive from this module instead of reading ``datetime.now()`` or the
global ``random`` module state directly. That is what makes a synthetic run
- a demo, a test, or a named reproducible scenario - fully deterministic
under a fixed starting instant and seed. This module must never import the
historical XGBoost model, SHAP, thresholds, metrics, or Bundle v3 code.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

# Matches ProjectSettings.random_seed's bound in src/utils/config.py, so a
# seed valid there is always valid here.
MIN_SEED = 0
MAX_SEED = 2_147_483_647


def require_timezone_aware(value: datetime, *, field_name: str) -> datetime:
    """Reject naive datetimes. Reusable by any module in this package."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value


def _require_utc(value: datetime, *, field_name: str) -> datetime:
    require_timezone_aware(value, field_name=field_name)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be UTC (utcoffset zero).")
    return value


def validate_seed(seed: int) -> int:
    if not MIN_SEED <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between {MIN_SEED} and {MAX_SEED}.")
    return seed


@runtime_checkable
class Clock(Protocol):
    """Anything that can report the current synthetic instant."""

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


@dataclass(frozen=True)
class SystemClock:
    """Wall-clock time. For illustrative/demo runs only - never used in tests."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class FixedClock:
    """A deterministic clock that only moves when explicitly advanced."""

    current: datetime

    def __post_init__(self) -> None:
        self.current = _require_utc(self.current, field_name="current")

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("delta must not be negative; FixedClock cannot move backward.")
        self.current = self.current + delta
        return self.current

    def set(self, value: datetime) -> datetime:
        self.current = _require_utc(value, field_name="value")
        return self.current


@dataclass
class SequenceClock:
    """Replays a fixed, explicit sequence of instants, one per call to now().

    Raises once the sequence is exhausted rather than silently repeating or
    wrapping, so a test fails loudly if it calls now() more times than it
    set up instants for. Instants need not be increasing - this is the
    primitive later modules use to construct deterministic late/out-of-order
    and duplicate-event scenarios.
    """

    instants: tuple[datetime, ...]
    _index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.instants:
            raise ValueError("instants must be non-empty.")
        self.instants = tuple(
            _require_utc(instant, field_name=f"instants[{i}]")
            for i, instant in enumerate(self.instants)
        )

    def now(self) -> datetime:
        if self._index >= len(self.instants):
            raise RuntimeError("SequenceClock exhausted: no more instants to return.")
        value = self.instants[self._index]
        self._index += 1
        return value

    def remaining(self) -> int:
        return len(self.instants) - self._index


def new_rng(seed: int) -> random.Random:
    """Create a fresh, isolated PRNG seeded deterministically.

    Never reads or mutates the global ``random`` module state, so concurrent
    or repeated synthetic runs cannot interfere with each other.
    """
    return random.Random(validate_seed(seed))


def derive_seed(seed: int, label: str) -> int:
    """Deterministically derive a sub-seed for a named sub-stream.

    Lets independent parts of a scenario (e.g. "device_id", "amount") draw
    from their own reproducible stream without the caller hand-managing a
    table of magic seed offsets, while staying perfectly reproducible for a
    given (seed, label) pair.
    """
    validate_seed(seed)
    if not label:
        raise ValueError("label must be non-empty.")
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    derived = int.from_bytes(digest[:4], byteorder="big")
    return derived % (MAX_SEED + 1)
