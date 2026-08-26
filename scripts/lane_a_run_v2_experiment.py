"""Lane A v2: bounded feature experiment, calibration, and capacity frontier.

Phases 4, 5 and 7 of the v2 amendment. XGBoost only, at the accepted v1
parameters, seed 42. ``final_test`` is never named, loaded, scored, or counted.
All artifacts go to a private directory outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.calibration import (  # noqa: E402
    apply_calibrator,
    evaluate_calibration,
    fit_calibrator,
)
from src.lane_a.capacity import (  # noqa: E402
    DECISIONS,
    ILLUSTRATIVE_CAPACITY_TIERS,
    POLICY_VERSION,
    MerchantCapacityConfig,
    frontier_row,
    workload_for_recall,
)
from src.lane_a.evaluation import (  # noqa: E402
    CALIBRATION_POSITIVE_FLOOR,
    MINIMUM_BRIER_IMPROVEMENT,
    core_metrics,
    paired_ap_difference,
    paired_brier_improvement,
)
from src.lane_a.modelling import (  # noqa: E402
    MIN_CATEGORY_FREQUENCY,
    RANDOM_SEED,
    ModellingError,
    build_variant_preprocessor,
    class_weight_from_training,
    model_specifications,
)
from src.lane_a.roles import (  # noqa: E402
    CALIBRATION_EVAL,
    CALIBRATION_FIT,
    TRAINING,
    VALIDATION_THRESHOLD,
    assert_labels_readable,
)
from src.lane_a.serving_schema import IDENTITY_PRESENCE_FEATURE  # noqa: E402
from src.lane_a.variants import (  # noqa: E402
    VARIANTS,
    VARIANTS_BY_ID,
    categorical_fields,
    choose_eligible_variant,
    numeric_fields,
    validate_all,
)

AP_IMPROVEMENT_GATE = 0.01
V1_CONTROL_AP = 0.2135817754
CONTROL_TOLERANCE = 1e-6
VALIDATION_DAYS = (9_940_286 - 8_022_314) / 86400.0
AMENDMENT_PATH = PROJECT_ROOT / "docs/evidence/LANE_A_PROTOCOL_V2_AMENDMENT.md"


def _digest(value: object) -> str:
    """SHA-256 of a canonical JSON representation."""
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _serialized_size(pipeline: Pipeline) -> int:
    """Measure the exact uncompressed joblib payload used for tie-breaking."""
    buffer = io.BytesIO()
    joblib.dump(pipeline, buffer, compress=0)
    return buffer.tell()


def _selected_schema(variant) -> dict[str, object]:
    return {
        "variant": variant.identifier,
        "name": variant.name,
        "input_count": variant.input_count,
        "fields": list(variant.fields),
        "numeric_fields": list(numeric_fields(variant)),
        "categorical_fields": list(categorical_fields(variant)),
        "boolean_fields": [IDENTITY_PRESENCE_FEATURE],
    }


def _preprocessing_configuration(variant) -> dict[str, object]:
    return {
        "numeric": {
            "fields": list(numeric_fields(variant)),
            "imputer": "SimpleImputer",
            "strategy": "median",
            "add_indicator": True,
            "scaler": "StandardScaler",
        },
        "categorical": {
            "fields": list(categorical_fields(variant)),
            "encoder": "OneHotEncoder",
            "handle_unknown": "infrequent_if_exist",
            "min_frequency": MIN_CATEGORY_FREQUENCY,
            "sparse_output": False,
            "dtype": "float32",
        },
        "boolean": {
            "fields": [IDENTITY_PRESENCE_FEATURE],
            "transformer": "passthrough",
        },
        "remainder": "drop",
        "verbose_feature_names_out": False,
        "fit_role": TRAINING,
    }


def _capacity_policy_contract() -> dict[str, object]:
    return {
        "version": POLICY_VERSION,
        "review_budget": "floor(daily_review_capacity * evaluation_period_days)",
        "ranking": "score descending",
        "tie_breaking": "ascending stable private source position",
        "decision_vocabulary": list(DECISIONS),
        "merchant_default": None,
    }


def _git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _working_tree_provenance() -> dict[str, object]:
    status = _git_output("status", "--porcelain=v1", "-uall").splitlines()
    tracked = [line for line in status if not line.startswith("??")]
    untracked = [line for line in status if line.startswith("??")]
    return {
        "head": _git_output("rev-parse", "HEAD"),
        "branch": _git_output("branch", "--show-current"),
        "tracked_changes_present": bool(tracked),
        "tracked_change_count": len(tracked),
        "staged_change_count": len(_git_output("diff", "--cached", "--name-only").splitlines()),
        "untracked_file_count": len(untracked),
    }


def _load(private: Path, role: str) -> tuple[pd.DataFrame, np.ndarray]:
    assert_labels_readable(role)
    features = pd.read_csv(private / f"lane_a_v2_{role}_superset.csv", low_memory=False)
    labels = pd.read_csv(private / f"lane_a_v2_{role}_labels.csv")
    merged = features.merge(labels, on="TransactionID", how="inner", validate="one_to_one")
    if len(merged) != len(features):
        raise ModellingError(f"Feature/label join lost rows for role {role!r}.")
    return merged, merged["isFraud"].to_numpy(dtype=int)


def _pipeline(variant, parameters) -> Pipeline:
    from xgboost import XGBClassifier

    return Pipeline(
        steps=[
            (
                "preprocess",
                build_variant_preprocessor(
                    numeric_fields(variant),
                    categorical_fields(variant),
                    (IDENTITY_PRESENCE_FEATURE,),
                ),
            ),
            ("model", XGBClassifier(**parameters)),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--amendment-sha256", required=True)
    args = parser.parse_args()
    private = args.private_dir.expanduser().resolve(strict=True)
    if private == PROJECT_ROOT or PROJECT_ROOT in private.parents:
        raise ModellingError("Private directory must be outside the repository.")

    actual_amendment_sha256 = _sha256_file(AMENDMENT_PATH)
    if args.amendment_sha256 != actual_amendment_sha256:
        raise ModellingError(
            "Amendment digest does not match the v2 protocol file; stopping before data load."
        )

    validate_all()
    report: dict[str, object] = {
        "lane": "A",
        "protocol": "v2",
        "amendment_sha256": actual_amendment_sha256,
        "seed": RANDOM_SEED,
        "final_test_touched": False,
    }

    train_df, y_train = _load(private, TRAINING)
    val_df, y_val = _load(private, VALIDATION_THRESHOLD)
    spw = class_weight_from_training(y_train)
    xgb_params = model_specifications(spw)["xgboost"]
    report["xgboost_parameters"] = xgb_params
    report["training"] = {
        "rows": int(len(train_df)),
        "positives": int(y_train.sum()),
        "scale_pos_weight": spw,
    }

    variant_results: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Pipeline] = {}
    scores: dict[str, np.ndarray] = {}
    for variant in VARIANTS:
        started = time.time()
        try:
            pipeline = _pipeline(variant, xgb_params)
            pipeline.fit(train_df[list(variant.fields)], y_train)
            score = pipeline.predict_proba(val_df[list(variant.fields)])[:, 1]
            metrics = core_metrics(y_val, score)
            artifact_size_bytes = _serialized_size(pipeline)
            fitted[variant.identifier] = pipeline
            scores[variant.identifier] = score
            variant_results[variant.identifier] = {
                "name": variant.name,
                "input_count": variant.input_count,
                "fields": list(variant.fields),
                "average_precision": metrics["average_precision"],
                "roc_auc": metrics["roc_auc"],
                "fit_seconds": round(time.time() - started, 2),
                "artifact_size_bytes": artifact_size_bytes,
                "status": "ok",
            }
            print(
                f"[v2] {variant.identifier} {variant.name}: AP={metrics['average_precision']:.6f}",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001 - failures are reported, not hidden
            variant_results[variant.identifier] = {
                "name": variant.name,
                "input_count": variant.input_count,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"[v2] {variant.identifier}: FAILED {exc}", file=sys.stderr)

    # positive control
    control = variant_results.get("A", {})
    control_ap = control.get("average_precision")
    control_ok = (
        control.get("status") == "ok"
        and control_ap is not None
        and abs(float(control_ap) - V1_CONTROL_AP) <= CONTROL_TOLERANCE
    )
    report["positive_control"] = {
        "variant": "A",
        "v1_recorded_ap": V1_CONTROL_AP,
        "v2_reproduced_ap": control_ap,
        "absolute_difference": (
            abs(float(control_ap) - V1_CONTROL_AP) if control_ap is not None else None
        ),
        "tolerance": CONTROL_TOLERANCE,
        "reproduced": control_ok,
    }
    if not control_ok:
        report["stopped"] = "variant A did not reproduce the v1 control"
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 1

    # gates against A
    gates: dict[str, object] = {}
    eligible: list[str] = []
    for identifier in ("B", "C", "D", "E"):
        result = variant_results[identifier]
        if result.get("status") != "ok":
            gates[identifier] = {"eligible": False, "reason": "variant failed to train"}
            continue
        interval = paired_ap_difference(y_val, scores[identifier], scores["A"])
        improvement = float(interval.point)
        meets_margin = improvement >= AP_IMPROVEMENT_GATE
        ci_above_zero = interval.excludes_zero_above()
        passes = meets_margin and ci_above_zero
        gates[identifier] = {
            "ap_improvement_vs_A": improvement,
            "ci_lower": interval.lower,
            "ci_upper": interval.upper,
            "meets_margin_0.01": meets_margin,
            "ci_lower_above_zero": ci_above_zero,
            "eligible": passes,
            "verdict": ("not distinguishable" if interval.includes_zero() else "distinguishable"),
        }
        if passes:
            eligible.append(identifier)

    if eligible:
        selected = choose_eligible_variant(eligible, variant_results)
        selection_reason = "highest validation AP among variants passing both gates"
    else:
        selected = "A"
        selection_reason = (
            "no expanded variant cleared both gates; the 13-feature baseline is retained"
        )
    report["variants"] = variant_results
    report["gates"] = gates
    report["selection"] = {
        "selected_variant": selected,
        "selected_name": VARIANTS_BY_ID[selected].name,
        "input_count": VARIANTS_BY_ID[selected].input_count,
        "reason": selection_reason,
        "baseline_retained": selected == "A",
        "development_optimistic": (
            "validation_threshold has now been used for v1 model selection, v1 "
            "threshold work and v2 feature selection; these are development "
            "estimates, not unbiased estimates of deployed performance"
        ),
    }

    # ---------------- Phase 5: calibration ----------------
    variant = VARIANTS_BY_ID[selected]
    cfit_df, y_cfit = _load(private, CALIBRATION_FIT)
    ceval_df, y_ceval = _load(private, CALIBRATION_EVAL)
    pipeline = fitted[selected]
    s_cfit = pipeline.predict_proba(cfit_df[list(variant.fields)])[:, 1]
    s_ceval = pipeline.predict_proba(ceval_df[list(variant.fields)])[:, 1]
    positives = int(y_ceval.sum())
    identity_metrics = evaluate_calibration(y_ceval, s_ceval)
    calibration: dict[str, object] = {
        "calibration_eval_positives": positives,
        "positive_floor": CALIBRATION_POSITIVE_FLOOR,
        "identity_brier": identity_metrics["brier_score"],
        "identity_ece": identity_metrics["expected_calibration_error"],
        "isotonic_reopened": False,
        "prior_use_disclosure": (
            "calibration_eval was already used during v1 calibration selection, so "
            "this v2 result is not an untouched independent estimate"
        ),
    }
    selected_calibrator = None
    if positives < CALIBRATION_POSITIVE_FLOOR:
        calibration["decision"] = "identity"
        calibration["decision_reason"] = (
            f"only {positives} positives; floor is {CALIBRATION_POSITIVE_FLOOR}"
        )
    else:
        calibrator = fit_calibrator(s_cfit, y_cfit, "platt")
        values = apply_calibrator(calibrator, s_ceval)
        platt_metrics = evaluate_calibration(y_ceval, values)
        interval = paired_brier_improvement(y_ceval, s_ceval, values)
        passes = (
            float(interval.point) >= MINIMUM_BRIER_IMPROVEMENT and interval.excludes_zero_above()
        )
        calibration["platt"] = {
            "brier": platt_metrics["brier_score"],
            "ece": platt_metrics["expected_calibration_error"],
            "improvement": float(interval.point),
            "ci_lower": interval.lower,
            "ci_upper": interval.upper,
            "meets_margin": float(interval.point) >= MINIMUM_BRIER_IMPROVEMENT,
            "ci_lower_above_zero": interval.excludes_zero_above(),
            "accepted": passes,
        }
        calibration["decision"] = "platt" if passes else "identity"
        calibration["decision_reason"] = (
            "cleared the Brier margin with a bootstrap lower bound above zero"
            if passes
            else "did not clear the pre-registered margin and CI condition"
        )
        if passes:
            selected_calibrator = calibrator
    calibration["score_terminology"] = (
        "calibrated probability" if selected_calibrator is not None else "raw model score"
    )
    report["calibration"] = calibration

    # ---------------- Phase 7: capacity frontier ----------------
    val_scores = scores[selected]
    if selected_calibrator is not None:
        val_scores = apply_calibrator(selected_calibrator, val_scores)
    frontier = [
        frontier_row(
            y_val,
            val_scores,
            MerchantCapacityConfig(
                daily_review_capacity=tier, evaluation_period_days=VALIDATION_DAYS
            ),
        )
        for tier in ILLUSTRATIVE_CAPACITY_TIERS
    ]
    report["capacity_frontier"] = {
        "role": VALIDATION_THRESHOLD,
        "evaluation_period_days": round(VALIDATION_DAYS, 4),
        "population": int(len(y_val)),
        "positives": int(y_val.sum()),
        "tiers": frontier,
    }
    report["workload_for_recall_80"] = workload_for_recall(
        y_val, val_scores, evaluation_period_days=VALIDATION_DAYS
    )

    # ---------------- freeze ----------------
    model_path = private / f"lane_a_v2_{selected}_pipeline.joblib"
    joblib.dump(pipeline, model_path)
    calibrator_sha256 = None
    if selected_calibrator is not None:
        calibrator_path = private / "lane_a_v2_calibrator.joblib"
        joblib.dump(selected_calibrator, calibrator_path)
        calibrator_sha256 = _sha256_file(calibrator_path)

    schema = _selected_schema(variant)
    preprocessing = _preprocessing_configuration(variant)
    policy = _capacity_policy_contract()
    report["frozen"] = {
        "selected_variant": selected,
        "selected_schema": schema,
        "selected_schema_digest": _digest(schema),
        "preprocessing_configuration": preprocessing,
        "preprocessing_configuration_digest": _digest(preprocessing),
        "xgboost_configuration_digest": _digest(xgb_params),
        "pipeline_sha256": _sha256_file(model_path),
        "calibrator_present": selected_calibrator is not None,
        "calibrator_sha256": calibrator_sha256,
        "calibration_decision_digest": _digest(calibration),
        "capacity_policy_version": POLICY_VERSION,
        "capacity_policy_contract": policy,
        "capacity_policy_digest": _digest(policy),
        "capacity_policy_source_sha256": _sha256_file(PROJECT_ROOT / "src/lane_a/capacity.py"),
        "code_sha256": {
            "experiment_runner": _sha256_file(Path(__file__)),
            "variants": _sha256_file(PROJECT_ROOT / "src/lane_a/variants.py"),
            "modelling": _sha256_file(PROJECT_ROOT / "src/lane_a/modelling.py"),
            "lane_a_evaluation": _sha256_file(PROJECT_ROOT / "src/lane_a/evaluation.py"),
            "calibration": _sha256_file(PROJECT_ROOT / "src/evaluation/calibration.py"),
        },
        "working_tree_provenance": _working_tree_provenance(),
    }
    report["frontier_digest"] = hashlib.sha256(
        json.dumps(frontier, sort_keys=True, default=str).encode()
    ).hexdigest()

    (private / "lane_a_v2_run.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
