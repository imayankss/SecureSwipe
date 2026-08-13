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
- Logs contain request metadata and model version, never complete feature vectors.

## Configure a bundle

The paths are server-side only:

```bash
export SECURESWIPE_ARTIFACT_ROOT="$PWD/artifacts"
export SECURESWIPE_BUNDLE_MANIFEST="$PWD/artifacts/bundles/model-1/manifest.json"
export SECURESWIPE_CORS_ORIGINS="http://localhost:3000"
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

The interactive OpenAPI description is available at `/docs`; the machine
contract is `/openapi.json`. `/metrics` uses Prometheus text exposition with
bounded route/status and fixed histogram buckets.

Container build, restricted runtime, smoke-test, scan, SBOM, and model-replacement
commands are documented in [`CONTAINER.md`](CONTAINER.md).
