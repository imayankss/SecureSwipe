"""Build the Lane A serving-core feature matrix for the training role only.

Streams the authorised transaction CSV, filters to rows whose frozen MT3a role
is ``training`` using only ``TransactionID``, and builds exactly the 13 locked
features. Non-training rows are skipped on the identifier alone: no other field
of a non-training row is read, validated, transformed, or retained.

Identity data is left-joined solely to obtain ``DeviceType`` and to derive
``identity_record_present``. The label column is never read.

The row-level matrix is written to a private directory outside the repository;
the runner refuses to write inside it. Only aggregates and digests are printed.
"""

from __future__ import annotations

import argparse
import csv
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
from src.lane_a.serving_schema import (  # noqa: E402
    IDENTITY_PRESENCE_FEATURE,
    SCHEMA_FIELD_NAMES,
    TRANSACTION_SOURCED_FIELDS,
    validate_against_contract,
)

TRAINING_ROLE = "training"
JOIN_KEY = "TransactionID"
LABEL_COLUMN = "isFraud"


def load_training_ids(path: Path) -> set[int]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index, role_index = header.index(JOIN_KEY), header.index("role")
        return {int(row[id_index]) for row in reader if row[role_index] == TRAINING_ROLE}


def load_training_device_types(path: Path, training_ids: set[int]) -> dict[int, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        device_index = header.index("DeviceType")
        devices: dict[int, str] = {}
        for row in reader:
            identifier = int(row[id_index])
            if identifier in training_ids:
                devices[identifier] = row[device_index]
        return devices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    args = parser.parse_args()

    validate_against_contract()
    csv.field_size_limit(10_000_000)

    private_dir = args.private_output_dir.expanduser().resolve()
    if private_dir == PROJECT_ROOT or PROJECT_ROOT in private_dir.parents:
        raise FeatureBuildError("Refusing to write the feature matrix inside the repository.")
    private_dir.mkdir(parents=True, exist_ok=True)

    training_ids = load_training_ids(args.assignment.expanduser().resolve(strict=True))
    devices = load_training_device_types(
        args.identity.expanduser().resolve(strict=True), training_ids
    )

    built: list[tuple[int, tuple[object, ...]]] = []
    skipped_non_training = 0
    with args.transactions.expanduser().resolve(strict=True).open(
        newline="", encoding="utf-8"
    ) as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        source_index = {name: header.index(name) for name in TRANSACTION_SOURCED_FIELDS}
        assert LABEL_COLUMN not in source_index
        for row in reader:
            identifier = int(row[id_index])
            if identifier not in training_ids:
                skipped_non_training += 1
                continue  # no other field of this row is ever touched
            present = identifier in devices
            record = build_row(
                {name: row[index] for name, index in source_index.items()},
                identity_record_present=present,
                device_type=devices.get(identifier),
            )
            built.append((identifier, tuple(record[name] for name in SCHEMA_FIELD_NAMES)))

    built.sort(key=lambda item: item[0])

    def as_rows() -> "list[dict[str, object]]":
        return [dict(zip(SCHEMA_FIELD_NAMES, values)) for _, values in built]

    matrix_path = private_dir / "lane_a_training_features.csv"
    with matrix_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([JOIN_KEY, *SCHEMA_FIELD_NAMES])
        for identifier, values in built:
            writer.writerow(
                [identifier, *["" if value is None else value for value in values]]
            )

    rows = as_rows()
    identity_present = sum(1 for row in rows if row[IDENTITY_PRESENCE_FEATURE])
    device_missing = sum(1 for row in rows if row["DeviceType"] == RESERVED_MISSING)

    print(
        json.dumps(
            {
                "lane": "A",
                "role_built": TRAINING_ROLE,
                "model_inputs": len(SCHEMA_FIELD_NAMES),
                "training_rows_built": len(built),
                "non_training_rows_skipped_on_identifier_only": skipped_non_training,
                "identity_record_present_true": identity_present,
                "identity_record_present_false": len(built) - identity_present,
                "device_type_reserved_missing": device_missing,
                "label_column_read": False,
                "final_test_rows_read": False,
                "encoders_fitted": 0,
                "aggregations_computed": 0,
                "feature_matrix_sha256": row_digest(rows),
                "schema": list(SCHEMA_FIELD_NAMES),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"\nprivate feature matrix written: {matrix_path.name} (outside the repository)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
