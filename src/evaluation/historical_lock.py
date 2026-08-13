"""Immutable integrity record for the already-observed historical test result."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

HISTORICAL_LOCK_VERSION = "1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HistoricalObservationError(RuntimeError):
    """Raised when the locked historical evidence is absent, changed, or reused."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_historical_observation(lock_path: str | Path, repository: str | Path) -> dict[str, Any]:
    """Verify every locked file before historical evidence is displayed or trusted."""
    root = Path(repository).resolve(strict=True)
    lock = Path(lock_path)
    if not lock.is_absolute():
        lock = root / lock
    if not lock.is_file() or lock.is_symlink():
        raise HistoricalObservationError(f"Historical lock is missing or unsafe: {lock}.")
    try:
        payload = json.loads(lock.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HistoricalObservationError(f"Historical lock is malformed: {exc}.") from exc
    if not isinstance(payload, dict) or payload.get("lock_version") != HISTORICAL_LOCK_VERSION:
        raise HistoricalObservationError("Unsupported historical lock version.")
    if payload.get("evaluation_scope") != "historical_reported_test":
        raise HistoricalObservationError("Historical lock has the wrong evaluation scope.")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise HistoricalObservationError("Historical lock has no file records.")
    for logical_name, record in sorted(files.items()):
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise HistoricalObservationError(f"Invalid historical record: {logical_name}.")
        relative = Path(str(record["path"]))
        expected = str(record["sha256"])
        if relative.is_absolute() or ".." in relative.parts or not _SHA256.fullmatch(expected):
            raise HistoricalObservationError(f"Unsafe historical record: {logical_name}.")
        artifact = (root / relative).resolve(strict=True)
        if not artifact.is_relative_to(root) or not artifact.is_file() or artifact.is_symlink():
            raise HistoricalObservationError(f"Unsafe historical artifact: {logical_name}.")
        actual = _sha256_file(artifact)
        if actual != expected:
            raise HistoricalObservationError(
                f"Historical artifact changed: {logical_name}; expected {expected}, got {actual}."
            )
    return payload
