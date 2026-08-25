"""Tamper-evident append-only audit evidence and in-process idempotency.

The hash chain and local head anchor make mutation, deletion, and reordering
detectable. They do not make the files immutable or protect an anchor that an
attacker can replace together with the log.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import stat
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

AUDIT_SCHEMA_VERSION = "1.0"
GENESIS_HASH = "0" * 64
AuditDecisionValue = Literal["human_review", "below_review_threshold"]

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_EVENT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_AUDIT_EVENT_FIELDS = {
    "schema_version",
    "api_schema_version",
    "event_id",
    "event_index",
    "request_id",
    "occurred_at_utc",
    "idempotency_key_sha256",
    "input_digest_sha256",
    "model_fingerprint_sha256",
    "model_version",
    "score",
    "threshold",
    "decision",
    "latency_ms",
    "status",
    "previous_hash",
    "event_hash",
}
_ANCHOR_FIELDS = {"schema_version", "event_count", "head_event_hash"}


class AuditIntegrityError(RuntimeError):
    """Raised when audit evidence is malformed or its hash chain is invalid."""


class IdempotencyConflictError(RuntimeError):
    """Raised when one request ID is reused for different canonical input."""


@dataclass(frozen=True)
class AuditDecision:
    score: float
    threshold: float
    decision: AuditDecisionValue
    model_version: str
    model_fingerprint_sha256: str


@dataclass(frozen=True)
class AuditVerificationResult:
    event_count: int
    head_event_hash: str


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def sha256_canonical(value: object) -> str:
    """Hash a JSON-compatible value after canonical key ordering and encoding."""
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def idempotency_key_sha256(request_id: str) -> str:
    if not _REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("request_id must be an opaque 1-64 character identifier.")
    return hashlib.sha256(request_id.encode("ascii")).hexdigest()


def _strict_json_object(encoded: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AuditIntegrityError(f"{label} contains duplicate key {key!r}.")
            result[key] = value
        return result

    try:
        decoded = json.loads(encoded, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, AuditIntegrityError):
            raise
        raise AuditIntegrityError(f"{label} is not strict UTF-8 JSON.") from exc
    if not isinstance(decoded, dict):
        raise AuditIntegrityError(f"{label} must be a JSON object.")
    return decoded


def _read_regular_file(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise AuditIntegrityError(f"{label} is unreadable or is a symbolic link.") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AuditIntegrityError(f"{label} must be a regular file.")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise AuditIntegrityError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _validate_timestamp(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AuditIntegrityError(f"{label} must be an RFC 3339 UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AuditIntegrityError(f"{label} must be an RFC 3339 UTC timestamp.") from exc
    if parsed.tzinfo != timezone.utc:
        raise AuditIntegrityError(f"{label} must use UTC.")


def _validate_event(event: dict[str, Any], *, line_number: int) -> None:
    label = f"Audit event line {line_number}"
    if set(event) != _AUDIT_EVENT_FIELDS:
        raise AuditIntegrityError(f"{label} fields are incomplete or unexpected.")
    if event["schema_version"] != AUDIT_SCHEMA_VERSION or event["api_schema_version"] != "1.0":
        raise AuditIntegrityError(f"{label} has an unsupported schema version.")
    if not isinstance(event["event_id"], str) or not _EVENT_ID_PATTERN.fullmatch(event["event_id"]):
        raise AuditIntegrityError(f"{label} has an invalid event_id.")
    if type(event["event_index"]) is not int or event["event_index"] < 0:
        raise AuditIntegrityError(f"{label} has an invalid event_index.")
    if not isinstance(event["request_id"], str) or not _REQUEST_ID_PATTERN.fullmatch(
        event["request_id"]
    ):
        raise AuditIntegrityError(f"{label} has an invalid request_id.")
    _validate_timestamp(event["occurred_at_utc"], label=f"{label} occurred_at_utc")
    for field_name in (
        "idempotency_key_sha256",
        "input_digest_sha256",
        "model_fingerprint_sha256",
        "previous_hash",
        "event_hash",
    ):
        _require_sha256(event[field_name], label=f"{label} {field_name}")
    if not isinstance(event["model_version"], str) or not event["model_version"]:
        raise AuditIntegrityError(f"{label} has an invalid model_version.")
    for field_name in ("score", "threshold", "latency_ms"):
        value = event[field_name]
        if type(value) not in {int, float} or not math.isfinite(float(value)):
            raise AuditIntegrityError(f"{label} {field_name} must be finite.")
    if not 0.0 <= float(event["score"]) <= 1.0:
        raise AuditIntegrityError(f"{label} score must be in [0, 1].")
    if not 0.0 <= float(event["threshold"]) <= 1.0:
        raise AuditIntegrityError(f"{label} threshold must be in [0, 1].")
    if float(event["latency_ms"]) < 0.0:
        raise AuditIntegrityError(f"{label} latency_ms must be non-negative.")
    if event["decision"] not in {"human_review", "below_review_threshold"}:
        raise AuditIntegrityError(f"{label} has an invalid bounded decision.")
    if event["status"] != "succeeded":
        raise AuditIntegrityError(f"{label} has an invalid status.")


def _default_anchor_path(log_path: Path) -> Path:
    return log_path.with_suffix(log_path.suffix + ".head.json")


def verify_audit_log(
    log_path: str | Path,
    *,
    anchor_path: str | Path | None = None,
) -> AuditVerificationResult:
    """Verify canonical NDJSON, the hash chain, and the local count/head anchor."""
    log = Path(log_path).expanduser().absolute()
    anchor = (
        Path(anchor_path).expanduser().absolute()
        if anchor_path is not None
        else _default_anchor_path(log)
    )
    if not log.exists():
        if anchor.exists():
            raise AuditIntegrityError("Audit anchor exists but the audit log is missing.")
        return AuditVerificationResult(event_count=0, head_event_hash=GENESIS_HASH)

    encoded = _read_regular_file(log, label="Audit log")
    if encoded and not encoded.endswith(b"\n"):
        raise AuditIntegrityError("Audit log must end with a newline.")

    previous_hash = GENESIS_HASH
    event_ids: set[str] = set()
    request_indexes: set[tuple[str, int]] = set()
    lines = encoded.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise AuditIntegrityError(f"Audit event line {line_number} is empty.")
        event = _strict_json_object(line, label=f"Audit event line {line_number}")
        _validate_event(event, line_number=line_number)
        if _canonical_json_bytes(event) != line:
            raise AuditIntegrityError(f"Audit event line {line_number} is not canonical JSON.")
        if event["event_id"] in event_ids:
            raise AuditIntegrityError(f"Audit event line {line_number} reuses an event_id.")
        event_ids.add(event["event_id"])
        request_index = (event["request_id"], event["event_index"])
        if request_index in request_indexes:
            raise AuditIntegrityError(
                f"Audit event line {line_number} reuses a request_id/event_index pair."
            )
        request_indexes.add(request_index)
        if event["previous_hash"] != previous_hash:
            raise AuditIntegrityError(f"Audit chain breaks at line {line_number}.")
        claimed_hash = event["event_hash"]
        unsigned = dict(event)
        del unsigned["event_hash"]
        expected_hash = sha256_canonical(unsigned)
        if claimed_hash != expected_hash:
            raise AuditIntegrityError(f"Audit event hash mismatch at line {line_number}.")
        previous_hash = claimed_hash

    if not anchor.exists():
        if lines:
            raise AuditIntegrityError("Non-empty audit log is missing its local head anchor.")
        return AuditVerificationResult(event_count=0, head_event_hash=GENESIS_HASH)

    anchor_encoded = _read_regular_file(anchor, label="Audit anchor")
    if not anchor_encoded.endswith(b"\n"):
        raise AuditIntegrityError("Audit anchor must end with a newline.")
    anchor_record = _strict_json_object(anchor_encoded.rstrip(b"\n"), label="Audit anchor")
    if set(anchor_record) != _ANCHOR_FIELDS:
        raise AuditIntegrityError("Audit anchor fields are incomplete or unexpected.")
    if _canonical_json_bytes(anchor_record) + b"\n" != anchor_encoded:
        raise AuditIntegrityError("Audit anchor is not canonical JSON.")
    if anchor_record["schema_version"] != AUDIT_SCHEMA_VERSION:
        raise AuditIntegrityError("Audit anchor has an unsupported schema version.")
    if type(anchor_record["event_count"]) is not int or anchor_record["event_count"] < 0:
        raise AuditIntegrityError("Audit anchor event_count is invalid.")
    head = _require_sha256(anchor_record["head_event_hash"], label="Audit anchor head")
    if anchor_record["event_count"] != len(lines) or head != previous_hash:
        raise AuditIntegrityError("Audit log count/head does not match its local anchor.")
    return AuditVerificationResult(event_count=len(lines), head_event_hash=previous_hash)


def _write_all(descriptor: int, encoded: bytes) -> None:
    offset = 0
    while offset < len(encoded):
        written = os.write(descriptor, encoded[offset:])
        if written <= 0:
            raise OSError("Short write while recording audit evidence.")
        offset += written


def _write_anchor(path: Path, *, event_count: int, head_event_hash: str) -> None:
    record = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "event_count": event_count,
        "head_event_hash": head_event_hash,
    }
    encoded = _canonical_json_bytes(record) + b"\n"
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary, flags, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


class AuditLog:
    """Single-process writer that exposes append operations only."""

    def __init__(self, log_path: str | Path, *, anchor_path: str | Path | None = None) -> None:
        self.path = Path(log_path).expanduser().absolute()
        self.anchor_path = (
            Path(anchor_path).expanduser().absolute()
            if anchor_path is not None
            else _default_anchor_path(self.path)
        )
        if not self.path.parent.is_dir():
            raise AuditIntegrityError("Audit log parent directory must already exist.")
        if self.anchor_path.parent != self.path.parent:
            raise AuditIntegrityError("Audit log and anchor must share one directory.")
        self._lock = threading.Lock()
        verified = verify_audit_log(self.path, anchor_path=self.anchor_path)
        self._event_count = verified.event_count
        self._head_event_hash = verified.head_event_hash

    def append_inference(
        self,
        *,
        request_id: str,
        api_schema_version: str,
        input_digest_sha256: str,
        latency_ms: float,
        decisions: Iterable[AuditDecision],
    ) -> tuple[str, ...]:
        """Append one canonical event per returned prediction and advance the anchor."""
        decision_list = list(decisions)
        if not decision_list:
            raise ValueError("At least one audit decision is required.")
        if api_schema_version != "1.0":
            raise ValueError("Unsupported API schema version for audit evidence.")
        _require_sha256(input_digest_sha256, label="input_digest_sha256")
        idempotency_digest = idempotency_key_sha256(request_id)
        if not math.isfinite(latency_ms) or latency_ms < 0.0:
            raise ValueError("latency_ms must be finite and non-negative.")

        with self._lock:
            verified = verify_audit_log(self.path, anchor_path=self.anchor_path)
            if (
                verified.event_count != self._event_count
                or verified.head_event_hash != self._head_event_hash
            ):
                raise AuditIntegrityError("Audit evidence changed outside the append-only writer.")

            previous_hash = self._head_event_hash
            event_hashes: list[str] = []
            encoded_lines: list[bytes] = []
            occurred_at = (
                datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
            )
            for event_index, decision in enumerate(decision_list):
                if not _SHA256_PATTERN.fullmatch(decision.model_fingerprint_sha256):
                    raise ValueError("model_fingerprint_sha256 must be a lowercase SHA-256 digest.")
                unsigned = {
                    "schema_version": AUDIT_SCHEMA_VERSION,
                    "api_schema_version": api_schema_version,
                    "event_id": uuid.uuid4().hex,
                    "event_index": event_index,
                    "request_id": request_id,
                    "occurred_at_utc": occurred_at,
                    "idempotency_key_sha256": idempotency_digest,
                    "input_digest_sha256": input_digest_sha256,
                    "model_fingerprint_sha256": decision.model_fingerprint_sha256,
                    "model_version": decision.model_version,
                    "score": float(decision.score),
                    "threshold": float(decision.threshold),
                    "decision": decision.decision,
                    "latency_ms": round(float(latency_ms), 3),
                    "status": "succeeded",
                    "previous_hash": previous_hash,
                }
                event_hash = sha256_canonical(unsigned)
                event = {**unsigned, "event_hash": event_hash}
                _validate_event(event, line_number=self._event_count + event_index + 1)
                encoded_lines.append(_canonical_json_bytes(event) + b"\n")
                event_hashes.append(event_hash)
                previous_hash = event_hash

            flags = (
                os.O_WRONLY
                | os.O_APPEND
                | os.O_CREAT
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(self.path, flags, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise AuditIntegrityError("Audit log must be a regular file.")
                _write_all(descriptor, b"".join(encoded_lines))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

            new_count = self._event_count + len(encoded_lines)
            _write_anchor(
                self.anchor_path,
                event_count=new_count,
                head_event_hash=previous_hash,
            )
            self._event_count = new_count
            self._head_event_hash = previous_hash
            return tuple(event_hashes)


@dataclass
class _IdempotencyEntry:
    input_digest_sha256: str
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    result: Any = None
    error: BaseException | None = None


@dataclass(frozen=True)
class IdempotencyReservation:
    key_sha256: str
    owner: bool
    _entry: _IdempotencyEntry


class IdempotencyRegistry:
    """Coordinate identical retries so only the first request performs scoring."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[str, _IdempotencyEntry] = {}

    async def reserve(self, *, request_id: str, input_digest_sha256: str) -> IdempotencyReservation:
        key = idempotency_key_sha256(request_id)
        _require_sha256(input_digest_sha256, label="input_digest_sha256")
        async with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                if existing.input_digest_sha256 != input_digest_sha256:
                    raise IdempotencyConflictError(
                        "The request ID was already used for different canonical input."
                    )
                return IdempotencyReservation(key_sha256=key, owner=False, _entry=existing)
            entry = _IdempotencyEntry(input_digest_sha256=input_digest_sha256)
            self._entries[key] = entry
            return IdempotencyReservation(key_sha256=key, owner=True, _entry=entry)

    async def replay(self, reservation: IdempotencyReservation) -> Any:
        if reservation.owner:
            raise RuntimeError("Owner reservations cannot be replayed.")
        await reservation._entry.ready.wait()
        if reservation._entry.error is not None:
            raise reservation._entry.error
        return reservation._entry.result

    def complete(self, reservation: IdempotencyReservation, result: Any) -> None:
        """Publish a completed result without a cancellation point after audit append."""
        if not reservation.owner:
            raise RuntimeError("Only an owner reservation can be completed.")
        reservation._entry.result = result
        reservation._entry.ready.set()

    async def fail(self, reservation: IdempotencyReservation, error: BaseException) -> None:
        if not reservation.owner:
            raise RuntimeError("Only an owner reservation can fail.")
        async with self._lock:
            current = self._entries.get(reservation.key_sha256)
            if current is reservation._entry:
                del self._entries[reservation.key_sha256]
            reservation._entry.error = error
            reservation._entry.ready.set()
