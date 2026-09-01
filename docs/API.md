# SecureSwipe API

The FastAPI service is a local/container reference interface for verified model
bundles. It is not a payment authorization system and must not receive real
cardholder/customer transactions.

## Runtime contract

- Liveness is independent of model availability: `GET /health/live`.
- Readiness requires a verified bundle: `GET /health/ready` returns 503 when absent.
- A configured corrupt, incomplete, schema-mismatched, or runtime-incompatible
  bundle prevents startup.
- Requests never supply artifact bytes or paths.
- The class-weighted model output is `raw_score`; it is not labelled a
  probability. `calibrated_probability` is null unless a verified calibrator is
  packaged and selected.
- `human_review` and `below_review_threshold` are bounded demonstration signals,
  not approval/block decisions.
- Named JSON fields are normalized to `Time`, `V1`–`V28`, `Amount`; object key
  order does not control model feature order.
- Default limits are 65,536 request bytes and 100 transactions per batch.
- Inference runs in the framework threadpool so synchronous model work does not
  block the event loop; estimator access remains serialized for safety.
- INFO request logs are parseable JSON with normalized method/route, status,
  latency, request ID, and model version. Downstream exception messages and
  complete feature vectors are never emitted.
- A valid `X-Request-ID` is also the in-process idempotency key. An identical
  retry returns the original response with `X-Idempotent-Replay: true` and does
  not score or append evidence twice; reuse with different canonical input
  returns `409 idempotency_conflict`.
- When `SECURESWIPE_AUDIT_LOG` is configured, each successful prediction emits
  canonical, redacted, hash-chained NDJSON plus a local count/head anchor. This
  is **tamper-evident append-only audit evidence**, not immutable storage.
- A successful audited single prediction returns the committed event hash in
  `X-Audit-Event-Hash`. Same-process replays return `X-Idempotent-Replay: true`;
  both headers are exposed to explicitly allowed browser origins.
- If that required audit append is unavailable or fails integrity verification,
  the computed result is not released: the request returns
  `503 audit_unavailable`. A pre-append transient failure removes the unfinished
  in-process idempotency reservation, so the same request ID can be retried after
  the sink recovers. A partial write or anchor mismatch remains fail-closed and
  requires operator repair; it is never bypassed automatically.
- Each inference request has a configurable deadline (default 5.0s,
  `SECURESWIPE_PREDICTION_TIMEOUT_SECONDS`, bounded 0.1-30.0). Exceeding it
  returns `504 prediction_timeout` immediately rather than holding the
  connection open. Cancelling the client-facing wait does not force-stop the
  underlying threadpool worker (CPython threads cannot be killed); this bounds
  client-facing latency, not raw server-side compute.
- In-flight inference work is admission-controlled (default 16 concurrent
  requests, `SECURESWIPE_MAX_CONCURRENT_PREDICTIONS`, bounded 1-256). Once the
  limit is reached, further requests fail closed immediately with
  `503 capacity_exceeded` instead of queueing behind the serialized model
  lock. A timed-out request retains its admission slot until the underlying
  prediction worker actually finishes.

## State profiles

`local-default` remains the default and preserves the complete score-bearing V1
contract described below. It uses the existing in-process registry and optional
local NDJSON audit sink.

`postgres-scale` is an explicit, non-default shared-state profile. It requires
`SECURESWIPE_POSTGRES_DSN`, `SECURESWIPE_POSTGRES_SCHEMA`, and a minimum 32-byte
`SECURESWIPE_IDEMPOTENCY_HMAC_SECRET`. Pool minimum/maximum and connection
timeout default to `1`, `4`, and `2.0` seconds. Scale-only settings are rejected
under `local-default`; `SECURESWIPE_AUDIT_LOG` is rejected under
`postgres-scale`; missing, unreachable, unmigrated, or incompatible PostgreSQL
state never falls back to memory, SQLite, or NDJSON.

Migrations are operator-controlled:

```bash
SECURESWIPE_STATE_BACKEND=postgres-scale \
  SECURESWIPE_POSTGRES_MIGRATION_DSN='<separate-migration-owner-dsn>' \
  SECURESWIPE_POSTGRES_APPLICATION_ROLE='<runtime-role>' \
  .venv/bin/python scripts/manage_postgres_migrations.py --apply
SECURESWIPE_STATE_BACKEND=postgres-scale \
  .venv/bin/python scripts/manage_postgres_migrations.py --check
```

`--apply` requires the separate migration-owner DSN and non-superuser runtime
role. It rejects an owner/superuser/member role relationship that would give the
runtime role implicit mutation rights on append-only events.

API startup performs only the equivalent read-only migration check and explicit
full-chain verification. It never applies migrations. A healthy configured
profile is ready only when the model, schema history, state store, and audit
chain verify. Failure in any of those boundaries stops startup or readiness;
there is no in-memory, SQLite, or NDJSON fallback.

`POST /v2/predict` is the only prediction route enabled for `postgres-scale`.
It accepts the existing single-transaction request schema and returns the
score-free `postgres-scale-bounded-v1` response: decision plus model, schema,
intended-use, and threshold-policy provenance derived from the loaded bundle.
The durable representation contains no plaintext request ID, features, payload,
or score. The request ID remains in `X-Request-ID`; the original committed event
hash is returned in `X-Audit-Event-Hash`; exact replays also return
`X-Idempotent-Replay: true` without rescoring or appending.

Score-bearing `/v1/predict` and `/v1/predict/batch` return
`503 scale_profile_requires_v2` under this profile. `/v2/predict/batch` is not
implemented and returns `404`. Under `local-default`, all existing V1 behavior
is unchanged and `/v2/predict` returns `503 scale_profile_unavailable`.

## Configure a bundle

The paths are server-side only:

```bash
export SECURESWIPE_ARTIFACT_ROOT="$PWD/artifacts"
export SECURESWIPE_BUNDLE_MANIFEST="$PWD/artifacts/bundles/model-1/manifest.json"
export SECURESWIPE_CORS_ORIGINS="http://localhost:3000"
export SECURESWIPE_PREDICTION_TIMEOUT_SECONDS="5.0"   # optional, default shown
export SECURESWIPE_MAX_CONCURRENT_PREDICTIONS="16"     # optional, default shown
mkdir -p "$PWD/artifacts/audit"
export SECURESWIPE_AUDIT_LOG="$PWD/artifacts/audit/prediction-events.ndjson"
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

With no manifest configured, the process remains live but deliberately unready,
which allows diagnostics without pretending inference is available.

## Synthetic single prediction

This example is generated data and has no connection to a real transaction:

```bash
curl --fail-with-body http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-001' \
  --data '{
    "Time": 1000.0,
    "V1": 0.1, "V2": -0.2, "V3": 0.3, "V4": -0.4,
    "V5": 0.5, "V6": -0.6, "V7": 0.7, "V8": -0.8,
    "V9": 0.9, "V10": -1.0, "V11": 1.1, "V12": -1.2,
    "V13": 1.3, "V14": -1.4, "V15": 1.5, "V16": -1.6,
    "V17": 1.7, "V18": -1.8, "V19": 1.9, "V20": -2.0,
    "V21": 2.1, "V22": -2.2, "V23": 2.3, "V24": -2.4,
    "V25": 2.5, "V26": -2.6, "V27": 2.7, "V28": -2.8,
    "Amount": 42.0
  }'
```

The response includes `raw_score`, nullable `calibrated_probability`, the score
used for the decision, operating threshold, bounded decision, model and bundle
versions, schema version, request ID, and an explicit provenance object. The
provenance reports the evidence category, training-data fingerprint, historical
taint, and decision/evaluation claim flags from the verified bundle.

## Idempotency and audit evidence

Clients must use opaque, non-PII `X-Request-ID` values. Within one API process,
the first validated request reserves the ID; concurrent or later byte-equivalent
canonical input waits for or replays that original result. Failed attempts are
not cached. The current registry is deliberately in-process and is lost on
restart; it is not a distributed idempotency service.

The optional NDJSON sink records only a strict allowlist: request/event IDs, UTC
time, audit/API schema versions, SHA-256 idempotency and canonical-input digests,
the verified serialized model-artifact SHA-256 and version, decision score,
threshold, bounded decision, latency/status, previous hash, and event hash. It
does not record headers, PAN/CVV, secrets, feature names or values, customer
identity, or a raw request body. Batch responses append one chained event per
returned prediction.

The writer opens the evidence file in append mode, verifies the existing chain
before each append, and advances an atomically replaced local `.head.json`
count/head anchor. The verifier detects line mutation, deletion, reordering,
non-canonical JSON, duplicate event identity, and count/head mismatch:

```bash
python3 scripts/verify_api_audit_log.py \
  artifacts/audit/prediction-events.ndjson
```

The anchor is local to the same trust domain. An attacker able to rewrite both
the log and anchor can manufacture a new valid history; durable remote/WORM
anchoring, retention, access control, replication, and multi-process
idempotency are not implemented.

## Batch and errors

`POST /v1/predict/batch` accepts:

```json
{"transactions": [{"Time": 0.0, "V1": 0.0, "V2": 0.0, "V3": 0.0, "V4": 0.0, "V5": 0.0, "V6": 0.0, "V7": 0.0, "V8": 0.0, "V9": 0.0, "V10": 0.0, "V11": 0.0, "V12": 0.0, "V13": 0.0, "V14": 0.0, "V15": 0.0, "V16": 0.0, "V17": 0.0, "V18": 0.0, "V19": 0.0, "V20": 0.0, "V21": 0.0, "V22": 0.0, "V23": 0.0, "V24": 0.0, "V25": 0.0, "V26": 0.0, "V27": 0.0, "V28": 0.0, "Amount": 0.0}]}
```

Errors use a stable envelope:

```json
{
  "schema_version": "1.0",
  "request_id": "demo-001",
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": [{"type": "finite_number", "location": ["body", "V1"], "message": "Invalid value."}]
  }
}
```

| HTTP | `error.code` | Meaning |
| --- | --- | --- |
| 409 | `idempotency_conflict` | One request ID was reused for different canonical input. |
| 413 | `request_too_large` | Body exceeded `SECURESWIPE_MAX_REQUEST_BYTES`. |
| 422 | `validation_error` | Schema/range validation failed. |
| 500 | `prediction_integrity_error` | Model output failed a sanity check. |
| 500 | `internal_error` | Unhandled server error. |
| 503 | `model_unavailable` | No verified bundle is loaded. |
| 503 | `capacity_exceeded` | In-flight predictions reached the configured admission limit. |
| 503 | `audit_unavailable` | Required audit evidence could not be recorded; no inference result was released. |
| 503 | `scale_profile_requires_v2` | A score-bearing V1 route was requested under `postgres-scale`; no V1 inference occurs. |
| 503 | `scale_profile_unavailable` | The bounded V2 route was requested without the explicit `postgres-scale` profile. |
| 503 | `idempotency_in_progress` / `idempotency_stale` / `idempotency_failed` | A durable reservation cannot truthfully release a completed response. |
| 503 | `state_store_unavailable` / `state_integrity_failure` | PostgreSQL state or its stored response/audit linkage failed closed. |
| 504 | `prediction_timeout` | A single inference call exceeded the configured deadline. |
| * | `http_error` | Generic HTTP-layer error (e.g. 404 on an unknown route). |

The interactive OpenAPI description is available at `/docs`; the machine
contract is `/openapi.json`. `/metrics` uses Prometheus text exposition with
bounded method/route/status labels and fixed histogram buckets.

Container build, restricted runtime, smoke-test, scan, SBOM, and model-replacement
commands are documented in [`CONTAINER.md`](CONTAINER.md).
Offline drift interpretation is documented in [`MONITORING.md`](MONITORING.md);
measured local behavior and incident/rollback guidance are in
[`OPERATIONS.md`](OPERATIONS.md).
