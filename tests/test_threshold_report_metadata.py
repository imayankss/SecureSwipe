"""Threshold report metadata must derive from caller policy, not stale constants."""

from scripts.run_day6_threshold_tuning import build_day6_threshold_tuning_report


def test_non_default_recall_policy_propagates_to_report() -> None:
    row = {
        "threshold": 0.73,
        "precision": 0.6,
        "recall": 0.74,
        "f1": 0.66,
        "tp": 10,
        "fp": 5,
        "fn": 3,
        "tn": 100,
    }
    report = build_day6_threshold_tuning_report(
        model_name="synthetic",
        validation_rows=118,
        validation_frauds=13,
        selected_thresholds={"default": row, "best_f1": row, "recall_target": row},
        min_recall=0.73,
        generated_at="deterministic",
    )
    assert "recall >= 0.73" in report
    assert "at least 80%" not in report
    assert "Recommended Operating" not in report
    assert "Development Operating Point" in report
