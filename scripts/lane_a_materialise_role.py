"""Materialise Lane A serving-core features (and optionally labels) for one role.

The role must be on the Lane A allowlist; ``final_test`` and unknown roles fail
closed before any file is opened. Features never involve labels. Labels, when
requested, are written to a separate private file so that feature code and label
code cannot be confused for one another.

All output goes to a private directory outside the repository.
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

from src.lane_a.feature_builder import (  # noqa: E402
    RESERVED_MISSING,
    FeatureBuildError,
    build_row,
    row_digest,
)
from src.lane_a.roles import assert_labels_readable, assert_role_permitted  # noqa: E402
from src.lane_a.serving_schema import (  # noqa: E402
    IDENTITY_PRESENCE_FEATURE,
    SCHEMA_FIELD_NAMES,
    TRANSACTION_SOURCED_FIELDS,
    validate_against_contract,
)

JOIN_KEY = "TransactionID"
LABEL_COLUMN = "isFraud"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_role_ids(path: Path, role: str) -> set[int]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index, role_index = header.index(JOIN_KEY), header.index("role")
        return {int(row[id_index]) for row in reader if row[role_index] == role}


def load_device_types(path: Path, wanted: set[int]) -> dict[int, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index, device_index = header.index(JOIN_KEY), header.index("DeviceType")
        return {
            int(row[id_index]): row[device_index]
            for row in reader
            if int(row[id_index]) in wanted
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    parser.add_argument("--with-labels", action="store_true")
    args = parser.parse_args()

    role = assert_role_permitted(args.role)  # fails closed on final_test
    if args.with_labels:
        assert_labels_readable(role)
    validate_against_contract()
    csv.field_size_limit(10_000_000)

    private_dir = args.private_output_dir.expanduser().resolve()
    if private_dir == PROJECT_ROOT or PROJECT_ROOT in private_dir.parents:
        raise FeatureBuildError("Refusing to write inside the repository.")
    private_dir.mkdir(parents=True, exist_ok=True)

    assignment = args.assignment.expanduser().resolve(strict=True)
    transactions = args.transactions.expanduser().resolve(strict=True)
    identity = args.identity.expanduser().resolve(strict=True)

    role_ids = load_role_ids(assignment, role)
    devices = load_device_types(identity, role_ids)

    built: list[tuple[int, tuple[object, ...]]] = []
    labels: list[tuple[int, int]] = []
    skipped = 0
    with transactions.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        label_index = header.index(LABEL_COLUMN) if args.with_labels else None
        source_index = {name: header.index(name) for name in TRANSACTION_SOURCED_FIELDS}
        assert LABEL_COLUMN not in source_index
        for row in reader:
            identifier = int(row[id_index])
            if identifier not in role_ids:
                skipped += 1
                continue  # no other field of an out-of-role row is touched
            present = identifier in devices
            record = build_row(
                {name: row[index] for name, index in source_index.items()},
                identity_record_present=present,
                device_type=devices.get(identifier),
            )
            built.append((identifier, tuple(record[name] for name in SCHEMA_FIELD_NAMES)))
            if label_index is not None:
                labels.append((identifier, int(row[label_index])))

    built.sort(key=lambda item: item[0])
    labels.sort(key=lambda item: item[0])

    features_path = private_dir / f"lane_a_{role}_features.csv"
    with features_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([JOIN_KEY, *SCHEMA_FIELD_NAMES])
        for identifier, values in built:
            writer.writerow([identifier, *["" if v is None else v for v in values]])

    label_digest = None
    if args.with_labels:
        labels_path = private_dir / f"lane_a_{role}_labels.csv"
        with labels_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([JOIN_KEY, LABEL_COLUMN])
            writer.writerows(labels)
        digest = hashlib.sha256()
        for identifier, value in labels:
            digest.update(f"{identifier},{value}\n".encode())
        label_digest = digest.hexdigest()

    rows = [dict(zip(SCHEMA_FIELD_NAMES, values)) for _, values in built]
    print(
        json.dumps(
            {
                "lane": "A",
                "role": role,
                "rows_built": len(built),
                "rows_skipped_on_identifier_only": skipped,
                "model_inputs": len(SCHEMA_FIELD_NAMES),
                "identity_record_present_true": sum(
                    1 for r in rows if r[IDENTITY_PRESENCE_FEATURE]
                ),
                "device_type_reserved_missing": sum(
                    1 for r in rows if r["DeviceType"] == RESERVED_MISSING
                ),
                "feature_content_digest": row_digest(rows),
                "labels_written": bool(args.with_labels),
                "label_digest": label_digest,
                "source_transaction_sha256": _sha256_file(transactions),
                "assignment_file_sha256": _sha256_file(assignment),
                "final_test_touched": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
