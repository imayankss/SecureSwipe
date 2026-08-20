"""Explicit reviewed-source approval fixtures for scientific-boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

from src.artifacts.bundle import sha256_file
from src.data.source_approval import NEW_SOURCE_ATTESTATION


def write_source_approval(source: Path, reference: str) -> Path:
    path = source.with_suffix(source.suffix + ".approval.json")
    path.write_text(
        json.dumps(
            {
                "approval_format_version": "1",
                "approved_file_sha256": sha256_file(source),
                "attestation": NEW_SOURCE_ATTESTATION,
                "reviewed_by": "test-fixture-reviewer",
                "source_reference": reference,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
