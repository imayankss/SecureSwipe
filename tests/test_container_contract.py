"""Daemon-independent container policy and synthetic smoke-bundle tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.schemas import TransactionFeatures
from api.service import ModelService
from scripts.create_synthetic_bundle import (
    create_synthetic_bundle,
    directory_fingerprint,
)
from src.artifacts.bundle import load_model_bundle

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_has_restricted_reproducible_runtime_contract() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert (
        "python:3.12.10-slim-bookworm@sha256:"
        "fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db" in dockerfile
    )
    assert "--require-hashes" in dockerfile
    assert "COPY --from=dependencies /install /usr/local" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "/health/live" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "RUN python -m pip uninstall --yes pip" in dockerfile
    assert dockerfile.index("RUN python -m pip uninstall --yes pip") < dockerfile.index(
        "USER 10001:10001"
    )
    assert "COPY ." not in dockerfile
    assert "apt-get" not in dockerfile


@pytest.mark.parametrize(
    "excluded",
    [
        ".git",
        ".env.*",
        ".kaggle",
        "artifacts",
        "data",
        "notebooks",
        "reports",
        "tests",
        "web",
        "*.csv",
        "*.joblib",
        "*.pem",
    ],
)
def test_docker_context_excludes_sensitive_or_development_content(excluded: str) -> None:
    patterns = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert excluded in patterns


def test_synthetic_smoke_bundle_is_deterministic_and_matches_service(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_manifest = create_synthetic_bundle(first_dir)
    create_synthetic_bundle(second_dir)

    assert directory_fingerprint(first_dir) == directory_fingerprint(second_dir)

    bundle = load_model_bundle(first_manifest, trusted_root=first_dir)
    request = json.loads((first_dir / "smoke_request.json").read_text(encoding="utf-8"))
    expected = json.loads((first_dir / "smoke_expected.json").read_text(encoding="utf-8"))
    actual = ModelService(bundle).predict_one(TransactionFeatures.model_validate(request))

    assert actual.model_version == expected["model_version"]
    assert actual.score_type == expected["score_type"]
    assert actual.operating_threshold == expected["operating_threshold"]
    assert actual.raw_score == expected["raw_score"]
    assert actual.decision_score == expected["decision_score"]
    assert actual.decision == expected["decision"]


def test_synthetic_bundle_refuses_to_overwrite_output(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    create_synthetic_bundle(output)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        create_synthetic_bundle(output)
