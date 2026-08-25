"""Integrity tests for tamper-evident append-only API audit evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.audit import (
    GENESIS_HASH,
    AuditDecision,
    AuditIntegrityError,
    AuditLog,
    verify_audit_log,
)


def _append(log: AuditLog, *, request_id: str, score: float) -> None:
    log.append_inference(
        request_id=request_id,
        api_schema_version="1.0",
        input_digest_sha256=(request_id[-1] * 64),
        latency_ms=12.3456,
        decisions=[
            AuditDecision(
                score=score,
                threshold=0.53,
                decision="human_review" if score >= 0.53 else "below_review_threshold",
                model_version="audit-fixture-v1",
                model_fingerprint_sha256="a" * 64,
            )
        ],
    )


def _three_event_log(tmp_path: Path) -> tuple[Path, Path, list[bytes]]:
    log_path = tmp_path / "events.ndjson"
    log = AuditLog(log_path)
    _append(log, request_id="audit-request-1", score=0.2)
    _append(log, request_id="audit-request-2", score=0.6)
    _append(log, request_id="audit-request-3", score=0.8)
    anchor_path = log_path.with_suffix(".ndjson.head.json")
    return log_path, anchor_path, log_path.read_bytes().splitlines(keepends=True)


def test_canonical_chain_contains_only_bounded_redacted_evidence(tmp_path: Path) -> None:
    log_path = tmp_path / "events.ndjson"
    log = AuditLog(log_path)
    _append(log, request_id="audit-request-a", score=0.8)
    _append(log, request_id="audit-request-b", score=0.2)

    verified = verify_audit_log(log_path)
    assert verified.event_count == 2
    assert verified.head_event_hash != GENESIS_HASH

    lines = log_path.read_text(encoding="ascii").splitlines()
    events = [json.loads(line) for line in lines]
    assert events[0]["previous_hash"] == GENESIS_HASH
    assert events[1]["previous_hash"] == events[0]["event_hash"]
    assert events[0]["decision"] == "human_review"
    assert events[1]["decision"] == "below_review_threshold"
    assert events[0]["latency_ms"] == 12.346
    assert lines == [
        json.dumps(event, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        for event in events
    ]


@pytest.mark.parametrize("tamper", ["mutation", "deletion", "reordering"])
def test_verifier_detects_mutation_deletion_and_reordering(tmp_path: Path, tamper: str) -> None:
    log_path, _anchor_path, lines = _three_event_log(tmp_path)
    if tamper == "mutation":
        mutated = json.loads(lines[1])
        mutated["score"] = 0.7
        lines[1] = (
            json.dumps(mutated, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
                "ascii"
            )
            + b"\n"
        )
    elif tamper == "deletion":
        lines = lines[:-1]
    else:
        lines[0], lines[1] = lines[1], lines[0]
    log_path.write_bytes(b"".join(lines))

    with pytest.raises(AuditIntegrityError):
        verify_audit_log(log_path)


def test_writer_refuses_to_append_after_external_tampering(tmp_path: Path) -> None:
    log_path, _anchor_path, lines = _three_event_log(tmp_path)
    writer = AuditLog(log_path)
    log_path.write_bytes(b"".join(lines[:-1]))

    with pytest.raises(AuditIntegrityError):
        _append(writer, request_id="audit-request-4", score=0.9)
