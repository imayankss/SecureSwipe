"""Read-only historical-quarantine anchor-candidate tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import src.data.historical_quarantine as quarantine_module
from scripts.derive_historical_quarantine_anchor_candidate import main, parse_args
from src.artifacts.bundle import sha256_file
from src.data.historical_quarantine import (
    DEFAULT_HISTORICAL_QUARANTINE_ANCHOR,
    MANIFEST_SERIALIZATION,
    build_historical_quarantine_anchor_candidate,
    build_historical_quarantine_manifest,
)
from src.preprocessing.feature_config import ALL_FEATURES, REQUIRED_COLUMNS
from tests.historical_quarantine_helpers import (
    approved_quarantine_environment,
    write_approved_quarantine_anchor,
)


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


def _split(frame: pd.DataFrame, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    x_path = directory / "X_test.parquet"
    y_path = directory / "y_test.parquet"
    frame[ALL_FEATURES].to_parquet(x_path, index=True)
    frame[["Class"]].to_parquet(y_path, index=True)
    return x_path, y_path


def _use_expected_counts(
    monkeypatch: pytest.MonkeyPatch, frame: pd.DataFrame
) -> None:
    monkeypatch.setattr(quarantine_module, "HISTORICAL_TEST_ROWS", len(frame))
    monkeypatch.setattr(
        quarantine_module,
        "HISTORICAL_TEST_FRAUD",
        int(frame["Class"].sum()),
    )


def test_candidate_is_deterministic_hash_only_and_matches_manifest_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    x_path, y_path = _split(frame, tmp_path)
    _use_expected_counts(monkeypatch, frame)
    tracked_anchor_before = DEFAULT_HISTORICAL_QUARANTINE_ANCHOR.read_bytes()
    with monkeypatch.context() as context:
        context.setattr(
            quarantine_module,
            "load_historical_quarantine_anchor",
            lambda: pytest.fail("candidate attempted to trust the existing anchor"),
        )
        first = build_historical_quarantine_anchor_candidate(
            x_test_path=x_path,
            y_test_path=y_path,
        )
        second = build_historical_quarantine_anchor_candidate(
            x_test_path=x_path,
            y_test_path=y_path,
        )

    assert first == second
    assert first["approval_status"] == "unapproved_candidate"
    assert first["approval_required"] is True
    assert first["decision_eligible"] is False
    assert first["training_use_prohibited"] is True
    assert first["candidate_contains_row_hashes"] is False
    assert first["contains_raw_transaction_values"] is False
    assert first["manifest_serialization"] == MANIFEST_SERIALIZATION
    assert first["total_row_count"] == len(frame)
    assert first["fraud_count"] == int(frame["Class"].sum())
    assert first["source_sha256"] == {
        "x_test": sha256_file(x_path),
        "y_test": sha256_file(y_path),
    }
    assert first["source_files"]["x_test"]["filename"] == x_path.name

    anchor = write_approved_quarantine_anchor(
        frame,
        x_path,
        y_path,
        tmp_path / "synthetic-approved-anchor.json",
    )
    with approved_quarantine_environment(
        anchor,
        tmp_path,
        rows=len(frame),
        fraud=int(frame["Class"].sum()),
    ):
        manifest = build_historical_quarantine_manifest(
            x_test_path=x_path,
            y_test_path=y_path,
        )
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    assert first["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()

    encoded = json.dumps(first, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert '"row_hashes":' not in encoded
    assert DEFAULT_HISTORICAL_QUARANTINE_ANCHOR.read_bytes() == tracked_anchor_before
    assert not (tmp_path / "artifacts").exists()


def test_cli_prints_candidate_without_accepting_an_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frame = _frame()
    x_path, y_path = _split(frame, tmp_path)
    _use_expected_counts(monkeypatch, frame)

    assert main(["--x-test", str(x_path), "--y-test", str(y_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidate_kind"] == "historical_test_quarantine_anchor_candidate"
    assert not (tmp_path / "artifacts").exists()

    with pytest.raises(SystemExit):
        parse_args(
            [
                "--x-test",
                str(x_path),
                "--y-test",
                str(y_path),
                "--output",
                str(tmp_path / "candidate.json"),
            ]
        )
    assert not (tmp_path / "candidate.json").exists()


def test_candidate_rejects_wrong_predeclared_counts(tmp_path: Path) -> None:
    frame = _frame()
    x_path, y_path = _split(frame, tmp_path)
    with pytest.raises(ValueError, match="predeclared retained split counts"):
        build_historical_quarantine_anchor_candidate(
            x_test_path=x_path,
            y_test_path=y_path,
        )


def test_candidate_preserves_exact_shared_dtype_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    frame["V1"] = frame["V1"].astype(np.float32)
    x_path, y_path = _split(frame, tmp_path)
    _use_expected_counts(monkeypatch, frame)
    with pytest.raises(ValueError, match="exact float64"):
        build_historical_quarantine_anchor_candidate(
            x_test_path=x_path,
            y_test_path=y_path,
        )


def test_candidate_preserves_shared_source_replacement_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    x_path, y_path = _split(frame, tmp_path)
    _use_expected_counts(monkeypatch, frame)
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
    with pytest.raises(ValueError, match="changed while they were being read"):
        build_historical_quarantine_anchor_candidate(
            x_test_path=x_path,
            y_test_path=y_path,
        )
