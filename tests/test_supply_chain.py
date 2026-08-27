"""Static policy tests for CI permissions, action pinning, and project governance."""

from __future__ import annotations

import hashlib
import json
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
    assert "--exclude-detectors=Lob" in text
    assert "--exclude-paths" not in text


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
    assert 'PLATFORM: ${{ matrix.platform }}' in text
    assert 'docker run --rm --platform "$PLATFORM"' in text
    assert 'docker run --detach --platform "$PLATFORM"' in text
    assert '--volume "$PWD:/workspace:ro"' in text
    assert 'python scripts/create_synthetic_bundle.py --output artifacts/synthetic-ci' in text
    assert "actions/setup-python" not in text
    assert text.index("- name: Build local image") < text.index(
        "- name: Generate synthetic-only smoke bundle with candidate runtime"
    )
    assert "for attempt in {1..90}" in text


def test_container_smoke_bundle_is_read_only_to_the_runtime_user() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/container.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["build-smoke-scan"]["steps"]
    generation = next(
        step
        for step in steps
        if step.get("name") == "Generate synthetic-only smoke bundle with candidate runtime"
    )["run"]
    smoke = next(
        step for step in steps if step.get("name") == "Smoke liveness, readiness, and inference"
    )["run"]

    assert '--user "$(id -u):$(id -g)"' in generation
    assert '"$IMAGE_NAME"' in generation
    assert "python scripts/create_synthetic_bundle.py --output artifacts/synthetic-ci" in generation
    assert "find artifacts/synthetic-ci -type d -exec chmod 0755 {} +" in generation
    assert "find artifacts/synthetic-ci -type f -exec chmod 0644 {} +" in generation
    assert generation.index("create_synthetic_bundle.py") < generation.index("chmod 0755")
    assert generation.index("chmod 0755") < generation.index("chmod 0644")
    assert "chmod 777" not in generation
    assert "chmod -R" not in generation
    assert "--privileged" not in generation
    assert '--volume "$PWD/artifacts/synthetic-ci:/artifacts/synthetic-ci:ro"' in smoke
    assert "--user 0" not in smoke
    assert "--privileged" not in smoke
    assert "os.getuid() == 10001" in smoke


def test_container_image_declares_source_revision_binding() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG VCS_REF=unknown" in dockerfile
    assert 'org.opencontainers.image.source="https://github.com/imayankss/SecureSwipe"' in dockerfile
    assert 'org.opencontainers.image.revision="${VCS_REF}"' in dockerfile


def test_container_scan_exceptions_are_narrow_documented_and_expiring() -> None:
    payload = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    exceptions = payload["vulnerabilities"]
    assert len(exceptions) == 14
    assert len({item["id"] for item in exceptions}) == len(exceptions)
    assert all(set(item) == {"id", "expired_at", "statement"} for item in exceptions)
    assert all(str(item["expired_at"]) == "2026-09-20" for item in exceptions)
    assert all(len(item["statement"]) >= 50 for item in exceptions)


def test_durable_container_scan_and_sbom_evidence_is_self_consistent() -> None:
    evidence = ROOT / "docs/industrialization/evidence/container"
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    scan_path = evidence / manifest["scan"]["evidence_file"]["filename"]
    sbom_path = evidence / manifest["sbom"]["evidence_file"]["filename"]
    for path, record in (
        (scan_path, manifest["scan"]["evidence_file"]),
        (sbom_path, manifest["sbom"]["evidence_file"]),
    ):
        assert path.stat().st_size == record["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]

    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    image = manifest["image"]
    assert scan["ArtifactID"] == manifest["scan"]["artifact_id"]
    assert scan["Metadata"]["ImageID"] == image["image_id"]
    assert scan["Metadata"]["ImageConfig"]["architecture"] == image["architecture"]
    labels = scan["Metadata"]["ImageConfig"]["config"]["Labels"]
    assert labels["org.opencontainers.image.revision"] == manifest["source"]["git_revision"]
    assert labels["org.opencontainers.image.source"] == image["oci_labels"][
        "org.opencontainers.image.source"
    ]
    assert scan["Trivy"]["Version"] == manifest["scan"]["scanner"]["version"]

    findings = [
        finding
        for result in scan["Results"]
        for finding in result.get("Vulnerabilities") or []
    ]
    dispositions = {item["finding_id"]: item for item in manifest["scan"]["dispositions"]}
    exceptions = {
        item["id"]: item
        for item in yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))[
            "vulnerabilities"
        ]
    }
    unfixed = json.loads(
        (evidence / "unfixed-cve-dispositions.json").read_text(encoding="utf-8")
    )
    current = {item["finding_id"] for item in unfixed["dispositions"]}

    assert len(findings) == manifest["scan"]["raw_finding_records"]
    # The frozen scan record stays internally exact: its findings are precisely
    # its dispositions. It cannot contain CVEs published after it was taken.
    assert {item["VulnerabilityID"] for item in findings} == set(dispositions)
    # Every scanner exception must still be backed by exactly one disposition,
    # in the frozen record or in the current unfixed record, and never both.
    assert set(dispositions).isdisjoint(current)
    assert set(exceptions) == set(dispositions) | current
    assert manifest["scan"]["policy_active_findings"] == 0
    for finding_id, disposition in dispositions.items():
        matching = [item for item in findings if item["VulnerabilityID"] == finding_id]
        assert disposition["occurrence_count"] == len(matching)
        assert disposition["packages"] == sorted(item["PkgName"] for item in matching)
        assert {item["Severity"] for item in matching} == {disposition["severity"]}
        assert all(not item.get("FixedVersion") for item in matching)
        assert disposition["expires"] == str(exceptions[finding_id]["expired_at"])
        assert disposition["statement"] == exceptions[finding_id]["statement"]

    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == manifest["sbom"]["format"]
    assert sbom["documentNamespace"] == manifest["sbom"]["document_namespace"]
    assert len(sbom["packages"]) == manifest["sbom"]["package_count"]


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


def test_unfixed_cve_dispositions_are_bounded_documented_and_reviewable() -> None:
    """A scanner exception may only exist with a full, expiring justification.

    This guards the narrow-exception contract: exactly the CVEs that have no
    published fix, each carrying package/version, no-fix status, reachability
    analysis, compensating controls, attempted remediations, an owner-review
    requirement, and a short expiry that matches repository convention.
    """
    evidence = ROOT / "docs/industrialization/evidence/container"
    record = json.loads(
        (evidence / "unfixed-cve-dispositions.json").read_text(encoding="utf-8")
    )
    exceptions = {
        item["id"]: item
        for item in yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))[
            "vulnerabilities"
        ]
    }

    assert record["owner_review_required"] is True
    assert record["owner_review_status"] == "pending"
    assert record["scanner"]["version"] == "0.70.0"

    dispositions = record["dispositions"]
    assert dispositions, "an empty record must not be used to justify exceptions"
    assert len({item["finding_id"] for item in dispositions}) == len(dispositions)

    for item in dispositions:
        # Narrowly scoped: no blanket ignore-unfixed policy.
        assert item["status"] == "temporary_no_fix_exception"
        assert item["severity"] in {"HIGH", "CRITICAL"}
        assert item["package"] and item["installed_version"]
        # Only genuinely unfixable findings qualify.
        assert item["fixed_version"] is None
        assert item["fixed_version_status"] == "none_published"
        assert "trixie-security" in item["suites_checked"]
        # Justification must be substantive, not a one-liner.
        assert item["reachability"] == "not_reachable"
        assert len(item["reachability_evidence"]) >= 3
        assert len(item["compensating_controls"]) >= 3
        assert len(item["remediation_attempts"]) >= 2
        # Short, convention-matching expiry, mirrored into the scanner policy.
        assert item["expires"] == "2026-09-20"
        assert item["finding_id"] in exceptions
        assert str(exceptions[item["finding_id"]]["expired_at"]) == item["expires"]


def test_scanner_policy_has_no_blanket_bypass() -> None:
    """The gate must stay strict: no ignore-unfixed, no relaxed exit code."""
    workflow = (ROOT / ".github/workflows/container.yml").read_text(encoding="utf-8")
    assert 'exit-code: "1"' in workflow
    assert "severity: HIGH,CRITICAL" in workflow
    assert "ignore-unfixed" not in workflow
    assert "--skip-dirs" not in workflow

    policy = (ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
    assert "ignore-unfixed" not in policy
    payload = yaml.safe_load(policy)
    assert set(payload) == {"vulnerabilities"}
