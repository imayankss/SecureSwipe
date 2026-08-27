"""Synthetic tests for the optional local SQLite idempotency prototype.

These prove the prototype closes the three crash/restart gaps MT6 demonstrated
in the in-memory registry, without persisting any raw payload.

Local single-node only. No network, no real model, no held-out role.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.operations.durable_idempotency import (
    ALLOWED_DECISIONS,
    COMPLETED,
    FAILED,
    PENDING,
    UNRESOLVED,
    DurableIdempotencyError,
    IdempotencyConflict,
    SqliteIdempotencyStore,
    UnresolvedRequestError,
    key_digest,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
EVENT_HASH = "c" * 64


def _store(tmp_path: Path, name: str = "state.db") -> SqliteIdempotencyStore:
    return SqliteIdempotencyStore(tmp_path / name)


def _complete(store, request_id, digest=DIGEST_A, decision="below_review_threshold"):
    reservation = store.reserve(request_id=request_id, input_digest_sha256=digest)
    store.complete(reservation, decision=decision, model_version="synthetic",
                   audit_event_hash=EVENT_HASH)
    return reservation


# -- configuration safety -------------------------------------------------


def test_relative_path_is_refused(tmp_path):
    with pytest.raises(DurableIdempotencyError, match="absolute"):
        SqliteIdempotencyStore("state.db")


def test_path_inside_the_repository_is_refused():
    repo_db = Path(__file__).resolve().parents[1] / "docs" / "state.db"
    with pytest.raises(DurableIdempotencyError, match="outside the repository"):
        SqliteIdempotencyStore(repo_db)


def test_symlinked_path_is_refused(tmp_path):
    target = tmp_path / "real.db"
    target.write_bytes(b"")
    link = tmp_path / "linked.db"
    link.symlink_to(target)
    with pytest.raises(DurableIdempotencyError, match="symlink"):
        SqliteIdempotencyStore(link)


def test_missing_parent_directory_is_refused(tmp_path):
    with pytest.raises(DurableIdempotencyError, match="parent directory"):
        SqliteIdempotencyStore(tmp_path / "absent" / "state.db")


def test_uses_only_stdlib_sqlite3(tmp_path):
    with _store(tmp_path) as store:
        assert isinstance(store._connection, sqlite3.Connection)


# -- G3: restart-safe completed replay ------------------------------------


def test_completed_request_replays_after_restart_without_rescoring(tmp_path):
    with _store(tmp_path) as first:
        _complete(first, "R1")
        assert first.state_of("R1") == COMPLETED

    # A new store on the same file is a restart.
    with _store(tmp_path) as second:
        reservation = second.reserve(request_id="R1", input_digest_sha256=DIGEST_A)
        assert reservation.owner is False          # no rescoring
        assert reservation.state == COMPLETED
        assert reservation.audit_event_hash == EVENT_HASH
        assert reservation.decision == "below_review_threshold"
        assert second.count() == 1                 # no duplicate record


def test_restart_conflict_still_detected(tmp_path):
    with _store(tmp_path) as first:
        _complete(first, "R2")
    with _store(tmp_path) as second:
        with pytest.raises(IdempotencyConflict):
            second.reserve(request_id="R2", input_digest_sha256=DIGEST_B)


# -- G1/G2: failure after a durable audit event ---------------------------


def test_failure_with_durable_audit_becomes_unresolved_not_retryable(tmp_path):
    with _store(tmp_path) as store:
        reservation = store.reserve(request_id="R3", input_digest_sha256=DIGEST_A)
        store.fail(reservation, audit_event_durable=True)
        assert store.state_of("R3") == UNRESOLVED
        with pytest.raises(UnresolvedRequestError, match="will not be\\s+rescored"):
            store.reserve(request_id="R3", input_digest_sha256=DIGEST_A)


def test_failure_without_durable_audit_is_honestly_retryable(tmp_path):
    with _store(tmp_path) as store:
        reservation = store.reserve(request_id="R4", input_digest_sha256=DIGEST_A)
        store.fail(reservation, audit_event_durable=False)
        assert store.state_of("R4") == FAILED
        retry = store.reserve(request_id="R4", input_digest_sha256=DIGEST_A)
        assert retry.owner is True                 # no durable decision was released


# -- PENDING recovery fails closed ----------------------------------------


def test_pending_becomes_unresolved_on_restart_and_fails_closed(tmp_path):
    with _store(tmp_path) as first:
        first.reserve(request_id="R5", input_digest_sha256=DIGEST_A)
        assert first.state_of("R5") == PENDING     # crash leaves it PENDING

    with _store(tmp_path) as second:
        assert second.recovered_unresolved == 1
        assert second.state_of("R5") == UNRESOLVED
        with pytest.raises(UnresolvedRequestError):
            second.reserve(request_id="R5", input_digest_sha256=DIGEST_A)


def test_in_flight_key_is_refused_in_the_same_process(tmp_path):
    with _store(tmp_path) as store:
        store.reserve(request_id="R6", input_digest_sha256=DIGEST_A)
        with pytest.raises(UnresolvedRequestError, match="already in flight"):
            store.reserve(request_id="R6", input_digest_sha256=DIGEST_A)


# -- atomicity ------------------------------------------------------------


class _FlakyConnection:
    """Delegates to a real connection but fails one named statement."""

    def __init__(self, inner, failing_prefix: str) -> None:
        self._inner = inner
        self._failing_prefix = failing_prefix
        self.calls = 0

    def execute(self, sql, *args, **kwargs):
        if sql.startswith(self._failing_prefix):
            self.calls += 1
            raise sqlite3.OperationalError("injected: commit failure")
        return self._inner.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_completion_rolls_back_on_injected_failure(tmp_path):
    with _store(tmp_path) as store:
        reservation = store.reserve(request_id="R7", input_digest_sha256=DIGEST_A)
        real = store._connection
        flaky = _FlakyConnection(real, "UPDATE idempotency SET state = ?, decision")
        store._connection = flaky  # type: ignore[assignment]
        with pytest.raises(sqlite3.OperationalError):
            store.complete(reservation, decision="human_review",
                           model_version="synthetic", audit_event_hash=EVENT_HASH)
        store._connection = real  # type: ignore[assignment]
        assert flaky.calls == 1
        # Rolled back: still PENDING, never COMPLETED.
        assert store.state_of("R7") == PENDING

    # And after restart that unresolved work fails closed rather than rescoring.
    with _store(tmp_path) as restarted:
        assert restarted.state_of("R7") == UNRESOLVED


def test_completion_requires_an_owner_reservation(tmp_path):
    with _store(tmp_path) as store:
        _complete(store, "R8")
        replay = store.reserve(request_id="R8", input_digest_sha256=DIGEST_A)
        with pytest.raises(DurableIdempotencyError, match="owner reservation"):
            store.complete(replay, decision="human_review", model_version="s",
                           audit_event_hash=EVENT_HASH)


# -- allowlists and validation --------------------------------------------


@pytest.mark.parametrize("decision", ALLOWED_DECISIONS)
def test_allowlisted_decisions_are_accepted(tmp_path, decision):
    with _store(tmp_path, f"{decision}.db") as store:
        _complete(store, f"R-{decision}", decision=decision)
        assert store.state_of(f"R-{decision}") == COMPLETED


def test_non_allowlisted_decision_is_refused(tmp_path):
    with _store(tmp_path) as store:
        reservation = store.reserve(request_id="R9", input_digest_sha256=DIGEST_A)
        with pytest.raises(DurableIdempotencyError, match="allowlist"):
            store.complete(reservation, decision="approved", model_version="s",
                           audit_event_hash=EVENT_HASH)


@pytest.mark.parametrize("bad", ["", "xyz", "A" * 64, "a" * 63, "g" * 64])
def test_malformed_digests_are_refused(tmp_path, bad):
    with _store(tmp_path) as store:
        with pytest.raises(DurableIdempotencyError):
            store.reserve(request_id="R10", input_digest_sha256=bad)


# -- privacy: nothing raw reaches the database ----------------------------


def test_database_bytes_contain_no_raw_payload_or_identifier(tmp_path):
    """Direct database-content inspection with synthetic sentinels."""
    sentinel_id = "SENTINEL-REQUEST-ID-98765"
    with _store(tmp_path) as store:
        _complete(store, sentinel_id)

    raw = (tmp_path / "state.db").read_bytes()
    wal = tmp_path / "state.db-wal"
    if wal.exists():
        raw += wal.read_bytes()

    # The plaintext request id is never persisted; only its digest is.
    assert sentinel_id.encode() not in raw
    assert key_digest(sentinel_id).encode() in raw
    # No feature names, payload keys, labels, or score fields.
    for forbidden in (b"TransactionAmt", b'"V1"', b"isFraud", b"raw_score",
                      b"decision_score", b"calibrated_probability", b"Amount"):
        assert forbidden not in raw


def test_schema_stores_only_allowlisted_columns(tmp_path):
    with _store(tmp_path) as store:
        columns = {
            row["name"]
            for row in store._connection.execute("PRAGMA table_info(idempotency)")
        }
    assert columns == {
        "key_sha256", "input_digest_sha256", "state", "decision",
        "model_version", "audit_event_hash", "created_utc", "resolved_utc",
    }
    # No column can hold a payload, feature, score, or label.
    for forbidden in ("payload", "body", "features", "score", "label", "request_id"):
        assert forbidden not in columns


# -- documented non-claims ------------------------------------------------


def test_second_store_sees_committed_state_but_multiwriter_is_unsupported(tmp_path):
    """Cross-restart sharing works; concurrent multi-process writing is not claimed."""
    with _store(tmp_path) as first:
        _complete(first, "R11")
        with _store(tmp_path) as second:
            reservation = second.reserve(request_id="R11", input_digest_sha256=DIGEST_A)
            assert reservation.state == COMPLETED
    # This test asserts visibility of committed rows only. Concurrent multi-writer
    # behaviour is explicitly out of scope and is documented as unsupported.
