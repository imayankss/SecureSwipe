"""Deterministic chronological role partitioning for Lane A.

The partition is computed from transaction timestamps alone. It never reads,
receives, or depends on the label column: role boundaries are a function of the
time axis and the target proportions only, so no label information can leak into
the split.

Every row sharing one timestamp is kept in a single role. Boundaries are chosen
to minimise absolute deviation from the declared cumulative target proportions
subject to that constraint. No randomness is involved and no seed is required:
the same input file always yields the same boundaries.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# Declared in docs/evidence/SCIENTIFIC_PROTOCOL.md 3.2. Order is chronological:
# earliest rows train, latest rows are the frozen final test.
ROLE_TARGETS: tuple[tuple[str, float], ...] = (
    ("training", 0.55),
    ("validation_threshold", 0.12),
    ("calibration_fit", 0.09),
    ("calibration_eval", 0.09),
    ("final_test", 0.15),
)

ROLE_NAMES: tuple[str, ...] = tuple(name for name, _ in ROLE_TARGETS)


class PartitionError(RuntimeError):
    """Raised when a partition cannot be produced or fails verification."""


@dataclass(frozen=True)
class RoleBoundary:
    """Inclusive upper timestamp bound of one role."""

    role: str
    upper_timestamp: int
    row_count: int
    target_fraction: float
    actual_fraction: float

    @property
    def deviation(self) -> float:
        return self.actual_fraction - self.target_fraction


def _validate_targets() -> None:
    total = sum(fraction for _, fraction in ROLE_TARGETS)
    if abs(total - 1.0) > 1e-9:
        raise PartitionError(f"Role target fractions must sum to 1.0, got {total!r}.")
    if len({name for name, _ in ROLE_TARGETS}) != len(ROLE_TARGETS):
        raise PartitionError("Role names must be unique.")
    if any(fraction <= 0.0 for _, fraction in ROLE_TARGETS):
        raise PartitionError("Role target fractions must be strictly positive.")


def timestamp_counts(timestamps: Iterable[int]) -> list[tuple[int, int]]:
    """Return ``(timestamp, row_count)`` pairs sorted ascending by timestamp."""
    counts: dict[int, int] = {}
    for value in timestamps:
        if not isinstance(value, int) or isinstance(value, bool):
            raise PartitionError("Timestamps must be plain integers.")
        if value < 0:
            raise PartitionError("Timestamps must be non-negative.")
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        raise PartitionError("At least one timestamp is required.")
    return sorted(counts.items())


def choose_boundaries(counts: Sequence[tuple[int, int]]) -> list[RoleBoundary]:
    """Pick inclusive upper timestamp bounds minimising target deviation.

    ``counts`` must be ascending ``(timestamp, row_count)`` pairs. Ties are
    indivisible: a boundary always falls between two distinct timestamps.
    """
    _validate_targets()
    if len(counts) < len(ROLE_TARGETS):
        raise PartitionError(
            f"Need at least {len(ROLE_TARGETS)} distinct timestamps to build "
            f"{len(ROLE_TARGETS)} non-empty roles; got {len(counts)}."
        )
    previous = None
    for timestamp, row_count in counts:
        if previous is not None and timestamp <= previous:
            raise PartitionError("Timestamp counts must be strictly ascending and unique.")
        if row_count < 1:
            raise PartitionError("Every timestamp must carry at least one row.")
        previous = timestamp

    total = sum(row_count for _, row_count in counts)
    cumulative: list[int] = []
    running = 0
    for _, row_count in counts:
        running += row_count
        cumulative.append(running)

    cut_indices: list[int] = []
    cumulative_target = 0.0
    # The final role needs no cut: it absorbs the remainder.
    for position, (_, fraction) in enumerate(ROLE_TARGETS[:-1]):
        cumulative_target += fraction
        # Each cut must leave room for the roles that still follow it.
        lowest = position if not cut_indices else cut_indices[-1] + 1
        highest = len(counts) - (len(ROLE_TARGETS) - 1 - position) - 1
        if lowest > highest:
            raise PartitionError("Not enough distinct timestamps to place all boundaries.")
        best_index = min(
            range(lowest, highest + 1),
            key=lambda index: (abs(cumulative[index] / total - cumulative_target), index),
        )
        cut_indices.append(best_index)

    boundaries: list[RoleBoundary] = []
    previous_cumulative = 0
    for position, (role, fraction) in enumerate(ROLE_TARGETS):
        index = cut_indices[position] if position < len(cut_indices) else len(counts) - 1
        row_count = cumulative[index] - previous_cumulative
        if row_count < 1:
            raise PartitionError(f"Role {role!r} would be empty.")
        boundaries.append(
            RoleBoundary(
                role=role,
                upper_timestamp=counts[index][0],
                row_count=row_count,
                target_fraction=fraction,
                actual_fraction=row_count / total,
            )
        )
        previous_cumulative = cumulative[index]
    return boundaries


def role_for_timestamp(timestamp: int, boundaries: Sequence[RoleBoundary]) -> str:
    """Return the role owning ``timestamp``. Roles are inclusive upper bounds."""
    for boundary in boundaries:
        if timestamp <= boundary.upper_timestamp:
            return boundary.role
    raise PartitionError("Timestamp exceeds the final role's upper bound.")


def verify_partition(
    counts: Sequence[tuple[int, int]], boundaries: Sequence[RoleBoundary]
) -> dict[str, object]:
    """Re-derive role membership independently and assert the freeze invariants."""
    if [b.role for b in boundaries] != list(ROLE_NAMES):
        raise PartitionError("Boundary roles must match the declared role order.")
    uppers = [b.upper_timestamp for b in boundaries]
    if uppers != sorted(set(uppers)):
        raise PartitionError("Role upper bounds must be strictly increasing.")

    observed: dict[str, int] = {name: 0 for name in ROLE_NAMES}
    seen_roles: list[str] = []
    for timestamp, row_count in counts:
        role = role_for_timestamp(timestamp, boundaries)
        observed[role] += row_count
        if not seen_roles or seen_roles[-1] != role:
            if role in seen_roles:
                raise PartitionError(f"Role {role!r} is not contiguous in time.")
            seen_roles.append(role)

    total = sum(row_count for _, row_count in counts)
    if sum(observed.values()) != total:
        raise PartitionError("Role counts do not sum to the row total.")
    for boundary in boundaries:
        if observed[boundary.role] != boundary.row_count:
            raise PartitionError(f"Recomputed count for {boundary.role!r} disagrees.")
    if seen_roles != list(ROLE_NAMES):
        raise PartitionError("Roles must appear in chronological order exactly once.")

    return {
        "total_rows": total,
        "role_counts": observed,
        "roles_contiguous": True,
        "roles_exhaustive": True,
        "roles_disjoint": True,
        "strictly_increasing_bounds": True,
    }


def assignment_digest(pairs: Iterable[tuple[int, str]]) -> str:
    """SHA-256 over canonical ``id,role`` lines sorted ascending by id.

    The digest is publishable; the underlying pairs are not.
    """
    digest = hashlib.sha256()
    previous_id = None
    for identifier, role in sorted(pairs):
        if role not in ROLE_NAMES:
            raise PartitionError(f"Unknown role {role!r}.")
        if previous_id is not None and identifier == previous_id:
            raise PartitionError("Duplicate identifier in assignment.")
        previous_id = identifier
        digest.update(f"{identifier},{role}\n".encode("utf-8"))
    return digest.hexdigest()


def summarise(boundaries: Sequence[RoleBoundary]) -> list[Mapping[str, object]]:
    """Public-safe per-role summary: no identifiers, no labels, no rows."""
    return [
        {
            "role": b.role,
            "row_count": b.row_count,
            "target_fraction": b.target_fraction,
            "actual_fraction": round(b.actual_fraction, 8),
            "deviation": round(b.deviation, 8),
            "upper_timestamp": b.upper_timestamp,
        }
        for b in boundaries
    ]
