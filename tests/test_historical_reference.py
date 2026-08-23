"""Synthetic-only tests for the fail-closed historical-reference runner."""

from __future__ import annotations

import json
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import src.data.historical_reference as reference_module
from src.artifacts import bundle as bundle_module
from src.artifacts.bundle import load_model_bundle, sha256_file
from src.data.historical_quarantine import (
    canonical_row_hashes,
    load_historical_quarantine_manifest,
    row_hashes_checksum,
)
from src.preprocessing.feature_config import ALL_FEATURES, REQUIRED_COLUMNS
from tests.historical_quarantine_helpers import (
    SYNTHETIC_QUARANTINE_FRAUD,
    SYNTHETIC_QUARANTINE_ROWS,
    approved_quarantine_environment,
    write_nonoverlapping_quarantine,
)


class _NoHistoricalPredictionModel:
    """Estimator that fails if the runner tries to score more than its golden row."""

    def __init__(self, **parameters: object) -> None:
        self.parameters = parameters

    def get_params(self, deep: bool = True) -> dict[str, object]:
        return dict(self.parameters)

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> "_NoHistoricalPredictionModel":
        self.feature_names_in_ = np.asarray(features.columns, dtype=object)
        self.n_features_in_ = len(features.columns)
        self.classes_ = np.asarray([0, 1], dtype=np.int64)
        self.fit_row_count = len(labels)
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        if len(features) != 1:
            raise AssertionError("Historical rows must never be scored by this runner.")
        return np.asarray([[0.75, 0.25]], dtype=float)


class _ReplaceVerifiedFileModel(_NoHistoricalPredictionModel):
    def __init__(self, path: Path, **parameters: object) -> None:
        super().__init__(**parameters)
        self.path = path

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> "_ReplaceVerifiedFileModel":
        super().fit(features, labels)
        self.path.write_bytes(self.path.read_bytes() + b" ")
        return self


@contextmanager
def _synthetic_recipe_policy(recipe: Path):
    """Bind a temporary synthetic recipe only inside this synthetic test process."""
    original = bundle_module._producer_policy
    digest = sha256_file(recipe)
    payload = json.loads(recipe.read_text(encoding="utf-8"))
    source_keys = ("x_train", "y_train", "x_val", "y_val")
    sources = tuple(
        bundle_module.HistoricalReferenceSourceIdentity(
            payload["candidate_sources"][key]["filename"],
            payload["candidate_sources"][key]["sha256"],
            payload["candidate_sources"][key]["size_bytes"],
            payload["candidate_sources"][key]["row_count"],
            payload["candidate_sources"][key]["fraud_count"],
        )
        for key in source_keys
    )
    quarantine_payload = payload["quarantine"]
    quarantine = bundle_module.QuarantineProvenance(
        quarantine_payload["anchor_sha256"],
        quarantine_payload["row_hashes_sha256"],
        quarantine_payload["total_row_count"],
        quarantine_payload["fraud_count"],
        quarantine_payload["unique_row_count"],
        quarantine_payload["duplicate_row_count"],
        0,
    )
    pool_payload = payload["training_pool"]
    provenance = bundle_module.HistoricalReferenceProvenance(
        bundle_module.HISTORICAL_REFERENCE_PROVENANCE_FORMAT_VERSION,
        bundle_module.HistoricalReferenceFileIdentity(
            "historical_reference_demo_recipe.json", digest, recipe.stat().st_size
        ),
        sources,
        quarantine,
        bundle_module.HistoricalReferenceFiltering(**payload["filtering"]),
        bundle_module.HistoricalReferencePool(
            pool_payload["row_hashes_sha256"],
            pool_payload["total_row_count"],
            pool_payload["legitimate_row_count"],
            pool_payload["fraud_count"],
            pool_payload["unique_row_count"],
            pool_payload["duplicate_row_count"],
        ),
    )
    evidence_digest = bundle_module._historical_reference_evidence_sha256(provenance)

    def policy(policy_id: str):
        value = deepcopy(original(policy_id))
        if policy_id == reference_module.HISTORICAL_REFERENCE_POLICY:
            value["canonical_recipe_sha256"] = digest
            value["canonical_reference_evidence_sha256"] = evidence_digest
        return value

    with patch.object(bundle_module, "_producer_policy", side_effect=policy):
        yield


def _frame(rows: list[tuple[float, int]], *, index_start: int) -> pd.DataFrame:
    values = np.zeros((len(rows), len(ALL_FEATURES)), dtype=np.float64)
    result = pd.DataFrame(values, columns=ALL_FEATURES)
    for position, (marker, label) in enumerate(rows):
        result.loc[position, "Time"] = marker
        result.loc[position, "Amount"] = marker + 0.5
        result.loc[position, "V1"] = marker / 10.0
        result.loc[position, "Class"] = label
    result["Class"] = result["Class"].astype(np.int64)
    result.index = pd.Index(range(index_start, index_start + len(result)), name="row_id")
    return result[REQUIRED_COLUMNS]


def _write_split(directory: Path, prefix: str, frame: pd.DataFrame) -> tuple[Path, Path]:
    x_path = directory / f"X_{prefix}.parquet"
    y_path = directory / f"y_{prefix}.parquet"
    frame[ALL_FEATURES].to_parquet(x_path, index=True)
    frame[["Class"]].to_parquet(y_path, index=True)
    return x_path, y_path


def _filter_quarantine(frame: pd.DataFrame, quarantine_hashes: frozenset[str]) -> pd.DataFrame:
    hashes = canonical_row_hashes(frame)
    return frame.iloc[
        [index for index, value in enumerate(hashes) if value not in quarantine_hashes]
    ].copy()


def _global_keep_first_pool(
    train: pd.DataFrame, validation: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    train_hashes = canonical_row_hashes(train)
    validation_hashes = canonical_row_hashes(validation)
    seen_train: set[str] = set()
    train_keep: list[bool] = []
    for value in train_hashes:
        train_keep.append(value not in seen_train)
        seen_train.add(value)
    seen_validation: set[str] = set()
    validation_keep: list[bool] = []
    cross_split_duplicates = 0
    for value in validation_hashes:
        if value in seen_validation:
            validation_keep.append(False)
            continue
        seen_validation.add(value)
        if value in seen_train:
            cross_split_duplicates += 1
            validation_keep.append(False)
            continue
        validation_keep.append(True)
    return (
        pd.concat(
            (
                train.iloc[np.flatnonzero(train_keep)].copy(),
                validation.iloc[np.flatnonzero(validation_keep)].copy(),
            ),
            ignore_index=True,
        ),
        cross_split_duplicates,
    )


def _approved_recipe(
    path: Path,
    *,
    x_train: Path,
    y_train: Path,
    x_val: Path,
    y_val: Path,
    train_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    quarantine_path: Path,
) -> Path:
    quarantine = load_historical_quarantine_manifest(quarantine_path)
    train_after_quarantine = _filter_quarantine(train_frame, quarantine.row_hashes)
    validation_after_quarantine = _filter_quarantine(validation_frame, quarantine.row_hashes)
    pool, cross_split_duplicates = _global_keep_first_pool(
        train_after_quarantine, validation_after_quarantine
    )
    hashes = canonical_row_hashes(pool)
    source_paths = {
        "x_train": (x_train, train_frame, None),
        "y_train": (y_train, train_frame, int(train_frame["Class"].sum())),
        "x_val": (x_val, validation_frame, None),
        "y_val": (y_val, validation_frame, int(validation_frame["Class"].sum())),
    }
    payload = {
        "approval_status": "approved",
        "candidate_identity_status": "pending_independent_verification",
        "candidate_sources": {
            key: {
                "filename": source.name,
                "sha256": sha256_file(source),
                "size_bytes": source.stat().st_size,
                "row_count": len(frame),
                "fraud_count": fraud,
            }
            for key, (source, frame, fraud) in source_paths.items()
        },
        "conflicting_feature_identical_labels": "reject",
        "cross_split_identical_labeled_rows": "deduplicate_deterministically_into_final_fitting_pool",
        "duplicate_policy": "filter_quarantine_then_global_keep_first_train_then_validation",
        "dtype_contract": {
            "features": {feature: "float64" for feature in ALL_FEATURES},
            "target": {"Class": "int64"},
        },
        "feature_schema": list(ALL_FEATURES),
        "expected_cross_split_duplicate_count": cross_split_duplicates,
        "final_training_pool": "quarantine_filtered_train_then_validation_global_keep_first_deduplicated_fitting_pool",
        "filtering": {
            "quarantine_occurrences_removed": len(train_frame) + len(validation_frame) - len(train_after_quarantine) - len(validation_after_quarantine),
            "duplicate_rows_removed": (
                len(train_after_quarantine) + len(validation_after_quarantine) - len(pool)
            ),
            "cross_split_duplicate_rows_removed": cross_split_duplicates,
            "feature_label_conflicts": 0,
        },
        "format_version": "1",
        "model": {
            "family": "xgboost_binary_classifier",
            "parameters": {
                **reference_module._XGBOOST_STATIC_PARAMETERS,
                "scale_pos_weight": (
                    (len(pool) - int(pool["Class"].sum())) / int(pool["Class"].sum())
                ),
            },
        },
        "model_version": "historical-reference-synthetic-fixture-demo-v1",
        "post_quarantine_split_roles": "abolished_merged_fitting_pool_only_no_evaluation",
        "preprocessing": {
            "column_transformer": {
                "n_jobs": None,
                "remainder": "drop",
                "sparse_threshold": 0.3,
                "transformer_weights": None,
                "verbose": False,
                "verbose_feature_names_out": False,
            },
            "scale_features": ["Time", "Amount"],
            "passthrough_features": [f"V{value}" for value in range(1, 29)],
            "scaler": {"copy": True, "with_mean": True, "with_std": True},
        },
        "producer_policy": "historical_reference_demo_v1",
        "quarantine": {
            "anchor_sha256": quarantine.anchor_sha256,
            "row_hashes_sha256": quarantine.row_hashes_sha256,
            "total_row_count": quarantine.total_row_count,
            "fraud_count": quarantine.fraud_count,
            "unique_row_count": quarantine.unique_row_count,
            "duplicate_row_count": quarantine.duplicate_row_count,
        },
        "quarantine_overlap_policy": "filter_all_occurrences_before_construction",
        "recipe_kind": "historical_reference_demo_bundle",
        "threshold": {
            "value": 0.53,
            "source": "historical_validation_selected_threshold",
            "historical_component_linkage": "unverified",
            "purpose": "demo_human_review_policy_only",
            "calibrated": False,
            "cost_optimal": False,
            "razorpay_approved": False,
            "production_approved": False,
        },
        "training_pool": {
            "row_hashes_sha256": row_hashes_checksum(hashes),
            "total_row_count": len(pool),
            "legitimate_row_count": len(pool) - int(pool["Class"].sum()),
            "fraud_count": int(pool["Class"].sum()),
            "unique_row_count": len(set(hashes)),
            "duplicate_row_count": len(hashes) - len(set(hashes)),
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def _environment(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    quarantine_path, anchor_path = write_nonoverlapping_quarantine(tmp_path)
    # The first row exactly matches the synthetic quarantine and must be removed.
    train = _frame(
        [(9_000_000.0, 0), (11.0, 0), (12.0, 1), (12.0, 1), (13.0, 0)], index_start=100
    )
    train.loc[100, "Amount"] = 9_000_002.0
    train.loc[100, "V1"] = 0.0
    validation = _frame([(21.0, 0), (22.0, 1), (23.0, 0)], index_start=200)
    x_train, y_train = _write_split(tmp_path, "train", train)
    x_val, y_val = _write_split(tmp_path, "val", validation)
    with approved_quarantine_environment(
        anchor_path,
        tmp_path,
        rows=SYNTHETIC_QUARANTINE_ROWS,
        fraud=SYNTHETIC_QUARANTINE_FRAUD,
    ):
        recipe = _approved_recipe(
            tmp_path / "historical_reference_demo_recipe.json",
            x_train=x_train,
            y_train=y_train,
            x_val=x_val,
            y_val=y_val,
            train_frame=train,
            validation_frame=validation,
            quarantine_path=quarantine_path,
        )
    return recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val


def test_unapproved_recipe_refuses_before_any_parquet_is_opened(tmp_path: Path) -> None:
    recipe, _quarantine, _anchor, _x_train, _y_train, _x_val, _y_val = _environment(tmp_path)
    payload = json.loads(recipe.read_text(encoding="utf-8"))
    payload["approval_status"] = "unapproved"
    recipe.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with (
        patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
        patch.object(reference_module.pd, "read_parquet") as read_parquet,
        patch.object(reference_module, "_read_checked_parquet") as read_checked_parquet,
        patch.object(reference_module, "load_historical_quarantine_manifest") as load_quarantine,
    ):
        with pytest.raises(ValueError, match="unapproved"):
            reference_module.create_historical_reference_demo_bundle(
                x_train=tmp_path / "missing-X_train.parquet",
                y_train=tmp_path / "missing-y_train.parquet",
                x_val=tmp_path / "missing-X_val.parquet",
                y_val=tmp_path / "missing-y_val.parquet",
                historical_quarantine=tmp_path / "missing-quarantine.json",
                output="artifacts/never-created",
            )
    read_parquet.assert_not_called()
    read_checked_parquet.assert_not_called()
    load_quarantine.assert_not_called()
    assert not (tmp_path / "artifacts" / "never-created").exists()


def test_approved_synthetic_recipe_filters_and_packages_without_scoring_rows(tmp_path: Path) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val = _environment(tmp_path)
    with (
        approved_quarantine_environment(
            anchor_path,
            tmp_path,
            rows=SYNTHETIC_QUARANTINE_ROWS,
            fraud=SYNTHETIC_QUARANTINE_FRAUD,
        ),
        patch.object(reference_module, "PROJECT_ROOT", tmp_path),
        patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
        patch.object(reference_module, "XGBClassifier", _NoHistoricalPredictionModel),
        _synthetic_recipe_policy(recipe),
    ):
        manifest = reference_module.create_historical_reference_demo_bundle(
            x_train=x_train,
            y_train=y_train,
            x_val=x_val,
            y_val=y_val,
            historical_quarantine=quarantine_path,
            output="artifacts/reference-fixture",
        )
        bundle = load_model_bundle(manifest, trusted_root=tmp_path / "artifacts")
    assert bundle.intended_use.evidence_category == "historical_reference_demo_inference"
    assert bundle.intended_use.historical_taint is True
    assert bundle.intended_use.decision_eligible is False
    assert bundle.intended_use.historical_metrics_claimed is False
    assert bundle.intended_use.evaluation_performed is False
    assert bundle.score_type == "raw_score"
    assert bundle.calibrator is None
    payload = json.loads(manifest.read_text())
    evidence = payload["historical_reference_provenance"]
    assert evidence["filtering"]["quarantine_occurrences_removed"] == 1
    assert evidence["filtering"]["duplicate_rows_removed"] == 1
    assert evidence["filtering"]["cross_split_duplicate_rows_removed"] == 0
    assert evidence["final_pool"]["total_row_count"] == 6
    assert "/" not in evidence["recipe"]["filename"]
    assert str(tmp_path) not in json.dumps(evidence)


def test_cross_split_identical_labeled_rows_are_deduplicated_into_fitting_pool(
    tmp_path: Path,
) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, _x_val, y_val = _environment(tmp_path)
    train = _frame([(31.0, 0), (32.0, 1)], index_start=1)
    validation = _frame([(31.0, 0), (41.0, 1)], index_start=100)
    x_train, y_train = _write_split(tmp_path, "train", train)
    x_val, y_val = _write_split(tmp_path, "val", validation)
    with approved_quarantine_environment(
        anchor_path,
        tmp_path,
        rows=SYNTHETIC_QUARANTINE_ROWS,
        fraud=SYNTHETIC_QUARANTINE_FRAUD,
    ):
        recipe = _approved_recipe(
            recipe,
            x_train=x_train,
            y_train=y_train,
            x_val=x_val,
            y_val=y_val,
            train_frame=train,
            validation_frame=validation,
            quarantine_path=quarantine_path,
        )
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(reference_module, "XGBClassifier", _NoHistoricalPredictionModel),
            _synthetic_recipe_policy(recipe),
        ):
            manifest = reference_module.create_historical_reference_demo_bundle(
                x_train=x_train,
                y_train=y_train,
                x_val=x_val,
                y_val=y_val,
                historical_quarantine=quarantine_path,
                output="artifacts/reference-fixture",
            )
            bundle = load_model_bundle(manifest, trusted_root=tmp_path / "artifacts")
    evidence = json.loads(manifest.read_text(encoding="utf-8"))["historical_reference_provenance"]
    assert evidence["filtering"] == {
        "quarantine_occurrences_removed": 0,
        "duplicate_rows_removed": 1,
        "cross_split_duplicate_rows_removed": 1,
        "feature_label_conflicts": 0,
    }
    assert evidence["final_pool"]["total_row_count"] == 3
    assert bundle.training_provenance.data_roles.evaluation is None
    assert bundle.training_provenance.data_roles.threshold_selection is None


def test_rejects_test_named_or_outside_output_before_parquet_parse(tmp_path: Path) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val = _environment(tmp_path)
    with approved_quarantine_environment(
        anchor_path,
        tmp_path,
        rows=SYNTHETIC_QUARANTINE_ROWS,
        fraud=SYNTHETIC_QUARANTINE_FRAUD,
    ):
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(reference_module.pd, "read_parquet") as read_parquet,
        ):
            with pytest.raises(ValueError, match="relative ignored artifacts"):
                reference_module.create_historical_reference_demo_bundle(
                    x_train=x_train,
                    y_train=y_train,
                    x_val=x_val,
                    y_val=y_val,
                    historical_quarantine=quarantine_path,
                    output=tmp_path / "outside",
                )
            with pytest.raises(ValueError, match="filename is not approved"):
                reference_module.create_historical_reference_demo_bundle(
                    x_train=tmp_path / "X_test.parquet",
                    y_train=y_train,
                    x_val=x_val,
                    y_val=y_val,
                    historical_quarantine=quarantine_path,
                    output="artifacts/refusal",
                )
    read_parquet.assert_not_called()


def test_rejects_wrong_dtype_before_preprocessor_or_model_construction(tmp_path: Path) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val = _environment(tmp_path)
    wrong_dtype = pd.read_parquet(x_train).astype({"V2": "float32"})
    wrong_dtype.to_parquet(x_train, index=True)
    payload = json.loads(recipe.read_text(encoding="utf-8"))
    payload["candidate_sources"]["x_train"]["sha256"] = sha256_file(x_train)
    payload["candidate_sources"]["x_train"]["size_bytes"] = x_train.stat().st_size
    recipe.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with approved_quarantine_environment(
        anchor_path,
        tmp_path,
        rows=SYNTHETIC_QUARANTINE_ROWS,
        fraud=SYNTHETIC_QUARANTINE_FRAUD,
    ):
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(reference_module, "_build_exact_preprocessor") as build_preprocessor,
        ):
            with pytest.raises(ValueError, match="exact float64"):
                reference_module.create_historical_reference_demo_bundle(
                    x_train=x_train,
                    y_train=y_train,
                    x_val=x_val,
                    y_val=y_val,
                    historical_quarantine=quarantine_path,
                    output="artifacts/refusal",
                )
    build_preprocessor.assert_not_called()
    assert not (tmp_path / "artifacts" / "refusal").exists()


def test_feature_label_conflict_refuses_before_model_construction(tmp_path: Path) -> None:
    recipe, quarantine_path, anchor_path, _x_train, _y_train, _x_val, _y_val = _environment(tmp_path)
    train = _frame([(51.0, 0), (52.0, 1)], index_start=1)
    validation = _frame([(51.0, 1), (53.0, 0)], index_start=100)
    x_train, y_train = _write_split(tmp_path, "train", train)
    x_val, y_val = _write_split(tmp_path, "val", validation)
    with approved_quarantine_environment(
        anchor_path, tmp_path, rows=SYNTHETIC_QUARANTINE_ROWS, fraud=SYNTHETIC_QUARANTINE_FRAUD
    ):
        _approved_recipe(
            recipe, x_train=x_train, y_train=y_train, x_val=x_val, y_val=y_val,
            train_frame=train, validation_frame=validation, quarantine_path=quarantine_path,
        )
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(reference_module, "_build_exact_preprocessor") as build_preprocessor,
        ):
            with pytest.raises(ValueError, match="contradictory labels"):
                reference_module.create_historical_reference_demo_bundle(
                    x_train=x_train, y_train=y_train, x_val=x_val, y_val=y_val,
                    historical_quarantine=quarantine_path, output="artifacts/refusal",
                )
    build_preprocessor.assert_not_called()
    assert not (tmp_path / "artifacts" / "refusal").exists()


def test_index_misalignment_refuses_before_model_construction(tmp_path: Path) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val = _environment(tmp_path)
    labels = pd.read_parquet(y_train)
    labels.index = pd.Index(range(900, 900 + len(labels)), name="row_id")
    labels.to_parquet(y_train, index=True)
    payload = json.loads(recipe.read_text(encoding="utf-8"))
    payload["candidate_sources"]["y_train"]["sha256"] = sha256_file(y_train)
    payload["candidate_sources"]["y_train"]["size_bytes"] = y_train.stat().st_size
    recipe.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with approved_quarantine_environment(
        anchor_path, tmp_path, rows=SYNTHETIC_QUARANTINE_ROWS, fraud=SYNTHETIC_QUARANTINE_FRAUD
    ):
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(reference_module, "_build_exact_preprocessor") as build_preprocessor,
        ):
            with pytest.raises(ValueError, match="unique-index aligned"):
                reference_module.create_historical_reference_demo_bundle(
                    x_train=x_train, y_train=y_train, x_val=x_val, y_val=y_val,
                    historical_quarantine=quarantine_path, output="artifacts/refusal",
                )
    build_preprocessor.assert_not_called()


def test_retained_file_refuses_parent_symlink_and_replacement(tmp_path: Path) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    target = safe / "source.parquet"
    target.write_bytes(b"first")
    link = tmp_path / "linked"
    link.symlink_to(safe, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic-link"):
        reference_module._retained_file(link / target.name, label="source", suffix=".parquet")
    retained = reference_module._retained_file(target, label="source", suffix=".parquet")
    target.write_bytes(b"second")
    with pytest.raises(ValueError, match="changed after verification"):
        reference_module._reverify_retained_file(retained, label="source", suffix=".parquet")


@pytest.mark.parametrize("replaced", ["recipe", "quarantine"])
def test_replacement_after_verification_refuses_before_publication(
    tmp_path: Path, replaced: str
) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val = _environment(tmp_path)
    target = recipe if replaced == "recipe" else quarantine_path
    with approved_quarantine_environment(
        anchor_path, tmp_path, rows=SYNTHETIC_QUARANTINE_ROWS, fraud=SYNTHETIC_QUARANTINE_FRAUD
    ):
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(
                reference_module,
                "XGBClassifier",
                side_effect=lambda **kwargs: _ReplaceVerifiedFileModel(target, **kwargs),
            ),
            patch.object(reference_module, "save_model_bundle") as save_bundle,
            _synthetic_recipe_policy(recipe),
        ):
            with pytest.raises(ValueError, match="changed after verification"):
                reference_module.create_historical_reference_demo_bundle(
                    x_train=x_train,
                    y_train=y_train,
                    x_val=x_val,
                    y_val=y_val,
                    historical_quarantine=quarantine_path,
                    output="artifacts/refusal",
                )
    save_bundle.assert_not_called()
    assert not (tmp_path / "artifacts" / "refusal").exists()


def test_output_symlink_and_existing_output_refuse_without_target_write(tmp_path: Path) -> None:
    recipe, quarantine_path, anchor_path, x_train, y_train, x_val, y_val = _environment(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (artifacts / "symlink-output").symlink_to(outside, target_is_directory=True)
    (artifacts / "existing-output").mkdir()
    with approved_quarantine_environment(
        anchor_path, tmp_path, rows=SYNTHETIC_QUARANTINE_ROWS, fraud=SYNTHETIC_QUARANTINE_FRAUD
    ):
        with (
            patch.object(reference_module, "PROJECT_ROOT", tmp_path),
            patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe),
            patch.object(reference_module, "XGBClassifier", _NoHistoricalPredictionModel),
            _synthetic_recipe_policy(recipe),
        ):
            for name in ("symlink-output", "existing-output"):
                with pytest.raises(FileExistsError, match="Refusing to overwrite"):
                    reference_module.create_historical_reference_demo_bundle(
                        x_train=x_train,
                        y_train=y_train,
                        x_val=x_val,
                        y_val=y_val,
                        historical_quarantine=quarantine_path,
                        output=f"artifacts/{name}",
                    )
    assert list(outside.iterdir()) == []


def test_real_xgboost_constructor_matches_exhaustive_recipe(tmp_path: Path) -> None:
    recipe_path, _quarantine_path, _anchor_path, _x_train, _y_train, _x_val, _y_val = _environment(
        tmp_path
    )
    with patch.object(reference_module, "DEFAULT_HISTORICAL_REFERENCE_RECIPE", recipe_path):
        recipe = reference_module.load_historical_reference_recipe()
    model = reference_module._build_exact_model(recipe)
    assert model.get_params(deep=False) == dict(recipe.model_parameters)
