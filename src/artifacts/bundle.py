"""Integrity and provenance controls for locally produced model bundles.

Joblib/pickle formats can execute code during deserialization. SHA-256 detects
corruption and unexpected replacement; it does not make arbitrary pickle input
safe. These functions therefore only load server-configured artifacts under an
explicit trusted local root and never accept API-supplied paths or bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
import ctypes
import errno
import os
import platform
import re
import secrets
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import metadata, resources
from pathlib import Path, PureWindowsPath
from typing import Any, Iterator, Literal, Mapping, Sequence, cast

import joblib
import numpy as np
import pandas as pd

from src.preprocessing.feature_config import ALL_FEATURES

BUNDLE_FORMAT_VERSION = "3"
MANIFEST_FILENAME = "manifest.json"
TRAINING_PROVENANCE_FORMAT_VERSION = "1"
PRODUCER_POLICY_FORMAT_VERSION = "1"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PRODUCER_POLICY_RESOURCE = "bundle_v3_producer_policies.json"
_RUNTIME_PACKAGES = (
    "joblib",
    "numpy",
    "pandas",
    "scikit-learn",
    "scipy",
    "xgboost",
)
POSITIVE_CLASS_LABEL = 1
GOLDEN_PROBE_TOLERANCE = 1e-12
ScoreType = Literal["raw_score", "calibrated_probability"]
EvidenceCategory = Literal[
    "synthetic_demo_inference",
    "new_authorized_development_evidence",
    "historical_reference_demo_inference",
]

_EVIDENCE_CATEGORIES = {
    "synthetic_demo_inference",
    "new_authorized_development_evidence",
    "historical_reference_demo_inference",
}
_INTENDED_USE_FIELDS = {
    "producer_policy",
    "producer_policy_sha256",
    "evidence_category",
    "historical_taint",
    "decision_eligible",
    "historical_metrics_claimed",
    "evaluation_performed",
}
_THRESHOLD_PROVENANCE_FIELDS = {
    "value",
    "source",
    "model_linkage",
    "purpose",
    "calibrated",
    "cost_optimal",
    "razorpay_approved",
    "production_approved",
}
_TRAINING_PROVENANCE_FIELDS = {
    "format_version",
    "producer_policy",
    "recipe",
    "data_roles",
    "data_roles_sha256",
    "quarantine",
}
_RECIPE_FIELDS = {"name", "version", "configuration_sha256"}
_DATA_ROLE_FIELDS = {
    "fingerprint_sha256",
    "total_row_count",
    "legitimate_row_count",
    "fraud_row_count",
    "duplicate_row_count",
}
_DATA_ROLES_FIELDS = {
    "model_fit",
    "calibrator_fit",
    "threshold_selection",
    "evaluation",
}
_QUARANTINE_FIELDS = {
    "anchor_sha256",
    "row_hashes_sha256",
    "total_row_count",
    "fraud_row_count",
    "unique_row_count",
    "duplicate_row_count",
    "overlap_row_count",
}
_HISTORICAL_REFERENCE_FIELDS = {
    "format_version",
    "recipe",
    "sources",
    "quarantine",
    "filtering",
    "final_pool",
}
_HISTORICAL_REFERENCE_FILE_FIELDS = {"filename", "sha256", "size_bytes"}
_HISTORICAL_REFERENCE_SOURCE_FIELDS = {
    "filename",
    "sha256",
    "size_bytes",
    "total_row_count",
    "fraud_row_count",
}
_HISTORICAL_REFERENCE_FILTERING_FIELDS = {
    "quarantine_occurrences_removed",
    "duplicate_rows_removed",
    "cross_split_duplicate_rows_removed",
    "feature_label_conflicts",
}
_HISTORICAL_REFERENCE_POOL_FIELDS = {
    "row_hashes_sha256",
    "total_row_count",
    "legitimate_row_count",
    "fraud_row_count",
    "unique_row_count",
    "duplicate_row_count",
}
HISTORICAL_REFERENCE_PROVENANCE_FORMAT_VERSION = "2"
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_READ_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


class ArtifactVerificationError(RuntimeError):
    """Raised when an artifact fails trust checks."""


@dataclass(frozen=True)
class IntendedUse:
    producer_policy: str
    producer_policy_sha256: str
    evidence_category: EvidenceCategory
    historical_taint: bool
    decision_eligible: bool
    historical_metrics_claimed: bool
    evaluation_performed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_policy": self.producer_policy,
            "producer_policy_sha256": self.producer_policy_sha256,
            "evidence_category": self.evidence_category,
            "historical_taint": self.historical_taint,
            "decision_eligible": self.decision_eligible,
            "historical_metrics_claimed": self.historical_metrics_claimed,
            "evaluation_performed": self.evaluation_performed,
        }


@dataclass(frozen=True)
class ThresholdProvenance:
    value: float
    source: str
    model_linkage: str
    purpose: str
    calibrated: bool
    cost_optimal: bool
    razorpay_approved: bool
    production_approved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source,
            "model_linkage": self.model_linkage,
            "purpose": self.purpose,
            "calibrated": self.calibrated,
            "cost_optimal": self.cost_optimal,
            "razorpay_approved": self.razorpay_approved,
            "production_approved": self.production_approved,
        }


@dataclass(frozen=True)
class RecipeProvenance:
    name: str
    version: str
    configuration_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "configuration_sha256": self.configuration_sha256,
        }


@dataclass(frozen=True)
class DataRoleProvenance:
    fingerprint_sha256: str
    total_row_count: int
    legitimate_row_count: int
    fraud_row_count: int
    duplicate_row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "fingerprint_sha256": self.fingerprint_sha256,
            "total_row_count": self.total_row_count,
            "legitimate_row_count": self.legitimate_row_count,
            "fraud_row_count": self.fraud_row_count,
            "duplicate_row_count": self.duplicate_row_count,
        }


@dataclass(frozen=True)
class DataRolesProvenance:
    model_fit: DataRoleProvenance
    calibrator_fit: DataRoleProvenance | None
    threshold_selection: DataRoleProvenance | None
    evaluation: DataRoleProvenance | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_fit": self.model_fit.to_dict(),
            "calibrator_fit": (
                None if self.calibrator_fit is None else self.calibrator_fit.to_dict()
            ),
            "threshold_selection": (
                None if self.threshold_selection is None else self.threshold_selection.to_dict()
            ),
            "evaluation": None if self.evaluation is None else self.evaluation.to_dict(),
        }


@dataclass(frozen=True)
class QuarantineProvenance:
    anchor_sha256: str
    row_hashes_sha256: str
    total_row_count: int
    fraud_row_count: int
    unique_row_count: int
    duplicate_row_count: int
    overlap_row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "anchor_sha256": self.anchor_sha256,
            "row_hashes_sha256": self.row_hashes_sha256,
            "total_row_count": self.total_row_count,
            "fraud_row_count": self.fraud_row_count,
            "unique_row_count": self.unique_row_count,
            "duplicate_row_count": self.duplicate_row_count,
            "overlap_row_count": self.overlap_row_count,
        }


@dataclass(frozen=True)
class HistoricalReferenceFileIdentity:
    filename: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class HistoricalReferenceSourceIdentity:
    filename: str
    sha256: str
    size_bytes: int
    total_row_count: int
    fraud_row_count: int | None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "total_row_count": self.total_row_count,
            "fraud_row_count": self.fraud_row_count,
        }


@dataclass(frozen=True)
class HistoricalReferenceFiltering:
    quarantine_occurrences_removed: int
    duplicate_rows_removed: int
    cross_split_duplicate_rows_removed: int
    feature_label_conflicts: int

    def to_dict(self) -> dict[str, int]:
        return {
            "quarantine_occurrences_removed": self.quarantine_occurrences_removed,
            "duplicate_rows_removed": self.duplicate_rows_removed,
            "cross_split_duplicate_rows_removed": self.cross_split_duplicate_rows_removed,
            "feature_label_conflicts": self.feature_label_conflicts,
        }


@dataclass(frozen=True)
class HistoricalReferencePool:
    row_hashes_sha256: str
    total_row_count: int
    legitimate_row_count: int
    fraud_row_count: int
    unique_row_count: int
    duplicate_row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "row_hashes_sha256": self.row_hashes_sha256,
            "total_row_count": self.total_row_count,
            "legitimate_row_count": self.legitimate_row_count,
            "fraud_row_count": self.fraud_row_count,
            "unique_row_count": self.unique_row_count,
            "duplicate_row_count": self.duplicate_row_count,
        }


@dataclass(frozen=True)
class HistoricalReferenceProvenance:
    format_version: str
    recipe: HistoricalReferenceFileIdentity
    sources: tuple[HistoricalReferenceSourceIdentity, ...]
    quarantine: QuarantineProvenance
    filtering: HistoricalReferenceFiltering
    final_pool: HistoricalReferencePool

    def to_dict(self) -> dict[str, Any]:
        keys = ("x_train", "y_train", "x_val", "y_val")
        return {
            "format_version": self.format_version,
            "recipe": self.recipe.to_dict(),
            "sources": {
                key: source.to_dict() for key, source in zip(keys, self.sources, strict=True)
            },
            "quarantine": self.quarantine.to_dict(),
            "filtering": self.filtering.to_dict(),
            "final_pool": self.final_pool.to_dict(),
        }


@dataclass(frozen=True)
class TrainingProvenance:
    format_version: str
    producer_policy: str
    recipe: RecipeProvenance
    data_roles: DataRolesProvenance
    data_roles_sha256: str
    quarantine: QuarantineProvenance | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "producer_policy": self.producer_policy,
            "recipe": self.recipe.to_dict(),
            "data_roles": self.data_roles.to_dict(),
            "data_roles_sha256": self.data_roles_sha256,
            "quarantine": None if self.quarantine is None else self.quarantine.to_dict(),
        }


@dataclass(frozen=True)
class ModelBundle:
    """A fitted preprocessing/model unit plus its immutable serving contract."""

    preprocessor: Any
    model: Any
    calibrator: Any | None
    operating_threshold: float
    feature_schema: tuple[str, ...]
    training_data_fingerprint: str
    model_version: str
    intended_use: IntendedUse
    threshold_provenance: ThresholdProvenance
    training_provenance: TrainingProvenance
    score_type: ScoreType = "raw_score"
    historical_reference_provenance: HistoricalReferenceProvenance | None = None
    model_artifact_sha256: str | None = None

    def validate(self) -> None:
        if self.preprocessor is None or not hasattr(self.preprocessor, "transform"):
            raise ValueError("ModelBundle preprocessor must expose transform().")
        if self.model is None or not hasattr(self.model, "predict_proba"):
            raise ValueError("ModelBundle model must expose predict_proba().")
        if self.calibrator is not None and not (
            hasattr(self.calibrator, "predict_proba") or hasattr(self.calibrator, "predict")
        ):
            raise ValueError("ModelBundle calibrator must expose predict() or predict_proba().")
        if (
            type(self.operating_threshold) not in {int, float}
            or not np.isfinite(self.operating_threshold)
            or not 0.0 <= float(self.operating_threshold) <= 1.0
        ):
            raise ValueError("ModelBundle operating_threshold must be finite and in [0, 1].")
        if tuple(self.feature_schema) != tuple(ALL_FEATURES):
            raise ValueError("ModelBundle feature_schema must match the canonical ordered schema.")
        _require_sha256(
            self.training_data_fingerprint,
            label="ModelBundle training_data_fingerprint",
        )
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("ModelBundle model_version must not be empty.")
        if self.model_artifact_sha256 is not None:
            _require_sha256(
                self.model_artifact_sha256,
                label="ModelBundle model_artifact_sha256",
            )
        if self.score_type not in {"raw_score", "calibrated_probability"}:
            raise ValueError("Unsupported ModelBundle score_type.")
        if self.calibrator is None and self.score_type != "raw_score":
            raise ValueError("A bundle without a calibrator must expose raw_score.")
        if self.calibrator is not None and self.score_type != "calibrated_probability":
            raise ValueError("A bundle with a calibrator must expose calibrated_probability.")
        if not isinstance(self.intended_use, IntendedUse):
            raise ValueError("ModelBundle intended_use must be immutable typed metadata.")
        if not isinstance(self.threshold_provenance, ThresholdProvenance):
            raise ValueError("ModelBundle threshold_provenance must be immutable typed metadata.")
        if not isinstance(self.training_provenance, TrainingProvenance):
            raise ValueError("ModelBundle training_provenance must be immutable typed metadata.")
        if self.historical_reference_provenance is not None and not isinstance(
            self.historical_reference_provenance, HistoricalReferenceProvenance
        ):
            raise ValueError(
                "ModelBundle historical_reference_provenance must be immutable typed metadata."
            )
        _validate_policy_binding(
            intended_use=self.intended_use,
            threshold_provenance=self.threshold_provenance,
            training_provenance=self.training_provenance,
            model_version=self.model_version,
            operating_threshold=float(self.operating_threshold),
            score_type=self.score_type,
        )
        if self.training_data_fingerprint != self.training_provenance.data_roles_sha256:
            raise ValueError(
                "ModelBundle training_data_fingerprint must bind every declared data role."
            )
        if self.intended_use.evidence_category == "historical_reference_demo_inference" and (
            self.score_type != "raw_score" or self.calibrator is not None
        ):
            raise ValueError(
                "Historical-reference demo bundles must expose raw_score without calibration."
            )
        _validate_historical_reference_binding(
            evidence_category=self.intended_use.evidence_category,
            historical_reference=self.historical_reference_provenance,
            data_roles=self.training_provenance.data_roles,
            quarantine=self.training_provenance.quarantine,
        )
        _validate_component_feature_identities(self.preprocessor, self.model)
        positive_class_index(self.model, component="model")
        if self.calibrator is not None and hasattr(self.calibrator, "predict_proba"):
            positive_class_index(self.calibrator, component="calibrator")


def _require_exact_mapping(
    value: object, expected_fields: set[str], *, label: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError(f"{label} fields are incomplete or unexpected.")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _require_nonnegative_int(value: object, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return value


def _require_identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a stable lowercase identifier.")
    return value


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _strict_json_object(encoded: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} must be strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return value


def _load_producer_policies() -> Mapping[str, Any]:
    resource = resources.files("src.artifacts").joinpath(_PRODUCER_POLICY_RESOURCE)
    payload = _strict_json_object(resource.read_bytes(), label="Bundle producer policy")
    if set(payload) != {"format_version", "policies"}:
        raise ValueError("Bundle producer policy fields are incomplete or unexpected.")
    if payload["format_version"] != PRODUCER_POLICY_FORMAT_VERSION:
        raise ValueError("Unsupported bundle producer policy format_version.")
    policies = payload["policies"]
    if not isinstance(policies, dict) or not policies:
        raise ValueError("Bundle producer policies are missing.")
    return policies


def _producer_policy(policy_id: str) -> Mapping[str, Any]:
    _require_identifier(policy_id, label="producer_policy")
    policy = _load_producer_policies().get(policy_id)
    expected_fields = {
        "evidence_category",
        "intended_use",
        "model_version_pattern",
        "recipe",
        "required_roles",
        "threshold",
    }
    if policy_id == "historical_reference_demo_v1":
        expected_fields.add("canonical_recipe_sha256")
        expected_fields.add("canonical_reference_evidence_sha256")
    if not isinstance(policy, dict) or set(policy) != expected_fields:
        raise ValueError("Unsupported or malformed bundle producer policy.")
    return policy


def _policy_sha256(policy: Mapping[str, Any]) -> str:
    return _canonical_json_sha256(policy)


def _parse_intended_use(value: object) -> IntendedUse:
    payload = _require_exact_mapping(value, _INTENDED_USE_FIELDS, label="intended_use")
    policy_id = _require_identifier(payload["producer_policy"], label="producer_policy")
    policy_sha = _require_sha256(payload["producer_policy_sha256"], label="producer_policy_sha256")
    category = payload["evidence_category"]
    if category not in _EVIDENCE_CATEGORIES:
        raise ValueError("Unsupported intended_use evidence_category.")
    boolean_fields = (
        "historical_taint",
        "decision_eligible",
        "historical_metrics_claimed",
        "evaluation_performed",
    )
    if any(type(payload[field]) is not bool for field in boolean_fields):
        raise ValueError("intended_use policy fields must be boolean.")
    return IntendedUse(
        producer_policy=policy_id,
        producer_policy_sha256=policy_sha,
        evidence_category=cast(EvidenceCategory, category),
        historical_taint=payload["historical_taint"],
        decision_eligible=payload["decision_eligible"],
        historical_metrics_claimed=payload["historical_metrics_claimed"],
        evaluation_performed=payload["evaluation_performed"],
    )


def _parse_threshold_provenance(value: object) -> ThresholdProvenance:
    provenance = _require_exact_mapping(
        value, _THRESHOLD_PROVENANCE_FIELDS, label="threshold_provenance"
    )
    threshold = provenance["value"]
    if type(threshold) not in {int, float} or not np.isfinite(threshold):
        raise ValueError("threshold_provenance.value must be finite and numeric.")
    for field in ("source", "model_linkage", "purpose"):
        _require_identifier(provenance[field], label=f"threshold_provenance.{field}")
    boolean_fields = (
        "calibrated",
        "cost_optimal",
        "razorpay_approved",
        "production_approved",
    )
    if any(type(provenance[field]) is not bool for field in boolean_fields):
        raise ValueError("threshold_provenance policy fields must be boolean.")
    return ThresholdProvenance(
        value=float(threshold),
        source=provenance["source"],
        model_linkage=provenance["model_linkage"],
        purpose=provenance["purpose"],
        calibrated=provenance["calibrated"],
        cost_optimal=provenance["cost_optimal"],
        razorpay_approved=provenance["razorpay_approved"],
        production_approved=provenance["production_approved"],
    )


def _parse_data_role(value: object, *, label: str) -> DataRoleProvenance:
    payload = _require_exact_mapping(value, _DATA_ROLE_FIELDS, label=label)
    fingerprint = _require_sha256(
        payload["fingerprint_sha256"], label=f"{label}.fingerprint_sha256"
    )
    total = _require_nonnegative_int(payload["total_row_count"], label=f"{label}.total")
    legitimate = _require_nonnegative_int(
        payload["legitimate_row_count"], label=f"{label}.legitimate"
    )
    fraud = _require_nonnegative_int(payload["fraud_row_count"], label=f"{label}.fraud")
    duplicates = _require_nonnegative_int(
        payload["duplicate_row_count"], label=f"{label}.duplicates"
    )
    if total == 0 or total != legitimate + fraud or duplicates > total:
        raise ValueError(f"{label} counts are inconsistent.")
    return DataRoleProvenance(
        fingerprint_sha256=fingerprint,
        total_row_count=total,
        legitimate_row_count=legitimate,
        fraud_row_count=fraud,
        duplicate_row_count=duplicates,
    )


def _parse_data_roles(value: object) -> DataRolesProvenance:
    payload = _require_exact_mapping(value, _DATA_ROLES_FIELDS, label="data_roles")

    def optional(role: str) -> DataRoleProvenance | None:
        item = payload[role]
        return None if item is None else _parse_data_role(item, label=f"data_roles.{role}")

    return DataRolesProvenance(
        model_fit=_parse_data_role(payload["model_fit"], label="data_roles.model_fit"),
        calibrator_fit=optional("calibrator_fit"),
        threshold_selection=optional("threshold_selection"),
        evaluation=optional("evaluation"),
    )


def _parse_quarantine(value: object) -> QuarantineProvenance:
    payload = _require_exact_mapping(value, _QUARANTINE_FIELDS, label="quarantine")
    anchor_sha256 = _require_sha256(payload["anchor_sha256"], label="quarantine.anchor")
    row_hashes_sha256 = _require_sha256(payload["row_hashes_sha256"], label="quarantine.row_hashes")
    total = _require_nonnegative_int(payload["total_row_count"], label="quarantine.total")
    unique = _require_nonnegative_int(payload["unique_row_count"], label="quarantine.unique")
    duplicates = _require_nonnegative_int(
        payload["duplicate_row_count"], label="quarantine.duplicates"
    )
    fraud = _require_nonnegative_int(payload["fraud_row_count"], label="quarantine.fraud")
    overlap = _require_nonnegative_int(payload["overlap_row_count"], label="quarantine.overlap")
    if total == 0 or total != unique + duplicates or fraud > total:
        raise ValueError("Quarantine counts are inconsistent.")
    if overlap != 0:
        raise ValueError("Bundle training data must have zero historical quarantine overlap.")
    try:
        from src.data.historical_quarantine import load_historical_quarantine_anchor

        approved_anchor = load_historical_quarantine_anchor()
    except (OSError, ValueError) as exc:
        raise ValueError("Approved historical quarantine anchor is unavailable.") from exc
    expected = {
        "anchor_sha256": approved_anchor.sha256,
        "row_hashes_sha256": approved_anchor.row_hashes_sha256,
        "total_row_count": approved_anchor.total_row_count,
        "fraud_row_count": approved_anchor.fraud_count,
        "unique_row_count": approved_anchor.unique_row_count,
        "duplicate_row_count": approved_anchor.duplicate_row_count,
    }
    if any(payload[field] != expected_value for field, expected_value in expected.items()):
        raise ValueError("Quarantine provenance does not match the approved canonical anchor.")
    return QuarantineProvenance(
        anchor_sha256=anchor_sha256,
        row_hashes_sha256=row_hashes_sha256,
        total_row_count=total,
        fraud_row_count=fraud,
        unique_row_count=unique,
        duplicate_row_count=duplicates,
        overlap_row_count=overlap,
    )


def _parse_historical_reference_file(
    value: object, *, label: str, expected_filename: str | None = None
) -> HistoricalReferenceFileIdentity:
    payload = _require_exact_mapping(value, _HISTORICAL_REFERENCE_FILE_FIELDS, label=label)
    filename = payload["filename"]
    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or Path(filename).is_absolute()
        or PureWindowsPath(filename).is_absolute()
        or bool(PureWindowsPath(filename).drive)
        or Path(filename).name != filename
        or (expected_filename is not None and filename != expected_filename)
    ):
        raise ValueError(f"{label}.filename is invalid.")
    return HistoricalReferenceFileIdentity(
        filename=filename,
        sha256=_require_sha256(payload["sha256"], label=f"{label}.sha256"),
        size_bytes=_require_nonnegative_int(payload["size_bytes"], label=f"{label}.size_bytes"),
    )


def _parse_historical_reference_provenance(
    value: object,
) -> HistoricalReferenceProvenance:
    payload = _require_exact_mapping(
        value, _HISTORICAL_REFERENCE_FIELDS, label="historical_reference_provenance"
    )
    if payload["format_version"] != HISTORICAL_REFERENCE_PROVENANCE_FORMAT_VERSION:
        raise ValueError("Unsupported historical_reference_provenance format_version.")
    recipe = _parse_historical_reference_file(
        payload["recipe"],
        label="historical_reference_provenance.recipe",
        expected_filename="historical_reference_demo_recipe.json",
    )
    sources_payload = payload["sources"]
    source_keys = ("x_train", "y_train", "x_val", "y_val")
    expected_filenames = ("X_train.parquet", "y_train.parquet", "X_val.parquet", "y_val.parquet")
    if not isinstance(sources_payload, Mapping) or set(sources_payload) != set(source_keys):
        raise ValueError("Historical reference source identities are incomplete or unexpected.")
    sources: list[HistoricalReferenceSourceIdentity] = []
    for key, expected_filename in zip(source_keys, expected_filenames, strict=True):
        source = _require_exact_mapping(
            sources_payload[key],
            _HISTORICAL_REFERENCE_SOURCE_FIELDS,
            label=f"historical_reference_provenance.sources.{key}",
        )
        file_identity = _parse_historical_reference_file(
            {
                "filename": source["filename"],
                "sha256": source["sha256"],
                "size_bytes": source["size_bytes"],
            },
            label=f"historical_reference_provenance.sources.{key}",
            expected_filename=expected_filename,
        )
        total = _require_nonnegative_int(
            source["total_row_count"], label=f"historical_reference_provenance.sources.{key}.total"
        )
        if total == 0:
            raise ValueError("Historical reference source identities must not be empty.")
        fraud = source["fraud_row_count"]
        if key.startswith("x_"):
            if fraud is not None:
                raise ValueError("Historical reference feature sources must not claim label counts.")
        else:
            fraud = _require_nonnegative_int(
                fraud, label=f"historical_reference_provenance.sources.{key}.fraud"
            )
            if fraud > total:
                raise ValueError("Historical reference source fraud count is inconsistent.")
        sources.append(
            HistoricalReferenceSourceIdentity(
                filename=file_identity.filename,
                sha256=file_identity.sha256,
                size_bytes=file_identity.size_bytes,
                total_row_count=total,
                fraud_row_count=fraud,
            )
        )
    if sources[0].total_row_count != sources[1].total_row_count or sources[2].total_row_count != sources[3].total_row_count:
        raise ValueError("Historical reference feature/label source row counts disagree.")
    quarantine = _parse_quarantine(payload["quarantine"])
    filtering_payload = _require_exact_mapping(
        payload["filtering"],
        _HISTORICAL_REFERENCE_FILTERING_FIELDS,
        label="historical_reference_provenance.filtering",
    )
    filtering = HistoricalReferenceFiltering(
        **{
            field: _require_nonnegative_int(
                filtering_payload[field], label=f"historical_reference_provenance.filtering.{field}"
            )
            for field in _HISTORICAL_REFERENCE_FILTERING_FIELDS
        }
    )
    if filtering.feature_label_conflicts != 0:
        raise ValueError("Historical-reference bundles must not retain feature-label conflicts.")
    if filtering.cross_split_duplicate_rows_removed > filtering.duplicate_rows_removed:
        raise ValueError(
            "Historical-reference cross-split duplicate count exceeds total duplicates removed."
        )
    pool_payload = _require_exact_mapping(
        payload["final_pool"],
        _HISTORICAL_REFERENCE_POOL_FIELDS,
        label="historical_reference_provenance.final_pool",
    )
    pool = HistoricalReferencePool(
        row_hashes_sha256=_require_sha256(
            pool_payload["row_hashes_sha256"],
            label="historical_reference_provenance.final_pool.row_hashes_sha256",
        ),
        total_row_count=_require_nonnegative_int(
            pool_payload["total_row_count"], label="historical_reference_provenance.final_pool.total"
        ),
        legitimate_row_count=_require_nonnegative_int(
            pool_payload["legitimate_row_count"],
            label="historical_reference_provenance.final_pool.legitimate",
        ),
        fraud_row_count=_require_nonnegative_int(
            pool_payload["fraud_row_count"], label="historical_reference_provenance.final_pool.fraud"
        ),
        unique_row_count=_require_nonnegative_int(
            pool_payload["unique_row_count"], label="historical_reference_provenance.final_pool.unique"
        ),
        duplicate_row_count=_require_nonnegative_int(
            pool_payload["duplicate_row_count"],
            label="historical_reference_provenance.final_pool.duplicates",
        ),
    )
    input_rows = sources[0].total_row_count + sources[2].total_row_count
    if (
        pool.total_row_count == 0
        or pool.total_row_count != pool.legitimate_row_count + pool.fraud_row_count
        or pool.total_row_count != pool.unique_row_count + pool.duplicate_row_count
        or input_rows
        != pool.total_row_count
        + filtering.quarantine_occurrences_removed
        + filtering.duplicate_rows_removed
    ):
        raise ValueError("Historical reference filtering or final-pool counts are inconsistent.")
    return HistoricalReferenceProvenance(
        format_version=HISTORICAL_REFERENCE_PROVENANCE_FORMAT_VERSION,
        recipe=recipe,
        sources=tuple(sources),
        quarantine=quarantine,
        filtering=filtering,
        final_pool=pool,
    )


def _validate_historical_reference_binding(
    *,
    evidence_category: EvidenceCategory,
    historical_reference: HistoricalReferenceProvenance | None,
    data_roles: DataRolesProvenance,
    quarantine: QuarantineProvenance | None,
) -> None:
    if evidence_category != "historical_reference_demo_inference":
        if historical_reference is not None:
            raise ValueError("Only historical-reference bundles may contain historical reference provenance.")
        return
    if historical_reference is None or quarantine is None:
        raise ValueError("Historical-reference bundles require quarantine-bound reference provenance.")
    policy = _producer_policy("historical_reference_demo_v1")
    expected_recipe_sha256 = _require_sha256(
        policy["canonical_recipe_sha256"], label="historical-reference policy recipe SHA-256"
    )
    if historical_reference.recipe.sha256 != expected_recipe_sha256:
        raise ValueError("Historical-reference recipe identity does not match tracked policy.")
    if historical_reference.quarantine != quarantine:
        raise ValueError("Historical-reference quarantine identity contradicts training provenance.")
    expected_evidence_sha256 = _require_sha256(
        policy["canonical_reference_evidence_sha256"],
        label="historical-reference policy evidence SHA-256",
    )
    if _historical_reference_evidence_sha256(historical_reference) != expected_evidence_sha256:
        raise ValueError("Historical-reference evidence contradicts tracked policy.")
    pool = historical_reference.final_pool
    model_fit = data_roles.model_fit
    if (
        model_fit.fingerprint_sha256 != pool.row_hashes_sha256
        or model_fit.total_row_count != pool.total_row_count
        or model_fit.legitimate_row_count != pool.legitimate_row_count
        or model_fit.fraud_row_count != pool.fraud_row_count
        or model_fit.duplicate_row_count != pool.duplicate_row_count
    ):
        raise ValueError("Historical-reference final pool contradicts model-fit provenance.")


def _parse_training_provenance(value: object) -> TrainingProvenance:
    payload = _require_exact_mapping(
        value, _TRAINING_PROVENANCE_FIELDS, label="training_provenance"
    )
    if payload["format_version"] != TRAINING_PROVENANCE_FORMAT_VERSION:
        raise ValueError("Unsupported training_provenance format_version.")
    policy_id = _require_identifier(
        payload["producer_policy"], label="training_provenance.producer_policy"
    )
    recipe_payload = _require_exact_mapping(
        payload["recipe"], _RECIPE_FIELDS, label="training_provenance.recipe"
    )
    recipe = RecipeProvenance(
        name=_require_identifier(recipe_payload["name"], label="training_provenance.recipe.name"),
        version=_require_identifier(
            recipe_payload["version"], label="training_provenance.recipe.version"
        ),
        configuration_sha256=_require_sha256(
            recipe_payload["configuration_sha256"],
            label="training_provenance.recipe.configuration_sha256",
        ),
    )
    roles = _parse_data_roles(payload["data_roles"])
    roles_sha256 = _require_sha256(
        payload["data_roles_sha256"], label="training_provenance.data_roles_sha256"
    )
    if roles_sha256 != training_data_fingerprint_for_roles(roles):
        raise ValueError("training_provenance data role checksum mismatch.")
    quarantine_value = payload["quarantine"]
    quarantine = None if quarantine_value is None else _parse_quarantine(quarantine_value)
    return TrainingProvenance(
        format_version=TRAINING_PROVENANCE_FORMAT_VERSION,
        producer_policy=policy_id,
        recipe=recipe,
        data_roles=roles,
        data_roles_sha256=roles_sha256,
        quarantine=quarantine,
    )


def _validate_policy_binding(
    *,
    intended_use: IntendedUse,
    threshold_provenance: ThresholdProvenance,
    training_provenance: TrainingProvenance,
    model_version: str,
    operating_threshold: float,
    score_type: str,
) -> None:
    policy = _producer_policy(intended_use.producer_policy)
    if training_provenance.producer_policy != intended_use.producer_policy:
        raise ValueError("Training provenance contradicts the producer policy.")
    if intended_use.producer_policy_sha256 != _policy_sha256(policy):
        raise ValueError("Producer policy checksum does not match tracked configuration.")
    expected_intended = {
        "evidence_category": policy["evidence_category"],
        **policy["intended_use"],
    }
    actual_intended = intended_use.to_dict()
    actual_intended.pop("producer_policy")
    actual_intended.pop("producer_policy_sha256")
    if actual_intended != expected_intended:
        raise ValueError("Intended use contradicts the tracked producer policy.")
    pattern = policy["model_version_pattern"]
    if not isinstance(pattern, str) or re.fullmatch(pattern, model_version) is None:
        raise ValueError("Model version contradicts the tracked producer policy.")

    recipe_policy = _require_exact_mapping(
        policy["recipe"], {"name", "version", "configuration"}, label="policy.recipe"
    )
    expected_recipe = RecipeProvenance(
        name=recipe_policy["name"],
        version=recipe_policy["version"],
        configuration_sha256=_canonical_json_sha256(recipe_policy["configuration"]),
    )
    if training_provenance.recipe != expected_recipe:
        raise ValueError("Training recipe does not match tracked canonical configuration.")

    threshold_policy = _require_exact_mapping(
        policy["threshold"],
        {
            "calibration_binding",
            "cost_optimal",
            "fixed_value",
            "model_linkage",
            "production_approved",
            "purpose",
            "razorpay_approved",
            "source",
        },
        label="policy.threshold",
    )
    if threshold_provenance.value != operating_threshold:
        raise ValueError("threshold_provenance.value must equal operating_threshold.")
    fixed_value = threshold_policy["fixed_value"]
    if fixed_value is not None and float(fixed_value) != operating_threshold:
        raise ValueError("Operating threshold contradicts the tracked producer policy.")
    calibration_binding = threshold_policy["calibration_binding"]
    if calibration_binding not in {"false", "score_type"}:
        raise ValueError("Tracked threshold calibration binding is unsupported.")
    expected_calibrated = (
        score_type == "calibrated_probability" if calibration_binding == "score_type" else False
    )
    expected_threshold = ThresholdProvenance(
        value=operating_threshold,
        source=threshold_policy["source"],
        model_linkage=threshold_policy["model_linkage"],
        purpose=threshold_policy["purpose"],
        calibrated=expected_calibrated,
        cost_optimal=threshold_policy["cost_optimal"],
        razorpay_approved=threshold_policy["razorpay_approved"],
        production_approved=threshold_policy["production_approved"],
    )
    if threshold_provenance != expected_threshold:
        raise ValueError("Threshold provenance contradicts the tracked producer policy.")

    required_roles = _require_exact_mapping(
        policy["required_roles"], _DATA_ROLES_FIELDS, label="policy.required_roles"
    )
    role_values = training_provenance.data_roles.to_dict()
    for role, required in required_roles.items():
        if type(required) is not bool or (role_values[role] is not None) is not required:
            raise ValueError("Declared data roles contradict the tracked producer policy.")
    if intended_use.evidence_category == "synthetic_demo_inference":
        if training_provenance.quarantine is not None:
            raise ValueError("Synthetic demo bundles must not claim quarantine provenance.")
    elif training_provenance.quarantine is None:
        raise ValueError("Non-synthetic bundles require quarantine provenance.")


def _validate_component_feature_identities(preprocessor: Any, model: Any) -> None:
    expected_count = len(ALL_FEATURES)
    if int(getattr(preprocessor, "n_features_in_", -1)) != expected_count:
        raise ValueError(f"ModelBundle preprocessor must expect {expected_count} features.")
    raw_names = getattr(preprocessor, "feature_names_in_", None)
    if raw_names is None or [str(name) for name in raw_names] != list(ALL_FEATURES):
        raise ValueError("ModelBundle preprocessor raw feature identity mismatch.")
    if not hasattr(preprocessor, "get_feature_names_out"):
        raise ValueError("ModelBundle preprocessor must expose transformed feature names.")
    transformed_names = [str(name).split("__")[-1] for name in preprocessor.get_feature_names_out()]
    if len(transformed_names) != expected_count or len(set(transformed_names)) != expected_count:
        raise ValueError("ModelBundle transformed feature identity is malformed.")
    if int(getattr(model, "n_features_in_", -1)) != expected_count:
        raise ValueError(f"ModelBundle model must expect {expected_count} features.")
    model_names = getattr(model, "feature_names_in_", None)
    if model_names is None or [str(name) for name in model_names] != transformed_names:
        raise ValueError("ModelBundle transformed feature order does not match the model.")


def intended_use_metadata(producer_policy: str) -> IntendedUse:
    """Return immutable intended-use metadata bound to a tracked producer policy."""
    policy = _producer_policy(producer_policy)
    intended = policy["intended_use"]
    return IntendedUse(
        producer_policy=producer_policy,
        producer_policy_sha256=_policy_sha256(policy),
        evidence_category=cast(EvidenceCategory, policy["evidence_category"]),
        historical_taint=intended["historical_taint"],
        decision_eligible=intended["decision_eligible"],
        historical_metrics_claimed=intended["historical_metrics_claimed"],
        evaluation_performed=intended["evaluation_performed"],
    )


def threshold_provenance_metadata(
    *,
    producer_policy: str,
    value: float,
    calibrated: bool,
) -> ThresholdProvenance:
    """Return immutable threshold metadata fixed by a tracked producer policy."""
    policy = _producer_policy(producer_policy)["threshold"]
    return ThresholdProvenance(
        value=float(value),
        source=policy["source"],
        model_linkage=policy["model_linkage"],
        purpose=policy["purpose"],
        calibrated=calibrated,
        cost_optimal=policy["cost_optimal"],
        razorpay_approved=policy["razorpay_approved"],
        production_approved=policy["production_approved"],
    )


def data_role_metadata(
    *,
    fingerprint_sha256: str,
    total_row_count: int,
    fraud_row_count: int,
    duplicate_row_count: int,
) -> DataRoleProvenance:
    """Build one immutable, count-checked data-role record."""
    role = DataRoleProvenance(
        fingerprint_sha256=fingerprint_sha256,
        total_row_count=total_row_count,
        legitimate_row_count=total_row_count - fraud_row_count,
        fraud_row_count=fraud_row_count,
        duplicate_row_count=duplicate_row_count,
    )
    return _parse_data_role(role.to_dict(), label="data_role")


def quarantine_provenance_metadata(
    *,
    anchor_sha256: str,
    row_hashes_sha256: str,
    total_row_count: int,
    fraud_row_count: int,
    unique_row_count: int,
    duplicate_row_count: int,
    overlap_row_count: int,
) -> QuarantineProvenance:
    """Build authoritative quarantine metadata; manifest identity stays run-local."""
    return _parse_quarantine(
        {
            "anchor_sha256": anchor_sha256,
            "row_hashes_sha256": row_hashes_sha256,
            "total_row_count": total_row_count,
            "fraud_row_count": fraud_row_count,
            "unique_row_count": unique_row_count,
            "duplicate_row_count": duplicate_row_count,
            "overlap_row_count": overlap_row_count,
        }
    )


def historical_reference_provenance_metadata(
    *,
    recipe: HistoricalReferenceFileIdentity,
    sources: tuple[HistoricalReferenceSourceIdentity, ...],
    quarantine: QuarantineProvenance,
    quarantine_occurrences_removed: int,
    duplicate_rows_removed: int,
    cross_split_duplicate_rows_removed: int,
    feature_label_conflicts: int,
    final_pool: HistoricalReferencePool,
) -> HistoricalReferenceProvenance:
    """Build fully loader-validated provenance for a historical-reference bundle."""
    provenance = HistoricalReferenceProvenance(
        format_version=HISTORICAL_REFERENCE_PROVENANCE_FORMAT_VERSION,
        recipe=recipe,
        sources=sources,
        quarantine=quarantine,
        filtering=HistoricalReferenceFiltering(
            quarantine_occurrences_removed=quarantine_occurrences_removed,
            duplicate_rows_removed=duplicate_rows_removed,
            cross_split_duplicate_rows_removed=cross_split_duplicate_rows_removed,
            feature_label_conflicts=feature_label_conflicts,
        ),
        final_pool=final_pool,
    )
    return _parse_historical_reference_provenance(provenance.to_dict())


def _historical_reference_evidence_sha256(
    provenance: HistoricalReferenceProvenance,
) -> str:
    """Digest every canonical historical-reference evidence field except recipe identity."""
    return _canonical_json_sha256(
        {
            "sources": {
                key: source.to_dict()
                for key, source in zip(
                    ("x_train", "y_train", "x_val", "y_val"),
                    provenance.sources,
                    strict=True,
                )
            },
            "quarantine": provenance.quarantine.to_dict(),
            "filtering": provenance.filtering.to_dict(),
            "final_pool": provenance.final_pool.to_dict(),
        }
    )


def training_data_fingerprint_for_roles(data_roles: DataRolesProvenance) -> str:
    """Bind every declared data role into one deterministic bundle fingerprint."""
    return _canonical_json_sha256(data_roles.to_dict())


def training_provenance_metadata(
    *,
    producer_policy: str,
    model_fit: DataRoleProvenance,
    calibrator_fit: DataRoleProvenance | None,
    threshold_selection: DataRoleProvenance | None,
    evaluation: DataRoleProvenance | None,
    quarantine: QuarantineProvenance | None,
) -> TrainingProvenance:
    """Build immutable role-complete provenance from one tracked producer policy."""
    policy = _producer_policy(producer_policy)
    recipe_policy = policy["recipe"]
    roles = DataRolesProvenance(
        model_fit=model_fit,
        calibrator_fit=calibrator_fit,
        threshold_selection=threshold_selection,
        evaluation=evaluation,
    )
    provenance = TrainingProvenance(
        format_version=TRAINING_PROVENANCE_FORMAT_VERSION,
        producer_policy=producer_policy,
        recipe=RecipeProvenance(
            name=recipe_policy["name"],
            version=recipe_policy["version"],
            configuration_sha256=_canonical_json_sha256(recipe_policy["configuration"]),
        ),
        data_roles=roles,
        data_roles_sha256=training_data_fingerprint_for_roles(roles),
        quarantine=quarantine,
    )
    return _parse_training_provenance(provenance.to_dict())


def positive_class_index(payload: Any, *, component: str = "model") -> int:
    """Return the explicit fraud-class column and reject ambiguous class semantics."""
    classes = getattr(payload, "classes_", None)
    if classes is None:
        raise ValueError(f"ModelBundle {component} must expose fitted classes_.")
    values = np.asarray(classes)
    if values.ndim != 1 or values.tolist() != [0, POSITIVE_CLASS_LABEL]:
        raise ValueError(
            f"ModelBundle {component} classes_ must be exactly [0, {POSITIVE_CLASS_LABEL}]."
        )
    return int(np.flatnonzero(values == POSITIVE_CLASS_LABEL)[0])


def canonical_golden_frame() -> pd.DataFrame:
    """Return a fixed synthetic transaction used only for compatibility probing."""
    values = {feature: 0.0 for feature in ALL_FEATURES}
    values["Amount"] = 1.0
    return pd.DataFrame([values], columns=ALL_FEATURES)


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _golden_probe(bundle: ModelBundle) -> dict[str, Any]:
    from src.inference.batch_scoring import score_bundle_frame

    scored = score_bundle_frame(bundle, canonical_golden_frame())
    probe: dict[str, Any] = {
        "calibrated_probability": (
            None
            if scored.calibrated_probabilities is None
            else float(scored.calibrated_probabilities[0])
        ),
        "decision_score": float(scored.decision_scores[0]),
        "features": {
            feature: float(canonical_golden_frame().iloc[0][feature]) for feature in ALL_FEATURES
        },
        "raw_score": float(scored.raw_scores[0]),
        "tolerance": GOLDEN_PROBE_TOLERANCE,
    }
    return {**probe, "sha256": _canonical_json_sha256(probe)}


def probe_bundle_runtime(bundle: ModelBundle) -> None:
    """Execute a fixed synthetic probe and raise on training-serving skew."""
    try:
        _golden_probe(bundle)
    except ArtifactVerificationError:
        raise
    except Exception:
        raise ArtifactVerificationError("Bundle runtime compatibility probe failed.") from None


def verify_bundle_golden_probe(bundle: ModelBundle, expected: Mapping[str, Any]) -> None:
    """Execute the complete preprocessing/scoring path before declaring readiness."""
    try:
        actual = _golden_probe(bundle)
    except ArtifactVerificationError:
        raise
    except Exception:
        raise ArtifactVerificationError("Bundle runtime compatibility probe failed.") from None
    for field in ("raw_score", "decision_score"):
        if not np.isclose(
            float(actual[field]),
            float(expected[field]),
            rtol=0.0,
            atol=GOLDEN_PROBE_TOLERANCE,
        ):
            raise ArtifactVerificationError(f"Bundle golden probe mismatch for {field}.")
    actual_calibrated = actual["calibrated_probability"]
    expected_calibrated = expected["calibrated_probability"]
    if (actual_calibrated is None) != (expected_calibrated is None):
        raise ArtifactVerificationError("Bundle golden calibration semantics mismatch.")
    if actual_calibrated is not None and not np.isclose(
        float(actual_calibrated),
        float(expected_calibrated),
        rtol=0.0,
        atol=GOLDEN_PROBE_TOLERANCE,
    ):
        raise ArtifactVerificationError("Bundle golden calibrated probability mismatch.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_safe_filesystem_primitives() -> None:
    required_dir_fd = (os.open, os.mkdir, os.stat, os.unlink, os.rmdir)
    if (
        not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(function not in os.supports_dir_fd for function in required_dir_fd)
        or os.stat not in os.supports_follow_symlinks
    ):
        raise RuntimeError(
            "Safe bundle I/O requires directory-descriptor and no-follow OS primitives."
        )


def _absolute_without_symlink_resolution(path: str | Path) -> Path:
    expanded = Path(path).expanduser()
    return Path(os.path.abspath(os.fspath(expanded)))


def _trusted_relative_parts(
    path: str | Path, trusted_root: str | Path
) -> tuple[Path, tuple[str, ...]]:
    root = _absolute_without_symlink_resolution(trusted_root)
    candidate_input = Path(path).expanduser()
    if candidate_input.is_absolute():
        candidate = _absolute_without_symlink_resolution(candidate_input)
    else:
        working_candidate = _absolute_without_symlink_resolution(candidate_input)
        candidate = (
            working_candidate
            if working_candidate.is_relative_to(root)
            else root.joinpath(*candidate_input.parts)
        )
    try:
        parts = candidate.relative_to(root).parts
    except ValueError as exc:
        raise ArtifactVerificationError(
            f"Artifact path '{candidate}' is outside trusted root '{root}'."
        ) from exc
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactVerificationError("Artifact path is malformed.")
    return root, parts


@dataclass(frozen=True)
class _OpenedTrustedParent:
    descriptor: int
    filename: str
    path: Path


def _open_directory_at(parent_fd: int | None, name_or_path: str | Path) -> int:
    try:
        return os.open(os.fspath(name_or_path), _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ArtifactVerificationError(
            f"Trusted path contains a missing, non-directory, or symbolic-link component: "
            f"{name_or_path}."
        ) from exc


@contextmanager
def _open_trusted_parent(
    path: str | Path, trusted_root: str | Path
) -> Iterator[_OpenedTrustedParent]:
    _require_safe_filesystem_primitives()
    root, parts = _trusted_relative_parts(path, trusted_root)
    descriptors: list[int] = []
    try:
        root_fd = _open_directory_at(None, root)
        descriptors.append(root_fd)
        parent_fd = root_fd
        for part in parts[:-1]:
            child_fd = _open_directory_at(parent_fd, part)
            descriptors.append(child_fd)
            parent_fd = child_fd
        yield _OpenedTrustedParent(
            descriptor=parent_fd,
            filename=parts[-1],
            path=root.joinpath(*parts),
        )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_regular_file_at(parent_fd: int, filename: str, *, label: str) -> bytes:
    try:
        descriptor = os.open(filename, _READ_FILE_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ArtifactVerificationError(
            f"{label} is missing, unreadable, or a symbolic link."
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ArtifactVerificationError(f"{label} must be a regular file.")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        encoded = b"".join(chunks)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ) or len(encoded) != before.st_size:
            raise ArtifactVerificationError(f"{label} changed while it was being read.")
        return encoded
    finally:
        os.close(descriptor)


def _checksum_sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def write_checksum_sidecar(path: str | Path) -> Path:
    """Write a deterministic checksum sidecar for a locally produced artifact."""
    artifact = Path(path).resolve(strict=True)
    digest = sha256_file(artifact)
    sidecar = _checksum_sidecar(artifact)
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="ascii")
    return sidecar


def _read_expected_checksum(encoded: bytes, artifact_name: str) -> str:
    try:
        parts = encoded.decode("ascii").strip().split()
    except UnicodeError as exc:
        raise ArtifactVerificationError("Malformed checksum sidecar.") from exc
    if len(parts) != 2 or parts[1] != artifact_name or not _SHA256_PATTERN.fullmatch(parts[0]):
        raise ArtifactVerificationError("Malformed checksum sidecar.")
    return parts[0]


def load_verified_joblib(
    path: str | Path,
    *,
    trusted_root: str | Path,
    required_attributes: Sequence[str] = (),
) -> Any:
    """Verify a trusted local joblib artifact before deserializing it."""
    if Path(path).suffix != ".joblib":
        raise ArtifactVerificationError("Only .joblib artifacts are accepted.")
    with _open_trusted_parent(path, trusted_root) as opened:
        artifact_bytes = _read_regular_file_at(
            opened.descriptor, opened.filename, label="Joblib artifact"
        )
        sidecar_bytes = _read_regular_file_at(
            opened.descriptor,
            f"{opened.filename}.sha256",
            label="Checksum sidecar",
        )
    expected = _read_expected_checksum(sidecar_bytes, opened.filename)
    actual = hashlib.sha256(artifact_bytes).hexdigest()
    if actual != expected:
        raise ArtifactVerificationError(
            f"Checksum mismatch for '{opened.filename}': expected {expected}, got {actual}."
        )

    loaded = joblib.load(io.BytesIO(artifact_bytes))
    missing = [name for name in required_attributes if not hasattr(loaded, name)]
    if missing:
        raise ArtifactVerificationError(
            f"Verified artifact payload is missing required attributes: {missing}."
        )
    return loaded


def _runtime_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in _RUNTIME_PACKAGES:
        if package == "xgboost":
            try:
                versions[package] = metadata.version("xgboost")
            except metadata.PackageNotFoundError:
                versions[package] = metadata.version("xgboost-cpu")
        else:
            versions[package] = metadata.version(package)
    return versions


def _joblib_bytes(payload: Any) -> bytes:
    stream = io.BytesIO()
    joblib.dump(payload, stream)
    return stream.getvalue()


def _artifact_entry(filename: str, encoded: bytes, payload: Any) -> dict[str, Any]:
    return {
        "filename": filename,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
        "python_type": f"{type(payload).__module__}.{type(payload).__qualname__}",
    }


def _bundle_manifest(
    bundle: ModelBundle,
    golden_probe: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "model_version": bundle.model_version,
        "operating_threshold": float(bundle.operating_threshold),
        "score_type": bundle.score_type,
        "feature_schema": list(bundle.feature_schema),
        "training_data_fingerprint": bundle.training_data_fingerprint,
        "intended_use": bundle.intended_use.to_dict(),
        "threshold_provenance": bundle.threshold_provenance.to_dict(),
        "training_provenance": bundle.training_provenance.to_dict(),
        "historical_reference_provenance": (
            None
            if bundle.historical_reference_provenance is None
            else bundle.historical_reference_provenance.to_dict()
        ),
        "positive_class_label": POSITIVE_CLASS_LABEL,
        "positive_class_index": positive_class_index(bundle.model),
        "golden_probe": golden_probe,
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "dependencies": _runtime_versions(),
        },
        "artifacts": dict(artifacts),
    }


def _canonical_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


@dataclass(frozen=True)
class _DirectoryIdentity:
    descriptor: int
    parent_fd: int | None
    name: str | None
    path: Path | None
    device: int
    inode: int


@dataclass(frozen=True)
class _PublicationParent:
    descriptor: int
    final_name: str
    output_path: Path
    chain: tuple[_DirectoryIdentity, ...]


def _record_directory_identity(
    descriptor: int,
    *,
    parent_fd: int | None,
    name: str | None,
    path: Path | None,
) -> _DirectoryIdentity:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Bundle output component is not a directory.")
    return _DirectoryIdentity(
        descriptor=descriptor,
        parent_fd=parent_fd,
        name=name,
        path=path,
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def _verify_directory_identity(identity: _DirectoryIdentity, *, name: str | None = None) -> None:
    descriptor_metadata = os.fstat(identity.descriptor)
    if not stat.S_ISDIR(descriptor_metadata.st_mode) or (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
    ) != (identity.device, identity.inode):
        raise ValueError("Bundle output directory descriptor was replaced.")
    if identity.parent_fd is None:
        if identity.path is None:
            raise RuntimeError("Bundle root identity is incomplete.")
        named_metadata = os.stat(identity.path, follow_symlinks=False)
    else:
        target_name = name if name is not None else identity.name
        if target_name is None:
            raise RuntimeError("Bundle directory identity is incomplete.")
        named_metadata = os.stat(
            target_name,
            dir_fd=identity.parent_fd,
            follow_symlinks=False,
        )
    if not stat.S_ISDIR(named_metadata.st_mode) or (
        named_metadata.st_dev,
        named_metadata.st_ino,
    ) != (identity.device, identity.inode):
        raise ValueError("Bundle output directory path was replaced.")


def _verify_directory_chain(chain: tuple[_DirectoryIdentity, ...]) -> None:
    for identity in chain:
        _verify_directory_identity(identity)


@contextmanager
def _open_publication_parent(output_dir: str | Path) -> Iterator[_PublicationParent]:
    _require_safe_filesystem_primitives()
    raw = Path(output_dir).expanduser()
    if any(part in {"", ".", ".."} for part in raw.parts):
        raise ValueError("Bundle output path must not contain dot traversal components.")
    target = _absolute_without_symlink_resolution(raw)
    if not target.name:
        raise ValueError("Bundle output must name a child directory.")
    anchor = Path(target.anchor)
    relative_parts = target.relative_to(anchor).parts
    descriptors: list[int] = []
    chain: list[_DirectoryIdentity] = []
    try:
        root_fd = _open_directory_at(None, anchor)
        descriptors.append(root_fd)
        chain.append(
            _record_directory_identity(
                root_fd,
                parent_fd=None,
                name=None,
                path=anchor,
            )
        )
        parent_fd = root_fd
        for part in relative_parts[:-1]:
            try:
                child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                try:
                    child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
                except OSError as exc:
                    raise ValueError(
                        "Bundle output path contains a symbolic link or unsafe directory."
                    ) from exc
            except OSError as exc:
                raise ValueError(
                    "Bundle output path contains a symbolic link or unsafe directory."
                ) from exc
            descriptors.append(child_fd)
            chain.append(
                _record_directory_identity(
                    child_fd,
                    parent_fd=parent_fd,
                    name=part,
                    path=None,
                )
            )
            parent_fd = child_fd
        opened = _PublicationParent(
            descriptor=parent_fd,
            final_name=relative_parts[-1],
            output_path=target,
            chain=tuple(chain),
        )
        _verify_directory_chain(opened.chain)
        yield opened
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _reject_existing_at(parent_fd: int, name: str, output_path: Path) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise FileExistsError(f"Refusing to overwrite bundle directory: {output_path}")


def _write_new_file_at(parent_fd: int, filename: str, encoded: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    descriptor = os.open(filename, flags, mode=0o600, dir_fd=parent_fd)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_directory_no_replace(
    parent_fd: int, temporary_name: str, final_name: str, output_path: Path
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    encoded_temporary = os.fsencode(temporary_name)
    encoded_final = os.fsencode(final_name)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        rename = libc.renameatx_np
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(parent_fd, encoded_temporary, parent_fd, encoded_final, 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(parent_fd, encoded_temporary, parent_fd, encoded_final, 0x00000001)
    else:
        raise RuntimeError("Atomic no-overwrite directory publication is unavailable.")
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(f"Refusing to overwrite bundle directory: {output_path}")
    raise OSError(error, os.strerror(error), os.fspath(output_path))


def _cleanup_temporary_directory(parent_fd: int, temporary_fd: int, name: str) -> None:
    for child in os.listdir(temporary_fd):
        metadata = os.stat(child, dir_fd=temporary_fd, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError("Unexpected directory appeared in bundle temporary output.")
        os.unlink(child, dir_fd=temporary_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _cleanup_unopened_temporary_name(parent_fd: int, name: str) -> None:
    """Remove only the untrusted name created for a temporary directory."""
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or stat.S_ISREG(metadata.st_mode):
        os.unlink(name, dir_fd=parent_fd)
        return
    if stat.S_ISDIR(metadata.st_mode):
        os.rmdir(name, dir_fd=parent_fd)
        return
    raise RuntimeError("Unexpected object replaced the bundle temporary output.")


def save_model_bundle(
    bundle: ModelBundle,
    output_dir: str | Path,
    *,
    additional_files: Mapping[str, bytes] | None = None,
) -> Path:
    """Atomically persist a complete, verified bundle without following symlinks."""
    _require_safe_filesystem_primitives()
    bundle.validate()
    golden_probe = _golden_probe(bundle)
    payloads: dict[str, Any] = {"preprocessor": bundle.preprocessor, "model": bundle.model}
    if bundle.calibrator is not None:
        payloads["calibrator"] = bundle.calibrator
    encoded_artifacts = {name: _joblib_bytes(payload) for name, payload in payloads.items()}
    artifacts = {
        name: _artifact_entry(f"{name}.joblib", encoded, payloads[name])
        for name, encoded in encoded_artifacts.items()
    }
    manifest_bytes = _canonical_manifest_bytes(_bundle_manifest(bundle, golden_probe, artifacts))
    extras = dict(additional_files or {})
    reserved = {
        MANIFEST_FILENAME,
        *(f"{name}.joblib" for name in payloads),
        *(f"{name}.joblib.sha256" for name in payloads),
    }
    for filename, encoded in extras.items():
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or filename in {"", ".", ".."}
            or "/" in filename
            or "\\" in filename
            or filename in reserved
            or not isinstance(encoded, bytes)
        ):
            raise ValueError("Additional bundle files must be unique basenames with byte values.")

    with _open_publication_parent(output_dir) as opened:
        _verify_directory_chain(opened.chain)
        _reject_existing_at(opened.descriptor, opened.final_name, opened.output_path)
        temporary_name = f".{opened.final_name}.{secrets.token_hex(16)}.tmp"
        os.mkdir(temporary_name, mode=0o700, dir_fd=opened.descriptor)
        try:
            temporary_fd = os.open(
                temporary_name,
                _DIRECTORY_FLAGS,
                dir_fd=opened.descriptor,
            )
        except BaseException:
            _cleanup_unopened_temporary_name(opened.descriptor, temporary_name)
            raise
        published = False
        renamed = False
        try:
            temporary_identity = _record_directory_identity(
                temporary_fd,
                parent_fd=opened.descriptor,
                name=temporary_name,
                path=None,
            )
            for name, encoded in encoded_artifacts.items():
                filename = f"{name}.joblib"
                _write_new_file_at(temporary_fd, filename, encoded)
                sidecar = f"{hashlib.sha256(encoded).hexdigest()}  {filename}\n".encode("ascii")
                _write_new_file_at(temporary_fd, f"{filename}.sha256", sidecar)
            _write_new_file_at(temporary_fd, MANIFEST_FILENAME, manifest_bytes)
            for filename, encoded in extras.items():
                _write_new_file_at(temporary_fd, filename, encoded)
            os.fsync(temporary_fd)
            _load_model_bundle_from_directory_fd(temporary_fd)
            _verify_directory_chain(opened.chain)
            _verify_directory_identity(temporary_identity)
            _reject_existing_at(opened.descriptor, opened.final_name, opened.output_path)
            _rename_directory_no_replace(
                opened.descriptor,
                temporary_name,
                opened.final_name,
                opened.output_path,
            )
            renamed = True
            _verify_directory_chain(opened.chain)
            _verify_directory_identity(
                temporary_identity,
                name=opened.final_name,
            )
            published = True
            os.fsync(opened.descriptor)
        finally:
            try:
                if not published:
                    _cleanup_temporary_directory(
                        opened.descriptor,
                        temporary_fd,
                        opened.final_name if renamed else temporary_name,
                    )
            finally:
                os.close(temporary_fd)
    return opened.output_path / MANIFEST_FILENAME


def _validate_manifest(
    manifest: Mapping[str, Any],
) -> tuple[
    IntendedUse,
    ThresholdProvenance,
    TrainingProvenance,
    HistoricalReferenceProvenance | None,
]:
    required = {
        "bundle_format_version",
        "model_version",
        "operating_threshold",
        "score_type",
        "feature_schema",
        "training_data_fingerprint",
        "positive_class_label",
        "positive_class_index",
        "golden_probe",
        "runtime",
        "artifacts",
        "intended_use",
        "threshold_provenance",
        "training_provenance",
        "historical_reference_provenance",
    }
    if "bundle_format_version" not in manifest:
        raise ArtifactVerificationError("Bundle manifest is missing bundle_format_version.")
    if manifest["bundle_format_version"] != BUNDLE_FORMAT_VERSION:
        raise ArtifactVerificationError("Unsupported bundle_format_version.")
    if set(manifest) != required:
        raise ArtifactVerificationError("Bundle manifest fields are incomplete or unexpected.")
    if not isinstance(manifest["model_version"], str) or not manifest["model_version"].strip():
        raise ArtifactVerificationError("Invalid model_version.")
    if manifest["feature_schema"] != list(ALL_FEATURES):
        raise ArtifactVerificationError("Bundle feature schema/order mismatch.")
    if (
        manifest["positive_class_label"] != POSITIVE_CLASS_LABEL
        or manifest["positive_class_index"] != 1
    ):
        raise ArtifactVerificationError("Bundle positive-class mapping mismatch.")
    if not _SHA256_PATTERN.fullmatch(str(manifest["training_data_fingerprint"])):
        raise ArtifactVerificationError("Invalid training_data_fingerprint.")
    threshold = manifest["operating_threshold"]
    if (
        type(threshold) not in {int, float}
        or not np.isfinite(threshold)
        or not 0.0 <= float(threshold) <= 1.0
    ):
        raise ArtifactVerificationError("Invalid operating_threshold.")
    score_type = manifest["score_type"]
    if score_type not in {"raw_score", "calibrated_probability"}:
        raise ArtifactVerificationError("Unsupported bundle score_type.")
    try:
        intended_use = _parse_intended_use(manifest["intended_use"])
        threshold_provenance = _parse_threshold_provenance(manifest["threshold_provenance"])
        training_provenance = _parse_training_provenance(manifest["training_provenance"])
        historical_reference_value = manifest["historical_reference_provenance"]
        historical_reference = (
            None
            if historical_reference_value is None
            else _parse_historical_reference_provenance(historical_reference_value)
        )
        _validate_policy_binding(
            intended_use=intended_use,
            threshold_provenance=threshold_provenance,
            training_provenance=training_provenance,
            model_version=str(manifest["model_version"]),
            operating_threshold=float(threshold),
            score_type=str(score_type),
        )
        if manifest["training_data_fingerprint"] != training_provenance.data_roles_sha256:
            raise ValueError("training_data_fingerprint does not bind declared data roles.")
        _validate_historical_reference_binding(
            evidence_category=intended_use.evidence_category,
            historical_reference=historical_reference,
            data_roles=training_provenance.data_roles,
            quarantine=training_provenance.quarantine,
        )
    except ValueError as exc:
        raise ArtifactVerificationError(f"Bundle provenance validation failed: {exc}") from None
    artifacts = manifest["artifacts"]
    expected_artifacts = {"model", "preprocessor"}
    if score_type == "calibrated_probability":
        expected_artifacts.add("calibrator")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        raise ArtifactVerificationError("Bundle artifact set contradicts score_type.")
    for name, entry in artifacts.items():
        required_entry = {"filename", "sha256", "size_bytes", "python_type"}
        if not isinstance(entry, dict) or set(entry) != required_entry:
            raise ArtifactVerificationError(f"Artifact entry fields are invalid for {name}.")
        if (
            entry["filename"] != f"{name}.joblib"
            or Path(entry["filename"]).name != entry["filename"]
        ):
            raise ArtifactVerificationError(f"Unsafe artifact filename for {name}.")
        if not isinstance(entry["sha256"], str) or not _SHA256_PATTERN.fullmatch(entry["sha256"]):
            raise ArtifactVerificationError(f"Invalid artifact checksum for {name}.")
        if type(entry["size_bytes"]) is not int or entry["size_bytes"] <= 0:
            raise ArtifactVerificationError(f"Invalid artifact size for {name}.")
        if not isinstance(entry["python_type"], str) or not entry["python_type"].strip():
            raise ArtifactVerificationError(f"Invalid artifact type for {name}.")
    if intended_use.evidence_category == "historical_reference_demo_inference":
        if score_type != "raw_score" or "calibrator" in artifacts:
            raise ArtifactVerificationError(
                "Historical-reference demo bundles must be uncalibrated raw-score bundles."
            )

    golden = manifest["golden_probe"]
    golden_fields = {
        "calibrated_probability",
        "decision_score",
        "features",
        "raw_score",
        "sha256",
        "tolerance",
    }
    if not isinstance(golden, dict) or set(golden) != golden_fields:
        raise ArtifactVerificationError("Bundle golden probe is incomplete.")
    unsigned_golden = {key: value for key, value in golden.items() if key != "sha256"}
    if golden["sha256"] != _canonical_json_sha256(unsigned_golden):
        raise ArtifactVerificationError("Bundle golden probe checksum mismatch.")
    if golden["features"] != {
        feature: float(canonical_golden_frame().iloc[0][feature]) for feature in ALL_FEATURES
    }:
        raise ArtifactVerificationError("Bundle golden probe feature schema mismatch.")
    if golden["tolerance"] != GOLDEN_PROBE_TOLERANCE:
        raise ArtifactVerificationError("Bundle golden probe tolerance mismatch.")
    numerical = [golden["raw_score"], golden["decision_score"]]
    if golden["calibrated_probability"] is not None:
        numerical.append(golden["calibrated_probability"])
    if not all(isinstance(value, (int, float)) and np.isfinite(value) for value in numerical):
        raise ArtifactVerificationError("Bundle golden probe contains invalid scores.")

    runtime = manifest["runtime"]
    runtime_fields = {
        "python",
        "python_implementation",
        "platform",
        "machine",
        "dependencies",
    }
    if not isinstance(runtime, dict) or set(runtime) != runtime_fields:
        raise ArtifactVerificationError("Bundle runtime metadata is missing.")
    current_runtime = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    for field, current in current_runtime.items():
        if runtime[field] != current:
            raise ArtifactVerificationError(
                f"Runtime mismatch for {field}: bundle {runtime[field]!r}, current {current!r}."
            )
    expected_python = str(runtime["python"])
    if expected_python != platform.python_version():
        raise ArtifactVerificationError(
            f"Python runtime mismatch: bundle {expected_python}, "
            f"current {platform.python_version()}."
        )
    dependencies = runtime.get("dependencies")
    if not isinstance(dependencies, dict) or set(dependencies) != set(_RUNTIME_PACKAGES):
        raise ArtifactVerificationError("Bundle runtime dependencies are missing.")
    for package, current in _runtime_versions().items():
        if dependencies.get(package) != current:
            raise ArtifactVerificationError(
                f"Dependency mismatch for {package}: bundle {dependencies.get(package)!r}, "
                f"current {current!r}."
            )
    return intended_use, threshold_provenance, training_provenance, historical_reference


def _load_model_bundle_from_directory_fd(directory_fd: int) -> ModelBundle:
    manifest_bytes = _read_regular_file_at(directory_fd, MANIFEST_FILENAME, label="Bundle manifest")
    try:
        manifest = _strict_json_object(manifest_bytes, label="Bundle manifest")
        (
            intended_use,
            threshold_provenance,
            training_provenance,
            historical_reference,
        ) = _validate_manifest(manifest)
    except ValueError as exc:
        raise ArtifactVerificationError(f"Invalid bundle manifest: {exc}") from exc

    artifacts = manifest["artifacts"]
    artifact_bytes: dict[str, bytes] = {}
    for name in ("preprocessor", "model", "calibrator"):
        if name not in artifacts:
            continue
        entry = artifacts[name]
        encoded = _read_regular_file_at(
            directory_fd, entry["filename"], label=f"Bundle {name} artifact"
        )
        if len(encoded) != entry["size_bytes"]:
            raise ArtifactVerificationError(f"Artifact size mismatch for {name}.")
        if hashlib.sha256(encoded).hexdigest() != entry["sha256"]:
            raise ArtifactVerificationError(f"Artifact checksum mismatch for {name}.")
        artifact_bytes[name] = encoded

    loaded: dict[str, Any] = {}
    # Deserialization consumes the exact immutable bytes read through verified,
    # no-follow directory descriptors; no pathname is reopened after verification.
    for name in ("preprocessor", "model", "calibrator"):
        if name in artifact_bytes:
            loaded[name] = joblib.load(io.BytesIO(artifact_bytes[name]))
            actual_type = f"{type(loaded[name]).__module__}.{type(loaded[name]).__qualname__}"
            if actual_type != artifacts[name]["python_type"]:
                raise ArtifactVerificationError(f"Payload type mismatch for {name}.")

    bundle = ModelBundle(
        preprocessor=loaded["preprocessor"],
        model=loaded["model"],
        calibrator=loaded.get("calibrator"),
        operating_threshold=float(manifest["operating_threshold"]),
        feature_schema=tuple(manifest["feature_schema"]),
        training_data_fingerprint=str(manifest["training_data_fingerprint"]),
        model_version=str(manifest["model_version"]),
        intended_use=intended_use,
        threshold_provenance=threshold_provenance,
        training_provenance=training_provenance,
        score_type=cast(ScoreType, manifest["score_type"]),
        historical_reference_provenance=historical_reference,
        model_artifact_sha256=str(artifacts["model"]["sha256"]),
    )
    try:
        bundle.validate()
    except ValueError:
        raise ArtifactVerificationError("Bundle semantic validation failed.") from None
    verify_bundle_golden_probe(bundle, manifest["golden_probe"])
    return bundle


def load_model_bundle(
    manifest_path: str | Path,
    *,
    trusted_root: str | Path,
) -> ModelBundle:
    """Validate exact retained bytes, then deserialize without reopening paths."""
    if Path(manifest_path).name != MANIFEST_FILENAME:
        raise ArtifactVerificationError(f"Expected manifest filename '{MANIFEST_FILENAME}'.")
    with _open_trusted_parent(manifest_path, trusted_root) as opened:
        if opened.filename != MANIFEST_FILENAME:
            raise ArtifactVerificationError(f"Expected manifest filename '{MANIFEST_FILENAME}'.")
        return _load_model_bundle_from_directory_fd(opened.descriptor)
