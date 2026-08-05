"""Tests for the deployment-safe SecureSwipe web artifact export."""

from __future__ import annotations

import json
from datetime import datetime, timezone

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
