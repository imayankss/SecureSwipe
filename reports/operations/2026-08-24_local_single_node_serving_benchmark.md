# 2026-08-24 local single-node serving benchmark (preliminary)

## Purpose and strict scope

**Classification: synthetic serving-path benchmark.** This records one bounded
localhost exercise of the existing `/v1/predict` path. It is evidence for this
specific local machine and code state only; it is not a model-quality result,
a network test, a public-production result, a Razorpay-scale claim, or a
capacity commitment. The returned `raw_score`/`decision_score` is not treated
as a probability.

The worktree was already uncommitted when the benchmark began, so this is
**preliminary evidence** and must be rerun after the final release commit.

## Source, environment, and safety boundary

| Item | Recorded value |
| --- | --- |
| Source commit | `6d38d3065e6aec2463e416b5faaef5c10f2c824d` |
| Worktree at start | Dirty: the dashboard worktree had uncommitted tracked edits and existing untracked local work; this report was added after the run. |
| OS / architecture | macOS 26.5.2, arm64 |
| CPU / memory | Apple M2, 8 physical / 8 logical cores, 8 GiB RAM |
| Python | CPython 3.12.10 (`.venv`) |
| Node / npm | Node v20.18.3 / npm 10.8.2 (recorded environment only; not used by the Python serving path) |
| Serving runtime | FastAPI 0.141.1, Uvicorn 0.52.2, HTTPX 0.28.1, Pydantic 2.13.4 |
| Model runtime | NumPy 2.5.2, pandas 3.0.5, scikit-learn 1.9.0, joblib 1.5.3 |
| Listener | One Uvicorn worker on `127.0.0.1:18000`; no external network target |
| Server limits | 65,536-byte request maximum, 16 in-flight predictions, 5.0-second prediction deadline |
| Input | Existing deterministic synthetic `TransactionFeatures` JSON (`Time`, `V1`–`V28`, `Amount`), one fixed single-prediction request per call; no real transaction or customer data |

## Bundle provenance

The checked-in `artifacts/synthetic-smoke` bundle is format 2 and correctly
failed current verification as unsupported. To avoid bypassing that control, the
existing `scripts/create_synthetic_bundle.py` was run unchanged into a temporary
directory outside the repository. The generated bundle was accepted by the API:

| Item | Recorded value |
| --- | --- |
| Evidence category | `synthetic_demo_inference` |
| Model version / bundle format | `synthetic-smoke-1` / `3` |
| Bundle provenance | deterministic synthetic-only `synthetic_api_smoke_v1`; no historical taint, no evaluation claim, not decision-eligible |
| Bundle directory SHA-256 | `c0e721ba72b02118ea5a509dfbdf060a8564a7a32d956d8aef0a635911725e1d` |
| Bundle size | 9,589 bytes |
| Live training-data fingerprint | `d92ed4fe5b3c43b5fce1dc3b0c61018f87267c79932f5ac14a9daaeab595a4ef` |

## Commands used

```bash
.venv/bin/python scripts/create_synthetic_bundle.py \
  --output /tmp/secureswipe-local-benchmark.<random>/synthetic-smoke

SECURESWIPE_ARTIFACT_ROOT=/tmp/secureswipe-local-benchmark.<random> \
SECURESWIPE_BUNDLE_MANIFEST=/tmp/secureswipe-local-benchmark.<random>/synthetic-smoke/manifest.json \
SECURESWIPE_PREDICTION_TIMEOUT_SECONDS=5.0 \
SECURESWIPE_MAX_CONCURRENT_PREDICTIONS=16 \
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 18000 --workers 1 --no-access-log

.venv/bin/python scripts/run_local_load_test.py \
  --url http://127.0.0.1:18000 \
  --payload /tmp/secureswipe-local-benchmark.<random>/synthetic-smoke/smoke_request.json \
  --output /tmp/secureswipe-local-benchmark.<random>/fixed-concurrency-8.json \
  --requests 500 --concurrency 8 --timeout-seconds 5 \
  --commit-sha 6d38d3065e6aec2463e416b5faaef5c10f2c824d \
  --bundle-manifest /tmp/secureswipe-local-benchmark.<random>/synthetic-smoke/manifest.json \
  --server-pid 37494

.venv/bin/python scripts/run_local_load_test.py \
  --url http://127.0.0.1:18000 \
  --payload /tmp/secureswipe-local-benchmark.<random>/synthetic-smoke/smoke_request.json \
  --output /tmp/secureswipe-local-benchmark.<random>/progressive-ramp.json \
  --timeout-seconds 5 --ramp \
  --ramp-concurrency-levels 1,2,4,8 --ramp-requests-per-stage 50
```

The harness performs one warm-up request before each measured stage. The fixed
run sampled the supplied server PID's RSS every 50 ms. Cold start was not
reported because a client-side timestamp after readiness checks would not be a
defensible process-start measurement.

## Measured results

Percentiles use the harness's `numpy_linear` method. Error counts include
non-200 or invalid-contract responses; all stages used a 5.0-second client
timeout and concurrent liveness probe.

| Run | Concurrency | Measured requests | Successful | Errors / timeouts | p50 ms | p95 ms | p99 ms | Throughput TPS | Duration s | Liveness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Fixed baseline | 8 | 500 | 500 | 0 / 0 | 33.60 | 39.75 | 70.24 | 246.10 | 2.032 | 200, 7.70 ms |
| Progressive ramp | 1 | 50 | 50 | 0 / 0 | 8.42 | 15.31 | 28.99 | 151.51 | 0.330 | 200, 1.76 ms |
| Progressive ramp | 2 | 50 | 50 | 0 / 0 | 10.94 | 13.20 | 14.21 | 241.34 | 0.207 | 200, 1.51 ms |
| Progressive ramp | 4 | 50 | 50 | 0 / 0 | 18.31 | 20.40 | 20.93 | 244.36 | 0.205 | 200, 5.07 ms |
| Progressive ramp | 8 | 50 | 50 | 0 / 0 | 33.57 | 36.44 | 37.60 | 239.81 | 0.208 | 200, 2.55 ms |

For the fixed baseline, warm-up was HTTP 200 in 29.37 ms and sampled peak RSS
was 111,648 KiB. The progressive ramp completed all requested stages; its
configured stop conditions (more than 1% errors, p95 above 500 ms, or non-200
liveness) were not reached.

## Interpretation and limitations

This demonstrates that the current synthetic-only local serving path completed
the stated bounded workload on this Apple M2 environment without observed
errors or client timeouts. It does not measure real-model quality, historical
evidence, calibrated probabilities, batch traffic, authentication, storage,
TLS, external network latency, multiple nodes, public traffic, resource limits,
or production readiness. The figures apply **only** to this tested local
environment, temporary synthetic bundle, command lines, and preliminary dirty
worktree state. Rerun the same procedure after the final release commit before
using it as release evidence.
