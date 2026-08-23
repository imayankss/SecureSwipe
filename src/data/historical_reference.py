"""Fail-closed creation of the quarantined historical-reference demo bundle."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Iterator

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler

from src.artifacts.bundle import (
    HistoricalReferenceFileIdentity,
    HistoricalReferencePool,
    HistoricalReferenceSourceIdentity,
    ModelBundle,
    data_role_metadata,
    historical_reference_provenance_metadata,
    intended_use_metadata,
    quarantine_provenance_metadata,
    save_model_bundle,
    threshold_provenance_metadata,
    training_provenance_metadata,
)
from src.data.data_loader import validate_dataset_schema
from src.data.historical_quarantine import (
    FEATURE_DTYPE,
    TARGET_DTYPE,
    HistoricalTestQuarantine,
    canonical_row_hashes,
    load_historical_quarantine_manifest,
    row_hashes_checksum,
)
from src.models.advanced_models import XGBClassifier
from src.preprocessing.feature_config import ALL_FEATURES, PCA_FEATURES, REQUIRED_COLUMNS, TARGET_COLUMN
from src.preprocessing.preprocessors import fit_preprocessor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORICAL_REFERENCE_RECIPE = (
    PROJECT_ROOT / "configs" / "historical_reference_demo_recipe.json"
)
HISTORICAL_REFERENCE_RECIPE_FORMAT_VERSION = "1"
HISTORICAL_REFERENCE_POLICY = "historical_reference_demo_v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_KEYS = ("x_train", "y_train", "x_val", "y_val")
_SOURCE_FILENAMES = {
    "x_train": "X_train.parquet",
    "y_train": "y_train.parquet",
    "x_val": "X_val.parquet",
    "y_val": "y_val.parquet",
}
_SOURCE_FIELDS = {"filename", "sha256", "size_bytes", "row_count", "fraud_count"}
_RECIPE_FIELDS = {
    "approval_status",
    "candidate_identity_status",
    "candidate_sources",
    "conflicting_feature_identical_labels",
    "cross_split_identical_labeled_rows",
    "duplicate_policy",
    "dtype_contract",
    "feature_schema",
    "filtering",
    "final_training_pool",
    "format_version",
    "model",
    "model_version",
    "expected_cross_split_duplicate_count",
    "post_quarantine_split_roles",
    "preprocessing",
    "producer_policy",
    "quarantine",
    "quarantine_overlap_policy",
    "recipe_kind",
    "threshold",
    "training_pool",
}
_FILTERING_FIELDS = {
    "quarantine_occurrences_removed",
    "duplicate_rows_removed",
    "cross_split_duplicate_rows_removed",
    "feature_label_conflicts",
}
_POOL_FIELDS = {
    "row_hashes_sha256",
    "total_row_count",
    "legitimate_row_count",
    "fraud_count",
    "unique_row_count",
    "duplicate_row_count",
}
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_FEATURE_HASH_DOMAIN = b"SecureSwipe historical reference feature vector v1\x00"
_PREPROCESSING_RECIPE = {
    "scale_features": ["Time", "Amount"],
    "passthrough_features": list(PCA_FEATURES),
    "scaler": {"copy": True, "with_mean": True, "with_std": True},
    "column_transformer": {
        "n_jobs": None,
        "remainder": "drop",
        "sparse_threshold": 0.3,
        "transformer_weights": None,
        "verbose": False,
        "verbose_feature_names_out": False,
    },
}
_XGBOOST_STATIC_PARAMETERS: dict[str, object] = {
    "objective": "binary:logistic",
    "base_score": None,
    "booster": None,
    "callbacks": None,
    "colsample_bylevel": None,
    "colsample_bynode": None,
    "colsample_bytree": 0.8,
    "device": None,
    "early_stopping_rounds": None,
    "enable_categorical": True,
    "eval_metric": "aucpr",
    "feature_types": None,
    "feature_weights": None,
    "gamma": None,
    "grow_policy": None,
    "importance_type": None,
    "interaction_constraints": None,
    "learning_rate": 0.05,
    "max_bin": None,
    "max_cat_threshold": None,
    "max_cat_to_onehot": None,
    "max_delta_step": None,
    "max_depth": 4,
    "max_leaves": None,
    "min_child_weight": None,
    "missing": None,
    "monotone_constraints": None,
    "multi_strategy": None,
    "n_estimators": 300,
    "n_jobs": 1,
    "num_parallel_tree": None,
    "random_state": 42,
    "reg_alpha": None,
    "reg_lambda": None,
    "sampling_method": None,
    "subsample": 0.8,
    "tree_method": "hist",
    "validate_parameters": None,
    "verbosity": None,
}
_XGBOOST_PARAMETER_FIELDS = frozenset((*_XGBOOST_STATIC_PARAMETERS, "scale_pos_weight"))


@dataclass(frozen=True)
class SourceExpectation:
    key: str
    filename: str
    sha256: str
    size_bytes: int
    row_count: int
    fraud_count: int | None


@dataclass(frozen=True)
class FilteringExpectation:
    quarantine_occurrences_removed: int
    duplicate_rows_removed: int
    cross_split_duplicate_rows_removed: int
    feature_label_conflicts: int


@dataclass(frozen=True)
class PoolExpectation:
    row_hashes_sha256: str
    total_row_count: int
    legitimate_row_count: int
    fraud_row_count: int
    unique_row_count: int
    duplicate_row_count: int


@dataclass(frozen=True)
class HistoricalReferenceRecipe:
    retained: "_RetainedFile"
    model_version: str
    model_parameters: tuple[tuple[str, object], ...]
    sources: tuple[SourceExpectation, ...]
    filtering: FilteringExpectation
    pool: PoolExpectation
    quarantine_anchor_sha256: str
    quarantine_row_hashes_sha256: str
    quarantine_total_row_count: int
    quarantine_fraud_count: int
    quarantine_unique_row_count: int
    quarantine_duplicate_row_count: int
    expected_cross_split_duplicate_count: int

    def source(self, key: str) -> SourceExpectation:
        return next(source for source in self.sources if source.key == key)


@dataclass(frozen=True)
class _RetainedFile:
    path: Path
    encoded: bytes
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class _FilteredSplit:
    frame: pd.DataFrame
    quarantine_occurrences_removed: int


@dataclass(frozen=True)
class _FinalFittingPool:
    frame: pd.DataFrame
    duplicate_rows_removed: int
    cross_split_duplicate_rows_removed: int


def _without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _strict_json(encoded: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=_without_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} must be strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _require_nonnegative_int(value: object, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return value


def _dtype_contract() -> dict[str, object]:
    return {
        "features": {feature: FEATURE_DTYPE for feature in ALL_FEATURES},
        "target": {TARGET_COLUMN: TARGET_DTYPE},
    }


def _require_safe_io_primitives() -> None:
    if (
        not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        raise RuntimeError("Historical reference I/O requires no-follow directory descriptors.")


def _absolute_parts(path: str | Path) -> tuple[Path, tuple[str, ...]]:
    candidate = Path(os.path.abspath(os.fspath(Path(path).expanduser())))
    if not candidate.is_absolute() or not candidate.parts or candidate.parts[0] != os.sep:
        raise ValueError("Historical reference path must resolve to an absolute POSIX path.")
    parts = candidate.parts[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Historical reference path is malformed.")
    return candidate, parts


@contextmanager
def _open_regular_file_no_follow(path: str | Path, *, label: str) -> Iterator[tuple[int, Path]]:
    _require_safe_io_primitives()
    candidate, parts = _absolute_parts(path)
    descriptors: list[int] = []
    try:
        parent_fd = os.open(os.sep, _DIRECTORY_FLAGS)
        descriptors.append(parent_fd)
        for part in parts[:-1]:
            child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            descriptors.append(child_fd)
            parent_fd = child_fd
        descriptor = os.open(parts[-1], _FILE_FLAGS, dir_fd=parent_fd)
        descriptors.append(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} must be a regular file.")
        yield descriptor, candidate
    except OSError as exc:
        raise ValueError(f"{label} is unavailable or contains a symbolic-link component.") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _retained_file(path: str | Path, *, label: str, suffix: str) -> _RetainedFile:
    if Path(path).suffix.lower() != suffix:
        raise ValueError(f"{label} must have {suffix} suffix.")
    with _open_regular_file_no_follow(path, label=label) as (descriptor, resolved):
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
    encoded = b"".join(chunks)
    return _RetainedFile(
        path=resolved,
        encoded=encoded,
        sha256=hashlib.sha256(encoded).hexdigest(),
        size_bytes=len(encoded),
    )


def _reverify_retained_file(retained: _RetainedFile, *, label: str, suffix: str) -> None:
    current = _retained_file(retained.path, label=label, suffix=suffix)
    if current.sha256 != retained.sha256 or current.size_bytes != retained.size_bytes:
        raise ValueError(f"{label} changed after verification.")


def _parse_source(key: str, value: object) -> SourceExpectation:
    if not isinstance(value, dict) or set(value) != _SOURCE_FIELDS:
        raise ValueError(f"Historical reference source {key} fields are incomplete or unexpected.")
    expected_filename = _SOURCE_FILENAMES[key]
    if value["filename"] != expected_filename:
        raise ValueError(f"Historical reference source {key} filename is not canonical.")
    row_count = _require_nonnegative_int(value["row_count"], label=f"{key}.row_count")
    fraud = value["fraud_count"]
    if key.startswith("x_"):
        if fraud is not None:
            raise ValueError(f"Historical reference feature source {key} must not claim labels.")
    else:
        fraud = _require_nonnegative_int(fraud, label=f"{key}.fraud_count")
        if fraud > row_count:
            raise ValueError(f"Historical reference source {key} fraud count is inconsistent.")
    return SourceExpectation(
        key=key,
        filename=expected_filename,
        sha256=_require_sha256(value["sha256"], label=f"{key}.sha256"),
        size_bytes=_require_nonnegative_int(value["size_bytes"], label=f"{key}.size_bytes"),
        row_count=row_count,
        fraud_count=fraud,
    )


def _parse_recipe(retained: _RetainedFile) -> HistoricalReferenceRecipe:
    payload = _strict_json(retained.encoded, label="Historical reference recipe")
    if set(payload) != _RECIPE_FIELDS:
        raise ValueError("Historical reference recipe fields are incomplete or unexpected.")
    if payload["approval_status"] not in {"approved", "unapproved"}:
        raise ValueError("Historical reference recipe approval_status is invalid.")
    if payload["candidate_identity_status"] != "pending_independent_verification":
        raise ValueError("Historical reference candidate identity status is invalid.")
    if payload["format_version"] != HISTORICAL_REFERENCE_RECIPE_FORMAT_VERSION:
        raise ValueError("Unsupported historical reference recipe format_version.")
    if (
        payload["recipe_kind"] != "historical_reference_demo_bundle"
        or payload["producer_policy"] != HISTORICAL_REFERENCE_POLICY
        or payload["feature_schema"] != list(ALL_FEATURES)
        or payload["dtype_contract"] != _dtype_contract()
        or payload["quarantine_overlap_policy"] != "filter_all_occurrences_before_construction"
        or payload["duplicate_policy"]
        != "filter_quarantine_then_global_keep_first_train_then_validation"
        or payload["cross_split_identical_labeled_rows"]
        != "deduplicate_deterministically_into_final_fitting_pool"
        or payload["conflicting_feature_identical_labels"] != "reject"
        or payload["post_quarantine_split_roles"]
        != "abolished_merged_fitting_pool_only_no_evaluation"
        or payload["final_training_pool"]
        != "quarantine_filtered_train_then_validation_global_keep_first_deduplicated_fitting_pool"
    ):
        raise ValueError("Historical reference recipe contract is invalid.")
    if payload["preprocessing"] != _PREPROCESSING_RECIPE:
        raise ValueError("Historical reference preprocessing configuration is invalid.")
    model_payload = payload["model"]
    if (
        not isinstance(model_payload, dict)
        or set(model_payload) != {"family", "parameters"}
        or model_payload["family"] != "xgboost_binary_classifier"
        or not isinstance(model_payload["parameters"], dict)
        or set(model_payload["parameters"]) != _XGBOOST_PARAMETER_FIELDS
    ):
        raise ValueError("Historical reference model configuration contradicts the fixed recipe.")
    model_parameters = model_payload["parameters"]
    if any(
        model_parameters[name] != value
        for name, value in _XGBOOST_STATIC_PARAMETERS.items()
    ):
        raise ValueError("Historical reference model parameters are incomplete or non-canonical.")
    model_version = payload["model_version"]
    if not isinstance(model_version, str) or not re.fullmatch(
        r"historical-reference-[a-z0-9.-]+-demo-v[0-9]+", model_version
    ):
        raise ValueError("Historical reference model_version is invalid.")
    if payload["threshold"] != {
        "value": 0.53, "source": "historical_validation_selected_threshold",
        "historical_component_linkage": "unverified", "purpose": "demo_human_review_policy_only",
        "calibrated": False, "cost_optimal": False, "razorpay_approved": False,
        "production_approved": False,
    }:
        raise ValueError("Historical reference threshold is not the fixed demo-review policy.")
    sources_payload = payload["candidate_sources"]
    if not isinstance(sources_payload, dict) or set(sources_payload) != set(_SOURCE_KEYS):
        raise ValueError("Historical reference source fields are invalid.")
    sources = tuple(_parse_source(key, sources_payload[key]) for key in _SOURCE_KEYS)
    if sources[0].row_count != sources[1].row_count or sources[2].row_count != sources[3].row_count:
        raise ValueError("Historical reference feature and label source counts disagree.")
    filtering_payload = payload["filtering"]
    if not isinstance(filtering_payload, dict) or set(filtering_payload) != _FILTERING_FIELDS:
        raise ValueError("Historical reference filtering fields are invalid.")
    filtering = FilteringExpectation(**{
        field: _require_nonnegative_int(filtering_payload[field], label=f"filtering.{field}")
        for field in _FILTERING_FIELDS
    })
    if filtering.feature_label_conflicts != 0:
        raise ValueError("Historical reference recipe must declare zero feature-label conflicts.")
    expected_cross_split_duplicates = _require_nonnegative_int(
        payload["expected_cross_split_duplicate_count"],
        label="expected_cross_split_duplicate_count",
    )
    if filtering.cross_split_duplicate_rows_removed != expected_cross_split_duplicates:
        raise ValueError(
            "Historical reference cross-split duplicate count contradicts filtering evidence."
        )
    if filtering.cross_split_duplicate_rows_removed > filtering.duplicate_rows_removed:
        raise ValueError(
            "Historical reference cross-split duplicate count exceeds all duplicates removed."
        )
    pool_payload = payload["training_pool"]
    if not isinstance(pool_payload, dict) or set(pool_payload) != _POOL_FIELDS:
        raise ValueError("Historical reference final-pool fields are invalid.")
    pool = PoolExpectation(
        row_hashes_sha256=_require_sha256(pool_payload["row_hashes_sha256"], label="pool.sha256"),
        total_row_count=_require_nonnegative_int(pool_payload["total_row_count"], label="pool.total"),
        legitimate_row_count=_require_nonnegative_int(pool_payload["legitimate_row_count"], label="pool.legitimate"),
        fraud_row_count=_require_nonnegative_int(pool_payload["fraud_count"], label="pool.fraud"),
        unique_row_count=_require_nonnegative_int(pool_payload["unique_row_count"], label="pool.unique"),
        duplicate_row_count=_require_nonnegative_int(pool_payload["duplicate_row_count"], label="pool.duplicates"),
    )
    input_rows = sources[0].row_count + sources[2].row_count
    if (
        pool.total_row_count != pool.legitimate_row_count + pool.fraud_row_count
        or pool.total_row_count != pool.unique_row_count + pool.duplicate_row_count
        or input_rows != pool.total_row_count + filtering.quarantine_occurrences_removed + filtering.duplicate_rows_removed
    ):
        raise ValueError("Historical reference final-pool accounting is inconsistent.")
    scale_pos_weight = model_parameters["scale_pos_weight"]
    if (
        type(scale_pos_weight) not in {int, float}
        or not np.isfinite(scale_pos_weight)
        or scale_pos_weight <= 0
        or pool.fraud_row_count == 0
        or float(scale_pos_weight)
        != pool.legitimate_row_count / pool.fraud_row_count
    ):
        raise ValueError("Historical reference scale_pos_weight is not bound to the fixed pool.")
    quarantine = payload["quarantine"]
    required_quarantine = {"anchor_sha256", "row_hashes_sha256", "total_row_count", "fraud_count", "unique_row_count", "duplicate_row_count"}
    if not isinstance(quarantine, dict) or set(quarantine) != required_quarantine:
        raise ValueError("Historical reference quarantine identity is invalid.")
    counts = {key: _require_nonnegative_int(quarantine[key], label=f"quarantine.{key}") for key in required_quarantine - {"anchor_sha256", "row_hashes_sha256"}}
    if counts["total_row_count"] != counts["unique_row_count"] + counts["duplicate_row_count"]:
        raise ValueError("Historical reference quarantine counts are inconsistent.")
    recipe = HistoricalReferenceRecipe(
        retained=retained, model_version=model_version,
        model_parameters=tuple(sorted(model_parameters.items())), sources=sources, filtering=filtering, pool=pool,
        quarantine_anchor_sha256=_require_sha256(quarantine["anchor_sha256"], label="quarantine.anchor"),
        quarantine_row_hashes_sha256=_require_sha256(quarantine["row_hashes_sha256"], label="quarantine.row_hashes"),
        quarantine_total_row_count=counts["total_row_count"], quarantine_fraud_count=counts["fraud_count"],
        quarantine_unique_row_count=counts["unique_row_count"], quarantine_duplicate_row_count=counts["duplicate_row_count"],
        expected_cross_split_duplicate_count=expected_cross_split_duplicates,
    )
    if payload["approval_status"] != "approved":
        raise ValueError("Historical reference recipe is unapproved; refusing before opening historical Parquet inputs.")
    return recipe


def load_historical_reference_recipe() -> HistoricalReferenceRecipe:
    return _parse_recipe(_retained_file(DEFAULT_HISTORICAL_REFERENCE_RECIPE, label="Canonical historical reference recipe", suffix=".json"))


def _read_checked_parquet(path: str | Path, expectation: SourceExpectation) -> _RetainedFile:
    if Path(path).name != expectation.filename:
        raise ValueError(f"Historical reference input {expectation.key} filename is not approved.")
    retained = _retained_file(path, label=f"Historical reference input {expectation.key}", suffix=".parquet")
    if retained.sha256 != expectation.sha256 or retained.size_bytes != expectation.size_bytes:
        raise ValueError(f"Historical reference input {expectation.key} does not match the approved identity.")
    return retained


def _validate_split(x_file: _RetainedFile, y_file: _RetainedFile, x_expected: SourceExpectation, y_expected: SourceExpectation) -> pd.DataFrame:
    x_frame = pd.read_parquet(io.BytesIO(x_file.encoded))
    y_frame = pd.read_parquet(io.BytesIO(y_file.encoded))
    if not isinstance(x_frame, pd.DataFrame) or list(x_frame.columns) != list(ALL_FEATURES):
        raise ValueError("Historical reference features must use canonical ALL_FEATURES order.")
    if not isinstance(y_frame, pd.DataFrame) or list(y_frame.columns) != [TARGET_COLUMN]:
        raise ValueError("Historical reference labels must contain only Class.")
    if len(x_frame) != len(y_frame) or not x_frame.index.equals(y_frame.index) or not x_frame.index.is_unique:
        raise ValueError("Historical reference features and labels are not exactly unique-index aligned.")
    if any(np.dtype(x_frame[column].dtype) != np.dtype(FEATURE_DTYPE) for column in ALL_FEATURES):
        raise ValueError("Historical reference features must use exact float64 dtypes.")
    if np.dtype(y_frame[TARGET_COLUMN].dtype) != np.dtype(TARGET_DTYPE):
        raise ValueError("Historical reference labels must use exact int64 dtype.")
    frame = x_frame.copy()
    frame[TARGET_COLUMN] = y_frame[TARGET_COLUMN]
    frame = frame[REQUIRED_COLUMNS]
    validate_dataset_schema(frame, reject_duplicate_rows=False)
    if len(frame) != x_expected.row_count or len(frame) != y_expected.row_count or int(frame[TARGET_COLUMN].sum()) != y_expected.fraud_count:
        raise ValueError("Historical reference source counts do not match the fixed recipe.")
    return frame


def _feature_only_hashes(frame: pd.DataFrame) -> list[str]:
    values = np.ascontiguousarray(frame[ALL_FEATURES].to_numpy(copy=True), dtype=np.dtype("<f8"))
    return [hashlib.sha256(_FEATURE_HASH_DOMAIN + row.tobytes(order="C")).hexdigest() for row in values]


def _reject_feature_label_conflicts(*frames: pd.DataFrame) -> None:
    labels_by_feature: dict[str, int] = {}
    for frame in frames:
        for feature_hash, label in zip(_feature_only_hashes(frame), frame[TARGET_COLUMN].tolist(), strict=True):
            previous = labels_by_feature.setdefault(feature_hash, int(label))
            if previous != int(label):
                raise ValueError("Historical reference contains contradictory labels for one feature vector.")


def _filter_quarantine(frame: pd.DataFrame, quarantine: HistoricalTestQuarantine) -> _FilteredSplit:
    hashes = canonical_row_hashes(frame)
    keep_after_quarantine = [row_hash not in quarantine.row_hashes for row_hash in hashes]
    filtered = frame.iloc[np.flatnonzero(keep_after_quarantine)].copy()
    return _FilteredSplit(filtered, len(frame) - len(filtered))


def _deduplicate_final_fitting_pool(
    train: pd.DataFrame, validation: pd.DataFrame
) -> _FinalFittingPool:
    """Keep first occurrences globally in canonical train-then-validation order."""
    train_hashes = canonical_row_hashes(train)
    validation_hashes = canonical_row_hashes(validation)
    seen_train: set[str] = set()
    train_keep: list[bool] = []
    for row_hash in train_hashes:
        train_keep.append(row_hash not in seen_train)
        seen_train.add(row_hash)
    seen_validation: set[str] = set()
    validation_keep: list[bool] = []
    cross_split_duplicates = 0
    for row_hash in validation_hashes:
        if row_hash in seen_validation:
            validation_keep.append(False)
            continue
        seen_validation.add(row_hash)
        if row_hash in seen_train:
            cross_split_duplicates += 1
            validation_keep.append(False)
            continue
        validation_keep.append(True)
    train_unique = train.iloc[np.flatnonzero(train_keep)].copy()
    validation_unique = validation.iloc[np.flatnonzero(validation_keep)].copy()
    pool = pd.concat((train_unique, validation_unique), axis=0, ignore_index=True)
    duplicate_rows_removed = len(train) + len(validation) - len(pool)
    return _FinalFittingPool(pool, duplicate_rows_removed, cross_split_duplicates)


def _validate_quarantine(recipe: HistoricalReferenceRecipe, quarantine: HistoricalTestQuarantine) -> None:
    if (
        quarantine.anchor_sha256, quarantine.row_hashes_sha256, quarantine.total_row_count, quarantine.fraud_count,
        quarantine.unique_row_count, quarantine.duplicate_row_count,
    ) != (
        recipe.quarantine_anchor_sha256, recipe.quarantine_row_hashes_sha256, recipe.quarantine_total_row_count,
        recipe.quarantine_fraud_count, recipe.quarantine_unique_row_count, recipe.quarantine_duplicate_row_count,
    ):
        raise ValueError("Approved historical quarantine does not match the fixed reference recipe.")


def _verified_quarantine_file(quarantine: HistoricalTestQuarantine) -> _RetainedFile:
    retained = _retained_file(quarantine.manifest_path, label="Historical quarantine manifest", suffix=".json")
    if retained.sha256 != quarantine.manifest_sha256 or retained.size_bytes != quarantine.manifest_size_bytes:
        raise ValueError("Historical quarantine manifest changed after validation.")
    return retained


def _approved_output_path(output: str | Path) -> Path:
    candidate = Path(output)
    if candidate.is_absolute() or PureWindowsPath(str(output)).is_absolute() or bool(PureWindowsPath(str(output)).drive):
        raise ValueError("Historical reference output must be a relative ignored artifacts/ path.")
    if any(part in {"", ".", ".."} or "\\" in part for part in candidate.parts) or len(candidate.parts) < 2 or candidate.parts[0] != "artifacts":
        raise ValueError("Historical reference output path is unsafe or outside ignored artifacts/.")
    return PROJECT_ROOT.joinpath(*candidate.parts)


def _pool_identity(frame: pd.DataFrame) -> PoolExpectation:
    hashes = canonical_row_hashes(frame)
    total = len(hashes)
    fraud = int(frame[TARGET_COLUMN].sum())
    unique = len(set(hashes))
    return PoolExpectation(row_hashes_checksum(hashes), total, total - fraud, fraud, unique, total - unique)


def _build_exact_preprocessor() -> Any:
    scaler = StandardScaler(copy=True, with_mean=True, with_std=True)
    preprocessor = ColumnTransformer(
        transformers=[
            ("scaler", scaler, ["Time", "Amount"]),
            ("passthrough", "passthrough", list(PCA_FEATURES)),
        ],
        remainder="drop",
        sparse_threshold=0.3,
        n_jobs=None,
        transformer_weights=None,
        verbose=False,
        verbose_feature_names_out=False,
    )
    actual_transformers = [
        (name, list(columns)) for name, _transformer, columns in preprocessor.transformers
    ]
    actual_parameters = {
        key: preprocessor.get_params(deep=False)[key]
        for key in _PREPROCESSING_RECIPE["column_transformer"]
    }
    if (
        actual_transformers
        != [("scaler", ["Time", "Amount"]), ("passthrough", list(PCA_FEATURES))]
        or scaler.get_params(deep=False) != _PREPROCESSING_RECIPE["scaler"]
        or actual_parameters != _PREPROCESSING_RECIPE["column_transformer"]
    ):
        raise ValueError("Constructed preprocessor contradicts the fixed historical reference recipe.")
    return preprocessor


def _build_exact_model(recipe: HistoricalReferenceRecipe) -> Any:
    if XGBClassifier is None:
        raise ImportError("xgboost is required for the historical-reference demo runner.")
    parameters = dict(recipe.model_parameters)
    model = XGBClassifier(**parameters)
    if model.get_params(deep=False) != parameters:
        raise ValueError("Constructed XGBoost model contradicts the fixed historical reference recipe.")
    return model


def create_historical_reference_demo_bundle(*, x_train: str | Path, y_train: str | Path, x_val: str | Path, y_val: str | Path, historical_quarantine: str | Path, output: str | Path) -> Path:
    """Create one bundle only after every fixed, approved check has passed."""
    recipe = load_historical_reference_recipe()
    output_path = _approved_output_path(output)
    quarantine = load_historical_quarantine_manifest(historical_quarantine)
    _validate_quarantine(recipe, quarantine)
    quarantine_file = _verified_quarantine_file(quarantine)
    x_train_file = _read_checked_parquet(x_train, recipe.source("x_train"))
    y_train_file = _read_checked_parquet(y_train, recipe.source("y_train"))
    x_val_file = _read_checked_parquet(x_val, recipe.source("x_val"))
    y_val_file = _read_checked_parquet(y_val, recipe.source("y_val"))
    train_frame = _validate_split(x_train_file, y_train_file, recipe.source("x_train"), recipe.source("y_train"))
    validation_frame = _validate_split(x_val_file, y_val_file, recipe.source("x_val"), recipe.source("y_val"))
    _reject_feature_label_conflicts(train_frame, validation_frame)
    train = _filter_quarantine(train_frame, quarantine)
    validation = _filter_quarantine(validation_frame, quarantine)
    final_fitting_pool = _deduplicate_final_fitting_pool(train.frame, validation.frame)
    pool = final_fitting_pool.frame
    actual_pool = _pool_identity(pool)
    actual_filtering = FilteringExpectation(
        train.quarantine_occurrences_removed + validation.quarantine_occurrences_removed,
        final_fitting_pool.duplicate_rows_removed,
        final_fitting_pool.cross_split_duplicate_rows_removed,
        0,
    )
    pool_hashes = set(canonical_row_hashes(pool))
    if (
        actual_pool != recipe.pool
        or actual_filtering != recipe.filtering
        or actual_filtering.cross_split_duplicate_rows_removed
        != recipe.expected_cross_split_duplicate_count
        or not pool_hashes.isdisjoint(quarantine.row_hashes)
    ):
        raise ValueError("Historical reference filtering or final pool does not match the fixed recipe.")
    features = pool[ALL_FEATURES]
    labels = pool[TARGET_COLUMN]
    preprocessor = fit_preprocessor(features, _build_exact_preprocessor())
    preprocessor.set_output(transform="pandas")
    model = _build_exact_model(recipe)
    model.fit(preprocessor.transform(features), labels)
    model_fit = data_role_metadata(fingerprint_sha256=actual_pool.row_hashes_sha256, total_row_count=actual_pool.total_row_count, fraud_row_count=actual_pool.fraud_row_count, duplicate_row_count=actual_pool.duplicate_row_count)
    quarantine_metadata = quarantine_provenance_metadata(anchor_sha256=quarantine.anchor_sha256, row_hashes_sha256=quarantine.row_hashes_sha256, total_row_count=quarantine.total_row_count, fraud_row_count=quarantine.fraud_count, unique_row_count=quarantine.unique_row_count, duplicate_row_count=quarantine.duplicate_row_count, overlap_row_count=0)
    provenance = training_provenance_metadata(producer_policy=HISTORICAL_REFERENCE_POLICY, model_fit=model_fit, calibrator_fit=None, threshold_selection=None, evaluation=None, quarantine=quarantine_metadata)
    historical_reference = historical_reference_provenance_metadata(
        recipe=HistoricalReferenceFileIdentity(recipe.retained.path.name, recipe.retained.sha256, recipe.retained.size_bytes),
        sources=tuple(HistoricalReferenceSourceIdentity(source.filename, source.sha256, source.size_bytes, source.row_count, source.fraud_count) for source in recipe.sources),
        quarantine=quarantine_metadata,
        quarantine_occurrences_removed=actual_filtering.quarantine_occurrences_removed,
        duplicate_rows_removed=actual_filtering.duplicate_rows_removed,
        cross_split_duplicate_rows_removed=(
            actual_filtering.cross_split_duplicate_rows_removed
        ),
        feature_label_conflicts=0,
        final_pool=HistoricalReferencePool(actual_pool.row_hashes_sha256, actual_pool.total_row_count, actual_pool.legitimate_row_count, actual_pool.fraud_row_count, actual_pool.unique_row_count, actual_pool.duplicate_row_count),
    )
    bundle = ModelBundle(preprocessor=preprocessor, model=model, calibrator=None, operating_threshold=0.53, feature_schema=tuple(ALL_FEATURES), training_data_fingerprint=provenance.data_roles_sha256, model_version=recipe.model_version, intended_use=intended_use_metadata(HISTORICAL_REFERENCE_POLICY), threshold_provenance=threshold_provenance_metadata(producer_policy=HISTORICAL_REFERENCE_POLICY, value=0.53, calibrated=False), training_provenance=provenance, score_type="raw_score", historical_reference_provenance=historical_reference)
    _reverify_retained_file(recipe.retained, label="Historical reference recipe", suffix=".json")
    _reverify_retained_file(quarantine_file, label="Historical quarantine manifest", suffix=".json")
    return save_model_bundle(bundle, output_path)
