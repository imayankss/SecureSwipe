"""Tests for deterministic clock and seed primitives."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.synthetic_realtime.clock import (
    MAX_SEED,
    MIN_SEED,
    Clock,
    FixedClock,
    SequenceClock,
    SystemClock,
    derive_seed,
    new_rng,
    require_timezone_aware,
    validate_seed,
)

UTC_INSTANT = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
NON_UTC_INSTANT = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


# --- require_timezone_aware / validate_seed -----------------------------------


def test_require_timezone_aware_accepts_aware_datetime() -> None:
    assert require_timezone_aware(UTC_INSTANT, field_name="x") == UTC_INSTANT


def test_require_timezone_aware_rejects_naive_datetime() -> None:
    naive = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        require_timezone_aware(naive, field_name="x")


@pytest.mark.parametrize("seed", [MIN_SEED, MAX_SEED, 42])
def test_validate_seed_accepts_in_range_values(seed: int) -> None:
    assert validate_seed(seed) == seed


@pytest.mark.parametrize("seed", [MIN_SEED - 1, MAX_SEED + 1])
def test_validate_seed_rejects_out_of_range_values(seed: int) -> None:
    with pytest.raises(ValueError):
        validate_seed(seed)


# --- SystemClock -----------------------------------------------------------------


def test_system_clock_returns_timezone_aware_utc_now() -> None:
    before = datetime.now(timezone.utc)
    observed = SystemClock().now()
    after = datetime.now(timezone.utc)
    assert observed.tzinfo is not None
    assert observed.utcoffset() == timedelta(0)
    assert before <= observed <= after


def test_system_clock_satisfies_clock_protocol() -> None:
    assert isinstance(SystemClock(), Clock)


# --- FixedClock --------------------------------------------------------------------


def test_fixed_clock_returns_same_instant_repeatedly() -> None:
    clock = FixedClock(current=UTC_INSTANT)
    assert clock.now() == UTC_INSTANT
    assert clock.now() == UTC_INSTANT


def test_fixed_clock_rejects_naive_start() -> None:
    naive = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(current=naive)


def test_fixed_clock_rejects_non_utc_start() -> None:
    with pytest.raises(ValueError, match="UTC"):
        FixedClock(current=NON_UTC_INSTANT)


def test_fixed_clock_advance_moves_forward() -> None:
    clock = FixedClock(current=UTC_INSTANT)
    new_value = clock.advance(timedelta(minutes=5))
    assert new_value == UTC_INSTANT + timedelta(minutes=5)
    assert clock.now() == UTC_INSTANT + timedelta(minutes=5)


def test_fixed_clock_advance_rejects_negative_delta() -> None:
    clock = FixedClock(current=UTC_INSTANT)
    with pytest.raises(ValueError, match="backward"):
        clock.advance(timedelta(minutes=-1))


def test_fixed_clock_set_updates_current_instant() -> None:
    clock = FixedClock(current=UTC_INSTANT)
    later = UTC_INSTANT + timedelta(hours=1)
    assert clock.set(later) == later
    assert clock.now() == later


def test_fixed_clock_set_rejects_naive_value() -> None:
    clock = FixedClock(current=UTC_INSTANT)
    naive = datetime(2026, 8, 24, 13, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.set(naive)


def test_fixed_clock_satisfies_clock_protocol() -> None:
    assert isinstance(FixedClock(current=UTC_INSTANT), Clock)


# --- SequenceClock -----------------------------------------------------------------


def test_sequence_clock_returns_instants_in_order() -> None:
    first = UTC_INSTANT
    second = UTC_INSTANT + timedelta(minutes=1)
    clock = SequenceClock(instants=(first, second))
    assert clock.now() == first
    assert clock.now() == second


def test_sequence_clock_raises_once_exhausted() -> None:
    clock = SequenceClock(instants=(UTC_INSTANT,))
    clock.now()
    with pytest.raises(RuntimeError, match="exhausted"):
        clock.now()


def test_sequence_clock_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        SequenceClock(instants=())


def test_sequence_clock_rejects_naive_instant_in_sequence() -> None:
    naive = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValueError, match="timezone-aware"):
        SequenceClock(instants=(UTC_INSTANT, naive))


def test_sequence_clock_allows_non_monotonic_instants_for_out_of_order_scenarios() -> None:
    later = UTC_INSTANT + timedelta(minutes=5)
    earlier = UTC_INSTANT
    clock = SequenceClock(instants=(later, earlier))
    assert clock.now() == later
    assert clock.now() == earlier


def test_sequence_clock_remaining_counts_down() -> None:
    clock = SequenceClock(instants=(UTC_INSTANT, UTC_INSTANT, UTC_INSTANT))
    assert clock.remaining() == 3
    clock.now()
    assert clock.remaining() == 2
    clock.now()
    clock.now()
    assert clock.remaining() == 0


def test_sequence_clock_satisfies_clock_protocol() -> None:
    assert isinstance(SequenceClock(instants=(UTC_INSTANT,)), Clock)


# --- new_rng / derive_seed -----------------------------------------------------------


def test_new_rng_is_deterministic_for_same_seed() -> None:
    first = new_rng(7).random()
    second = new_rng(7).random()
    assert first == second


def test_new_rng_differs_across_seeds() -> None:
    first = new_rng(1).random()
    second = new_rng(2).random()
    assert first != second


def test_new_rng_does_not_touch_global_random_state() -> None:
    import random as random_module

    random_module.seed(12345)
    expected_next = random_module.random()
    random_module.seed(12345)

    new_rng(999).random()  # should not perturb the global generator
    observed_next = random_module.random()

    assert observed_next == expected_next


def test_new_rng_rejects_out_of_range_seed() -> None:
    with pytest.raises(ValueError):
        new_rng(MAX_SEED + 1)


def test_derive_seed_is_deterministic() -> None:
    assert derive_seed(7, "device_id") == derive_seed(7, "device_id")


def test_derive_seed_differs_by_label() -> None:
    assert derive_seed(7, "device_id") != derive_seed(7, "amount")


def test_derive_seed_differs_by_seed() -> None:
    assert derive_seed(1, "device_id") != derive_seed(2, "device_id")


def test_derive_seed_is_in_valid_seed_range() -> None:
    derived = derive_seed(7, "device_id")
    assert MIN_SEED <= derived <= MAX_SEED


def test_derive_seed_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="label"):
        derive_seed(7, "")


def test_derive_seed_rejects_out_of_range_seed() -> None:
    with pytest.raises(ValueError):
        derive_seed(MAX_SEED + 1, "device_id")
