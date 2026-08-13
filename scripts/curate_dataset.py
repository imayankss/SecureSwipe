"""Atomically curate exact duplicates and emit row-content lineage evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.artifacts.bundle import sha256_file  # noqa: E402
from src.data.curation import curate_exact_feature_duplicates  # noqa: E402
from src.data.data_loader import validate_dataset_schema  # noqa: E402
from src.utils.config import load_project_config  # noqa: E402
from src.utils.evidence_directory import atomic_evidence_directory  # noqa: E402
from src.utils.run_manifest import build_run_manifest, write_run_manifest  # noqa: E402

SourceKind = Literal["historical_kaggle_reference", "new_authorized_development"]
CONFIG = load_project_config()
KNOWN_HISTORICAL_ROWS = 284_807
KNOWN_HISTORICAL_FRAUD = 492


def _write_json(payload: object, path: Path) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def curate_dataset(
    *,
    source_path: Path,
    output_dir: Path,
    source_kind: SourceKind,
    source_reference: str,
) -> dict[str, Path]:
    """Curate one local CSV without treating the historical corpus as new data."""
    source = source_path.expanduser().resolve(strict=True)
    if not source.is_file() or source.is_symlink() or source.suffix.lower() != ".csv":
        raise ValueError("source_path must be a regular non-symlink CSV file.")
    if source_kind not in {
        "historical_kaggle_reference",
        "new_authorized_development",
    }:
        raise ValueError("Unsupported source_kind.")
    if not source_reference.strip():
        raise ValueError("source_reference must identify the authorized source.")
    configured_historical = (PROJECT_ROOT / CONFIG.data.raw_path).resolve()
    if source_kind == "new_authorized_development" and source == configured_historical:
        raise ValueError(
            "The configured historical Kaggle corpus is already test-observed and cannot "
            "be declared new development data."
        )

    raw = pd.read_csv(source)
    validate_dataset_schema(raw, reject_duplicate_rows=False)
    looks_like_known_historical = (
        len(raw) == KNOWN_HISTORICAL_ROWS and int(raw["Class"].sum()) == KNOWN_HISTORICAL_FRAUD
    )
    if source_kind == "new_authorized_development" and looks_like_known_historical:
        raise ValueError(
            "This dataset matches the known already-observed Kaggle corpus signature "
            f"({KNOWN_HISTORICAL_ROWS} rows/{KNOWN_HISTORICAL_FRAUD} fraud); it is "
            "reference-only even if copied or renamed."
        )
    curated, summary = curate_exact_feature_duplicates(raw)
    decision_eligible = source_kind == "new_authorized_development"

    with atomic_evidence_directory(output_dir) as temporary:
        curated_path = temporary / "curated.csv"
        curated.to_csv(curated_path, index=False, float_format="%.17g")
        reloaded = pd.read_csv(curated_path)
        validate_dataset_schema(reloaded)
        reloaded_summary = curate_exact_feature_duplicates(reloaded)[1]

        record_path = temporary / "curation.json"
        record = {
            "curation_format_version": "1",
            "curated_file_sha256": sha256_file(curated_path),
            "curated_fingerprint": reloaded_summary.curated_fingerprint,
            "curated_rows": summary.curated_rows,
            "decision_eligible": decision_eligible,
            "duplicate_groups": summary.duplicate_groups,
            "duplicate_policy": "keep_first_exact_feature_vector_conflicts_fail",
            "matches_known_historical_signature": looks_like_known_historical,
            "raw_file_sha256": sha256_file(source),
            "raw_fingerprint": summary.raw_fingerprint,
            "raw_rows": summary.raw_rows,
            "removed_fraud": summary.removed_fraud,
            "removed_legitimate": summary.removed_legitimate,
            "removed_rows": summary.removed_rows,
            "row_lineage_fingerprint": reloaded_summary.row_lineage_fingerprint,
            "source_kind": source_kind,
            "source_reference": source_reference.strip(),
        }
        _write_json(record, record_path)
        manifest = build_run_manifest(
            run_kind="dataset_duplicate_curation",
            evaluation_scope=(
                "new_authorized_development_curation"
                if decision_eligible
                else "historical_kaggle_reference_curation"
            ),
            repository=PROJECT_ROOT,
            inputs={"source_dataset": source},
            outputs={"curated_dataset": curated_path, "curation_record": record_path},
            parameters={
                "duplicate_policy": record["duplicate_policy"],
                "source_kind": source_kind,
                "source_reference": source_reference.strip(),
            },
            seeds={},
            packages=["numpy", "pandas"],
            data_fingerprint=reloaded_summary.curated_fingerprint,
        )
        write_run_manifest(manifest, temporary / "run_manifest.json")

    return {
        "curated_dataset": output_dir / "curated.csv",
        "curation_record": output_dir / "curation.json",
        "run_manifest": output_dir / "run_manifest.json",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-kind",
        choices=["historical_kaggle_reference", "new_authorized_development"],
        required=True,
    )
    parser.add_argument("--source-reference", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = curate_dataset(
        source_path=args.source,
        output_dir=args.output_dir.resolve(),
        source_kind=args.source_kind,
        source_reference=args.source_reference,
    )
    print(json.dumps({key: str(value) for key, value in sorted(outputs.items())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
