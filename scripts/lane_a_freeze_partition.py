"""Freeze the Lane A chronological partition from an authorised local CSV.

Reads only ``TransactionID`` and ``TransactionDT``. The label column is never
read, so no label information can reach the role boundaries.

Row-level role membership is written to a private directory that must be
outside the repository; the script refuses to write inside it. Only aggregates,
timestamps, and digests are printed for the public freeze record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lane_a.partition import (  # noqa: E402
    PartitionError,
    assignment_digest,
    choose_boundaries,
    role_for_timestamp,
    summarise,
    verify_partition,
)

ID_COLUMN = "TransactionID"
TIME_COLUMN = "TransactionDT"
LABEL_COLUMN = "isFraud"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_time_axis(source: Path) -> list[tuple[int, int]]:
    """Return ``(TransactionID, TransactionDT)`` pairs. Never reads the label."""
    csv.field_size_limit(10_000_000)
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        for required in (ID_COLUMN, TIME_COLUMN):
            if required not in header:
                raise PartitionError(f"Source is missing required column {required!r}.")
        id_index = header.index(ID_COLUMN)
        time_index = header.index(TIME_COLUMN)
        width = len(header)
        pairs: list[tuple[int, int]] = []
        for row in reader:
            if len(row) != width:
                raise PartitionError("Source contains a ragged row; refusing to partition.")
            pairs.append((int(row[id_index]), int(row[time_index])))
    if not pairs:
        raise PartitionError("Source contains no data rows.")
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.expanduser().resolve(strict=True)
    private_dir = args.private_output_dir.expanduser().resolve()
    if private_dir == PROJECT_ROOT or PROJECT_ROOT in private_dir.parents:
        raise PartitionError(
            "Refusing to write row-level role membership inside the repository."
        )
    private_dir.mkdir(parents=True, exist_ok=True)

    source_sha256 = sha256_file(source)
    pairs = read_time_axis(source)

    counts_map: dict[int, int] = {}
    for _, timestamp in pairs:
        counts_map[timestamp] = counts_map.get(timestamp, 0) + 1
    counts = sorted(counts_map.items())

    boundaries = choose_boundaries(counts)
    report = verify_partition(counts, boundaries)

    assignments = [
        (identifier, role_for_timestamp(timestamp, boundaries)) for identifier, timestamp in pairs
    ]
    if len({identifier for identifier, _ in assignments}) != len(assignments):
        raise PartitionError("Duplicate TransactionID in source; refusing to freeze.")
    digest = assignment_digest(assignments)

    membership_path = private_dir / "lane_a_role_assignment.csv"
    with membership_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([ID_COLUMN, "role"])
        for identifier, role in sorted(assignments):
            writer.writerow([identifier, role])

    public = {
        "lane": "A",
        "source_file": source.name,
        "source_sha256": source_sha256,
        "label_column_read": False,
        "label_column_name_present_in_source": LABEL_COLUMN,
        "identity_join_performed": False,
        "feature_engineering_performed": False,
        "shuffled": False,
        "rng_used": False,
        "total_rows": report["total_rows"],
        "distinct_timestamps": len(counts),
        "assignment_sha256": digest,
        "roles": summarise(boundaries),
        "verification": {
            key: value for key, value in report.items() if key != "role_counts"
        },
    }
    print(json.dumps(public, indent=2, sort_keys=True))
    print(f"\nprivate membership file written to: {membership_path.name} (outside the repository)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
