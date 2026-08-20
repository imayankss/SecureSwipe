"""One-time guarded migration of decision metadata; historical metrics are unchanged."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_day6_threshold_tuning import build_day6_threshold_tuning_report
from src.artifacts.bundle import sha256_file
from src.evaluation.final_evaluation import write_final_evaluation_report
from src.utils.config import load_project_config

EXPECTED_OLD_HASHES = {
    "reports/final/final_model_evaluation.json": "b8f4da9d2532b56d3410ea4049bc2f12673fc42089cded1247afb9d3a84c5c04",
    "reports/final/final_evaluation_report.md": "129278ed93e9eca883f925b3f0c0c22afbfe4d68d7d030512197a44e376f60e5",
    "reports/threshold_tuning/selected_thresholds.json": "4d11e134811491cb225317f485328b84dad936df1aa877e3aa47bf5382b4345c",
}


def _atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def migrate() -> None:
    for relative, expected in EXPECTED_OLD_HASHES.items():
        path = PROJECT_ROOT / relative
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"Refusing migration because {relative} is not the reviewed source "
                f"(expected {expected}, got {actual})."
            )

    config = load_project_config()
    selected_path = PROJECT_ROOT / config.reports.threshold_dir / "selected_thresholds.json"
    selected = _load_json(selected_path)
    recall = selected["recall_target"]
    recall.update(
        {
            "evaluation_scope": config.evaluation.development_scope,
            "minimum_recall": config.evaluation.recall_target,
            "selection_method": "highest_precision_meeting_recall_target",
        }
    )

    final_path = PROJECT_ROOT / config.reports.historical_json
    final = _load_json(final_path)
    original_metrics = {
        key: value
        for key, value in final.items()
        if key not in {"threshold_source"}
    }
    final["threshold_source"] = (
        f"{recall['evaluation_scope']} — {recall['selection_method']} "
        f"(minimum_recall={recall['minimum_recall']})"
    )
    if any(final[key] != value for key, value in original_metrics.items()):
        raise RuntimeError("Historical metric/content fields changed during metadata migration.")

    old_day6 = (PROJECT_ROOT / "reports/threshold_tuning/day6_threshold_tuning_report.md").read_text(
        encoding="utf-8"
    )
    generated = re.search(r"\*\*Generated:\*\* (.+)", old_day6)
    model = re.search(r"\*\*Model:\*\* (.+)", old_day6)
    comparison = json.loads(
        (PROJECT_ROOT / "reports/model_comparison/validation_model_comparison.json").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(comparison, list) or not comparison or not isinstance(comparison[0], dict):
        raise ValueError("Historical model comparison must be a non-empty JSON array.")
    first_model = comparison[0]
    day6 = build_day6_threshold_tuning_report(
        model_name=model.group(1) if model else "xgboost_baseline",
        validation_rows=int(first_model["validation_rows"]),
        validation_frauds=int(first_model["validation_frauds"]),
        selected_thresholds=selected,
        min_recall=float(recall["minimum_recall"]),
        generated_at=generated.group(1) if generated else "historical timestamp unavailable",
    )

    with tempfile.TemporaryDirectory(prefix="secureswipe-historical-migration-") as directory:
        temporary_report = Path(directory) / "report.md"
        write_final_evaluation_report(final, temporary_report)
        report_content = temporary_report.read_text(encoding="utf-8")

    _atomic_replace(selected_path, json.dumps(selected, indent=2, allow_nan=False) + "\n")
    _atomic_replace(final_path, json.dumps(final, indent=2, allow_nan=False) + "\n")
    _atomic_replace(PROJECT_ROOT / config.reports.historical_report, report_content)
    _atomic_replace(PROJECT_ROOT / "reports/threshold_tuning/day6_threshold_tuning_report.md", day6)

    digest = hashlib.sha256()
    for path in sorted((selected_path, final_path, PROJECT_ROOT / config.reports.historical_report)):
        digest.update(path.read_bytes())
    print(json.dumps({"metadata_migration_sha256": digest.hexdigest(), "metrics_changed": False}))


if __name__ == "__main__":
    migrate()
