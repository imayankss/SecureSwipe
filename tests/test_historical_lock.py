"""Historical observation integrity and non-reuse tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_final_evaluation import run_final_evaluation
from src.artifacts.bundle import sha256_file
from src.evaluation.historical_lock import (
    HistoricalObservationError,
    verify_historical_observation,
)
from src.utils.config import load_project_config

ROOT = Path(__file__).resolve().parents[1]


def test_tracked_historical_observation_verifies() -> None:
    config = load_project_config()
    lock = verify_historical_observation(config.reports.historical_lock, ROOT)
    assert lock["evaluation_scope"] == "historical_reported_test"
    assert set(lock["files"]) == {
        "final_evaluation_json",
        "final_evaluation_report",
        "selected_validation_thresholds",
    }


def test_historical_verifier_detects_tamper_before_use(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"metric": 1}\n', encoding="utf-8")
    lock = {
        "lock_version": "1",
        "evaluation_scope": "historical_reported_test",
        "files": {
            "evidence": {
                "path": "evidence.json",
                "sha256": sha256_file(evidence),
            }
        },
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    verify_historical_observation(lock_path, tmp_path)
    evidence.write_text('{"metric": 2}\n', encoding="utf-8")
    with pytest.raises(HistoricalObservationError, match="changed"):
        verify_historical_observation(lock_path, tmp_path)


def test_historical_evaluation_runner_is_permanently_locked() -> None:
    with pytest.raises(HistoricalObservationError, match="already observed"):
        run_final_evaluation()
