"""Synthetic concurrency-correctness tests for the MT4 experiment.

These establish the preconditions the MT4 protocol requires before a lock-free
serving variant may even be measured: concurrent semantic parity, idempotent
replay, audit-chain validity, admission-limit behaviour, and fail-closed
behaviour.

Everything is synthetic and in-process. No real transaction data, no held-out
role, no network.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.audit import verify_audit_log
from api.main import ApiSettings, create_app
from api.schemas import TransactionFeatures
from api.service import ModelService
from src.operations.benchmark import synthetic_corpus
from tests.synthetic_bundle import build_synthetic_serving_bundle
from src.operations.serving_variants import _NullLock, build_service

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bundle():
    """Synthetic in-process bundle.

    `artifacts/` is generated output and is git-ignored, so loading a bundle
    from it fails on a clean checkout and in CI. This uses the approved
    synthetic fixture instead; trusted-path validation is untouched.
    """
    return build_synthetic_serving_bundle()


@pytest.fixture
def corpus():
    return synthetic_corpus(64)


def _client(service, tmp_path: Path, *, limit: int = 16) -> TestClient:
    settings = ApiSettings(
        artifact_root=tmp_path,
        bundle_manifest=None,
        cors_origins=(),
        max_concurrent_predictions=limit,
        audit_log_path=tmp_path / "audit.ndjson",
    )
    return TestClient(create_app(service=service, settings=settings))


# -- the default is unchanged --------------------------------------------


def test_default_service_still_holds_a_real_lock(bundle):
    """MT4 must not change shipped behaviour."""
    import threading

    default = ModelService(bundle)
    assert isinstance(default._prediction_lock, type(threading.Lock()))
    assert not isinstance(default._prediction_lock, _NullLock)


def test_lock_free_variant_is_opt_in_only(bundle):
    assert isinstance(build_service(bundle, "baseline")._prediction_lock, type(__import__("threading").Lock()))
    assert isinstance(build_service(bundle, "lock_free")._prediction_lock, _NullLock)


def test_unknown_variant_is_refused(bundle):
    with pytest.raises(ValueError, match="Unknown serving variant"):
        build_service(bundle, "micro_batching")  # type: ignore[arg-type]


# -- concurrent semantic parity ------------------------------------------


@pytest.mark.parametrize("variant", ["baseline", "lock_free"])
@pytest.mark.parametrize("threads", [2, 8, 16])
def test_concurrent_scoring_is_bit_exact_against_serial(bundle, corpus, variant, threads):
    """A lock-free path may only be measured if parity is exact first."""
    service = build_service(bundle, variant)
    reference = [service.predict_one(TransactionFeatures(**row)) for row in corpus]

    def score(index: int):
        return index, service.predict_one(TransactionFeatures(**corpus[index]))

    with ThreadPoolExecutor(max_workers=threads) as pool:
        observed = dict(pool.map(score, range(len(corpus))))

    assert len(observed) == len(corpus)
    for index, expected in enumerate(reference):
        got = observed[index]
        assert got.decision_score == expected.decision_score
        assert got.raw_score == expected.raw_score
        assert got.decision == expected.decision


def test_both_variants_agree_with_each_other(bundle, corpus):
    baseline = build_service(bundle, "baseline")
    lock_free = build_service(bundle, "lock_free")
    for row in corpus[:16]:
        a = baseline.predict_one(TransactionFeatures(**row))
        b = lock_free.predict_one(TransactionFeatures(**row))
        assert (a.raw_score, a.decision_score, a.decision) == (
            b.raw_score, b.decision_score, b.decision)


# -- idempotency ----------------------------------------------------------


@pytest.mark.parametrize("variant", ["baseline", "lock_free"])
def test_duplicate_request_id_replays_and_appends_one_event(bundle, corpus, tmp_path, variant):
    with _client(build_service(bundle, variant), tmp_path) as client:
        headers = {"X-Request-ID": "mt4-idem-1"}
        first = client.post("/v1/predict", json=corpus[0], headers=headers)
        replay = client.post("/v1/predict", json=corpus[0], headers=headers)
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        events = [
            json.loads(line)
            for line in (tmp_path / "audit.ndjson").read_text().splitlines()
            if line
        ]
        assert sum(1 for e in events if e["request_id"] == "mt4-idem-1") == 1


@pytest.mark.parametrize("variant", ["baseline", "lock_free"])
def test_same_id_with_different_body_is_a_conflict(bundle, corpus, tmp_path, variant):
    with _client(build_service(bundle, variant), tmp_path) as client:
        headers = {"X-Request-ID": "mt4-idem-2"}
        assert client.post("/v1/predict", json=corpus[0], headers=headers).status_code == 200
        conflict = client.post("/v1/predict", json=corpus[1], headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_concurrent_duplicate_ids_still_yield_one_audit_event(bundle, corpus, tmp_path):
    """Idempotency must hold under races, not just sequentially."""
    with _client(build_service(bundle, "lock_free"), tmp_path) as client:
        headers = {"X-Request-ID": "mt4-idem-race"}

        def send(_: int):
            return client.post("/v1/predict", json=corpus[0], headers=headers)

        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(send, range(8)))
        assert all(r.status_code == 200 for r in responses)
        bodies = {json.dumps(r.json(), sort_keys=True) for r in responses}
        assert len(bodies) == 1
        events = [
            json.loads(line)
            for line in (tmp_path / "audit.ndjson").read_text().splitlines()
            if line
        ]
        assert sum(1 for e in events if e["request_id"] == "mt4-idem-race") == 1


# -- audit chain ----------------------------------------------------------


@pytest.mark.parametrize("variant", ["baseline", "lock_free"])
def test_audit_chain_verifies_after_concurrent_load(bundle, corpus, tmp_path, variant):
    with _client(build_service(bundle, variant), tmp_path) as client:
        def send(index: int):
            return client.post("/v1/predict", json=corpus[index % len(corpus)],
                               headers={"X-Request-ID": f"mt4-audit-{variant}-{index}"})

        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(send, range(48)))
        assert all(r.status_code == 200 for r in responses)

    verified = verify_audit_log(tmp_path / "audit.ndjson")
    assert verified.event_count == 48


def test_audit_chain_detects_tampering(bundle, corpus, tmp_path):
    from api.audit import AuditIntegrityError

    with _client(build_service(bundle, "baseline"), tmp_path) as client:
        for index in range(4):
            client.post("/v1/predict", json=corpus[index],
                        headers={"X-Request-ID": f"mt4-tamper-{index}"})
    log = tmp_path / "audit.ndjson"
    lines = log.read_text().splitlines()
    event = json.loads(lines[1])
    event["latency_ms"] = 999.0
    lines[1] = json.dumps(event, separators=(",", ":"), sort_keys=True)
    log.write_text("\n".join(lines) + "\n")
    with pytest.raises(AuditIntegrityError):
        verify_audit_log(log)


# -- admission control ----------------------------------------------------


def test_admission_limit_rejects_deterministically_rather_than_queueing(bundle, corpus, tmp_path):
    """Beyond the limit the service must refuse, not queue unboundedly."""
    from api.main import ConcurrencyGate, CapacityExceededError

    gate = ConcurrencyGate(limit=2)
    assert gate.try_acquire() is True
    assert gate.try_acquire() is True
    assert gate.try_acquire() is False
    assert gate.in_flight == 2
    gate.release()
    assert gate.try_acquire() is True
    with pytest.raises(ValueError):
        ConcurrencyGate(limit=0)
    assert issubclass(CapacityExceededError, Exception)


def test_gate_release_is_thread_safe(bundle):
    from api.main import ConcurrencyGate

    gate = ConcurrencyGate(limit=16)

    def cycle(_: int) -> bool:
        acquired = gate.try_acquire()
        if acquired:
            gate.release()
        return acquired

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(cycle, range(512)))
    assert gate.in_flight == 0


# -- fail-closed ----------------------------------------------------------


def test_unready_service_fails_closed_and_never_approves(tmp_path):
    with _client(ModelService(None), tmp_path) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        response = client.post("/v1/predict", json=synthetic_corpus(1)[0],
                               headers={"X-Request-ID": "mt4-unready"})
        assert response.status_code >= 500
        assert "approve" not in response.text.lower()
