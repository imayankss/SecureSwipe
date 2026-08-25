# 2026-08-25 genuine-model local API benchmark

## Purpose and evidence class

**Classification: genuine demo inference, local single-node API benchmark.**
This run exercised the selected, byte-verified historical-reference XGBoost
estimator through the real FastAPI `/v1/predict` endpoint. It measures only this
local machine, process, fixed example, and source state. It is not a model-quality
result, public-network test, container result, Razorpay-scale claim, production
SLO, or capacity commitment.

The bundle remains `historical_reference_demo_inference`, historical-tainted,
not decision-eligible, and not proven to have produced the locked historical
metrics. Its raw score is not a calibrated fraud probability.

## Source and artifact identity

| Item | Recorded value |
| --- | --- |
| Run completion | `2026-08-25T10:40:58 UTC` |
| Git HEAD | `bc2fc8502f8479fbbc0b9f30a68d3eb1236df7d7` |
| Worktree | Dirty with the cumulative intended micro-task changes plus unrelated pre-existing untracked paths; this is not an exact committed release candidate. |
| Tracked serving/harness patch SHA-256 | `c64bc286a3344267942e930de1be03d780e3dd52153f23b6872b8c8615ee2103` for the binary Git diff of `api/main.py`, `api/schemas.py`, `api/service.py`, `src/artifacts/bundle.py`, `src/inference/risk_scoring.py`, and `scripts/run_local_load_test.py` against HEAD. |
| Untracked audit module SHA-256 | `8585b2fecb82aeeb28e0f18270b85cc2f0d033a42514a7300c3d5b71e3b7952b` (`api/audit.py`; imported by the server, audit sink disabled for this run). |
| Raw benchmark JSON SHA-256 | `f4c9023e8d9b86595fbebdee4becf36f26762e5311a7142daa98d7f9ca2054ff` |
| Fixed input JSON SHA-256 | `924e5043cc9cd3301ca8779a03371c0beb2ffd3a8311c20388b3fd463184b0a0` |

The exact Git SHA is recorded, but the source state includes disclosed
uncommitted changes. Therefore this evidence must be rerun after a clean release
commit; the patch/module hashes above identify this measured local state without
pretending HEAD alone describes it.

## Bundle fingerprint

| Item | Recorded value |
| --- | --- |
| Manifest | `artifacts/historical-reference-demo-v1/manifest.json` |
| Manifest SHA-256 | `e355834d916ab3951e3069fc38ce286dd3e3abe4251c8643c4d859cd781bbbf0` |
| Model version / format | `historical-reference-xgboost-20260624-demo-v1` / `3` |
| Serialized model SHA-256 | `5ce63f1a7efa5625fbaa61177e76a548fd9ccc1c3f0a1530ccff835cf8b1dc73` |
| Preprocessor SHA-256 | `07d4a9f49448b6aa09a41c5c71dbaff5172a5fb5c870154d284671f323c7862f` |
| Training-data fingerprint | `76e867c9809da64a34ee45e0895cae03b1aea233af5b901384cd6d958f5dac13` |
| Bundle directory size | 490,948 bytes |

The harness recomputed the manifest and component hashes and refused a mismatch.
The live model-info response matched the version, format, and training-data
fingerprint recorded above.

## Hardware and runtime

| Item | Recorded value |
| --- | --- |
| OS / architecture | macOS 26.5.2, arm64 |
| CPU | Apple M2, 8 logical CPUs |
| System memory | 8,589,934,592 bytes (8 GiB) |
| Python | CPython 3.12.10 |
| API packages | FastAPI 0.141.1, Uvicorn 0.52.2, Pydantic 2.13.4, HTTPX 0.28.1 |
| Model packages | XGBoost 3.3.0, scikit-learn 1.9.0, NumPy 2.5.2, pandas 3.0.5, joblib 1.5.3 |
| Server | One Uvicorn worker, `127.0.0.1:18001`, no external network |
| Server limits | 5.0-second prediction deadline, 16 admitted in-flight predictions |
| Audit sink | Disabled; this run measures the configured core API/model path without audit persistence overhead. |

## Workload and commands

- Endpoint: `POST /v1/predict`.
- Input mix: one fixed synthetic example repeated 500 times, exactly matching
  the verified manifest golden-probe features (`Time=0`, `V1`–`V28=0`,
  `Amount=1`). No customer or real transaction data was used.
- Concurrency: 8 clients, each request with a unique opaque request ID.
- One unmeasured warm-up preceded the 500-request measurement window.
- A liveness request ran concurrently with prediction load.

The server command was:

```bash
SECURESWIPE_ARTIFACT_ROOT="$PWD/artifacts" \
SECURESWIPE_BUNDLE_MANIFEST="$PWD/artifacts/historical-reference-demo-v1/manifest.json" \
SECURESWIPE_PREDICTION_TIMEOUT_SECONDS=5.0 \
SECURESWIPE_MAX_CONCURRENT_PREDICTIONS=16 \
.venv/bin/uvicorn api.main:app \
  --host 127.0.0.1 --port 18001 --workers 1 --no-access-log
```

The measured harness command was:

```bash
.venv/bin/python scripts/run_local_load_test.py \
  --url http://127.0.0.1:18001 \
  --payload reports/operations/2026-08-25_genuine_model_benchmark_input.json \
  --output reports/operations/2026-08-25_genuine_model_api_benchmark.json \
  --requests 500 --concurrency 8 --timeout-seconds 5 \
  --commit-sha bc2fc8502f8479fbbc0b9f30a68d3eb1236df7d7 \
  --bundle-manifest artifacts/historical-reference-demo-v1/manifest.json \
  --server-pid '<spawned-server-pid>' \
  --server-start-epoch '<captured-immediately-before-spawn>'
```

## Measured result

Percentiles use NumPy linear interpolation. Throughput uses only the measured
500-request window; readiness, model-info, and warm-up time are excluded.

| Metric | Measured value |
| --- | ---: |
| Total / successful / errors | 500 / 500 / 0 |
| Successful requests per second | 169.3493 |
| Measurement window | 2.9525 s |
| p50 / p95 / p99 latency | 44.6333 / 80.3703 / 308.4804 ms |
| Maximum latency | 317.4931 ms |
| Timeouts / non-2xx / invalid contracts / transport errors | 0 / 0 / 0 / 0 |
| Concurrent liveness | HTTP 200 in 10.5706 ms |
| Warm-up | HTTP 200 in 39.6760 ms |
| Launch-to-warm-up completion | 5.8494 s |
| Peak process CPU sample | 109.4% (`ps`; multi-core values can exceed 100%) |
| Peak process RSS | 117,488 KiB (120,307,712 bytes) |

Core model inference uses **zero LLM tokens**. The request path is deterministic
schema validation, preprocessing, XGBoost scoring, threshold comparison, and
response serialization; it makes no LLM/provider call. Tokens used to author or
inspect repository evidence are outside the inference path and are not included
in this statement.

## Prior synthetic evidence

The prior dated local report is explicitly **synthetic serving-path plumbing
evidence only**. Its logistic-regression throughput values are not genuine-model
measurements and are not combined with or substituted for this run. The
execution prompt also references a prior 100-record synthetic batch; no retained
repository artifact matching that exact description was found. Any such run is
likewise classified as plumbing evidence only and carries no capacity or model
performance claim.

## Limitations and interpretation

This single run observed a long p99 tail (308.48 ms) despite zero errors; it must
not be replaced by the median or extrapolated into a latency SLO. The 5.8494-second
cold-start field is an end-to-end upper-bound from an operator-captured epoch
immediately before process spawn to completion of the harness warm-up. It
includes readiness polling and client/harness startup overhead and is not
server-internal initialization telemetry.

The result uses one fixed input, one local process, a serialized estimator lock,
loopback networking, no audit persistence, no TLS/authentication, no container,
no resource limits, and no competing representative workload. Process CPU/RSS
were sampled every 50 ms and may miss shorter peaks. This run does not establish
1,000 or 10,000 requests/second, autoscaling behavior, multi-node capacity,
availability, production readiness, fraud-detection quality, or customer impact.
