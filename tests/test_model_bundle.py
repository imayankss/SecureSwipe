"""Trust-boundary and round-trip tests for versioned ModelBundle artifacts."""

from __future__ import annotations

import json
import io
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from src.artifacts import bundle as bundle_module
from src.artifacts.bundle import (
    ArtifactVerificationError,
    BUNDLE_FORMAT_VERSION,
    HistoricalReferenceFileIdentity,
    HistoricalReferencePool,
    HistoricalReferenceSourceIdentity,
    ModelBundle,
    data_role_metadata,
    historical_reference_provenance_metadata,
    intended_use_metadata,
    load_model_bundle,
    load_verified_joblib,
    quarantine_provenance_metadata,
    save_model_bundle,
    sha256_file,
    threshold_provenance_metadata,
    training_provenance_metadata,
    write_checksum_sidecar,
)
from src.data.historical_quarantine import load_historical_quarantine_anchor
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor


def _training_fixture() -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(42)
    values = rng.normal(size=(40, len(ALL_FEATURES)))
    frame = pd.DataFrame(values, columns=ALL_FEATURES)
    frame["Time"] = np.arange(len(frame), dtype=float)
    frame["Amount"] = np.abs(frame["Amount"])
    labels = np.array([0, 1] * 20)
    return frame, labels


def _bundle() -> tuple[ModelBundle, pd.DataFrame]:
    frame, labels = _training_fixture()
    preprocessor = fit_preprocessor(frame, build_preprocessor())
    preprocessor.set_output(transform="pandas")
    processed = preprocessor.transform(frame)
    model = LogisticRegression(random_state=42).fit(processed, labels)
    model_fit = data_role_metadata(
        fingerprint_sha256="a" * 64,
        total_row_count=len(frame),
        fraud_row_count=int(labels.sum()),
        duplicate_row_count=0,
    )
    training_provenance = training_provenance_metadata(
        producer_policy="synthetic_api_smoke_v1",
        model_fit=model_fit,
        calibrator_fit=None,
        threshold_selection=None,
        evaluation=None,
        quarantine=None,
    )
    return (
        ModelBundle(
            preprocessor=preprocessor,
            model=model,
            calibrator=None,
            operating_threshold=0.53,
            feature_schema=tuple(ALL_FEATURES),
            training_data_fingerprint=training_provenance.data_roles_sha256,
            model_version="synthetic-smoke-1",
            intended_use=intended_use_metadata("synthetic_api_smoke_v1"),
            threshold_provenance=threshold_provenance_metadata(
                producer_policy="synthetic_api_smoke_v1",
                value=0.53,
                calibrated=False,
            ),
            training_provenance=training_provenance,
        ),
        frame,
    )


def _historical_bundle() -> ModelBundle:
    bundle, _ = _bundle()
    recipe_path = Path(__file__).parents[1] / "configs" / "historical_reference_demo_recipe.json"
    recipe_payload = json.loads(recipe_path.read_text(encoding="utf-8"))
    pool_payload = recipe_payload["training_pool"]
    anchor = load_historical_quarantine_anchor()
    quarantine = quarantine_provenance_metadata(
        anchor_sha256=anchor.sha256,
        row_hashes_sha256=anchor.row_hashes_sha256,
        total_row_count=anchor.total_row_count,
        fraud_row_count=anchor.fraud_count,
        unique_row_count=anchor.unique_row_count,
        duplicate_row_count=anchor.duplicate_row_count,
        overlap_row_count=0,
    )
    training_provenance = training_provenance_metadata(
        producer_policy="historical_reference_demo_v1",
        model_fit=data_role_metadata(
            fingerprint_sha256=pool_payload["row_hashes_sha256"],
            total_row_count=pool_payload["total_row_count"],
            fraud_row_count=pool_payload["fraud_count"],
            duplicate_row_count=pool_payload["duplicate_row_count"],
        ),
        calibrator_fit=None,
        threshold_selection=None,
        evaluation=None,
        quarantine=quarantine,
    )
    historical_reference = historical_reference_provenance_metadata(
        recipe=HistoricalReferenceFileIdentity(
            filename="historical_reference_demo_recipe.json",
            sha256=sha256_file(recipe_path),
            size_bytes=recipe_path.stat().st_size,
        ),
        sources=(
            *(
                HistoricalReferenceSourceIdentity(
                    recipe_payload["candidate_sources"][key]["filename"],
                    recipe_payload["candidate_sources"][key]["sha256"],
                    recipe_payload["candidate_sources"][key]["size_bytes"],
                    recipe_payload["candidate_sources"][key]["row_count"],
                    recipe_payload["candidate_sources"][key]["fraud_count"],
                )
                for key in ("x_train", "y_train", "x_val", "y_val")
            ),
        ),
        quarantine=quarantine,
        quarantine_occurrences_removed=recipe_payload["filtering"]["quarantine_occurrences_removed"],
        duplicate_rows_removed=recipe_payload["filtering"]["duplicate_rows_removed"],
        cross_split_duplicate_rows_removed=recipe_payload["filtering"][
            "cross_split_duplicate_rows_removed"
        ],
        feature_label_conflicts=0,
        final_pool=HistoricalReferencePool(
            row_hashes_sha256=pool_payload["row_hashes_sha256"],
            total_row_count=pool_payload["total_row_count"],
            legitimate_row_count=pool_payload["legitimate_row_count"],
            fraud_row_count=pool_payload["fraud_count"],
            unique_row_count=pool_payload["unique_row_count"],
            duplicate_row_count=pool_payload["duplicate_row_count"],
        ),
    )
    return replace(
        bundle,
        model_version="historical-reference-fixture-demo-v1",
        intended_use=intended_use_metadata("historical_reference_demo_v1"),
        threshold_provenance=threshold_provenance_metadata(
            producer_policy="historical_reference_demo_v1",
            value=0.53,
            calibrated=False,
        ),
        training_data_fingerprint=training_provenance.data_roles_sha256,
        training_provenance=training_provenance,
        historical_reference_provenance=historical_reference,
    )


def test_model_bundle_roundtrip_preserves_golden_scores(tmp_path: Path) -> None:
    bundle, frame = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    loaded = load_model_bundle(manifest, trusted_root=tmp_path / "trusted")

    expected = bundle.model.predict_proba(bundle.preprocessor.transform(frame.iloc[:3]))[:, 1]
    actual = loaded.model.predict_proba(loaded.preprocessor.transform(frame.iloc[:3]))[:, 1]
    np.testing.assert_array_equal(actual, expected)
    assert loaded.operating_threshold == pytest.approx(0.53)
    assert loaded.score_type == "raw_score"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["bundle_format_version"] == BUNDLE_FORMAT_VERSION == "3"
    assert payload["intended_use"] == intended_use_metadata("synthetic_api_smoke_v1").to_dict()
    assert payload["threshold_provenance"]["value"] == 0.53
    assert payload["training_provenance"]["data_roles"]["model_fit"]["total_row_count"] == 40
    assert payload["positive_class_label"] == 1
    assert payload["positive_class_index"] == 1
    assert {"scipy", "xgboost"} <= set(payload["runtime"]["dependencies"])
    assert len(payload["golden_probe"]["sha256"]) == 64


def test_historical_reference_v3_metadata_round_trips(tmp_path: Path) -> None:
    bundle = _historical_bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "historical-reference")
    loaded = load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
    assert loaded.intended_use == intended_use_metadata("historical_reference_demo_v1")
    assert loaded.score_type == "raw_score"
    assert loaded.calibrator is None
    assert loaded.threshold_provenance.purpose == "demo_human_review_policy_only"
    assert loaded.training_provenance.quarantine is not None
    assert loaded.training_provenance.quarantine.overlap_row_count == 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "manifest_sha256" not in payload["training_provenance"]["quarantine"]


def test_model_bundle_never_overwrites_existing_directory(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    destination = tmp_path / "trusted" / "fixture-1"
    save_model_bundle(bundle, destination)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        save_model_bundle(bundle, destination)


def test_provenance_objects_are_deeply_immutable() -> None:
    bundle, _ = _bundle()
    with pytest.raises(FrozenInstanceError):
        bundle.intended_use.decision_eligible = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        bundle.training_provenance.recipe.version = "2"  # type: ignore[misc]
    with pytest.raises(TypeError):
        bundle.intended_use["decision_eligible"] = True  # type: ignore[index]


def test_policy_binding_rejects_cross_category_relabeling() -> None:
    bundle, _ = _bundle()
    relabelled = replace(
        bundle,
        intended_use=intended_use_metadata("historical_reference_demo_v1"),
    )
    with pytest.raises(ValueError, match="producer policy"):
        relabelled.validate()


def test_save_rejects_symlink_output_without_touching_target(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "bundle"
    output.symlink_to(outside, target_is_directory=True)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        save_model_bundle(bundle, output)
    assert list(outside.iterdir()) == []


def test_save_rejects_symlinked_parent_without_touching_target(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = tmp_path / "linked-parent"
    parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link|unsafe directory"):
        save_model_bundle(bundle, parent / "bundle")
    assert list(outside.iterdir()) == []


def test_save_cleans_temporary_name_replaced_before_descriptor_open(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle()
    output = tmp_path / "trusted" / "fixture-1"
    outside = tmp_path / "outside"
    outside.mkdir()
    real_open = os.open
    replaced = False

    def replace_temporary_with_symlink(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        name = os.fsdecode(path)
        if not replaced and name.startswith(".fixture-1.") and name.endswith(".tmp"):
            replaced = True
            assert dir_fd is not None
            os.rmdir(name, dir_fd=dir_fd)
            os.symlink(outside, name, target_is_directory=True, dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    with (
        patch("src.artifacts.bundle._require_safe_filesystem_primitives"),
        patch("src.artifacts.bundle.os.open", side_effect=replace_temporary_with_symlink),
    ):
        with pytest.raises(OSError):
            save_model_bundle(bundle, output)
    assert replaced
    assert not output.exists()
    assert list(outside.iterdir()) == []
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_save_failure_removes_temporary_directory_and_final_target(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle()
    output = tmp_path / "trusted" / "fixture-1"
    real_write = bundle_module._write_new_file_at

    def fail_manifest(parent_fd: int, filename: str, encoded: bytes) -> None:
        if filename == "manifest.json":
            raise OSError("injected publication failure")
        real_write(parent_fd, filename, encoded)

    with patch("src.artifacts.bundle._write_new_file_at", side_effect=fail_manifest):
        with pytest.raises(OSError, match="injected publication failure"):
            save_model_bundle(bundle, output)
    assert not output.exists()
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_atomic_publication_refuses_concurrent_target_without_overwrite(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle()
    output = tmp_path / "trusted" / "fixture-1"
    real_publish = bundle_module._rename_directory_no_replace

    def race(parent_fd: int, temporary: str, final: str, path: Path) -> None:
        os.mkdir(final, dir_fd=parent_fd)
        directory_fd = os.open(final, os.O_RDONLY | os.O_DIRECTORY, dir_fd=parent_fd)
        try:
            marker_fd = os.open(
                "marker",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            os.close(marker_fd)
        finally:
            os.close(directory_fd)
        real_publish(parent_fd, temporary, final, path)

    with patch("src.artifacts.bundle._rename_directory_no_replace", side_effect=race):
        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            save_model_bundle(bundle, output)
    assert (output / "marker").is_file()
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_missing_safe_primitives_fail_before_output(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    output = tmp_path / "trusted" / "fixture-1"
    with patch("src.artifacts.bundle.os.supports_dir_fd", set()):
        with pytest.raises(RuntimeError, match="directory-descriptor"):
            save_model_bundle(bundle, output)
    assert not output.exists()


def test_missing_safe_load_primitives_fail_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    with (
        patch("src.artifacts.bundle.os.supports_dir_fd", set()),
        patch("src.artifacts.bundle.joblib.load") as deserialize,
    ):
        with pytest.raises(RuntimeError, match="directory-descriptor"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_invalid_mutable_provenance_fails_before_output(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    output = tmp_path / "trusted" / "fixture-1"
    invalid = replace(bundle, intended_use=bundle.intended_use.to_dict())
    with pytest.raises(ValueError, match="immutable typed metadata"):
        save_model_bundle(invalid, output)
    assert not output.exists()


def test_corrupt_bundle_fails_before_any_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    model_path = manifest.parent / "model.joblib"
    model_path.write_bytes(model_path.read_bytes() + b"corruption")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="size|checksum"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_component_path_replacement_cannot_change_verified_deserialization(
    tmp_path: Path,
) -> None:
    bundle, frame = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    model_path = manifest.parent / "model.joblib"
    original_load = joblib.load
    replaced = False

    def replace_path_then_load(source: object) -> object:
        nonlocal replaced
        assert isinstance(source, io.BytesIO)
        if not replaced:
            model_path.write_bytes(b"unverified replacement")
            replaced = True
        return original_load(source)

    with patch("src.artifacts.bundle.joblib.load", side_effect=replace_path_then_load):
        loaded = load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
    assert replaced is True
    expected = bundle.model.predict_proba(bundle.preprocessor.transform(frame.iloc[:1]))[:, 1]
    actual = loaded.model.predict_proba(loaded.preprocessor.transform(frame.iloc[:1]))[:, 1]
    np.testing.assert_array_equal(actual, expected)


def test_manifest_path_replacement_cannot_change_verified_validation(
    tmp_path: Path,
) -> None:
    bundle, frame = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    real_read = bundle_module._read_regular_file_at
    replaced = False

    def replace_manifest_after_read(parent_fd: int, filename: str, *, label: str) -> bytes:
        nonlocal replaced
        encoded = real_read(parent_fd, filename, label=label)
        if filename == "manifest.json" and not replaced:
            manifest.write_text('{"bundle_format_version":"2"}\n', encoding="utf-8")
            replaced = True
        return encoded

    with patch(
        "src.artifacts.bundle._read_regular_file_at",
        side_effect=replace_manifest_after_read,
    ):
        loaded = load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
    assert replaced
    expected = bundle.model.predict_proba(bundle.preprocessor.transform(frame.iloc[:1]))[:, 1]
    actual = loaded.model.predict_proba(loaded.preprocessor.transform(frame.iloc[:1]))[:, 1]
    np.testing.assert_array_equal(actual, expected)


def test_manifest_symlink_is_rejected_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    outside = tmp_path / "outside-manifest.json"
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(outside)
    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="symbolic link"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_component_symlink_is_rejected_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    outside = tmp_path / "outside.joblib"
    outside.write_bytes((manifest.parent / "model.joblib").read_bytes())
    (manifest.parent / "model.joblib").unlink()
    (manifest.parent / "model.joblib").symlink_to(outside)
    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="symbolic link"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_v2_bundle_is_rejected_clearly_before_v3_schema_checks_or_deserialization(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    manifest.write_text('{"bundle_format_version":"2"}\n', encoding="utf-8")
    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Unsupported bundle_format_version"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_duplicate_json_fields_fail_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    encoded = manifest.read_text(encoding="utf-8").replace(
        '"bundle_format_version": "3",',
        '"bundle_format_version": "3",\n  "bundle_format_version": "3",',
        1,
    )
    manifest.write_text(encoded, encoding="utf-8")
    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Duplicate JSON field"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_manifest_schema_mismatch_fails_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["feature_schema"] = list(reversed(payload["feature_schema"]))
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="schema"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.pop("intended_use"), "incomplete or unexpected"),
        (lambda payload: payload.update({"unexpected": True}), "incomplete or unexpected"),
        (
            lambda payload: payload["intended_use"].pop("historical_taint"),
            "intended_use fields",
        ),
        (
            lambda payload: payload["threshold_provenance"].update({"unexpected": True}),
            "threshold_provenance fields",
        ),
        (
            lambda payload: payload["intended_use"].update({"producer_policy_sha256": "f" * 64}),
            "policy checksum",
        ),
        (
            lambda payload: payload.update(
                {"model_version": "historical-reference-relabeled-demo-v1"}
            ),
            "Model version contradicts",
        ),
        (
            lambda payload: payload["training_provenance"]["recipe"].update({"unexpected": True}),
            "recipe fields",
        ),
        (
            lambda payload: payload["training_provenance"]["recipe"].update(
                {"configuration_sha256": "f" * 64}
            ),
            "Training recipe",
        ),
        (
            lambda payload: payload["threshold_provenance"].update({"value": 0.52}),
            "must equal operating_threshold",
        ),
        (
            lambda payload: payload["training_provenance"]["data_roles"]["model_fit"].update(
                {"fingerprint_sha256": "f" * 64}
            ),
            "data role checksum mismatch",
        ),
        (
            lambda payload: payload["training_provenance"]["data_roles"]["model_fit"].update(
                {"fraud_row_count": 41}
            ),
            "counts are inconsistent",
        ),
        (
            lambda payload: payload["artifacts"]["model"].update({"unexpected": True}),
            "Artifact entry fields",
        ),
    ],
)
def test_v3_metadata_tampering_fails_before_deserialization(
    tmp_path: Path, mutation: object, message: str
) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    mutation(payload)  # type: ignore[operator]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match=message):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_historical_reference_invariant_tampering_fails_before_deserialization(
    tmp_path: Path,
) -> None:
    bundle = _historical_bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["intended_use"]["decision_eligible"] = True
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Intended use contradicts"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_historical_cross_split_deduplication_evidence_tampering_fails_before_deserialization(
    tmp_path: Path,
) -> None:
    manifest = save_model_bundle(
        _historical_bundle(), tmp_path / "trusted" / "historical-reference"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["historical_reference_provenance"]["filtering"][
        "cross_split_duplicate_rows_removed"
    ] -= 1
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="evidence contradicts"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("overlap_row_count", 1, "zero historical quarantine overlap"),
        ("duplicate_row_count", 2, "counts are inconsistent"),
        ("anchor_sha256", "4" * 64, "approved canonical anchor"),
    ],
)
def test_historical_quarantine_provenance_tampering_fails_before_deserialization(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    manifest = save_model_bundle(
        _historical_bundle(), tmp_path / "trusted" / "historical-reference"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["training_provenance"]["quarantine"][field] = value
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match=message):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_historical_recipe_identity_tampering_fails_before_deserialization(
    tmp_path: Path,
) -> None:
    manifest = save_model_bundle(
        _historical_bundle(), tmp_path / "trusted" / "historical-reference"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["training_provenance"]["recipe"]["version"] = "2"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Training recipe"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["historical_reference_provenance"]["recipe"].update(
                {"sha256": "0" * 64}
            ),
            "recipe identity",
        ),
        (
            lambda payload: payload["historical_reference_provenance"]["sources"]["x_train"].update(
                {"total_row_count": 19}
            ),
            "row counts disagree",
        ),
        (
            lambda payload: payload["historical_reference_provenance"]["sources"]["x_train"].update(
                {"sha256": "0" * 64, "size_bytes": 1}
            ),
            "evidence contradicts tracked policy",
        ),
        (
            lambda payload: payload["historical_reference_provenance"]["filtering"].update(
                {"feature_label_conflicts": 1}
            ),
            "conflicts",
        ),
        (
            lambda payload: payload["historical_reference_provenance"]["filtering"].update(
                {
                    "quarantine_occurrences_removed": 381,
                    "duplicate_rows_removed": 648,
                }
            ),
            "evidence contradicts tracked policy",
        ),
        (
            lambda payload: payload["historical_reference_provenance"]["final_pool"].update(
                {"row_hashes_sha256": "9" * 64}
            ),
            "evidence contradicts tracked policy",
        ),
    ],
)
def test_historical_reference_provenance_tampering_fails_before_deserialization(
    tmp_path: Path, mutation: object, message: str
) -> None:
    manifest = save_model_bundle(
        _historical_bundle(), tmp_path / "trusted" / "historical-reference"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    mutation(payload)  # type: ignore[operator]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match=message):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_runtime_mismatch_fails_before_deserialization(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime"]["dependencies"]["xgboost"] = "0.0.0-wrong"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Dependency mismatch for xgboost"):
            load_model_bundle(manifest, trusted_root=tmp_path / "trusted")
        deserialize.assert_not_called()


def test_reversed_model_class_mapping_is_rejected() -> None:
    bundle, _ = _bundle()
    bundle.model.classes_ = np.array([1, 0])
    with pytest.raises(ValueError, match=r"classes_ must be exactly \[0, 1\]"):
        bundle.validate()


def test_golden_probe_rejects_preprocessor_model_dimensional_skew(tmp_path: Path) -> None:
    bundle, _ = _bundle()
    manifest = save_model_bundle(bundle, tmp_path / "trusted" / "fixture-1")
    wrong_model = LogisticRegression(random_state=42).fit(
        np.arange(80, dtype=float).reshape(40, 2), np.array([0, 1] * 20)
    )
    model_path = manifest.parent / "model.joblib"
    joblib.dump(wrong_model, model_path)
    write_checksum_sidecar(model_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"]["model"].update(
        {
            "sha256": sha256_file(model_path),
            "size_bytes": model_path.stat().st_size,
            "python_type": (f"{type(wrong_model).__module__}.{type(wrong_model).__qualname__}"),
        }
    )
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="semantic validation"):
        load_model_bundle(manifest, trusted_root=tmp_path / "trusted")


def test_verified_joblib_rejects_untrusted_path(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside.joblib"
    joblib.dump({"value": 1}, outside)
    write_checksum_sidecar(outside)
    with pytest.raises(ArtifactVerificationError, match="outside trusted root"):
        load_verified_joblib(outside, trusted_root=trusted)


def test_verified_joblib_requires_checksum_before_deserialization(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    artifact = trusted / "model.joblib"
    joblib.dump({"value": 1}, artifact)
    with patch("src.artifacts.bundle.joblib.load") as deserialize:
        with pytest.raises(ArtifactVerificationError, match="Checksum sidecar"):
            load_verified_joblib(artifact, trusted_root=trusted)
        deserialize.assert_not_called()


def test_verified_joblib_deserializes_retained_verified_bytes(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    artifact = trusted / "model.joblib"
    joblib.dump({"value": 1}, artifact)
    write_checksum_sidecar(artifact)
    original_load = joblib.load

    def replace_path_then_load(source: object) -> object:
        assert isinstance(source, io.BytesIO)
        artifact.write_bytes(b"unverified replacement")
        return original_load(source)

    with patch("src.artifacts.bundle.joblib.load", side_effect=replace_path_then_load):
        loaded = load_verified_joblib(artifact, trusted_root=trusted)
    assert loaded == {"value": 1}
