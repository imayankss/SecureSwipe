"""Tests for the deployment-safe SecureSwipe web artifact export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

import scripts.export_web_data as exporter
from scripts.export_web_data import build_web_payload, export_web_data, sanitize_for_json


def test_web_payload_matches_locked_project_outputs() -> None:
    payload = build_web_payload()

    assert payload["project"]["deploymentMode"] == "precomputed-demonstration"
    assert payload["dataset"]["totalTransactions"] == 284_807
    assert payload["modelSelection"]["modelName"] == "xgboost_baseline"
    assert payload["modelSelection"]["validationMetrics"]["pr_auc"] == 0.8129
    assert payload["finalEvaluation"]["pr_auc"] == 0.8287848539773868
    assert payload["finalEvaluation"]["threshold"] == 0.53
    assert payload["finalEvaluation"]["true_positives"] == 62
    assert len(payload["thresholdAnalysis"]["points"]) == 99
    assert payload["thresholdAnalysis"]["costAnalysisAvailable"] is False
    assert payload["explainability"]["features"][0]["feature"] == "V4"
    assert payload["curves"]["precisionRecall"]["averagePrecision"] == 0.8129
    assert "0.53" in payload["methodology"]["selection"]
    assert "future-performance guarantee" in payload["methodology"]["selection"]


def test_export_writes_strict_json_without_model_or_transaction_data(tmp_path) -> None:
    output = tmp_path / "dashboard.json"
    export_web_data(output, sync_assets=False)

    raw = output.read_text(encoding="utf-8")
    payload = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

    assert "NaN" not in raw
    assert "Infinity" not in raw
    assert payload["sources"]
    assert "transactions" not in payload
    assert "modelArtifact" not in payload


def test_json_sanitizer_handles_scientific_scalars_and_non_finite_values() -> None:
    class Scalar:
        def item(self) -> int:
            return 7

    result = sanitize_for_json(
        {
            "timestamp": datetime(2026, 1, 2, tzinfo=timezone.utc),
            "scalar": Scalar(),
            "nan": float("nan"),
            "infinity": float("inf"),
        }
    )

    assert result == {
        "timestamp": "2026-01-02T00:00:00+00:00",
        "scalar": 7,
        "nan": None,
        "infinity": None,
    }


def test_export_is_byte_deterministic(tmp_path: Path) -> None:
    first = export_web_data(tmp_path / "first.json", sync_assets=False)
    second = export_web_data(tmp_path / "second.json", sync_assets=False)
    assert first.read_bytes() == second.read_bytes()


def test_figure_verification_is_read_only_on_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    published = tmp_path / "published.png"
    source.write_bytes(b"verified")
    published.write_bytes(b"tampered")
    before = published.read_bytes()
    monkeypatch.setattr(exporter, "_figure_pairs", lambda: [(source, published)])

    with pytest.raises(ValueError, match="stale or modified"):
        exporter.verify_public_figures()
    assert published.read_bytes() == before


def test_source_digest_changes_when_a_figure_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = []
    for index in range(2):
        report = tmp_path / f"report-{index}.txt"
        report.write_text(f"report {index}", encoding="utf-8")
        reports.append(report)
    figure = tmp_path / "source.png"
    published = tmp_path / "published.png"
    figure.write_bytes(b"first")
    published.write_bytes(b"first")
    monkeypatch.setattr(exporter, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(exporter, "SOURCE_FILES", tuple(reports))
    monkeypatch.setattr(exporter, "_figure_pairs", lambda: [(figure, published)])
    first = exporter._source_digest()
    figure.write_bytes(b"second")
    assert exporter._source_digest() != first


def test_threshold_tamper_fails_metric_cross_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = pd.read_csv(exporter.THRESHOLD_METRICS)
    frame.loc[0, "precision"] = 0.999
    tampered = tmp_path / "thresholds.csv"
    frame.to_csv(tampered, index=False)
    monkeypatch.setattr(exporter, "THRESHOLD_METRICS", tampered)
    with pytest.raises(ValueError, match="confusion-matrix"):
        exporter._parse_threshold_points(42_721, 74)


def test_selected_threshold_tamper_fails_sweep_cross_check() -> None:
    points = exporter._parse_threshold_points(42_721, 74)
    selected_raw = exporter._read_json(exporter.SELECTED_THRESHOLDS)
    selected = exporter._normalise_selected_thresholds(selected_raw)
    selected[0]["recall"] = 0.123
    with pytest.raises(ValueError, match="stale recall"):
        exporter._validate_selected_thresholds(selected, points)


def test_final_threshold_must_equal_selected_validation_threshold() -> None:
    final = exporter._read_json(exporter.FINAL_EVALUATION)
    with pytest.raises(ValueError, match="selected validation threshold"):
        exporter._validate_final_evaluation(
            final,
            test_rows=42_722,
            test_frauds=74,
            selected_threshold=0.77,
        )


def test_methodology_is_derived_from_alternate_threshold() -> None:
    text = exporter._selection_methodology(0.77)
    assert "0.77" in text
    assert "0.53" not in text


def test_check_mode_never_calls_asset_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["export_web_data.py", "--check", "--output", str(exporter.DEFAULT_OUTPUT)]
    )
    monkeypatch.setattr(
        exporter,
        "sync_public_figures",
        lambda: (_ for _ in ()).throw(AssertionError("check attempted a write")),
    )
    exporter.main()
