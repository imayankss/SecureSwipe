"""Synthetic historical-quarantine helpers shared by development tests."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import numpy as np
import pandas as pd

import src.data.historical_quarantine as quarantine_module
from src.artifacts.bundle import sha256_file
from src.data.historical_quarantine import (
    FEATURE_DTYPE,
    HISTORICAL_QUARANTINE_ANCHOR_FORMAT_VERSION,
    HISTORICAL_QUARANTINE_FORMAT_VERSION,
    ROW_HASH_ALGORITHM,
    TARGET_DTYPE,
    canonical_row_hashes,
    row_hashes_checksum,
    write_historical_quarantine_manifest,
)
from src.preprocessing.feature_config import ALL_FEATURES, REQUIRED_COLUMNS

SYNTHETIC_QUARANTINE_ROWS = 2
SYNTHETIC_QUARANTINE_FRAUD = 1


@contextmanager
def approved_quarantine_environment(
    anchor_path: Path,
    project_root: Path,
    *,
    rows: int,
    fraud: int,
) -> Iterator[None]:
    """Redirect canonical production constants only within a synthetic test."""
    with (
        patch.object(quarantine_module, "PROJECT_ROOT", project_root),
        patch.object(
            quarantine_module,
            "DEFAULT_HISTORICAL_QUARANTINE_ANCHOR",
            anchor_path,
        ),
        patch.object(quarantine_module, "HISTORICAL_TEST_ROWS", rows),
        patch.object(quarantine_module, "HISTORICAL_TEST_FRAUD", fraud),
    ):
        yield


def write_approved_quarantine_anchor(
    frame: pd.DataFrame,
    x_path: Path,
    y_path: Path,
    anchor_path: Path,
) -> Path:
    """Write test-only approval values independently from manifest construction."""
    row_hashes = canonical_row_hashes(frame)
    unique_rows = len(set(row_hashes))
    payload = {
        "anchor_format_version": HISTORICAL_QUARANTINE_ANCHOR_FORMAT_VERSION,
        "approval_status": "approved",
        "dtype_contract": {
            "features": {feature: FEATURE_DTYPE for feature in ALL_FEATURES},
            "target": {"Class": TARGET_DTYPE},
        },
        "duplicate_row_count": len(frame) - unique_rows,
        "fraud_count": int(frame["Class"].sum()),
        "quarantine_format_version": HISTORICAL_QUARANTINE_FORMAT_VERSION,
        "review_reference": "synthetic-fixture-review-v1",
        "reviewed_by": "test-fixture-reviewer",
        "row_hash_algorithm": ROW_HASH_ALGORITHM,
        "row_hashes_sha256": row_hashes_checksum(row_hashes),
        "source_sha256": {
            "x_test": sha256_file(x_path),
            "y_test": sha256_file(y_path),
        },
        "total_row_count": len(frame),
        "unique_row_count": unique_rows,
    }
    anchor_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return anchor_path


def write_nonoverlapping_quarantine(directory: Path) -> tuple[Path, Path]:
    """Write an approved two-row quarantine outside ordinary fixture values."""
    directory.mkdir(parents=True, exist_ok=True)
    values = np.zeros((SYNTHETIC_QUARANTINE_ROWS, len(ALL_FEATURES)), dtype=np.float64)
    frame = pd.DataFrame(values, columns=ALL_FEATURES)
    frame["Time"] = [9_000_000.0, 9_000_001.0]
    frame["Amount"] = [9_000_002.0, 9_000_003.0]
    frame["Class"] = np.array([0, 1], dtype=np.int64)
    frame = frame[REQUIRED_COLUMNS]
    x_path = directory / "quarantine-X.parquet"
    y_path = directory / "quarantine-y.parquet"
    frame[ALL_FEATURES].to_parquet(x_path, index=True)
    frame[["Class"]].to_parquet(y_path, index=True)
    anchor = write_approved_quarantine_anchor(
        frame, x_path, y_path, directory / "historical-quarantine-anchor.json"
    )
    with approved_quarantine_environment(
        anchor,
        directory,
        rows=SYNTHETIC_QUARANTINE_ROWS,
        fraud=SYNTHETIC_QUARANTINE_FRAUD,
    ):
        manifest = write_historical_quarantine_manifest(
            x_test_path=x_path,
            y_test_path=y_path,
            output_path="artifacts/historical-quarantine.json",
        )
    return manifest, anchor
