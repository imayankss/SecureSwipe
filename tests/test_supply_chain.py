"""Static policy tests for CI permissions, action pinning, and project governance."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_workflows_are_valid_yaml_and_default_to_read_only() -> None:
    assert {path.name for path in WORKFLOWS} == {"container.yml", "quality.yml", "security.yml"}
    for path in WORKFLOWS:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert payload["permissions"] == {"contents": "read"}


def test_every_third_party_action_is_pinned_to_full_commit() -> None:
    action_pattern = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
    pinned_pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")
    found: list[str] = []
    for path in WORKFLOWS:
        found.extend(action_pattern.findall(path.read_text(encoding="utf-8")))
    assert found
    assert all(pinned_pattern.fullmatch(action) for action in found), found


def test_pull_requests_cannot_deploy_or_gain_broad_write_permissions() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in WORKFLOWS)
    assert "pull_request_target" not in combined
    assert "contents: write" not in combined
    assert "id-token: write" not in combined
    assert "push: true" not in combined
    assert "npm publish" not in combined
    assert "docker push" not in combined
    assert "gh release" not in combined


def test_security_write_permission_is_isolated_to_codeql_job() -> None:
    security = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8"))
    assert security["jobs"]["secrets"].get("permissions") is None
    assert security["jobs"]["codeql"]["permissions"] == {
        "actions": "read",
        "contents": "read",
        "packages": "read",
        "security-events": "write",
    }


def test_history_secret_scan_does_not_suppress_unverified_candidates() -> None:
    text = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in text
    assert "--only-verified" not in text


def test_container_workflow_builds_without_push_and_scans_each_architecture() -> None:
    text = (ROOT / ".github/workflows/container.yml").read_text(encoding="utf-8")
    assert "linux/amd64" in text
    assert "linux/arm64" in text
    assert "push: false" in text
    assert "build-args: VCS_REF=${{ github.sha }}" in text
    assert "severity: HIGH,CRITICAL" in text
    assert "exit-code: \"1\"" in text
    assert "trivyignores: .trivyignore.yaml" in text
    assert "ignore-unfixed" not in text
    assert "format: spdx-json" in text
    assert "smoke_expected.json" in text
    assert "os.getuid() == 10001" in text
    assert "find_spec('pip') is None" in text


def test_container_image_declares_source_revision_binding() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG VCS_REF=unknown" in dockerfile
    assert 'org.opencontainers.image.source="https://github.com/imayankss/SecureSwipe"' in dockerfile
    assert 'org.opencontainers.image.revision="${VCS_REF}"' in dockerfile


def test_container_scan_exceptions_are_narrow_documented_and_expiring() -> None:
    payload = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    exceptions = payload["vulnerabilities"]
    assert len(exceptions) == 12
    assert len({item["id"] for item in exceptions}) == len(exceptions)
    assert all(set(item) == {"id", "expired_at", "statement"} for item in exceptions)
    assert all(str(item["expired_at"]) == "2026-09-20" for item in exceptions)
    assert all(len(item["statement"]) >= 50 for item in exceptions)


def test_dependabot_covers_python_npm_and_actions() -> None:
    payload = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    assert {item["package-ecosystem"] for item in payload["updates"]} == {
        "pip",
        "npm",
        "github-actions",
    }


def test_license_and_security_governance_files_are_present() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License")
    assert "Mayank Suryavanshi" in license_text
    assert (ROOT / "CONTRIBUTING.md").stat().st_size > 0
    assert (ROOT / "SECURITY.md").stat().st_size > 0
    assert (ROOT / ".github/pull_request_template.md").stat().st_size > 0
    required_docs = {
        "API.md",
        "ARCHITECTURE.md",
        "CONTAINER.md",
        "DATA_CARD.md",
        "DEMO.md",
        "DEPLOYMENT.md",
        "FRONTEND_PERFORMANCE.md",
        "INTERVIEW_DEFENSE.md",
        "LIMITATIONS.md",
        "MODEL_CARD.md",
        "MONITORING.md",
        "OPERATIONS.md",
        "REPRODUCIBILITY.md",
        "SCIENTIFIC_VALIDITY.md",
        "THREAT_MODEL.md",
    }
    assert all((ROOT / "docs" / name).stat().st_size > 0 for name in required_docs)


def test_lock_generator_is_isolated_and_fixed_versions_are_pinned() -> None:
    lock_tools_input = (ROOT / "requirements/lock-tools.in").read_text(encoding="utf-8")
    lock_tools = (ROOT / "requirements/lock-tools.lock").read_text(encoding="utf-8")
    quality_input = (ROOT / "requirements/quality.in").read_text(encoding="utf-8")
    quality_lock = (ROOT / "requirements/quality.lock").read_text(encoding="utf-8")
    api_linux_lock = (ROOT / "requirements/api-linux.lock").read_text(encoding="utf-8")
    quality_linux_lock = (ROOT / "requirements/quality-linux.lock").read_text(
        encoding="utf-8"
    )

    assert "pip==26.2.1" in lock_tools_input
    assert "pip-tools==7.6.1" in lock_tools_input
    assert "pip==26.2.1" in lock_tools
    assert "pip-tools==7.6.1" in lock_tools
    assert "pip-tools" not in quality_input
    assert "pip-tools" not in quality_lock
    assert "streamlit" not in quality_input.lower()
    assert "streamlit" not in quality_lock.lower()
    assert "xgboost-cpu==3.3.0" in api_linux_lock
    assert "xgboost-cpu==3.3.0" in quality_linux_lock
    assert "\nxgboost==" not in api_linux_lock
    assert "\nxgboost==" not in quality_linux_lock
    assert "nvidia-" not in api_linux_lock
    assert "nvidia-" not in quality_linux_lock
