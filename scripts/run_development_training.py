"""Train, select, evaluate, and atomically package a new-data model bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.schemas import TransactionFeatures  # noqa: E402
from api.service import ModelService  # noqa: E402
from src.artifacts.bundle import (  # noqa: E402
    ModelBundle,
    load_model_bundle,
    save_model_bundle,
)
from src.data.curation import load_curated_dataset, row_content_fingerprints  # noqa: E402
from src.data.data_loader import fingerprint_dataframe  # noqa: E402
from src.evaluation.calibration import apply_calibrator, compare_calibrators  # noqa: E402
from src.evaluation.statistical_metrics import (  # noqa: E402
    classification_wilson_intervals,
    paired_average_precision_difference,
)
from src.evaluation.threshold_tuning import (  # noqa: E402
    build_threshold_metrics_table,
    select_best_f1_threshold,
)
from src.inference.batch_scoring import score_bundle_frame  # noqa: E402
from src.models.advanced_models import (  # noqa: E402
    build_xgboost_classifier,
    calculate_scale_pos_weight,
)
from src.models.baseline_models import (  # noqa: E402
    create_logistic_regression_baseline,
    create_random_forest_baseline,
)
from src.preprocessing.feature_config import ALL_FEATURES, RANDOM_STATE  # noqa: E402
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor  # noqa: E402
from src.utils.evidence_directory import atomic_evidence_directory  # noqa: E402
from src.utils.run_manifest import build_run_manifest, write_run_manifest  # noqa: E402

CandidateFactory = Callable[[pd.Series], Any]
ROLE_ORDER = (
    "model_training",
    "calibration_fit",
    "operating_point_selection",
    "untouched_development_evaluation",
)


def default_candidate_factories() -> dict[str, CandidateFactory]:
    return {
        "logistic_regression": lambda _labels: create_logistic_regression_baseline(),
        "random_forest": lambda _labels: create_random_forest_baseline(),
        "xgboost": lambda labels: build_xgboost_classifier(
            calculate_scale_pos_weight(labels)
        ),
    }


def _json_write(payload: object, path: Path) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _time_roles(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    unique_times = np.unique(frame["Time"].to_numpy(dtype=float))
    if len(unique_times) < 20:
        raise ValueError("Development training requires at least 20 unique Time values.")
    blocks = np.array_split(unique_times, 20)
    role_times = {
        "model_training": np.concatenate(blocks[:10]),
        "calibration_fit": np.concatenate(blocks[10:13]),
        "operating_point_selection": np.concatenate(blocks[13:16]),
        "untouched_development_evaluation": np.concatenate(blocks[16:]),
    }
    roles = {
        role: np.flatnonzero(frame["Time"].isin(times).to_numpy())
        for role, times in role_times.items()
    }
    previous_max: float | None = None
    for role in ROLE_ORDER:
        indices = roles[role]
        labels = set(frame.iloc[indices]["Class"].astype(int))
        if not len(indices) or labels != {0, 1}:
            raise ValueError(f"Role {role} must be non-empty and contain both classes.")
        current_min = float(frame.iloc[indices]["Time"].min())
        current_max = float(frame.iloc[indices]["Time"].max())
        if previous_max is not None and current_min <= previous_max:
            raise RuntimeError("Temporal role boundaries overlap.")
        previous_max = current_max
    return roles


def _fit_candidate(
    raw_train: pd.DataFrame, labels: pd.Series, factory: CandidateFactory
) -> tuple[Any, Any]:
    preprocessor = fit_preprocessor(raw_train, build_preprocessor())
    model = factory(labels)
    model.fit(preprocessor.transform(raw_train), labels)
    return preprocessor, model


def _positive_scores(model: Any, transformed: object) -> np.ndarray:
    if np.asarray(model.classes_).tolist() != [0, 1]:
        raise ValueError("Candidate classes_ must be exactly [0, 1].")
    probabilities = np.asarray(model.predict_proba(transformed), dtype=float)
    scores = probabilities[:, 1]
    if probabilities.ndim != 2 or probabilities.shape[1] != 2 or not np.isfinite(
        scores
    ).all():
        raise ValueError("Candidate produced malformed scores.")
    return scores


def _score_digest(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def run_development_training(
    *,
    curated_path: Path,
    curation_record_path: Path,
    output_dir: Path,
    candidate_factories: Mapping[str, CandidateFactory] | None = None,
    simplicity_margin: float = 0.005,
    minimum_brier_improvement: float = 0.0,
    bootstrap_resamples: int = 2_000,
) -> dict[str, Path]:
    """Use four temporal roles; the last remains untouched until final evidence."""
    frame, raw_curation = load_curated_dataset(
        curated_path,
        curation_record_path,
        require_decision_eligible=True,
    )
    curation = {key: value for key, value in raw_curation.items()}
    curated_fingerprint = str(curation["curated_fingerprint"])
    factories = dict(candidate_factories or default_candidate_factories())
    if len(factories) < 2 or not 0 <= simplicity_margin <= 1:
        raise ValueError("At least two ordered candidates and a valid margin are required.")
    roles = _time_roles(frame)
    hashes = row_content_fingerprints(frame)
    role_hashes = {role: set(hashes.iloc[indices]) for role, indices in roles.items()}
    for left_index, left in enumerate(ROLE_ORDER):
        for right in ROLE_ORDER[left_index + 1 :]:
            if role_hashes[left] & role_hashes[right]:
                raise ValueError(f"Row-content lineage overlap between {left} and {right}.")

    training = frame.iloc[roles["model_training"]]
    calibration = frame.iloc[roles["calibration_fit"]]
    selection = frame.iloc[roles["operating_point_selection"]]
    evaluation = frame.iloc[roles["untouched_development_evaluation"]]
    train_features, train_labels = training[ALL_FEATURES], training["Class"].astype(int)

    selection_scores: dict[str, np.ndarray] = {}
    candidate_rows: list[dict[str, Any]] = []
    for name, factory in factories.items():
        preprocessor, model = _fit_candidate(train_features, train_labels, factory)
        scores = _positive_scores(
            model, preprocessor.transform(selection[ALL_FEATURES])
        )
        selection_scores[name] = scores
        candidate_rows.append(
            {
                "candidate": name,
                "selection_average_precision": float(
                    average_precision_score(selection["Class"], scores)
                ),
                "selection_roc_auc": float(roc_auc_score(selection["Class"], scores)),
            }
        )

    candidate_metrics = pd.DataFrame(candidate_rows)
    best_metric = float(candidate_metrics["selection_average_precision"].max())
    selected_name = next(
        name
        for name in factories
        if float(
            candidate_metrics.loc[
                candidate_metrics["candidate"] == name, "selection_average_precision"
            ].iloc[0]
        )
        >= best_metric - simplicity_margin
    )
    simple_name = next(iter(factories))
    bootstrap = {
        name: paired_average_precision_difference(
            selection["Class"].to_numpy(),
            selection_scores[simple_name],
            selection_scores[name],
            n_resamples=bootstrap_resamples,
            random_seed=RANDOM_STATE,
        )
        for name in factories
        if name != simple_name
    }

    # Random-split diagnostic uses only the pre-evaluation development pool and
    # never participates in selection.
    pre_evaluation = frame.drop(index=evaluation.index)
    random_train, random_validation = train_test_split(
        pre_evaluation,
        test_size=len(selection) / len(pre_evaluation),
        stratify=pre_evaluation["Class"],
        random_state=RANDOM_STATE,
    )
    random_diagnostic: dict[str, float] = {}
    for name, factory in factories.items():
        preprocessor, model = _fit_candidate(
            random_train[ALL_FEATURES], random_train["Class"].astype(int), factory
        )
        scores = _positive_scores(
            model, preprocessor.transform(random_validation[ALL_FEATURES])
        )
        random_diagnostic[name] = float(
            average_precision_score(random_validation["Class"], scores)
        )

    # Refit from a fresh selected estimator on the model-training role only;
    # later role labels remain outside model fitting.
    preprocessor, model = _fit_candidate(
        train_features, train_labels, factories[selected_name]
    )
    calibration_scores = _positive_scores(
        model, preprocessor.transform(calibration[ALL_FEATURES])
    )
    selected_raw_scores = _positive_scores(
        model, preprocessor.transform(selection[ALL_FEATURES])
    )
    calibration_comparison, calibrator, calibration_method = compare_calibrators(
        calibration_scores,
        calibration["Class"].to_numpy(),
        selected_raw_scores,
        selection["Class"].to_numpy(),
        calibration_train_row_ids=sorted(role_hashes["calibration_fit"]),
        evaluation_row_ids=sorted(role_hashes["operating_point_selection"]),
        minimum_brier_improvement=minimum_brier_improvement,
    )
    selection_decision_scores = (
        apply_calibrator(calibrator, selected_raw_scores)
        if calibrator is not None
        else selected_raw_scores
    )
    selected_threshold = select_best_f1_threshold(
        build_threshold_metrics_table(selection["Class"], selection_decision_scores)
    )
    model_identity = hashlib.sha256(
        json.dumps(
            {
                "candidate": selected_name,
                "parameters": model.get_params(deep=True),
            },
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    bundle = ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=calibrator,
        operating_threshold=float(selected_threshold["threshold"]),
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=fingerprint_dataframe(training),
        model_version=(
            f"development-{curated_fingerprint[:12]}-{selected_name}-{model_identity[:12]}"
        ),
        score_type=("calibrated_probability" if calibrator is not None else "raw_score"),
    )

    with atomic_evidence_directory(output_dir) as temporary:
        bundle_manifest = save_model_bundle(bundle, temporary / "bundle")
        loaded = load_model_bundle(bundle_manifest, trusted_root=temporary)
        direct = score_bundle_frame(bundle, evaluation[ALL_FEATURES])
        loaded_scores = score_bundle_frame(loaded, evaluation[ALL_FEATURES])
        transactions = [
            TransactionFeatures(**{feature: float(row[feature]) for feature in ALL_FEATURES})
            for _, row in evaluation.iterrows()
        ]
        service_results = ModelService(loaded).predict_many(transactions)
        service_raw = np.array([result.raw_score for result in service_results])
        service_decision = np.array([result.decision_score for result in service_results])
        np.testing.assert_allclose(direct.raw_scores, loaded_scores.raw_scores, atol=1e-12, rtol=0)
        np.testing.assert_allclose(direct.raw_scores, service_raw, atol=1e-12, rtol=0)
        np.testing.assert_allclose(direct.decision_scores, service_decision, atol=1e-12, rtol=0)

        predictions = (
            direct.decision_scores >= bundle.operating_threshold
        ).astype(int)
        evaluation_payload = {
            "average_precision": float(
                average_precision_score(evaluation["Class"], direct.decision_scores)
            ),
            "brier_score": float(
                brier_score_loss(evaluation["Class"], direct.decision_scores)
            ),
            "evaluation_scope": "untouched_development_evaluation",
            "operating_threshold": bundle.operating_threshold,
            "roc_auc": float(roc_auc_score(evaluation["Class"], direct.decision_scores)),
            "wilson_intervals": classification_wilson_intervals(
                evaluation["Class"].to_numpy(), predictions
            ),
        }
        lineage_payload = {
            role: {
                "content_fingerprint": hashlib.sha256(
                    "".join(sorted(role_hashes[role])).encode("ascii")
                ).hexdigest(),
                "fraud_rows": int(frame.iloc[roles[role]]["Class"].sum()),
                "rows": len(roles[role]),
                "time_min": float(frame.iloc[roles[role]]["Time"].min()),
                "time_max": float(frame.iloc[roles[role]]["Time"].max()),
            }
            for role in ROLE_ORDER
        }
        selection_payload = {
            "bootstrap_complex_minus_simple": bootstrap,
            "calibration_method": calibration_method,
            "evaluation_was_untouched_during_selection": True,
            "primary_metric": "average_precision",
            "random_split_diagnostic_average_precision": random_diagnostic,
            "selected_model": selected_name,
            "selected_model_identity_sha256": model_identity,
            "selected_candidate_refit_scope": "model_training",
            "selection_scope": "operating_point_selection",
            "simplicity_margin": simplicity_margin,
            "threshold": selected_threshold,
        }
        parity_payload = {
            "decision_score_sha256": _score_digest(direct.decision_scores),
            "evaluation_rows": len(evaluation),
            "loaded_raw_score_sha256": _score_digest(loaded_scores.raw_scores),
            "maximum_absolute_difference": float(
                max(
                    np.max(np.abs(direct.raw_scores - service_raw)),
                    np.max(np.abs(direct.decision_scores - service_decision)),
                )
            ),
            "model_version": bundle.model_version,
            "raw_score_sha256": _score_digest(direct.raw_scores),
            "service_raw_score_sha256": _score_digest(service_raw),
            "tolerance": 1e-12,
        }
        outputs = {
            "calibration_comparison": temporary / "calibration_comparison.csv",
            "candidate_comparison": temporary / "candidate_comparison.csv",
            "evaluation": temporary / "untouched_evaluation.json",
            "golden_parity": temporary / "golden_parity.json",
            "lineage": temporary / "lineage.json",
            "selection": temporary / "selection.json",
            "development_scores": temporary / "development_scores.csv",
        }
        score_evidence = pd.concat(
            [
                pd.DataFrame(
                    {
                        "row_fingerprint": list(hashes.iloc[roles["calibration_fit"]]),
                        "partition": "calibration_fit",
                        "y_true": calibration["Class"].to_numpy(dtype=int),
                        "raw_score": calibration_scores,
                    }
                ),
                pd.DataFrame(
                    {
                        "row_fingerprint": list(
                            hashes.iloc[roles["operating_point_selection"]]
                        ),
                        "partition": "operating_point_selection",
                        "y_true": selection["Class"].to_numpy(dtype=int),
                        "raw_score": selected_raw_scores,
                    }
                ),
                pd.DataFrame(
                    {
                        "row_fingerprint": list(
                            hashes.iloc[roles["untouched_development_evaluation"]]
                        ),
                        "partition": "untouched_development_evaluation",
                        "y_true": evaluation["Class"].to_numpy(dtype=int),
                        "raw_score": direct.raw_scores,
                    }
                ),
            ],
            ignore_index=True,
        )
        score_evidence.to_csv(outputs["development_scores"], index=False)
        calibration_comparison.to_csv(outputs["calibration_comparison"], index=False)
        candidate_metrics.to_csv(outputs["candidate_comparison"], index=False)
        _json_write(evaluation_payload, outputs["evaluation"])
        _json_write(parity_payload, outputs["golden_parity"])
        _json_write(lineage_payload, outputs["lineage"])
        _json_write(selection_payload, outputs["selection"])
        for path in sorted((temporary / "bundle").iterdir()):
            if path.is_file():
                outputs[f"bundle/{path.name}"] = path
        manifest = build_run_manifest(
            run_kind="development_training_and_bundle",
            evaluation_scope="new_authorized_three_way_development",
            repository=PROJECT_ROOT,
            inputs={
                "curated_dataset": curated_path,
                "curation_record": curation_record_path,
            },
            outputs=outputs,
            parameters={
                "bootstrap_resamples": bootstrap_resamples,
                "candidate_order": list(factories),
                "minimum_brier_improvement": minimum_brier_improvement,
                "role_order": list(ROLE_ORDER),
                "simplicity_margin": simplicity_margin,
            },
            seeds={"canonical_random_state": RANDOM_STATE},
            packages=[
                "joblib",
                "numpy",
                "pandas",
                "scikit-learn",
                "scipy",
                "xgboost",
            ],
            data_fingerprint=curated_fingerprint,
        )
        write_run_manifest(manifest, temporary / "run_manifest.json")

    return {
        "bundle_manifest": output_dir / "bundle" / "manifest.json",
        "evaluation": output_dir / "untouched_evaluation.json",
        "golden_parity": output_dir / "golden_parity.json",
        "run_manifest": output_dir / "run_manifest.json",
        "selection": output_dir / "selection.json",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curated-data", required=True, type=Path)
    parser.add_argument("--curation-record", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--simplicity-margin", type=float, default=0.005)
    parser.add_argument("--minimum-brier-improvement", type=float, default=0.0)
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_development_training(
        curated_path=args.curated_data,
        curation_record_path=args.curation_record,
        output_dir=args.output_dir.resolve(),
        simplicity_margin=args.simplicity_margin,
        minimum_brier_improvement=args.minimum_brier_improvement,
        bootstrap_resamples=args.bootstrap_resamples,
    )
    print(json.dumps({key: str(value) for key, value in sorted(outputs.items())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
