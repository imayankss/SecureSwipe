"""Lane A development run: train, select, calibrate, freeze a threshold.

Phases 2-5 of MT3. Reads only permitted roles; ``final_test`` is never named,
loaded, scored, or counted. All artifacts go to a private directory outside the
repository; only aggregates, decisions and digests are printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import cast

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.calibration import (  # noqa: E402
    apply_calibrator,
    evaluate_calibration,
    fit_calibrator,
)
from src.evaluation.statistical_metrics import classification_wilson_intervals  # noqa: E402
from src.lane_a.evaluation import (  # noqa: E402
    CALIBRATION_POSITIVE_FLOOR,
    MINIMUM_BRIER_IMPROVEMENT,
    confusion_counts,
    core_metrics,
    paired_ap_difference,
    paired_brier_improvement,
    select_champion,
    select_threshold,
)
from src.lane_a.modelling import (  # noqa: E402
    MODEL_ORDER,
    RANDOM_SEED,
    ModellingError,
    TrainedModel,
    build_pipeline,
    class_weight_from_training,
    model_specifications,
    positive_scores,
)
from src.lane_a.roles import (  # noqa: E402
    CALIBRATION_EVAL,
    CALIBRATION_FIT,
    TRAINING,
    VALIDATION_THRESHOLD,
    assert_labels_readable,
)
from src.lane_a.serving_schema import SCHEMA_FIELD_NAMES  # noqa: E402

# Published frozen boundaries (MT3a record); used only for the day span.
VALIDATION_DT_SPAN_SECONDS = 9_940_286 - 8_022_314


def _load(private: Path, role: str) -> tuple[pd.DataFrame, np.ndarray]:
    assert_labels_readable(role)
    features = pd.read_csv(private / f"lane_a_{role}_features.csv")
    labels = pd.read_csv(private / f"lane_a_{role}_labels.csv")
    merged = features.merge(labels, on="TransactionID", how="inner", validate="one_to_one")
    if len(merged) != len(features):
        raise ModellingError(f"Feature/label join lost rows for role {role!r}.")
    return merged[list(SCHEMA_FIELD_NAMES)], merged["isFraud"].to_numpy(dtype=int)


def _digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    args = parser.parse_args()
    private = args.private_dir.expanduser().resolve(strict=True)
    if private == PROJECT_ROOT or PROJECT_ROOT in private.parents:
        raise ModellingError("Private directory must be outside the repository.")

    report: dict[str, object] = {"lane": "A", "seed": RANDOM_SEED, "final_test_touched": False}

    # ---------------- Phase 2: train on training only ----------------
    x_train, y_train = _load(private, TRAINING)
    scale_pos_weight = class_weight_from_training(y_train)
    specs = model_specifications(scale_pos_weight)
    report["training"] = {
        "rows": int(len(x_train)),
        "positives": int(y_train.sum()),
        "prevalence": float(y_train.mean()),
        "scale_pos_weight": scale_pos_weight,
    }

    trained: dict[str, TrainedModel] = {}
    failures: list[dict[str, str]] = []
    for name in MODEL_ORDER:
        started = time.time()
        try:
            pipeline = build_pipeline(name, specs[name])
            pipeline.fit(x_train, y_train)
            trained[name] = TrainedModel(
                name=name,
                pipeline=pipeline,
                parameters=specs[name],
                fit_seconds=time.time() - started,
            )
            print(f"[fit] {name}: ok in {time.time() - started:.1f}s", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - a failure must be reported, not hidden
            failures.append({"model": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[fit] {name}: FAILED {exc}", file=sys.stderr)
    report["model_failures"] = failures
    if not trained:
        report["stopped"] = "no model trained successfully"
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    # ---------------- Phase 3: validation-only selection ----------------
    x_val, y_val = _load(private, VALIDATION_THRESHOLD)
    val_scores = {name: positive_scores(m.pipeline, x_val) for name, m in trained.items()}
    comparison: dict[str, dict[str, object]] = {}
    for name, scores in val_scores.items():
        metrics = core_metrics(y_val, scores)
        predicted = (scores >= 0.5).astype(int)
        counts = confusion_counts(y_val, predicted)
        wilson = classification_wilson_intervals(y_val, predicted)
        comparison[name] = {
            **metrics,
            "confusion_at_0.5": counts,
            "precision_wilson": wilson.get("precision"),
            "recall_wilson": wilson.get("recall"),
            "fit_seconds": round(trained[name].fit_seconds, 2),
            "parameters": trained[name].parameters,
        }
    validation_ap = {
        name: float(cast(float, comparison[name]["average_precision"])) for name in comparison
    }
    champion, reason = select_champion(validation_ap)

    ap_intervals = {}
    for name in comparison:
        if name == champion:
            continue
        interval = paired_ap_difference(y_val, val_scores[champion], val_scores[name])
        ap_intervals[f"{champion}_minus_{name}"] = {
            "point": interval.point,
            "ci_lower": interval.lower,
            "ci_upper": interval.upper,
            "distinguishable": not interval.includes_zero(),
            "verdict": (
                "not distinguishable" if interval.includes_zero() else "distinguishable"
            ),
        }
    report["validation_selection"] = {
        "role": VALIDATION_THRESHOLD,
        "rows": int(len(x_val)),
        "positives": int(y_val.sum()),
        "models": comparison,
        "champion": champion,
        "selection_reason": reason,
        "ap_difference_intervals": ap_intervals,
        "development_optimistic": (
            "validation also supports threshold selection, so this operating point "
            "is development-optimistic and is not an unbiased estimate"
        ),
    }

    # ---------------- Phase 4: calibration on its authorised roles ----------------
    x_cfit, y_cfit = _load(private, CALIBRATION_FIT)
    x_ceval, y_ceval = _load(private, CALIBRATION_EVAL)
    s_cfit = positive_scores(trained[champion].pipeline, x_cfit)
    s_ceval = positive_scores(trained[champion].pipeline, x_ceval)
    eval_positives = int(y_ceval.sum())

    calibration: dict[str, object] = {
        "fit_role": CALIBRATION_FIT,
        "eval_role": CALIBRATION_EVAL,
        "calibration_eval_positives": eval_positives,
        "positive_floor": CALIBRATION_POSITIVE_FLOOR,
    }
    identity_metrics = evaluate_calibration(y_ceval, s_ceval)
    candidates: dict[str, object] = {
        "identity": {
            "brier_score": identity_metrics["brier_score"],
            "expected_calibration_error": identity_metrics["expected_calibration_error"],
        }
    }
    selected_calibrator = None
    if eval_positives < CALIBRATION_POSITIVE_FLOOR:
        calibration["decision"] = "identity"
        calibration["decision_reason"] = (
            f"insufficient positives to select calibration: {eval_positives} < "
            f"{CALIBRATION_POSITIVE_FLOOR}"
        )
        calibration["floor_bound"] = True
    else:
        calibration["floor_bound"] = False
        eligible: list[tuple[str, float, object]] = []
        for method in ("platt", "isotonic"):
            calibrator = fit_calibrator(s_cfit, y_cfit, method)  # type: ignore[arg-type]
            values = apply_calibrator(calibrator, s_ceval)
            metrics = evaluate_calibration(y_ceval, values)
            interval = paired_brier_improvement(y_ceval, s_ceval, values)
            improvement = float(interval.point)
            passes = (
                improvement >= MINIMUM_BRIER_IMPROVEMENT and interval.excludes_zero_above()
            )
            candidates[method] = {
                "brier_score": metrics["brier_score"],
                "expected_calibration_error": metrics["expected_calibration_error"],
                "improvement_vs_identity": improvement,
                "improvement_ci_lower": interval.lower,
                "improvement_ci_upper": interval.upper,
                "meets_margin": improvement >= MINIMUM_BRIER_IMPROVEMENT,
                "ci_lower_above_zero": interval.excludes_zero_above(),
                "eligible": passes,
            }
            if passes:
                eligible.append((method, metrics["brier_score"], calibrator))
        if eligible:
            eligible.sort(key=lambda item: (item[1],))
            method, _, calibrator = eligible[0]
            calibration["decision"] = method
            calibration["decision_reason"] = (
                "cleared the declared Brier margin with a bootstrap lower bound above zero"
            )
            selected_calibrator = calibrator
        else:
            calibration["decision"] = "identity"
            calibration["decision_reason"] = (
                "no calibrator cleared the pre-registered margin and CI condition"
            )
    calibration["candidates"] = candidates
    calibration["score_type"] = (
        "calibrated_probability" if selected_calibrator is not None else "raw_score"
    )
    report["calibration"] = calibration

    # ---------------- Phase 5: validation-only threshold freeze ----------------
    threshold_scores = val_scores[champion]
    if selected_calibrator is not None:
        threshold_scores = apply_calibrator(selected_calibrator, threshold_scores)
    partition_days = VALIDATION_DT_SPAN_SECONDS / 86400.0
    decision = select_threshold(y_val, threshold_scores, partition_days=partition_days)
    report["threshold"] = {
        "role": VALIDATION_THRESHOLD,
        "partition_days": round(partition_days, 4),
        "review_capacity_per_day_SYNTHETIC": 100,
        "recall_target": 0.80,
        "applied_calibration": calibration["decision"],
        **decision,
    }

    # ---------------- freeze artifacts ----------------
    bundle_path = private / "lane_a_champion_pipeline.joblib"
    joblib.dump(trained[champion].pipeline, bundle_path)
    if selected_calibrator is not None:
        joblib.dump(selected_calibrator, private / "lane_a_calibrator.joblib")
    model_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    report["frozen_artifacts"] = {
        "champion_model": champion,
        "champion_pipeline_sha256": model_sha,
        "calibrator_present": selected_calibrator is not None,
        "report_digest": None,
    }
    report["frozen_artifacts"]["report_digest"] = _digest(report)  # type: ignore[index]

    (private / "lane_a_development_run.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
