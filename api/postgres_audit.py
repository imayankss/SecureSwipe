"""Canonical PostgreSQL audit events and explicit full-chain verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from api.scale_response import (
    BoundedPredictionRepresentation,
    response_sha256,
)

AUDIT_SCHEMA_VERSION = "postgres-audit-v1"
AUDIT_CHAIN_ID = "primary"
GENESIS_HASH = "0" * 64
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PostgresAuditIntegrityError(RuntimeError):
    """The durable audit chain or its completion linkage is invalid."""


@dataclass(frozen=True)
class CanonicalAuditEvent:
    event_id: str
    chain_id: str
    sequence: int
    previous_hash: str
    key_digest: str
    request_digest: str
    decision: str
    bounded_response: dict[str, Any]
    response_sha256: str
    occurred_at: datetime
    event_hash: str


@dataclass(frozen=True)
class AuditChainVerification:
    chain_id: str
    event_count: int
    last_sequence: int
    last_hash: str


def canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise PostgresAuditIntegrityError("Audit timestamps must include a timezone.")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _event_document(
    *,
    event_id: str,
    chain_id: str,
    sequence: int,
    previous_hash: str,
    key_digest: str,
    request_digest: str,
    decision: str,
    bounded_response: dict[str, Any],
    response_digest: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "bounded_response": bounded_response,
        "chain_id": chain_id,
        "decision": decision,
        "event_id": event_id,
        "idempotency_key_hmac_sha256": key_digest,
        "occurred_at": canonical_timestamp(occurred_at),
        "previous_hash": previous_hash,
        "request_digest_sha256": request_digest,
        "response_sha256": response_digest,
        "sequence": sequence,
    }


def canonical_event_bytes(**values: Any) -> bytes:
    return json.dumps(
        _event_document(**values),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_audit_event(
    *,
    chain_id: str,
    sequence: int,
    previous_hash: str,
    key_digest: str,
    request_digest: str,
    response: BoundedPredictionRepresentation,
    occurred_at: datetime,
    event_id: str | None = None,
) -> CanonicalAuditEvent:
    if sequence < 1:
        raise PostgresAuditIntegrityError("Audit sequence must be positive.")
    for value in (previous_hash, key_digest, request_digest):
        if not _SHA256_PATTERN.fullmatch(value):
            raise PostgresAuditIntegrityError("Audit digests must be lowercase SHA-256.")
    identifier = event_id or str(uuid.uuid4())
    try:
        uuid.UUID(identifier)
    except ValueError as exc:
        raise PostgresAuditIntegrityError("Audit event ID is invalid.") from exc
    document = response.model_dump(mode="json", by_alias=True)
    response_digest = response_sha256(response)
    digest = hashlib.sha256(
        canonical_event_bytes(
            event_id=identifier,
            chain_id=chain_id,
            sequence=sequence,
            previous_hash=previous_hash,
            key_digest=key_digest,
            request_digest=request_digest,
            decision=response.decision,
            bounded_response=document,
            response_digest=response_digest,
            occurred_at=occurred_at,
        )
    ).hexdigest()
    return CanonicalAuditEvent(
        event_id=identifier,
        chain_id=chain_id,
        sequence=sequence,
        previous_hash=previous_hash,
        key_digest=key_digest,
        request_digest=request_digest,
        decision=response.decision,
        bounded_response=document,
        response_sha256=response_digest,
        occurred_at=occurred_at,
        event_hash=digest,
    )


def _validate_event_row(row: dict[str, Any], expected_previous: str) -> str:
    try:
        response = BoundedPredictionRepresentation.model_validate(row["bounded_response"])
        event = build_audit_event(
            event_id=str(row["event_id"]),
            chain_id=str(row["chain_id"]),
            sequence=int(row["sequence"]),
            previous_hash=str(row["previous_hash"]),
            key_digest=str(row["key_digest"]),
            request_digest=str(row["request_digest"]),
            response=response,
            occurred_at=row["occurred_at"],
        )
    except (KeyError, TypeError, ValueError, PostgresAuditIntegrityError) as exc:
        raise PostgresAuditIntegrityError("Audit event encoding is invalid.") from exc
    if not hmac.compare_digest(event.previous_hash, expected_previous):
        raise PostgresAuditIntegrityError("Audit chain previous-hash linkage failed.")
    if not hmac.compare_digest(event.decision, str(row["decision"])):
        raise PostgresAuditIntegrityError("Audit decision does not match its bounded response.")
    if not hmac.compare_digest(event.response_sha256, str(row["response_sha256"])):
        raise PostgresAuditIntegrityError("Audit response digest is invalid.")
    if not hmac.compare_digest(event.event_hash, str(row["event_hash"])):
        raise PostgresAuditIntegrityError("Audit event hash is invalid.")
    return event.event_hash


async def verify_audit_chain(
    connection: psycopg.AsyncConnection[Any], *, schema: str
) -> AuditChainVerification:
    """Perform the intentionally O(n) startup/on-demand verifier."""
    connection.row_factory = dict_row
    head_cursor = await connection.execute(
        sql.SQL(
            "SELECT chain_id, last_sequence, last_hash FROM {}.audit_chain_heads "
            "WHERE chain_id = %s"
        ).format(sql.Identifier(schema)),
        (AUDIT_CHAIN_ID,),
    )
    head = await head_cursor.fetchone()
    if head is None:
        raise PostgresAuditIntegrityError("The seeded audit chain head is missing.")
    boundary_cursor = await connection.execute(
        sql.SQL(
            """
            SELECT
                (SELECT count(*) FROM {}.audit_chain_heads) AS head_count,
                (SELECT count(*) FROM {}.audit_events WHERE chain_id <> %s)
                    AS foreign_event_count
            """
        ).format(sql.Identifier(schema), sql.Identifier(schema)),
        (AUDIT_CHAIN_ID,),
    )
    boundary = await boundary_cursor.fetchone()
    if (
        boundary is None
        or int(boundary["head_count"]) != 1
        or int(boundary["foreign_event_count"]) != 0
    ):
        raise PostgresAuditIntegrityError("The audit chain boundary is not singular.")
    event_cursor = await connection.execute(
        sql.SQL(
            """
            SELECT event_id, chain_id, sequence, previous_hash, event_hash,
                   key_digest, request_digest, decision, bounded_response,
                   response_sha256, occurred_at
            FROM {}.audit_events
            WHERE chain_id = %s
            ORDER BY sequence
            """
        ).format(sql.Identifier(schema)),
        (AUDIT_CHAIN_ID,),
    )
    rows = await event_cursor.fetchall()
    expected_previous = GENESIS_HASH
    for expected_sequence, row in enumerate(rows, start=1):
        if int(row["sequence"]) != expected_sequence:
            raise PostgresAuditIntegrityError("Audit sequence is not contiguous.")
        expected_previous = _validate_event_row(row, expected_previous)
    count = len(rows)
    if int(head["last_sequence"]) != count:
        raise PostgresAuditIntegrityError("Audit chain head count does not match events.")
    if not hmac.compare_digest(str(head["last_hash"]), expected_previous):
        raise PostgresAuditIntegrityError("Audit chain head hash does not match events.")

    consistency_cursor = await connection.execute(
        sql.SQL(
            """
            SELECT count(*) AS inconsistent_count
            FROM {}.secureswipe_idempotency AS idempotency
            FULL JOIN {}.audit_events AS event
              ON event.key_digest = idempotency.key_digest
             AND event.event_hash = idempotency.audit_receipt_sha256
            WHERE (idempotency.state = 'completed' OR event.event_id IS NOT NULL)
              AND (
                  idempotency.state IS DISTINCT FROM 'completed'
                  OR event.event_id IS NULL
                  OR idempotency.request_digest <> event.request_digest
                  OR idempotency.response_sha256 <> event.response_sha256
                  OR idempotency.response_document <> event.bounded_response
              )
            """
        ).format(sql.Identifier(schema), sql.Identifier(schema))
    )
    consistency = await consistency_cursor.fetchone()
    if consistency is None or int(consistency["inconsistent_count"]) != 0:
        raise PostgresAuditIntegrityError(
            "Audit events and completed idempotency rows are inconsistent."
        )
    return AuditChainVerification(
        chain_id=str(head["chain_id"]),
        event_count=count,
        last_sequence=count,
        last_hash=expected_previous,
    )


__all__ = [
    "AUDIT_CHAIN_ID",
    "AUDIT_SCHEMA_VERSION",
    "AuditChainVerification",
    "CanonicalAuditEvent",
    "GENESIS_HASH",
    "PostgresAuditIntegrityError",
    "build_audit_event",
    "canonical_event_bytes",
    "verify_audit_chain",
]
