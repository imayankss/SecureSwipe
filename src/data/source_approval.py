"""Explicit operator approval for data claimed to be genuinely new.

File content alone cannot prove that a CSV was not derived from an already
observed corpus.  This boundary therefore records an explicit human attestation
and binds it to the exact source bytes.  Historical lineage detected locally
still wins over an approval.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.artifacts.bundle import sha256_file

SOURCE_APPROVAL_FORMAT_VERSION = "1"
NEW_SOURCE_ATTESTATION = (
    "I attest that this exact file is authorized for development and contains "
    "no rows derived from the already-observed SecureSwipe historical corpus."
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "approval_format_version",
    "approved_file_sha256",
    "attestation",
    "reviewed_by",
    "source_reference",
}


def load_source_approval(
    approval_path: str | Path,
    *,
    source_path: str | Path,
    source_reference: str,
) -> dict[str, Any]:
    """Verify an operator approval bound to the exact source file."""
    approval = Path(approval_path).expanduser().resolve(strict=True)
    source = Path(source_path).expanduser().resolve(strict=True)
    return load_source_approval_evidence(
        approval,
        approved_file_sha256=sha256_file(source),
        source_reference=source_reference,
    )


def load_source_approval_evidence(
    approval_path: str | Path,
    *,
    approved_file_sha256: str,
    source_reference: str,
) -> dict[str, Any]:
    """Verify retained canonical approval evidence without the original CSV."""
    approval = Path(approval_path).expanduser().resolve(strict=True)
    if approval.is_symlink() or not approval.is_file():
        raise ValueError("Source approval must be a regular non-symlink JSON file.")
    try:
        payload = json.loads(approval.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Source approval must be valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise ValueError(f"Source approval fields must be exactly {sorted(_FIELDS)}.")
    if payload["approval_format_version"] != SOURCE_APPROVAL_FORMAT_VERSION:
        raise ValueError("Unsupported source approval format version.")
    digest = payload["approved_file_sha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("Source approval has an invalid file checksum.")
    if digest != approved_file_sha256:
        raise ValueError("Source approval is not bound to these exact source bytes.")
    if payload["attestation"] != NEW_SOURCE_ATTESTATION:
        raise ValueError("Source approval does not contain the required attestation.")
    if not isinstance(payload["reviewed_by"], str) or not payload["reviewed_by"].strip():
        raise ValueError("Source approval must identify the human reviewer.")
    if payload["source_reference"] != source_reference.strip():
        raise ValueError("Source approval reference does not match this curation request.")
    return payload
