"""Hash-only historical-test quarantine and early training-refusal tests."""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import src.data.historical_quarantine as quarantine_module
from scripts.curate_dataset import curate_dataset
from scripts.run_development_training import run_development_training
from src.artifacts.bundle import sha256_file
from src.data.historical_quarantine import (
    build_historical_quarantine_manifest,
    canonical_row_hashes,
    load_historical_quarantine_anchor,
    load_historical_quarantine_manifest,
    require_no_historical_test_overlap,
    resolve_quarantine_output_path,
    reverify_historical_quarantine_identity,
    write_historical_quarantine_manifest,
)
from src.preprocessing.feature_config import ALL_FEATURES, REQUIRED_COLUMNS
from tests.historical_quarantine_helpers import (
    approved_quarantine_environment,
    write_approved_quarantine_anchor,
)
from tests.source_approval_helpers import write_source_approval


def _frame(rows: int = 4) -> pd.DataFrame:
    indices = np.arange(rows, dtype=np.float64)
    values: dict[str, np.ndarray] = {
        "Time": indices + 0.125,
        "Amount": indices + 1.25,
    }
    for feature in range(1, 29):
        values[f"V{feature}"] = indices + feature / 100.0
    values["Class"] = np.array(
        ([0, 1] * (rows // 2 + 1))[:rows], dtype=np.int64
    )
    return pd.DataFrame(values, columns=REQUIRED_COLUMNS)


def _split_paths(frame: pd.DataFrame, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    x_path = directory / "X_test.parquet"
    y_path = directory / "y_test.parquet"
    frame[ALL_FEATURES].to_parquet(x_path, index=True)
    frame[["Class"]].to_parquet(y_path, index=True)
    return x_path, y_path


def _approved_inputs(
    frame: pd.DataFrame, directory: Path
) -> tuple[Path, Path, Path]:
    x_path, y_path = _split_paths(frame, directory)
    anchor = write_approved_quarantine_anchor(
        frame, x_path, y_path, directory / "anchor.json"
    )
    return x_path, y_path, anchor


def _approved_manifest(
    frame: pd.DataFrame, directory: Path
) -> tuple[Path, Path, Path, Path]:
    x_path, y_path, anchor = _approved_inputs(frame, directory)
    with approved_quarantine_environment(
        anchor,
        directory,
        rows=len(frame),
        fraud=int(frame["Class"].sum()),
    ):
        manifest = write_historical_quarantine_manifest(
            x_test_path=x_path,
            y_test_path=y_path,
            output_path="artifacts/quarantine.json",
        )
    return manifest, anchor, x_path, y_path


def _environment(
    frame: pd.DataFrame, directory: Path, anchor: Path
):
    return approved_quarantine_environment(
        anchor,
        directory,
        rows=len(frame),
        fraud=int(frame["Class"].sum()),
    )


def _write_payload(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def test_valid_manifest_is_hash_only_deterministic_and_path_free(tmp_path: Path) -> None:
    frame = _frame()
    x_path, y_path, anchor = _approved_inputs(frame, tmp_path)
    with _environment(frame, tmp_path, anchor):
        first = build_historical_quarantine_manifest(
            x_test_path=x_path, y_test_path=y_path
        )
        second = build_historical_quarantine_manifest(
            x_test_path=x_path, y_test_path=y_path
        )
    assert first == second
    assert first["contains_raw_transaction_values"] is False
    assert first["feature_schema"] == list(ALL_FEATURES)
    assert first["dtype_contract"]["target"] == {"Class": "int64"}
    assert first["total_row_count"] == len(frame)
    assert first["fraud_count"] == 2
    encoded = json.dumps(first, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert first["sources"]["x_test"]["filename"] == x_path.name
    assert all(len(value) == 64 for value in first["row_hashes"])

    with _environment(frame, tmp_path, anchor):
        output = write_historical_quarantine_manifest(
            x_test_path=x_path,
            y_test_path=y_path,
            output_path="artifacts/quarantine.json",
        )
        loaded = load_historical_quarantine_manifest(output)
    assert loaded.total_row_count == len(frame)
    assert loaded.row_hashes_sha256 == first["row_hashes_sha256"]
    assert loaded.manifest_sha256 == sha256_file(output)


def test_exact_float_bits_are_part_of_each_canonical_row_hash() -> None:
    frame = _frame(2)
    frame.loc[0, "V1"] = 0.0
    frame.loc[1] = frame.loc[0]
    frame.loc[1, "V1"] = -0.0
    assert canonical_row_hashes(frame)[0] != canonical_row_hashes(frame)[1]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: frame.__setitem__("V1", frame["V1"].astype(np.float32)), "float64"),
        (lambda frame: frame.__setitem__("V1", np.arange(len(frame))), "float64"),
        (lambda frame: frame.__setitem__("Class", frame["Class"].astype(float)), "int64"),
    ],
)
def test_wrong_dtypes_fail_before_hashing(
    tmp_path: Path,
    mutate: Callable[[pd.DataFrame], None],
    message: str,
) -> None:
    valid = _frame()
    _, _, anchor = _approved_inputs(valid, tmp_path / "valid")
    invalid = valid.copy()
    mutate(invalid)
    x_path, y_path = _split_paths(invalid, tmp_path / "invalid")
    with _environment(valid, tmp_path, anchor):
        with pytest.raises(ValueError, match=message):
            build_historical_quarantine_manifest(
                x_test_path=x_path, y_test_path=y_path
            )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("V1", np.inf, "non-finite"),
        ("V2", np.nan, "missing values"),
        ("Class", 2, "only contain 0 and 1"),
    ],
)
def test_nonfinite_values_and_invalid_labels_fail_closed(
    tmp_path: Path, column: str, value: float, message: str
) -> None:
    valid = _frame()
    _, _, anchor = _approved_inputs(valid, tmp_path / "valid")
    invalid = valid.copy()
    invalid.loc[0, column] = value
    x_path, y_path = _split_paths(invalid, tmp_path / "invalid")
    with _environment(valid, tmp_path, anchor):
        with pytest.raises(ValueError, match=message):
            build_historical_quarantine_manifest(
                x_test_path=x_path, y_test_path=y_path
            )


def test_rejects_malformed_feature_schema(tmp_path: Path) -> None:
    frame = _frame()
    _, _, anchor = _approved_inputs(frame, tmp_path / "valid")
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    x_path = invalid / "X_test.parquet"
    y_path = invalid / "y_test.parquet"
    frame[list(reversed(ALL_FEATURES))].to_parquet(x_path, index=True)
    frame[["Class"]].to_parquet(y_path, index=True)
    with _environment(frame, tmp_path, anchor):
        with pytest.raises(ValueError, match="canonical ALL_FEATURES schema/order"):
            build_historical_quarantine_manifest(
                x_test_path=x_path, y_test_path=y_path
            )


def test_rejects_x_y_index_misalignment(tmp_path: Path) -> None:
    frame = _frame()
    _, _, anchor = _approved_inputs(frame, tmp_path / "valid")
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    x_path = invalid / "X_test.parquet"
    y_path = invalid / "y_test.parquet"
    frame[ALL_FEATURES].to_parquet(x_path, index=True)
    shifted = frame[["Class"]].copy()
    shifted.index = shifted.index + 1
    shifted.to_parquet(y_path, index=True)
    with _environment(frame, tmp_path, anchor):
        with pytest.raises(ValueError, match="not exactly aligned"):
            build_historical_quarantine_manifest(
                x_test_path=x_path, y_test_path=y_path
            )


def test_duplicate_hashes_are_recorded_and_overlap_is_rejected(tmp_path: Path) -> None:
    frame = _frame()
    frame.loc[3] = frame.loc[2]
    manifest_path, anchor, _, _ = _approved_manifest(frame, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["duplicate_row_count"] == 1
    assert payload["unique_row_count"] == len(frame) - 1
    candidate = _frame(1)
    with _environment(frame, tmp_path, anchor):
        with pytest.raises(ValueError, match="overlaps the locked historical test"):
            require_no_historical_test_overlap(candidate, manifest_path)


def test_unapproved_bootstrap_anchor_refuses_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    x_path, y_path = _split_paths(frame, tmp_path)
    anchor = write_approved_quarantine_anchor(
        frame,
        x_path,
        y_path,
        tmp_path / "synthetic-unapproved-anchor.json",
    )
    payload = json.loads(anchor.read_text(encoding="utf-8"))
    payload.update(
        {
            "approval_status": "unapproved",
            "duplicate_row_count": None,
            "review_reference": None,
            "reviewed_by": None,
            "row_hashes_sha256": None,
            "source_sha256": {"x_test": None, "y_test": None},
            "unique_row_count": None,
        }
    )
    _write_payload(anchor, payload)
    monkeypatch.setattr(quarantine_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        quarantine_module,
        "DEFAULT_HISTORICAL_QUARANTINE_ANCHOR",
        anchor,
    )
    with pytest.raises(ValueError, match="not populated and independently approved"):
        write_historical_quarantine_manifest(
            x_test_path=x_path,
            y_test_path=y_path,
            output_path="artifacts/quarantine.json",
        )
    assert not (tmp_path / "artifacts").exists()


def test_anchor_mismatch_refuses_a_self_consistent_manifest(tmp_path: Path) -> None:
    frame = _frame()
    manifest, anchor, _, _ = _approved_manifest(frame, tmp_path)
    anchor_payload = json.loads(anchor.read_text(encoding="utf-8"))
    anchor_payload["row_hashes_sha256"] = "0" * 64
    _write_payload(anchor, anchor_payload)
    with _environment(frame, tmp_path, anchor):
        with pytest.raises(ValueError, match="approved canonical anchor"):
            load_historical_quarantine_manifest(manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_field",
        "missing_field",
        "malformed_hash",
        "checksum",
        "count",
        "version",
        "windows_path",
    ],
)
def test_manifest_tampering_fails_closed(tmp_path: Path, mutation: str) -> None:
    frame = _frame()
    manifest, anchor, _, _ = _approved_manifest(frame, tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if mutation == "unknown_field":
        payload["unexpected"] = True
    elif mutation == "missing_field":
        del payload["target_column"]
    elif mutation == "malformed_hash":
        payload["row_hashes"][0] = "not-a-hash"
    elif mutation == "checksum":
        payload["row_hashes_sha256"] = "0" * 64
    elif mutation == "count":
        payload["total_row_count"] += 1
    elif mutation == "version":
        payload["format_version"] = "999"
    elif mutation == "windows_path":
        payload["sources"]["x_test"]["filename"] = r"C:\Users\candidate.parquet"
    tampered = _write_payload(tmp_path / f"tampered-{mutation}.json", payload)
    with _environment(frame, tmp_path, anchor):
        with pytest.raises(ValueError):
            load_historical_quarantine_manifest(tampered)


def test_output_path_rejects_escape_absolute_symlink_and_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(quarantine_module, "PROJECT_ROOT", tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    with pytest.raises(ValueError, match="inside ignored artifacts"):
        resolve_quarantine_output_path("outside.json")
    with pytest.raises(ValueError, match="relative path"):
        resolve_quarantine_output_path(str(artifacts / "absolute.json"))
    with pytest.raises(ValueError, match="relative path"):
        resolve_quarantine_output_path(r"C:\temp\quarantine.json")
    with pytest.raises(ValueError, match="relative path"):
        resolve_quarantine_output_path("C:quarantine.json")

    existing = artifacts / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        resolve_quarantine_output_path("artifacts/existing.json")

    target = artifacts / "target.json"
    symlink = artifacts / "symlink.json"
    symlink.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        resolve_quarantine_output_path("artifacts/symlink.json")

    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = artifacts / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        resolve_quarantine_output_path("artifacts/linked-parent/quarantine.json")


def test_production_apis_do_not_accept_alternate_anchor_or_root() -> None:
    public_apis = (
        load_historical_quarantine_anchor,
        build_historical_quarantine_manifest,
        load_historical_quarantine_manifest,
        require_no_historical_test_overlap,
        resolve_quarantine_output_path,
        write_historical_quarantine_manifest,
    )
    for api in public_apis:
        parameters = inspect.signature(api).parameters
        assert "anchor_path" not in parameters
        assert "project_root" not in parameters

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        load_historical_quarantine_anchor(anchor_path=Path("alternate.json"))
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        resolve_quarantine_output_path(
            "artifacts/quarantine.json", project_root=Path("alternate-root")
        )


def test_publication_uses_verified_directory_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    x_path, y_path, anchor = _approved_inputs(frame, tmp_path)
    real_link = os.link
    calls: list[tuple[object, object, dict[str, object]]] = []

    def recording_link(
        source: object, destination: object, **kwargs: object
    ) -> None:
        calls.append((source, destination, kwargs))
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(quarantine_module.os, "link", recording_link)
    monkeypatch.setattr(
        quarantine_module.os,
        "supports_dir_fd",
        os.supports_dir_fd | {recording_link},
    )
    monkeypatch.setattr(
        quarantine_module.os,
        "supports_follow_symlinks",
        os.supports_follow_symlinks | {recording_link},
    )
    with _environment(frame, tmp_path, anchor):
        output = write_historical_quarantine_manifest(
            x_test_path=x_path,
            y_test_path=y_path,
            output_path="artifacts/nested/quarantine.json",
        )

    assert output.is_file()
    assert len(calls) == 1
    source, destination, kwargs = calls[0]
    assert isinstance(source, str) and "/" not in source
    assert destination == "quarantine.json"
    assert kwargs["src_dir_fd"] == kwargs["dst_dir_fd"]
    assert isinstance(kwargs["src_dir_fd"], int)
    assert kwargs["follow_symlinks"] is False


def test_publication_fails_closed_without_safe_os_primitives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(quarantine_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(quarantine_module.os, "supports_dir_fd", set())
    with pytest.raises(RuntimeError, match="Safe quarantine publication requires"):
        resolve_quarantine_output_path("artifacts/quarantine.json")


def test_source_replacement_while_reading_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    x_path, y_path, anchor = _approved_inputs(frame, tmp_path)
    original_read = pd.read_parquet
    changed = False

    def replacing_read(path: Path, *args: object, **kwargs: object) -> pd.DataFrame:
        nonlocal changed
        result = original_read(path, *args, **kwargs)
        if Path(path) == x_path and not changed:
            x_path.write_bytes(x_path.read_bytes() + b"changed")
            changed = True
        return result

    monkeypatch.setattr(pd, "read_parquet", replacing_read)
    with _environment(frame, tmp_path, anchor):
        with pytest.raises(ValueError, match="changed while they were being read"):
            build_historical_quarantine_manifest(
                x_test_path=x_path, y_test_path=y_path
            )


@pytest.mark.parametrize("replace", ["manifest", "anchor"])
def test_checked_manifest_and_anchor_replacement_is_detected(
    tmp_path: Path, replace: str
) -> None:
    frame = _frame()
    manifest, anchor, _, _ = _approved_manifest(frame, tmp_path)
    with _environment(frame, tmp_path, anchor):
        quarantine = load_historical_quarantine_manifest(manifest)
    selected = manifest if replace == "manifest" else anchor
    selected.write_bytes(selected.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed after verification"):
        reverify_historical_quarantine_identity(quarantine)


def test_training_runner_refuses_overlap_before_any_split_or_fit(tmp_path: Path) -> None:
    source_frame = _frame(60)
    source = tmp_path / "authorized.csv"
    source_frame.to_csv(source, index=False)
    approval = write_source_approval(source, "quarantine-gate-fixture")
    curated = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "curated",
        source_kind="new_authorized_development",
        source_reference="quarantine-gate-fixture",
        source_approval_path=approval,
    )
    quarantine_frame = pd.read_csv(curated["curated_dataset"]).iloc[[0, 1]].copy()
    quarantine_path, anchor, _, _ = _approved_manifest(
        quarantine_frame, tmp_path / "quarantine"
    )

    with (
        patch.object(
            quarantine_module,
            "DEFAULT_HISTORICAL_QUARANTINE_ANCHOR",
            anchor,
        ),
        patch.object(quarantine_module, "HISTORICAL_TEST_ROWS", 2),
        patch.object(quarantine_module, "HISTORICAL_TEST_FRAUD", 1),
        patch("scripts.run_development_training._time_roles") as split,
    ):
        with pytest.raises(ValueError, match="overlaps the locked historical test"):
            run_development_training(
                curated_path=curated["curated_dataset"],
                curation_record_path=curated["curation_record"],
                historical_quarantine_path=quarantine_path,
                output_dir=tmp_path / "training",
                candidate_factories={
                    "must_not_fit_1": lambda _labels: pytest.fail("model fit reached"),
                    "must_not_fit_2": lambda _labels: pytest.fail("model fit reached"),
                },
                bootstrap_resamples=10,
            )
        split.assert_not_called()
    assert not (tmp_path / "training").exists()
