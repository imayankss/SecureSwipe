"""Deterministic exact-duplicate curation before any split or model decision."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.data_loader import fingerprint_dataframe, validate_dataset_schema
from src.preprocessing.feature_config import ALL_FEATURES


@dataclass(frozen=True)
class CurationSummary:
    raw_fingerprint: str
    curated_fingerprint: str
    raw_rows: int
    curated_rows: int
    removed_rows: int
    duplicate_groups: int
    removed_legitimate: int
    removed_fraud: int
    row_lineage_fingerprint: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_curated_dataset(
    curated_path: str | Path,
    curation_record_path: str | Path,
    *,
    require_decision_eligible: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Verify a curated CSV against its record and declared scientific scope."""
    curated = Path(curated_path).resolve(strict=True)
    record_path = Path(curation_record_path).resolve(strict=True)
    if curated.is_symlink() or record_path.is_symlink():
        raise ValueError("Curated inputs must not be symbolic links.")
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Curation record must be a JSON object.")
    required = {
        "curation_format_version",
        "curated_file_sha256",
        "curated_fingerprint",
        "decision_eligible",
        "source_kind",
        "historical_taint",
        "source_trust_basis",
        "source_approval_sha256",
    }
    if required - payload.keys():
        raise ValueError("Curation record is incomplete.")
    if require_decision_eligible and (
        payload["source_kind"] != "new_authorized_development"
        or payload["decision_eligible"] is not True
        or payload["historical_taint"] is not False
        or payload["source_trust_basis"] != "operator_attested_exact_file"
    ):
        raise ValueError(
            "Only genuinely new authorized development data may create decision evidence."
        )
    if payload["curation_format_version"] != "1":
        raise ValueError("Unsupported curation record format version.")
    if _sha256_file(curated) != payload["curated_file_sha256"]:
        raise ValueError("Curated file checksum does not match its curation record.")
    frame = pd.read_csv(curated)
    validate_dataset_schema(frame)
    if fingerprint_dataframe(frame) != payload["curated_fingerprint"]:
        raise ValueError("Curated data fingerprint does not match its curation record.")
    manifest_path = record_path.parent / "run_manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("Curation run manifest is required beside the curation record.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("run_kind") != "dataset_duplicate_curation":
        raise ValueError("Curation run manifest has the wrong provenance scope.")
    outputs = manifest.get("outputs")
    inputs = manifest.get("inputs")
    parameters = manifest.get("parameters")
    if not all(isinstance(value, dict) for value in (outputs, inputs, parameters)):
        raise ValueError("Curation run manifest inputs/outputs/parameters are missing.")
    assert isinstance(outputs, dict) and isinstance(inputs, dict) and isinstance(parameters, dict)
    if (
        manifest.get("data_fingerprint") != payload["curated_fingerprint"]
        or parameters.get("duplicate_policy") != payload.get("duplicate_policy")
        or parameters.get("source_kind") != payload["source_kind"]
        or parameters.get("source_reference") != payload.get("source_reference")
        or parameters.get("source_trust_basis") != payload["source_trust_basis"]
    ):
        raise ValueError("Curation run manifest source provenance is inconsistent.")
    source_entry = inputs.get("source_dataset")
    if (
        not isinstance(source_entry, dict)
        or source_entry.get("sha256") != payload.get("raw_file_sha256")
    ):
        raise ValueError("Curation source checksum is inconsistent with its run manifest.")
    approval_digest = payload["source_approval_sha256"]
    approval_entry = inputs.get("source_approval")
    if payload["decision_eligible"] is True:
        if (
            not isinstance(approval_digest, str)
            or not isinstance(approval_entry, dict)
            or approval_entry.get("sha256") != approval_digest
        ):
            raise ValueError("Decision-eligible curation lacks a verified source approval.")
    elif approval_digest is not None or approval_entry is not None:
        raise ValueError("Historical curation must not contain a new-source approval.")
    expected = {
        "curated_dataset": (curated, payload["curated_file_sha256"]),
        "curation_record": (record_path, _sha256_file(record_path)),
    }
    for logical_name, (path, digest) in expected.items():
        entry = outputs.get(logical_name)
        if (
            not isinstance(entry, dict)
            or entry.get("filename") != path.name
            or entry.get("sha256") != digest
            or entry.get("size_bytes") != path.stat().st_size
        ):
            raise ValueError(f"Curation run manifest mismatch for {logical_name}.")
    return frame, payload


def row_content_fingerprints(frame: pd.DataFrame) -> pd.Series:
    """Hash canonical row content; caller-authored IDs never define lineage."""
    validate_dataset_schema(frame, reject_duplicate_rows=False)
    raw = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    return raw.map(
        lambda value: hashlib.sha256(str(int(value)).encode("ascii")).hexdigest()
    )


def curate_exact_feature_duplicates(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, CurationSummary]:
    """Keep the first identical feature vector and fail on label conflicts.

    Input order is preserved because Time/order is part of subsequent temporal
    evaluation. The raw frame is never mutated.
    """
    validate_dataset_schema(frame, reject_duplicate_rows=False)
    feature_columns = list(ALL_FEATURES)
    duplicated = frame.duplicated(subset=feature_columns, keep=False)
    duplicate_frame = frame.loc[duplicated]
    if not duplicate_frame.empty:
        conflicting = duplicate_frame.groupby(
            feature_columns, sort=False, dropna=False
        )["Class"].nunique()
        conflict_count = int((conflicting > 1).sum())
        if conflict_count:
            raise ValueError(
                "Duplicate feature vectors have conflicting Class labels; "
                f"refusing curation ({conflict_count} conflicting group(s))."
            )

    keep = ~frame.duplicated(subset=feature_columns, keep="first")
    curated = frame.loc[keep].reset_index(drop=True).copy()
    validate_dataset_schema(curated)
    removed = frame.loc[~keep, "Class"].astype(int)
    row_hashes = row_content_fingerprints(curated)
    lineage_fingerprint = hashlib.sha256(
        "".join(row_hashes.tolist()).encode("ascii")
    ).hexdigest()
    summary = CurationSummary(
        raw_fingerprint=fingerprint_dataframe(frame, reject_duplicate_rows=False),
        curated_fingerprint=fingerprint_dataframe(curated),
        raw_rows=len(frame),
        curated_rows=len(curated),
        removed_rows=int((~keep).sum()),
        duplicate_groups=int(
            duplicate_frame.groupby(feature_columns, sort=False, dropna=False).ngroups
        )
        if not duplicate_frame.empty
        else 0,
        removed_legitimate=int((removed == 0).sum()),
        removed_fraud=int((removed == 1).sum()),
        row_lineage_fingerprint=lineage_fingerprint,
    )
    return curated, summary
