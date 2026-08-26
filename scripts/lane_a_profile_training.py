"""Profile Lane A training-role columns. Aggregate output only.

Reads the authorised transaction and identity CSVs plus the private MT3a role
assignment, restricts to rows whose frozen role is ``training``, and emits
dtype, missingness, cardinality and invalid-value counts per column.

The label column is skipped by index and never parsed. No cell value,
identifier, email domain, device string, or amount is retained or printed.
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

from src.lane_a.feature_contract import (  # noqa: E402
    JOIN_KEY,
    LABEL_COLUMN,
    PARTITION_KEY,
    RULES_BY_NAME,
)
from src.lane_a.profiling import ProfilingError, new_accumulators  # noqa: E402

TRAINING_ROLE = "training"
NON_NEGATIVE = frozenset({"TransactionAmt"})


def load_training_ids(assignment_path: Path) -> set[int]:
    with assignment_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index, role_index = header.index(JOIN_KEY), header.index("role")
        return {int(row[id_index]) for row in reader if row[role_index] == TRAINING_ROLE}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    args = parser.parse_args()

    csv.field_size_limit(10_000_000)
    training_ids = load_training_ids(args.assignment.expanduser().resolve(strict=True))
    if not training_ids:
        raise ProfilingError("No training rows found in the role assignment.")

    # ---- transaction columns ----
    tx_path = args.transactions.expanduser().resolve(strict=True)
    with tx_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        label_index = header.index(LABEL_COLUMN)
        id_index = header.index(JOIN_KEY)
        profiled = tuple(
            name for name in header if name not in {LABEL_COLUMN, JOIN_KEY, PARTITION_KEY}
        )
        accumulators = new_accumulators(profiled, NON_NEGATIVE)
        index_of = {name: header.index(name) for name in profiled}
        training_rows = 0
        for row in reader:
            if int(row[id_index]) not in training_ids:
                continue
            training_rows += 1
            for name in profiled:
                accumulators[name].update(row[index_of[name]])
        assert label_index not in {index_of[name] for name in profiled}

    # ---- identity columns, restricted to training rows ----
    id_path = args.identity.expanduser().resolve(strict=True)
    with id_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        id_header = next(reader)
        id_join = id_header.index(JOIN_KEY)
        id_profiled = tuple(name for name in id_header if name != JOIN_KEY)
        id_accumulators = new_accumulators(id_profiled)
        id_index_of = {name: id_header.index(name) for name in id_profiled}
        identity_training_rows = 0
        for row in reader:
            if int(row[id_join]) not in training_ids:
                continue
            identity_training_rows += 1
            for name in id_profiled:
                id_accumulators[name].update(row[id_index_of[name]])

    # Identity absence is a signal, not a gap to be imputed away: every training
    # row lacking an identity record is counted as missing for every identity
    # column, so the published missing_rate reflects real availability.
    for name, accumulator in id_accumulators.items():
        for _ in range(training_rows - identity_training_rows):
            accumulator.update("")

    payload = {
        "lane": "A",
        "role_profiled": TRAINING_ROLE,
        "label_column_read": False,
        "final_test_rows_read": False,
        "training_rows": training_rows,
        "identity_records_for_training_rows": identity_training_rows,
        "identity_coverage_rate": round(identity_training_rows / training_rows, 6),
        "transaction_columns_profiled": len(profiled),
        "identity_columns_profiled": len(id_profiled),
        "columns": [
            dict(accumulators[name].finalize(), eligibility=RULES_BY_NAME[name].eligibility.value)
            for name in profiled
        ]
        + [
            dict(
                id_accumulators[name].finalize(),
                eligibility=RULES_BY_NAME[name].eligibility.value,
            )
            for name in id_profiled
        ],
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
