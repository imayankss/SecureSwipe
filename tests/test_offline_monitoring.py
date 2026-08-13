"""Privacy, schema, drift, scoring, and determinism tests for offline monitoring."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.create_synthetic_bundle import build_synthetic_bundle, synthetic_training_data
from scripts.create_synthetic_monitoring_demo import generate_demo
from src.monitoring.io import write_report
from src.monitoring.offline import DriftThresholds, audit_batch, monitor_batches


def labeled_synthetic() -> pd.DataFrame:
    frame, labels = synthetic_training_data()
    frame["Class"] = labels
    return frame


def test_invalid_schema_reports_counts_and_never_requires_a_model() -> None:
    reference = labeled_synthetic()
    current = reference.copy()
    current.loc[0, "Amount"] = np.nan
    report = monitor_batches(reference, current, bundle=None)
    assert report["status"] == "invalid"
    assert report["signals"] == {
        "feature_drift": None,
        "schema_violation": True,
        "score_drift": None,
    }
    current_audit = report["schema"]["current"]
    assert current_audit["missingness"] == {"Amount": 1}
    assert "nan" not in json.dumps(report).lower()


@pytest.mark.parametrize(
    "mutator,code",
    [
        (lambda frame: frame.drop(columns=["V2"]), "missing_columns"),
        (lambda frame: frame.assign(secret=1.0), "unexpected_columns"),
        (lambda frame: frame.iloc[:, ::-1], "incorrect_column_order"),
        (lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True), "dataset_contract"),
    ],
)
def test_contract_audit_reports_violation_without_row_values(mutator: object, code: str) -> None:
    frame = mutator(labeled_synthetic())  # type: ignore[operator]
    audit = audit_batch(frame)
    assert audit["valid"] is False
    assert code in {violation["code"] for violation in audit["violations"]}
    assert "0.176" not in json.dumps(audit)


def test_same_batch_has_no_drift_and_is_deterministic() -> None:
    bundle, _ = build_synthetic_bundle()
    frame = labeled_synthetic()
    first = monitor_batches(frame, frame.copy(), bundle=bundle)
    second = monitor_batches(frame, frame.copy(), bundle=bundle)
    assert first == second
    assert first["status"] == "valid"
    assert first["signals"] == {
        "feature_drift": False,
        "schema_violation": False,
        "score_drift": False,
    }
    assert first["performance"]["current"]["available"] is True
    assert first["performance"]["calibrated_probability_claim"] is False


def test_shift_is_detected_but_not_called_model_failure() -> None:
    bundle, _ = build_synthetic_bundle()
    reference = labeled_synthetic()
    shifted = reference.copy()
    shifted["Amount"] = shifted["Amount"] * 4.0 + 100.0
    shifted["V1"] = shifted["V1"] + 3.0
    report = monitor_batches(
        reference,
        shifted,
        bundle=bundle,
        thresholds=DriftThresholds(population_stability_index=0.2, ks_statistic=0.2),
    )
    assert report["signals"]["feature_drift"] is True
    assert report["feature_drift"]["features"]["Amount"]["drift_signal"] is True
    assert report["feature_drift"]["features"]["V1"]["drift_signal"] is True
    assert report["interpretation"]["drift_is_model_failure"] is False
    assert "investigation" in report["interpretation"]["guidance"]


def test_unlabeled_and_one_class_batches_do_not_invent_performance() -> None:
    bundle, _ = build_synthetic_bundle()
    labeled = labeled_synthetic()
    unlabeled = labeled.drop(columns=["Class"])
    report = monitor_batches(unlabeled, unlabeled.copy(), bundle=bundle)
    assert report["performance"]["current"] == {
        "available": False,
        "reason": "Delayed labels were not supplied.",
    }

    one_class = labeled.copy()
    one_class["Class"] = 0
    one_class_report = monitor_batches(one_class, one_class.copy(), bundle=bundle)
    assert one_class_report["performance"]["current"]["available"] is False
    assert "Both delayed-label classes" in one_class_report["performance"]["current"]["reason"]


def test_demo_and_report_check_are_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    generate_demo(first)
    generate_demo(second)
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    write_report(payload, first, check=True)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_report(payload, first, check=False)
    first.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        write_report(payload, first, check=True)
