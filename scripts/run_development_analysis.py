"""Verify one training run and add frozen post-training cost diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.artifacts.bundle import load_model_bundle, sha256_file  # noqa: E402
from src.data.curation import load_curated_dataset, row_content_fingerprints  # noqa: E402
from src.evaluation.calibration import evaluate_calibration  # noqa: E402
from src.evaluation.cost_analysis import CostScenario, analyze_cost_scenarios  # noqa: E402
from src.evaluation.threshold_tuning import build_threshold_metrics_table  # noqa: E402
from src.inference.batch_scoring import score_bundle_frame  # noqa: E402
from src.utils.evidence_directory import (  # noqa: E402
    atomic_evidence_directory,
    require_absent_evidence_target,
)
from src.utils.run_manifest import build_run_manifest, write_run_manifest  # noqa: E402

REQUIRED_SCORE_COLUMNS = ["row_fingerprint", "partition", "y_true", "raw_score"]
ALLOWED_PARTITIONS = {
    "calibration_fit",
    "operating_point_selection",
    "forward_development_backtest",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _native_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _native_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native_json(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _json_write(payload: Any, path: Path) -> Path:
    path.write_text(
        json.dumps(_native_json(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_development_scores(path: str | Path) -> pd.DataFrame:
    """Load explicit development partitions and reject malformed score evidence."""
    frame = pd.read_csv(path)
    if list(frame.columns) != REQUIRED_SCORE_COLUMNS:
        raise ValueError(f"Score CSV columns must be exactly {REQUIRED_SCORE_COLUMNS}.")
    fingerprints = frame["row_fingerprint"].astype(str)
    if (
        frame.empty
        or frame["row_fingerprint"].isna().any()
        or fingerprints.duplicated().any()
        or not fingerprints.map(lambda value: bool(_SHA256.fullmatch(value))).all()
    ):
        raise ValueError(
            "Score CSV must have non-empty, globally unique SHA-256 row_fingerprint values."
        )
    if set(frame["partition"]) != ALLOWED_PARTITIONS:
        raise ValueError(
            "Score CSV must contain exactly calibration_fit, operating_point_selection, "
            "and forward_development_backtest; historical/test partitions are prohibited."
        )
    labels = frame["y_true"].to_numpy()
    scores = frame["raw_score"].to_numpy(dtype=float)
    if not np.isfinite(scores).all() or np.logical_or(scores < 0.0, scores > 1.0).any():
        raise ValueError("raw_score must be finite and in [0, 1].")
    if not set(np.unique(labels)).issubset({0, 1}):
        raise ValueError("y_true must contain only 0 and 1.")
    for partition, group in frame.groupby("partition", sort=True):
        if set(group["y_true"]) != {0, 1}:
            raise ValueError(f"Partition {partition} must contain both classes.")
    return frame


def load_cost_scenarios(path: str | Path) -> list[CostScenario]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("scenarios"), list):
        raise ValueError("Cost configuration must contain a scenarios list.")
    allowed = {
        "name",
        "false_positive_cost",
        "false_negative_cost",
        "review_cost",
        "fraud_recovery_rate",
    }
    scenarios: list[CostScenario] = []
    for item in payload["scenarios"]:
        if not isinstance(item, dict) or set(item) != allowed:
            raise ValueError(f"Every cost scenario must contain exactly {sorted(allowed)}.")
        scenario = CostScenario(**item)
        scenario.validate()
        scenarios.append(scenario)
    if not scenarios or len({item.name for item in scenarios}) != len(scenarios):
        raise ValueError("Cost scenarios must be non-empty and uniquely named.")
    return scenarios


def _verify_file_record(records: dict[str, Any], logical_name: str, path: Path) -> None:
    resolved = path.resolve(strict=True)
    entry = records.get(logical_name)
    if (
        not isinstance(entry, dict)
        or entry.get("filename") != resolved.name
        or entry.get("size_bytes") != resolved.stat().st_size
        or entry.get("sha256") != sha256_file(resolved)
    ):
        raise ValueError(f"Training run manifest mismatch for {logical_name}.")


def run_development_analysis(
    *,
    scores_path: Path,
    curated_path: Path,
    curation_record_path: Path,
    training_run_manifest_path: Path,
    scenarios_path: Path,
    output_dir: Path,
    minimum_brier_improvement: float | None = None,
) -> dict[str, Path]:
    """Recompute every score from a verified bundle before publishing diagnostics."""
    output_dir = require_absent_evidence_target(output_dir)
    scores = load_development_scores(scores_path)
    curated, curation = load_curated_dataset(
        curated_path, curation_record_path, require_decision_eligible=True
    )
    training_manifest_path = training_run_manifest_path.resolve(strict=True)
    if training_manifest_path.is_symlink():
        raise ValueError("Training run manifest must not be a symbolic link.")
    manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("run_kind") != "development_training_and_bundle"
        or manifest.get("data_fingerprint") != curation["curated_fingerprint"]
    ):
        raise ValueError("Scores require a matching verified development-training run.")
    inputs = manifest.get("inputs")
    outputs = manifest.get("outputs")
    parameters = manifest.get("parameters")
    if not all(isinstance(value, dict) for value in (inputs, outputs, parameters)):
        raise ValueError("Training run manifest input/output/parameter records are missing.")
    assert isinstance(inputs, dict) and isinstance(outputs, dict) and isinstance(parameters, dict)
    trained_margin = parameters.get("minimum_brier_improvement")
    if minimum_brier_improvement is not None and minimum_brier_improvement != trained_margin:
        raise ValueError(
            "Post-training analysis cannot change the frozen calibration-selection policy."
        )
    _verify_file_record(inputs, "curated_dataset", curated_path)
    _verify_file_record(inputs, "curation_record", curation_record_path)
    _verify_file_record(outputs, "development_scores", scores_path)
    training_root = training_manifest_path.parent
    bundle_manifest_path = training_root / "bundle" / "manifest.json"
    lineage_path = training_root / "lineage.json"
    source_backtest_path = training_root / "forward_backtest.json"
    _verify_file_record(outputs, "bundle/manifest.json", bundle_manifest_path)
    _verify_file_record(outputs, "lineage", lineage_path)
    _verify_file_record(outputs, "backtest", source_backtest_path)
    bundle = load_model_bundle(bundle_manifest_path, trusted_root=training_root)

    curated_fingerprints = row_content_fingerprints(curated)
    source_fingerprints = set(curated_fingerprints)
    score_fingerprints = set(scores["row_fingerprint"].astype(str))
    if not score_fingerprints <= source_fingerprints:
        raise ValueError("Development scores contain row fingerprints outside verified data.")
    source_metadata = {
        fingerprint: (index, float(curated.iloc[index]["Time"]), int(curated.iloc[index]["Class"]))
        for index, fingerprint in enumerate(curated_fingerprints)
    }
    for row in scores.itertuples(index=False):
        _index, _time, source_label = source_metadata[str(row.row_fingerprint)]
        if int(row.y_true) != source_label:
            raise ValueError("Development score labels do not match curated source lineage.")
    role_bounds: dict[str, tuple[float, float]] = {}
    for role in ALLOWED_PARTITIONS:
        role_times = [
            source_metadata[fingerprint][1]
            for fingerprint in scores.loc[
                scores["partition"] == role, "row_fingerprint"
            ].astype(str)
        ]
        role_bounds[role] = (min(role_times), max(role_times))
    if not (
        role_bounds["calibration_fit"][1]
        < role_bounds["operating_point_selection"][0]
        <= role_bounds["operating_point_selection"][1]
        < role_bounds["forward_development_backtest"][0]
    ):
        raise ValueError("Development score roles must be strictly chronological.")
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    for role in ALLOWED_PARTITIONS:
        digest = hashlib.sha256(
            "".join(
                sorted(
                    scores.loc[scores["partition"] == role, "row_fingerprint"].astype(str)
                )
            ).encode("ascii")
        ).hexdigest()
        if (
            not isinstance(lineage, dict)
            or not isinstance(lineage.get(role), dict)
            or lineage[role].get("content_fingerprint") != digest
        ):
            raise ValueError(f"Training lineage mismatch for {role}.")

    row_indices = [source_metadata[value][0] for value in scores["row_fingerprint"].astype(str)]
    recomputed = score_bundle_frame(
        bundle, curated.iloc[row_indices][list(bundle.feature_schema)]
    )
    if not np.allclose(
        scores["raw_score"].to_numpy(dtype=float),
        recomputed.raw_scores,
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError(
            "Development scores do not match scores recomputed from the verified bundle."
        )

    selection_mask = scores["partition"].to_numpy() == "operating_point_selection"
    selection = scores.loc[selection_mask]
    selection_labels = selection["y_true"].to_numpy(dtype=int)
    selection_scores = recomputed.decision_scores[selection_mask]
    calibration_metrics = evaluate_calibration(selection_labels, selection_scores)
    threshold_table = build_threshold_metrics_table(selection_labels, selection_scores)
    cost_table, cost_selections = analyze_cost_scenarios(
        selection_labels, selection_scores, load_cost_scenarios(scenarios_path)
    )
    comparison = pd.DataFrame(
        [
            {
                "brier_score": calibration_metrics["brier_score"],
                "expected_calibration_error": calibration_metrics[
                    "expected_calibration_error"
                ],
                "maximum_calibration_error": calibration_metrics[
                    "maximum_calibration_error"
                ],
                "method": bundle.score_type,
                "selected": True,
            }
        ]
    )

    filenames = {
        "calibration_comparison": "calibration_comparison.csv",
        "calibration_metrics": "calibration_metrics.json",
        "cost_sensitivity": "cost_sensitivity.csv",
        "selected_operating_points": "selected_operating_points.json",
        "threshold_metrics": "threshold_metrics.csv",
    }
    with atomic_evidence_directory(output_dir) as temporary:
        generated = {name: temporary / filename for name, filename in filenames.items()}
        comparison.to_csv(generated["calibration_comparison"], index=False)
        threshold_table.to_csv(generated["threshold_metrics"], index=False)
        cost_table.to_csv(generated["cost_sensitivity"], index=False)
        _json_write(calibration_metrics, generated["calibration_metrics"])
        _json_write(
            {
                "calibration_method": bundle.score_type,
                "cost_scenarios": cost_selections,
                "evaluation_scope": "verified_post_training_selection_diagnostics",
                "frozen_operating_threshold": bundle.operating_threshold,
                "model_version": bundle.model_version,
                "score_type": bundle.score_type,
                "source_backtest_artifact_sha256": sha256_file(source_backtest_path),
            },
            generated["selected_operating_points"],
        )
        run_manifest = build_run_manifest(
            run_kind="verified_post_training_analysis",
            evaluation_scope="verified_post_training_selection_diagnostics",
            repository=PROJECT_ROOT,
            inputs={
                "cost_scenarios": scenarios_path,
                "curated_dataset": curated_path,
                "curation_record": curation_record_path,
                "development_scores": scores_path,
                "training_run_manifest": training_manifest_path,
            },
            outputs=generated,
            parameters={
                "minimum_brier_improvement": trained_margin,
                "partition_roles": sorted(ALLOWED_PARTITIONS),
                "post_training_only": True,
                "threshold_grid": {"minimum": 0.01, "maximum": 0.99, "step": 0.01},
            },
            seeds={},
            packages=["numpy", "pandas", "pyyaml", "scikit-learn"],
            data_fingerprint=str(curation["curated_fingerprint"]),
        )
        write_run_manifest(run_manifest, temporary / "run_manifest.json")
    return {
        **{name: output_dir / filename for name, filename in filenames.items()},
        "run_manifest": output_dir / "run_manifest.json",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--curated-data", required=True, type=Path)
    parser.add_argument("--curation-record", required=True, type=Path)
    parser.add_argument("--training-run-manifest", required=True, type=Path)
    parser.add_argument("--cost-scenarios", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--minimum-brier-improvement", type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_development_analysis(
        scores_path=args.scores.resolve(strict=True),
        curated_path=args.curated_data.resolve(strict=True),
        curation_record_path=args.curation_record.resolve(strict=True),
        training_run_manifest_path=args.training_run_manifest.resolve(strict=True),
        scenarios_path=args.cost_scenarios.resolve(strict=True),
        output_dir=args.output_dir.resolve(),
        minimum_brier_improvement=args.minimum_brier_improvement,
    )
    print(json.dumps({name: str(path) for name, path in sorted(outputs.items())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
