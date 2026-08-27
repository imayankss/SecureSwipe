"""Synthetic-only tests for the Lane A chronological partition.

No test here reads the IEEE-CIS CSVs, any label column, or any real row. Every
fixture is generated in-process from integers.
"""

from __future__ import annotations

import pytest

from src.lane_a.partition import (
    ROLE_NAMES,
    ROLE_TARGETS,
    PartitionError,
    assignment_digest,
    choose_boundaries,
    role_for_timestamp,
    summarise,
    timestamp_counts,
    verify_partition,
)


def _uniform_counts(n_timestamps: int, rows_each: int = 1) -> list[tuple[int, int]]:
    return [(100 + index, rows_each) for index in range(n_timestamps)]


def test_role_targets_are_declared_and_sum_to_one() -> None:
    assert ROLE_NAMES == (
        "training",
        "validation_threshold",
        "calibration_fit",
        "calibration_eval",
        "final_test",
    )
    assert sum(fraction for _, fraction in ROLE_TARGETS) == pytest.approx(1.0)


def test_uniform_stream_lands_within_one_row_of_every_target() -> None:
    counts = _uniform_counts(10_000)
    boundaries = choose_boundaries(counts)
    total = sum(c for _, c in counts)
    for boundary in boundaries:
        assert abs(boundary.actual_fraction - boundary.target_fraction) * total <= 1.0


def test_partition_is_exhaustive_disjoint_and_time_ordered() -> None:
    counts = _uniform_counts(5_000, rows_each=3)
    boundaries = choose_boundaries(counts)
    report = verify_partition(counts, boundaries)
    assert report["total_rows"] == 15_000
    assert sum(report["role_counts"].values()) == 15_000  # type: ignore[union-attr]
    assert report["roles_contiguous"] and report["roles_exhaustive"]
    uppers = [b.upper_timestamp for b in boundaries]
    assert uppers == sorted(set(uppers))


def test_every_timestamp_maps_to_exactly_one_role() -> None:
    counts = _uniform_counts(600)
    boundaries = choose_boundaries(counts)
    seen: dict[int, str] = {}
    for timestamp, _ in counts:
        role = role_for_timestamp(timestamp, boundaries)
        assert timestamp not in seen
        seen[timestamp] = role
    assert len(seen) == 600
    assert set(seen.values()) == set(ROLE_NAMES)


def test_tied_timestamps_are_never_split_across_roles() -> None:
    # One enormous tie group straddling a natural boundary must stay whole.
    counts = [(t, 1) for t in range(1000, 1300)]
    counts[164] = (counts[164][0], 500)
    counts.sort()
    boundaries = choose_boundaries(counts)
    verify_partition(counts, boundaries)
    heavy_timestamp = 1164
    role = role_for_timestamp(heavy_timestamp, boundaries)
    assert sum(1 for b in boundaries if b.role == role) == 1


def test_roles_are_chronologically_ordered_earliest_train_latest_test() -> None:
    counts = _uniform_counts(2_000)
    boundaries = choose_boundaries(counts)
    assert role_for_timestamp(counts[0][0], boundaries) == "training"
    assert role_for_timestamp(counts[-1][0], boundaries) == "final_test"


def test_boundaries_are_deterministic_across_repeated_calls() -> None:
    counts = _uniform_counts(3_333, rows_each=2)
    first = summarise(choose_boundaries(counts))
    second = summarise(choose_boundaries(list(counts)))
    assert first == second


def test_summary_exposes_no_identifiers_or_labels() -> None:
    counts = _uniform_counts(1_000)
    rows = summarise(choose_boundaries(counts))
    permitted = {
        "role",
        "row_count",
        "target_fraction",
        "actual_fraction",
        "deviation",
        "upper_timestamp",
    }
    for row in rows:
        assert set(row) == permitted


def test_timestamp_counts_rejects_bad_input() -> None:
    with pytest.raises(PartitionError):
        timestamp_counts([])
    with pytest.raises(PartitionError):
        timestamp_counts([-1])
    with pytest.raises(PartitionError):
        timestamp_counts([True])  # bool must not pass as int


def test_too_few_distinct_timestamps_is_refused() -> None:
    with pytest.raises(PartitionError):
        choose_boundaries(_uniform_counts(4))


def test_unsorted_or_duplicated_counts_are_refused() -> None:
    with pytest.raises(PartitionError):
        choose_boundaries([(5, 1), (3, 1), (9, 1), (11, 1), (13, 1), (15, 1)])
    with pytest.raises(PartitionError):
        choose_boundaries([(5, 1), (5, 1), (9, 1), (11, 1), (13, 1), (15, 1)])


def test_timestamp_beyond_final_bound_is_refused() -> None:
    boundaries = choose_boundaries(_uniform_counts(1_000))
    with pytest.raises(PartitionError):
        role_for_timestamp(10_000_000, boundaries)


def test_verify_rejects_non_increasing_bounds() -> None:
    counts = _uniform_counts(1_000)
    boundaries = choose_boundaries(counts)
    tampered = list(boundaries)
    tampered[1] = type(tampered[1])(
        role=tampered[1].role,
        upper_timestamp=tampered[0].upper_timestamp,
        row_count=tampered[1].row_count,
        target_fraction=tampered[1].target_fraction,
        actual_fraction=tampered[1].actual_fraction,
    )
    with pytest.raises(PartitionError):
        verify_partition(counts, tampered)


def test_assignment_digest_is_order_independent_and_collision_sensitive() -> None:
    pairs = [(3, "training"), (1, "training"), (2, "final_test")]
    assert assignment_digest(pairs) == assignment_digest(sorted(pairs, reverse=True))
    changed = [(3, "training"), (1, "training"), (2, "calibration_fit")]
    assert assignment_digest(pairs) != assignment_digest(changed)


def test_assignment_digest_rejects_duplicates_and_unknown_roles() -> None:
    with pytest.raises(PartitionError):
        assignment_digest([(1, "training"), (1, "final_test")])
    with pytest.raises(PartitionError):
        assignment_digest([(1, "not_a_role")])


def test_partition_never_consults_a_label_column() -> None:
    """The public surface accepts timestamps only; there is no label parameter."""
    import inspect

    for function in (timestamp_counts, choose_boundaries, role_for_timestamp):
        signature = inspect.signature(function)
        joined = " ".join(signature.parameters).lower()
        assert "label" not in joined and "fraud" not in joined and "y" not in joined.split()
