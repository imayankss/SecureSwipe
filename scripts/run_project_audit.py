"""Execute current quality gates and render a deterministic, non-misleading audit."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_web_data import build_web_payload
from src.artifacts.bundle import ArtifactVerificationError, load_model_bundle

DEFAULT_FINAL_DIR = PROJECT_ROOT / "reports/final"
DEFAULT_CHECKLIST_PATH = DEFAULT_FINAL_DIR / "project_audit_checklist.md"
DEFAULT_PROJECT_REPORT_PATH = DEFAULT_FINAL_DIR / "final_project_report.md"

INVENTORY = {
    "README": PROJECT_ROOT / "README.md",
    "Day 2 EDA report": PROJECT_ROOT / "reports/day2_eda_summary.md",
    "Day 3 preprocessing report": PROJECT_ROOT / "reports/day3_preprocessing_summary.md",
    "Day 4 baseline report": PROJECT_ROOT / "reports/day4_baseline_model_summary.md",
    "Day 5 model comparison report": (
        PROJECT_ROOT / "reports/model_comparison/day5_model_comparison.md"
    ),
    "Day 6 threshold report": (
        PROJECT_ROOT / "reports/threshold_tuning/day6_threshold_tuning_report.md"
    ),
    "Day 7 SHAP report": PROJECT_ROOT / "reports/explainability/shap_summary_report.md",
    "Final evaluation JSON": PROJECT_ROOT / "reports/final/final_model_evaluation.json",
    "Final evaluation report": PROJECT_ROOT / "reports/final/final_evaluation_report.md",
    "Historical observation lock": (
        PROJECT_ROOT / "reports/final/historical_observation.lock.json"
    ),
    "SHAP top features": PROJECT_ROOT / "reports/explainability/shap_top_features.json",
    "API application": PROJECT_ROOT / "api/main.py",
    "Container definition": PROJECT_ROOT / "Dockerfile",
    "Monitoring guide": PROJECT_ROOT / "docs/MONITORING.md",
    "Operations runbook": PROJECT_ROOT / "docs/OPERATIONS.md",
    "Architecture guide": PROJECT_ROOT / "docs/ARCHITECTURE.md",
    "Limitations and non-goals": PROJECT_ROOT / "docs/LIMITATIONS.md",
    "Deployment runbook": PROJECT_ROOT / "docs/DEPLOYMENT.md",
    "Interview defense": PROJECT_ROOT / "docs/INTERVIEW_DEFENSE.md",
    "Demonstration script": PROJECT_ROOT / "docs/DEMO.md",
    "Synthetic monitoring evidence": (
        PROJECT_ROOT / "reports/monitoring/synthetic_shift_report.json"
    ),
}


@dataclass(frozen=True)
class AuditRow:
    status: str
    item: str
    evidence: str


@dataclass(frozen=True)
class CommandGate:
    name: str
    command: tuple[str, ...]
    working_directory: Path = PROJECT_ROOT


def command_gates() -> list[CommandGate]:
    python = sys.executable
    return [
        CommandGate(
            "Python compile", (python, "-m", "compileall", "-q", "api", "src", "scripts", "tests")
        ),
        CommandGate(
            "Python lint", (python, "-m", "ruff", "check", "api", "src", "scripts", "tests")
        ),
        CommandGate(
            "Critical Python types",
            (
                python,
                "-m",
                "mypy",
                "--ignore-missing-imports",
                "api",
                "src/artifacts",
                "src/inference",
                "src/monitoring",
                "src/evaluation/statistical_metrics.py",
                "src/evaluation/calibration.py",
                "src/evaluation/cost_analysis.py",
                "src/evaluation/temporal_validation.py",
                "src/evaluation/historical_lock.py",
                "src/utils/config.py",
                "src/utils/run_manifest.py",
                "scripts/run_development_analysis.py",
                "scripts/run_offline_monitoring.py",
                "scripts/create_synthetic_monitoring_demo.py",
                "scripts/run_local_load_test.py",
                "scripts/verify_historical_observation.py",
            ),
        ),
        CommandGate(
            "Reference-stage wrapper types",
            (
                python,
                "-m",
                "mypy",
                "--no-incremental",
                "--ignore-missing-imports",
                "--follow-imports=skip",
                "scripts/run_reference_stage.py",
            ),
        ),
        CommandGate("Python tests", (python, "-m", "pytest")),
        CommandGate("Web artifact determinism", (python, "scripts/export_web_data.py", "--check")),
        CommandGate(
            "Historical observation integrity",
            (python, "scripts/verify_historical_observation.py"),
        ),
        CommandGate(
            "Synthetic monitoring determinism",
            (
                python,
                "scripts/create_synthetic_monitoring_demo.py",
                "--output",
                "reports/monitoring/synthetic_shift_report.json",
                "--check",
            ),
        ),
        CommandGate(
            "API dependency vulnerabilities",
            (
                python,
                "-m",
                "pip_audit",
                "-r",
                "requirements/api.lock",
                "--disable-pip",
                "--progress-spinner",
                "off",
            ),
        ),
        CommandGate(
            "Quality dependency vulnerabilities",
            (
                python,
                "-m",
                "pip_audit",
                "-r",
                "requirements/quality.lock",
                "--disable-pip",
                "--progress-spinner",
                "off",
            ),
        ),
        CommandGate("Frontend test gate", ("npm", "test"), PROJECT_ROOT / "web"),
        CommandGate("Frontend production build", ("npm", "run", "build"), PROJECT_ROOT / "web"),
        CommandGate(
            "Frontend production browser gate",
            ("npm", "run", "test:e2e"),
            PROJECT_ROOT / "web",
        ),
        CommandGate(
            "Frontend dependency vulnerabilities",
            ("npm", "audit", "--audit-level=high"),
            PROJECT_ROOT / "web",
        ),
    ]


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def inventory_rows() -> list[AuditRow]:
    """Classify files as PRESENT, never PASS; zero-byte files are missing."""
    rows: list[AuditRow] = []
    for label, path in INVENTORY.items():
        present = path.is_file() and path.stat().st_size > 0
        rows.append(
            AuditRow(
                status="PRESENT" if present else "MISSING",
                item=label,
                evidence=_display_path(path),
            )
        )
    return rows


def verified_model_row() -> AuditRow:
    """Verify a configured local bundle or report it unavailable without fallback."""
    artifact_root = Path(os.getenv("SECURESWIPE_ARTIFACT_ROOT", "artifacts")).expanduser()
    manifest_value = os.getenv("SECURESWIPE_BUNDLE_MANIFEST", "").strip()
    if not manifest_value:
        return AuditRow(
            "UNAVAILABLE",
            "Verified serving model bundle",
            "SECURESWIPE_BUNDLE_MANIFEST is not configured",
        )
    manifest = Path(manifest_value).expanduser()
    if not artifact_root.exists() or not manifest.exists():
        return AuditRow(
            "UNAVAILABLE",
            "Verified serving model bundle",
            f"manifest not found: {_display_path(manifest)}",
        )
    try:
        bundle = load_model_bundle(manifest, trusted_root=artifact_root)
    except (ArtifactVerificationError, FileNotFoundError, ValueError) as exc:
        return AuditRow("FAIL", "Verified serving model bundle", str(exc))
    return AuditRow(
        "PASS",
        "Verified serving model bundle",
        f"model_version={bundle.model_version}; manifest={_display_path(manifest)}",
    )


def execute_gate(gate: CommandGate) -> AuditRow:
    """Run one gate and retain bounded diagnostic evidence without shell execution."""
    display_command = (
        ("python", *gate.command[1:]) if gate.command[0] == sys.executable else gate.command
    )
    command_text = shlex.join(display_command)
    try:
        result = subprocess.run(
            gate.command,
            cwd=gate.working_directory,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return AuditRow("FAIL", gate.name, f"{command_text}: {type(exc).__name__}")
    if result.returncode == 0:
        return AuditRow("PASS", gate.name, command_text)
    combined = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    diagnostic = combined.splitlines()[-1] if combined else "no diagnostic output"
    return AuditRow(
        "FAIL",
        gate.name,
        f"{command_text} (exit {result.returncode}: {diagnostic[:240]})",
    )


def render_checklist(rows: Sequence[AuditRow], overall_status: str) -> str:
    lines = [
        "# Current Project Audit Checklist",
        "",
        f"Overall status: **{overall_status}**",
        "",
        "`PASS` is reserved for an executed verification. `PRESENT` means only a",
        "non-empty file inventory check. `UNAVAILABLE` is an explicit external/local",
        "artifact blocker and must not be interpreted as passing.",
        "",
        "| Status | Item | Evidence |",
        "|---|---|---|",
    ]
    for row in rows:
        safe_evidence = row.evidence.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row.status} | {row.item} | `{safe_evidence}` |")
    return "\n".join(lines) + "\n"


def render_project_report(overall_status: str) -> str:
    payload = build_web_payload()
    final = payload["finalEvaluation"]
    selected = next(
        point
        for point in payload["thresholdAnalysis"]["selected"]
        if point["key"] == "recall_target"
    )
    return "\n".join(
        [
            "# Current Project Report: SecureSwipe",
            "",
            f"Audit status: **{overall_status}**",
            "",
            "SecureSwipe is a portfolio reference for offline fraud-risk modelling and",
            "a bundle-gated inference API. It is not a bank authorization or compliance",
            "system and no verified trained fraud model is present in this checkout.",
            "",
            "## Historical reported test observation",
            "",
            f"- Model: `{final['model_name']}`",
            f"- Recorded validation-selected threshold: `{selected['threshold']}`",
            f"- Average precision (historical key `pr_auc`): `{final['pr_auc']}`",
            f"- Precision / recall / F1: `{final['precision']}` / `{final['recall']}` / `{final['f1_score']}`",
            f"- Confusion counts TP/FP/FN/TN: `{final['true_positives']}` / `{final['false_positives']}` / `{final['false_negatives']}` / `{final['true_negatives']}`",
            "",
            "The random test result has already been observed, has possible duplicate",
            "contamination, lacks original artifact/runtime provenance, and is excluded",
            "from all new decisions. It is not out-of-time or deployment evidence.",
            "",
            "## Current evidence",
            "",
            "See `docs/industrialization/STATE.md` and `QUALITY_SCORECARD.md` for",
            "executed commands, external blockers, and the next action. File presence",
            "alone is never reported as a passing quality gate.",
            "",
        ]
    )


def _write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Audit output is stale: {_display_path(path)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_project_audit(
    *,
    checklist_path: Path = DEFAULT_CHECKLIST_PATH,
    project_report_path: Path = DEFAULT_PROJECT_REPORT_PATH,
    execute_commands: bool = True,
    require_model: bool = True,
    check: bool = False,
) -> dict[str, object]:
    rows = inventory_rows()
    if execute_commands:
        rows.extend(execute_gate(gate) for gate in command_gates())
    else:
        rows.append(AuditRow("NOT_RUN", "Executable quality gates", "--skip-gates"))
    model_row = verified_model_row()
    rows.append(model_row)

    hard_fail = any(row.status in {"FAIL", "MISSING"} for row in rows)
    model_block = model_row.status != "PASS"
    overall_status = "PASS" if not hard_fail and not model_block else "INCOMPLETE"
    checklist = render_checklist(rows, overall_status)
    project_report = render_project_report(overall_status)
    _write_or_check(checklist_path, checklist, check)
    _write_or_check(project_report_path, project_report, check)
    return {
        "checklist_path": checklist_path,
        "project_report_path": project_report_path,
        "rows": rows,
        "ok": not hard_fail and (not require_model or not model_block),
        "overall_status": overall_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist-path", type=Path, default=DEFAULT_CHECKLIST_PATH)
    parser.add_argument("--project-report-path", type=Path, default=DEFAULT_PROJECT_REPORT_PATH)
    parser.add_argument("--check", action="store_true", help="Verify outputs without writing.")
    parser.add_argument("--skip-gates", action="store_true", help="Inventory only; never PASS.")
    parser.add_argument(
        "--allow-missing-model",
        action="store_true",
        help="Return success for the static checkout while still reporting INCOMPLETE.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_project_audit(
        checklist_path=args.checklist_path.resolve(),
        project_report_path=args.project_report_path.resolve(),
        execute_commands=not args.skip_gates,
        require_model=not args.allow_missing_model,
        check=args.check,
    )
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
