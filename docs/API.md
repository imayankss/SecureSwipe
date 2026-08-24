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
- `review` is a demonstration signal, not an approval/block decision.
- Named JSON fields are normalized to `Time`, `V1`–`V28`, `Amount`; object key
  order does not control model feature order.
- Default limits are 65,536 request bytes and 100 transactions per batch.
- Inference runs in the framework threadpool so synchronous model work does not
  block the event loop; estimator access remains serialized for safety.
- INFO request logs are parseable JSON with normalized method/route, status,
  latency, request ID, and model version. Downstream exception messages and
  complete feature vectors are never emitted.
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

## Configure a bundle

The paths are server-side only:

```bash
export SECURESWIPE_ARTIFACT_ROOT="$PWD/artifacts"
export SECURESWIPE_BUNDLE_MANIFEST="$PWD/artifacts/bundles/model-1/manifest.json"
export SECURESWIPE_CORS_ORIGINS="http://localhost:3000"
export SECURESWIPE_PREDICTION_TIMEOUT_SECONDS="5.0"   # optional, default shown
export SECURESWIPE_MAX_CONCURRENT_PREDICTIONS="16"     # optional, default shown
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
used for the decision, operating threshold, review/pass signal, model version,
schema version, and request ID.

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
| 413 | `request_too_large` | Body exceeded `SECURESWIPE_MAX_REQUEST_BYTES`. |
| 422 | `validation_error` | Schema/range validation failed. |
| 500 | `prediction_integrity_error` | Model output failed a sanity check. |
| 500 | `internal_error` | Unhandled server error. |
| 503 | `model_unavailable` | No verified bundle is loaded. |
| 503 | `capacity_exceeded` | In-flight predictions reached the configured admission limit. |
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
