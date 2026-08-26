"""Materialise the Lane A v2 variant superset (24 fields) for one permitted role.

Every variant is a column subset of this superset, so one pass per role is
sufficient and every variant is guaranteed to see byte-identical inputs.

The role must be on the Lane A allowlist; ``final_test`` and unknown roles fail
closed before any file is opened. Labels, when requested, go to a separate file.
Output is written to a private directory outside the repository.
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
    normalise_categorical,
    normalise_numeric,
)
from src.lane_a.roles import assert_labels_readable, assert_role_permitted  # noqa: E402
from src.lane_a.serving_schema import IDENTITY_PRESENCE_FEATURE, NUMERIC_FIELDS  # noqa: E402
from src.lane_a.variants import (  # noqa: E402
    SUPERSET_FIELDS,
    is_permanently_prohibited,
    validate_all,
)

JOIN_KEY = "TransactionID"
LABEL_COLUMN = "isFraud"
IDENTITY_SOURCED = ("DeviceType", "DeviceInfo")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_digest(rows: list[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for values in rows:
        parts = []
        for value in values:
            if value is None:
                parts.append("")
            elif isinstance(value, bool):
                parts.append("1" if value else "0")
            elif isinstance(value, float):
                parts.append(repr(value))
            else:
                parts.append(str(value))
        digest.update("\x1f".join(parts).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    parser.add_argument("--with-labels", action="store_true")
    args = parser.parse_args()

    role = assert_role_permitted(args.role)
    if args.with_labels:
        assert_labels_readable(role)
    validate_all()
    for name in SUPERSET_FIELDS:
        if is_permanently_prohibited(name):
            raise FeatureBuildError(f"Prohibited field {name!r} in the superset.")

    private_dir = args.private_output_dir.expanduser().resolve()
    if private_dir == PROJECT_ROOT or PROJECT_ROOT in private_dir.parents:
        raise FeatureBuildError("Refusing to write inside the repository.")
    private_dir.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(10_000_000)

    assignment = args.assignment.expanduser().resolve(strict=True)
    transactions = args.transactions.expanduser().resolve(strict=True)
    identity = args.identity.expanduser().resolve(strict=True)

    with assignment.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        idx, role_idx = header.index(JOIN_KEY), header.index("role")
        role_ids = {int(row[idx]) for row in reader if row[role_idx] == role}

    with identity.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        idx = header.index(JOIN_KEY)
        cols = {name: header.index(name) for name in IDENTITY_SOURCED}
        identity_rows: dict[int, dict[str, str]] = {}
        for row in reader:
            identifier = int(row[idx])
            if identifier in role_ids:
                identity_rows[identifier] = {n: row[i] for n, i in cols.items()}

    transaction_sourced = tuple(
        name
        for name in SUPERSET_FIELDS
        if name not in IDENTITY_SOURCED and name != IDENTITY_PRESENCE_FEATURE
    )
    built: list[tuple[int, tuple[object, ...]]] = []
    labels: list[tuple[int, int]] = []
    skipped = 0
    with transactions.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        label_index = header.index(LABEL_COLUMN) if args.with_labels else None
        source_index = {name: header.index(name) for name in transaction_sourced}
        assert LABEL_COLUMN not in source_index
        for row in reader:
            identifier = int(row[id_index])
            if identifier not in role_ids:
                skipped += 1
                continue  # no other field of an out-of-role row is touched
            present = identifier in identity_rows
            record: dict[str, object] = {}
            for name in transaction_sourced:
                raw = row[source_index[name]]
                record[name] = (
                    normalise_numeric(name, raw)
                    if name in NUMERIC_FIELDS
                    else normalise_categorical(name, raw)
                )
            for name in IDENTITY_SOURCED:
                identity_raw: str | None = identity_rows[identifier][name] if present else None
                record[name] = normalise_categorical(name, identity_raw)
            record[IDENTITY_PRESENCE_FEATURE] = present
            built.append((identifier, tuple(record[n] for n in SUPERSET_FIELDS)))
            if label_index is not None:
                labels.append((identifier, int(row[label_index])))

    built.sort(key=lambda item: item[0])
    labels.sort(key=lambda item: item[0])

    features_path = private_dir / f"lane_a_v2_{role}_superset.csv"
    with features_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([JOIN_KEY, *SUPERSET_FIELDS])
        for identifier, values in built:
            writer.writerow([identifier, *["" if v is None else v for v in values]])

    label_digest = None
    if args.with_labels:
        labels_path = private_dir / f"lane_a_v2_{role}_labels.csv"
        with labels_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([JOIN_KEY, LABEL_COLUMN])
            writer.writerows(labels)
        digest = hashlib.sha256()
        for identifier, value in labels:
            digest.update(f"{identifier},{value}\n".encode())
        label_digest = digest.hexdigest()

    print(
        json.dumps(
            {
                "lane": "A",
                "protocol": "v2",
                "role": role,
                "rows_built": len(built),
                "rows_skipped_on_identifier_only": skipped,
                "superset_fields": len(SUPERSET_FIELDS),
                "identity_record_present_true": sum(
                    1 for _, v in built if v[SUPERSET_FIELDS.index(IDENTITY_PRESENCE_FEATURE)]
                ),
                "device_info_reserved_missing": sum(
                    1
                    for _, v in built
                    if v[SUPERSET_FIELDS.index("DeviceInfo")] == RESERVED_MISSING
                ),
                "superset_content_digest": _content_digest([v for _, v in built]),
                "labels_written": bool(args.with_labels),
                "label_digest": label_digest,
                "source_transaction_sha256": _sha256_file(transactions),
                "final_test_touched": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
