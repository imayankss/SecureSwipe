"""MT6 synthetic fault-injection harness for state and crash recovery.

Every fixture is synthetic. No IEEE-CIS file, no held-out role, no real model
artifact, and no network. Failures are injected at named boundaries through
fakes rather than timing sleeps, so each scenario is deterministic.

A scenario is only reported as handled if a test here demonstrates it.
Protocol: docs/evidence/MT6_STATE_AND_CRASH_PROTOCOL.md
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.audit import AuditIntegrityError, AuditLog, verify_audit_log
from api.main import ApiSettings, create_app
from api.service import ModelService
from src.artifacts.bundle import load_model_bundle
from src.operations.benchmark import synthetic_corpus

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "artifacts" / "historical-reference-demo-v1" / "manifest.json"
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"

APPROVAL_LIKE = ("approve", "approved", "accept", "cleared", "allow")


@pytest.fixture(scope="module")
def bundle():
    return load_model_bundle(MANIFEST, trusted_root=ARTIFACT_ROOT)


@pytest.fixture
def payload():
    return synthetic_corpus(1)[0]


def _settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        artifact_root=tmp_path,
        bundle_manifest=None,
        cors_origins=(),
        audit_log_path=tmp_path / "audit.ndjson",
    )


def _client(bundle, tmp_path: Path) -> TestClient:
    return TestClient(create_app(service=ModelService(bundle), settings=_settings(tmp_path)))


def _events(tmp_path: Path) -> list[dict[str, Any]]:
    log = tmp_path / "audit.ndjson"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line]


def _assert_not_approval_like(response) -> None:
    body = response.text.lower()
    for token in APPROVAL_LIKE:
        assert token not in body, f"approval-like token {token!r} leaked in a failure response"


class _FaultyAuditLog:
    """Delegating audit log that fails at a named boundary."""

    def __init__(self, inner: AuditLog, *, mode: str) -> None:
        self._inner = inner
        self._mode = mode
        self.calls = 0

    def append_inference(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self._mode == "before_write":
            raise OSError("injected: audit sink unavailable before write")
        result = self._inner.append_inference(**kwargs)
        if self._mode == "after_write":
            raise OSError("injected: crash after audit fsync, before completion")
        return result


# -- point 1: before idempotency reservation ------------------------------


def test_point1_failure_before_reservation_scores_nothing(bundle, tmp_path):
    with _client(bundle, tmp_path) as client:
        response = client.post("/v1/predict", json={"not": "a transaction"},
                               headers={"X-Request-ID": "mt6-p1"})
    assert response.status_code == 422
    _assert_not_approval_like(response)
    assert _events(tmp_path) == []            # no audit event
    assert verify_audit_log(tmp_path / "audit.ndjson").event_count == 0


# -- point 2: after reservation, before scoring ---------------------------


def test_point2_scoring_failure_leaves_no_audit_and_frees_the_key(bundle, payload, tmp_path,
                                                                  monkeypatch):
    app = create_app(service=ModelService(bundle), settings=_settings(tmp_path))

    def explode(_transaction):
        raise RuntimeError("injected: scoring failed after reservation")

    with TestClient(app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(app.state.model_service, "predict_one", explode)
        first = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p2"})
        assert first.status_code >= 500
        _assert_not_approval_like(first)
        assert _events(tmp_path) == []

        # The key was released, so an honest retry may score again.
        monkeypatch.undo()
        retry = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p2"})
        assert retry.status_code == 200
    assert len(_events(tmp_path)) == 1        # exactly one event for the completed decision


# -- point 3: after scoring, before durable completion --------------------


def test_point3_audit_failure_before_write_releases_no_result(bundle, payload, tmp_path):
    app = create_app(service=ModelService(bundle), settings=_settings(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.audit_log = _FaultyAuditLog(app.state.audit_log, mode="before_write")
        response = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p3"})
    assert response.status_code >= 500
    _assert_not_approval_like(response)
    assert "audit" in response.text.lower()
    assert _events(tmp_path) == []            # nothing durable, nothing released


# -- point 4: during audit/state commit -----------------------------------


def test_point4_crash_after_audit_write_before_completion(bundle, payload, tmp_path):
    """The audit event is durable but the caller never receives a result."""
    app = create_app(service=ModelService(bundle), settings=_settings(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.audit_log = _FaultyAuditLog(app.state.audit_log, mode="after_write")
        response = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p4"})
    assert response.status_code >= 500
    _assert_not_approval_like(response)
    events = _events(tmp_path)
    assert len(events) == 1                   # audit committed
    assert events[0]["request_id"] == "mt6-p4"
    assert verify_audit_log(tmp_path / "audit.ndjson").event_count == 1


def test_point4_same_process_retry_after_partial_commit_bricks_the_chain(bundle, payload,
                                                                        tmp_path):
    """Demonstrated gap: the released key allows a retry that duplicates the event."""
    app = create_app(service=ModelService(bundle), settings=_settings(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        faulty = _FaultyAuditLog(app.state.audit_log, mode="after_write")
        app.state.audit_log = faulty
        client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p4b"})
        # Recover the sink, then retry the same key as a client naturally would.
        app.state.audit_log = faulty._inner
        retry = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p4b"})
        # OBSERVED GAP: the failure released the key, so the retry rescored and
        # returned 200 while silently writing a duplicate event.
        assert retry.status_code == 200
        assert len(_events(tmp_path)) == 2

    # Two events now share a request_id, so the chain no longer verifies.
    with pytest.raises(AuditIntegrityError, match="reuses a request_id"):
        verify_audit_log(tmp_path / "audit.ndjson")


# -- point 5: after durable completion, before HTTP response --------------


def test_point5_completion_then_response_failure_keeps_one_event(bundle, payload, tmp_path):
    app = create_app(service=ModelService(bundle), settings=_settings(tmp_path))
    registry = app.state.idempotency_registry
    original_complete = registry.complete

    def complete_then_crash(reservation, result):
        original_complete(reservation, result)
        raise RuntimeError("injected: crash after completion, before response")

    with TestClient(app, raise_server_exceptions=False) as client:
        registry.complete = complete_then_crash  # type: ignore[method-assign]
        response = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p5"})
        assert response.status_code >= 500
        _assert_not_approval_like(response)
        assert len(_events(tmp_path)) == 1

        # OBSERVED GAP: the handler's failure path deletes the entry even though
        # the audit event was already durable, so a retry rescores and appends a
        # second event rather than replaying the completed result.
        registry.complete = original_complete  # type: ignore[method-assign]
        retry = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p5"})
        assert retry.status_code == 200
    assert len(_events(tmp_path)) == 2
    with pytest.raises(AuditIntegrityError, match="reuses a request_id"):
        verify_audit_log(tmp_path / "audit.ndjson")


# -- point 6: process restart followed by a duplicate retry ---------------


def test_point6_restart_then_duplicate_retry_breaks_exactly_once(bundle, payload, tmp_path):
    """DEMONSTRATED GAP: in-memory idempotency does not survive a restart."""
    with _client(bundle, tmp_path) as first_process:
        original = first_process.post("/v1/predict", json=payload,
                                      headers={"X-Request-ID": "mt6-p6"})
        assert original.status_code == 200
    assert len(_events(tmp_path)) == 1

    # A second process is a restart: the registry is empty, the audit log is not.
    with _client(bundle, tmp_path) as second_process:
        retry = second_process.post("/v1/predict", json=payload,
                                    headers={"X-Request-ID": "mt6-p6"})

    _assert_not_approval_like(retry) if retry.status_code >= 400 else None
    events = _events(tmp_path)
    # The request was scored again and a duplicate event was written.
    assert len(events) == 2, "restart allowed a second scoring pass for the same key"
    assert [e["request_id"] for e in events] == ["mt6-p6", "mt6-p6"]
    # The chain is now permanently unverifiable.
    with pytest.raises(AuditIntegrityError, match="reuses a request_id"):
        verify_audit_log(tmp_path / "audit.ndjson")


def test_point6_bricked_chain_blocks_the_next_restart(bundle, payload, tmp_path):
    """The consequence: after the duplicate, the service cannot reopen its log."""
    with _client(bundle, tmp_path) as first_process:
        first_process.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p6b"})
    with _client(bundle, tmp_path) as second_process:
        second_process.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p6b"})

    with pytest.raises(AuditIntegrityError):
        AuditLog(tmp_path / "audit.ndjson")


def test_point6_same_process_replay_is_correct(bundle, payload, tmp_path):
    """Within one process the invariant holds: one result, one event."""
    with _client(bundle, tmp_path) as client:
        first = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p6c"})
        replay = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p6c"})
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers.get("x-idempotent-replay") == "true"
    assert len(_events(tmp_path)) == 1


def test_same_key_different_body_conflicts_without_extra_audit(bundle, tmp_path):
    rows = synthetic_corpus(2)
    with _client(bundle, tmp_path) as client:
        assert client.post("/v1/predict", json=rows[0],
                           headers={"X-Request-ID": "mt6-conflict"}).status_code == 200
        conflict = client.post("/v1/predict", json=rows[1],
                               headers={"X-Request-ID": "mt6-conflict"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    _assert_not_approval_like(conflict)
    assert len(_events(tmp_path)) == 1


# -- point 7: corrupted or truncated store --------------------------------


def test_point7_mutation_is_detected(bundle, payload, tmp_path):
    with _client(bundle, tmp_path) as client:
        client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p7"})
    log = tmp_path / "audit.ndjson"
    event = json.loads(log.read_text().splitlines()[0])
    event["score"] = 0.99
    log.write_text(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
    with pytest.raises(AuditIntegrityError):
        verify_audit_log(log)


def test_point7_truncation_is_detected(bundle, payload, tmp_path):
    rows = synthetic_corpus(3)
    with _client(bundle, tmp_path) as client:
        for index, row in enumerate(rows):
            client.post("/v1/predict", json=row, headers={"X-Request-ID": f"mt6-p7t-{index}"})
    log = tmp_path / "audit.ndjson"
    lines = log.read_text().splitlines()
    log.write_text("\n".join(lines[:-1]) + "\n")     # drop the last event
    with pytest.raises(AuditIntegrityError):
        verify_audit_log(log)


def test_point7_corrupted_store_refuses_to_serve(bundle, payload, tmp_path):
    with _client(bundle, tmp_path) as client:
        client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p7c"})
    log = tmp_path / "audit.ndjson"
    log.write_text(log.read_text() + "{\"not\": \"a valid event\"}\n")
    # The audit writer re-verifies on open, so a corrupted store refuses the
    # restart outright rather than serving from a broken chain.
    with pytest.raises(AuditIntegrityError):
        with TestClient(create_app(service=ModelService(bundle),
                                   settings=_settings(tmp_path))):
            pass


# -- point 8: unavailable or unwritable sink ------------------------------


def test_point8_unwritable_sink_fails_closed(bundle, payload, tmp_path):
    app = create_app(service=ModelService(bundle), settings=_settings(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.audit_log = _FaultyAuditLog(app.state.audit_log, mode="before_write")
        response = client.post("/v1/predict", json=payload, headers={"X-Request-ID": "mt6-p8"})
    assert response.status_code >= 500
    _assert_not_approval_like(response)
    assert _events(tmp_path) == []


def test_point8_missing_fingerprint_fails_closed(bundle, payload, tmp_path):
    """Audit evidence requires a verified model fingerprint; without it, refuse."""
    unfingerprinted = replace(bundle, model_artifact_sha256=None)
    # Fail-closed at startup: the service refuses to run at all rather than
    # serving decisions it could not audit.
    with pytest.raises(RuntimeError, match="verified model-artifact SHA-256 fingerprint"):
        with TestClient(create_app(service=ModelService(unfingerprinted),
                                   settings=_settings(tmp_path))):
            pass
    assert _events(tmp_path) == []


# -- privacy --------------------------------------------------------------


def test_no_raw_payload_or_feature_value_is_persisted(bundle, tmp_path):
    sentinel = 424242.42
    row = {**synthetic_corpus(1)[0], "Amount": sentinel}
    with _client(bundle, tmp_path) as client:
        assert client.post("/v1/predict", json=row,
                           headers={"X-Request-ID": "mt6-privacy"}).status_code == 200
    raw = (tmp_path / "audit.ndjson").read_text()
    assert "424242" not in raw
    for feature in ("V1", "V17", "Time", "Amount"):
        assert f'"{feature}"' not in raw
    event = json.loads(raw.splitlines()[0])
    assert set(event) == {
        "api_schema_version", "decision", "event_hash", "event_id", "event_index",
        "idempotency_key_sha256", "input_digest_sha256", "latency_ms",
        "model_fingerprint_sha256", "model_version", "occurred_at_utc", "previous_hash",
        "request_id", "schema_version", "score", "status", "threshold",
    }
