"""Tests that current audit status comes from evidence, not filename existence."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import scripts.run_project_audit as audit


def test_zero_byte_inventory_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty.txt"
    empty.touch()
    monkeypatch.setattr(audit, "INVENTORY", {"empty": empty})
    assert audit.inventory_rows() == [audit.AuditRow("MISSING", "empty", str(empty))]


def test_inventory_never_labels_file_presence_as_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    present = tmp_path / "present.txt"
    present.write_text("evidence", encoding="utf-8")
    monkeypatch.setattr(audit, "INVENTORY", {"present": present})
    row = audit.inventory_rows()[0]
    assert row.status == "PRESENT"
    assert row.status != "PASS"


def test_command_gate_status_uses_exit_code(tmp_path: Path) -> None:
    passing = audit.CommandGate("passing", (sys.executable, "-c", "raise SystemExit(0)"), tmp_path)
    failing = audit.CommandGate("failing", (sys.executable, "-c", "raise SystemExit(3)"), tmp_path)
    assert audit.execute_gate(passing).status == "PASS"
    failure = audit.execute_gate(failing)
    assert failure.status == "FAIL"
    assert "exit 3" in failure.evidence


def test_missing_model_is_explicitly_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECURESWIPE_BUNDLE_MANIFEST", raising=False)
    row = audit.verified_model_row()
    assert row.status == "UNAVAILABLE"
    assert "not configured" in row.evidence


def test_audit_without_model_is_incomplete_and_strict_mode_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("present", encoding="utf-8")
    monkeypatch.setattr(audit, "INVENTORY", {"artifact": artifact})
    monkeypatch.setattr(
        audit,
        "verified_model_row",
        lambda: audit.AuditRow("UNAVAILABLE", "model", "absent"),
    )
    result = audit.run_project_audit(
        checklist_path=tmp_path / "checklist.md",
        project_report_path=tmp_path / "report.md",
        execute_commands=False,
        require_model=True,
    )
    assert result["overall_status"] == "INCOMPLETE"
    assert result["ok"] is False
    checklist = (tmp_path / "checklist.md").read_text(encoding="utf-8")
    assert "UNAVAILABLE" in checklist
    assert "File presence" not in checklist


def test_check_mode_detects_stale_output_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("present", encoding="utf-8")
    checklist = tmp_path / "checklist.md"
    report = tmp_path / "report.md"
    checklist.write_text("stale", encoding="utf-8")
    report.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(audit, "INVENTORY", {"artifact": artifact})
    monkeypatch.setattr(
        audit,
        "verified_model_row",
        lambda: audit.AuditRow("UNAVAILABLE", "model", "absent"),
    )
    before = checklist.read_bytes()
    with pytest.raises(RuntimeError, match="stale"):
        audit.run_project_audit(
            checklist_path=checklist,
            project_report_path=report,
            execute_commands=False,
            require_model=False,
            check=True,
        )
    assert checklist.read_bytes() == before
