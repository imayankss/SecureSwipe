# Operations, local service objectives, and incident response

No public backend deployment is authorized or present. This runbook covers the
local/container reference and must be extended with provider ownership,
authentication, TLS, rate limits, storage, paging, retention, and recovery tests
before any public service exists.

## Measured genuine-model local result

The current [genuine-model benchmark](../reports/operations/2026-08-25_genuine_model_api_benchmark.md)
used the selected historical-reference XGBoost bundle on one macOS/Apple M2
loopback Uvicorn worker. At concurrency 8, 500/500 requests returned a valid
bounded response with zero non-2xx responses, timeouts, transport errors, or
contract failures. Successful throughput was 169.35 requests/second; p50/p95/p99
were 44.63/80.37/308.48 ms. The high observed p99 is preserved and is not an
SLO. Peak sampled process CPU was 109.4% and RSS was 117,488 KiB. This is local
dirty-worktree evidence and must be rerun on a clean release SHA.

Core model inference uses zero LLM tokens. The path performs deterministic
preprocessing, XGBoost scoring, threshold comparison, and serialization without
an LLM/provider call.

## Prior synthetic plumbing baseline

The tracked [M2 load result](../reports/operations/local_m2_load_baseline.json)
was measured on macOS 26.5.2, Apple M2 arm64, CPython 3.12.10, using the
deterministic synthetic logistic-regression bundle—not the historical XGBoost
artifact. The loopback Uvicorn process used one worker; synchronous inference
was offloaded from the event loop and model access remained serialized.

This prior result is **synthetic serving-path plumbing evidence only**. It is not
a genuine-model benchmark and its throughput must not be used as a model or
capacity claim. No retained repository artifact matching the execution prompt's
description of a prior 100-record synthetic batch was found; any such run has
the same plumbing-only classification.

Conditions: 500 measured single-prediction requests after one warmup,
concurrency 8, five-second client timeout. Result: 500/500 successful, p50
25.98 ms, p95 29.99 ms, p99 38.72 ms, approximately 314.4 requests/second, and
a liveness probe issued during the first request wave completed in 9.82 ms. Three additional
500-request repetitions produced zero errors, p95 29.48–31.67 ms, and p99
31.63–78.79 ms. The variation is why a single best run is not a capacity claim.

## Local regression objectives

These objectives apply only to the exact synthetic loopback harness on a
comparable M2. They are derived from the measured upper repeat values with a 2x
regression allowance; they are not production or customer SLOs:

- all 500 contract-valid responses succeed;
- p95 does not exceed 63.35 ms;
- p99 does not exceed 157.58 ms;
- the concurrent liveness probe remains HTTP 200 and below 19.64 ms.

A failed local objective blocks a release candidate pending investigation; it
does not identify the cause. Container objectives remain unset because Docker
Desktop was unavailable. A deployment SLO cannot be set until representative
container/provider load, cold start, resource limits, network behavior, and
failure modes are measured.

Run only against loopback; the harness rejects external hosts:

```bash
.venv/bin/python scripts/run_local_load_test.py \
  --url http://127.0.0.1:8000 \
  --payload artifacts/synthetic-smoke/smoke_request.json \
  --output reports/local/load-result.json \
  --requests 500 --concurrency 8 --timeout-seconds 5 \
  --commit-sha "$(git rev-parse HEAD)" \
  --bundle-manifest "$SECURESWIPE_BUNDLE_MANIFEST" \
  --server-pid "$(pgrep -f 'uvicorn api.main:app')" \
  --server-start-epoch "$SERVER_START_EPOCH"
```

The four flags on the second line are optional evidence-only additions and do
not affect load generation: `--commit-sha` and `--server-start-epoch` are
operator-supplied and merely recorded, never derived by the script itself;
`--bundle-manifest` only sizes local files on disk (it does not deserialize or
trust the bundle); `--server-pid` is sampled read-only via `ps`. Omitting any
of them leaves the corresponding report field `null` with an explanatory
`*_note` rather than a fabricated value.

## Benchmark result schema and report template

`run_load_test()` returns (and `--output` writes) a JSON object with these
fields. This is documentation of the current schema, not a new measured claim
— running the harness again on different hardware produces a new, differently
labeled result; it does not update the locked
[M2 baseline](../reports/operations/local_m2_load_baseline.json) above.

| Field | Meaning |
| --- | --- |
| `endpoint` | Fixed `"/v1/predict"` — this harness exercises one endpoint. |
| `payload_mix` | Fixed `"single_fixed_payload"` — one synthetic transaction repeated, not a mix. |
| `commit_sha` | Operator-supplied VCS ref, or `null` if omitted. |
| `bundle_fingerprint` | `model_version`, `bundle_format_version`, `training_data_fingerprint` read from a live `GET /v1/model-info` call at the start of the run. |
| `bundle_size_bytes` | Sum of file sizes under the `--bundle-manifest` directory, or `null`. |
| `concurrency`, `request_count`, `timeout_seconds` | Requested run parameters. |
| `successful_count`, `error_count`, `error_rate` | Totals across all requests. |
| `error_breakdown` | `non_2xx_count`, `invalid_contract_count`, `timeout_count`, `transport_error_count` — non-2xx responses, HTTP 200 responses that violate the bounded contract, client timeouts, and other transport failures are counted separately. |
| `warm_up` | `latency_ms`/`status` of the single warm-up request, kept separate from the steady-state stats below. |
| `cold_start_seconds` | Only measured if `--server-start-epoch` was supplied; otherwise `null` with `cold_start_note` explaining why. A client-only harness cannot observe true process cold start on its own. |
| `latency_ms` | `max`/`p50`/`p95`/`p99` over all requests via `compute_latency_percentiles()` (numpy linear interpolation), plus `percentile_method`. |
| `throughput_requests_per_second` | `request_count / wall_seconds` (all attempted requests). |
| `successful_throughput_requests_per_second` | `successful_count / wall_seconds` (successful only). |
| `health_probe` | Liveness probe issued concurrently with the load wave. |
| `peak_cpu_percent`, `peak_memory_kib` | Only measured if `--server-pid` was supplied (sampled every 50ms via `ps`); otherwise `null` with explicit notes. Multi-core CPU samples may exceed 100%. |
| `environment` | CPU model/count and total memory (dependency-free: `/proc` on Linux, `sysctl` on macOS; `null` where unavailable). |
| `runtime` | Python/platform plus exact serving/model package versions. |
| `model_versions`, `wall_seconds`, `total_harness_wall_seconds` | Model versions plus the measured-request window and total harness duration. |
| `bundle_local_identity` | Recomputed manifest/model/preprocessor SHA-256 values; a supplied manifest with mismatched artifact bytes fails the run. |
| `core_model_inference_llm_tokens` | Always `0`: the core model-serving path makes no LLM call. |

To write up a new benchmark run, capture: the command line used (including
which optional flags were supplied), the full JSON output, the machine/OS
description in prose (the `environment`/`runtime` blocks alone are not always
self-explanatory), and an explicit statement that objectives derived from it
apply only to that exact harness and hardware — mirroring the caveats already
stated for the M2 baseline above. Do not extrapolate a number from one
environment onto another, and do not present `null` evidence fields as zero
or as "not applicable."

### Progressive concurrency ramp

`--ramp` runs a sequence of stages at ascending concurrency levels
(`--ramp-concurrency-levels`, default `1,2,4,8`), reusing `run_load_test()` as
the per-stage primitive, and stops at the first stage that exceeds
`--ramp-max-error-rate` (default 1%), `--ramp-max-p95-latency-ms` (default
500ms), or where the concurrent liveness probe is not HTTP 200. The output is
a list of per-stage results plus `stopped_reason` (`null` if every level
completed cleanly) and `stopped_at_concurrency`. This is exploratory: it finds
where behavior degrades on the operator's own machine, not a substitute for
the fixed-concurrency baseline above, and is never invoked automatically in
CI or tests.

## Operational signals

- Readiness non-200: no verified bundle or failed startup verification. Keep the
  instance out of traffic; liveness alone is insufficient.
- HTTP errors or latency regression: inspect bounded metrics and request-ID JSON
  logs; do not log or request transaction vectors.
- `prediction_timeout` (504): a single inference call exceeded
  `SECURESWIPE_PREDICTION_TIMEOUT_SECONDS`. The client-facing request is
  bounded, but the underlying threadpool worker keeps running in the
  background (CPython threads cannot be force-stopped). Its admission slot is
  retained until that worker actually finishes and releases the model lock. A
  sustained run of these signals a genuine latency regression, not a one-off
  blip; investigate before raising the deadline.
- `capacity_exceeded` (503): in-flight predictions reached
  `SECURESWIPE_MAX_CONCURRENT_PREDICTIONS`. This is deliberate fail-closed
  backpressure, not queueing — treat a sustained run of these as an
  under-provisioned instance, not a bug.
- `audit_unavailable` (503): scoring may have completed, but the result was not
  released because required audit evidence could not be appended safely. For a
  transient failure before any bytes are appended, restore the sink and retry
  the same request ID. If the log/anchor integrity check fails or a write may be
  partial, keep inference fail-closed, preserve both files, and repair or rotate
  the explicitly configured sink under operator control before retrying.
- Prediction integrity error: stop serving the bundle and preserve its manifest,
  payload hashes, image digest, code commit, and redacted event records.
- Drift report signal: follow `MONITORING.md`; never auto-retrain or auto-deploy.
- High/critical dependency/image finding: block the candidate unless a reviewed,
  time-bounded exception records exploitability and compensating control.

## Incident response

1. Declare the reference instance unhealthy and remove it from traffic. If it is
   local-only, stop the explicitly named container/process.
2. Preserve redacted request IDs/times, metrics, bundle manifest/checksums, image
   digest/SBOM/scan result, code SHA, and configuration names. Do not copy raw
   transactions, tokens, `.env` values, or Kaggle credentials.
3. Classify whether the event is availability, artifact integrity, schema/data,
   privacy/secret exposure, dependency, or scientific-evidence integrity.
4. Contain: revoke exposed credentials first; quarantine invalid batches;
   prevent an unverified bundle or vulnerable image from becoming ready.
5. Recover with the last reviewed immutable image and bundle. Verify manifest,
   liveness, readiness, model-info, golden synthetic prediction, and bounded
   smoke load before restoring traffic.
6. Confirm monitoring/report namespaces and historical test evidence were not
   overwritten. Record cause, impact, evidence, corrective tests, and owner.

Do not delete logs/history or rotate a model in place during investigation.

## Failure/recovery demonstration

This deterministic local demonstration uses the exact selected genuine-model
manifest, injects one audit failure before append, verifies
`503 audit_unavailable` with no decision, retries the same request ID after the
sink recovers, and verifies one bounded response and one audit event:

```bash
.venv/bin/python scripts/demo_api_failure_recovery.py
```

The command enforces a 20-second ceiling and uses a temporary audit directory.
It does not alter the selected bundle or repository evidence. Timeout and
admission-control tests use synchronization events rather than sleeping to
make the unsafe state deterministic. The service has no circuit breaker:
startup bundle verification, per-request deadlines, non-queueing admission
control, and mandatory audit append are independent fail-closed boundaries, so
there is no closed/open/half-open state machine or recovery claim.

## Model replacement and rollback

Bundles are immutable, reviewed directories mounted read-only. Start a new
container with the candidate manifest, verify it, then switch traffic outside
the application. If any gate fails, stop the candidate and restart the previous
image/bundle pair; never edit a mounted bundle.

Required pre-switch evidence:

- bundle verification and exact model-info version/fingerprint;
- golden evaluation/service parity;
- development/backtest approval that excludes the historical observed test;
- schema, calibration/score semantics, threshold, and monitoring baselines;
- image digest, SBOM, dependency/image scans, readiness/inference smoke;
- rollback image/bundle identity and an operator authorized to execute it.

Exact restricted container commands are in `CONTAINER.md`. Provider routing,
deployment, DNS, or public rollback actions require explicit owner approval.

## Audit critical-section timing diagnostic (opt-in, local only)

The P1-S4 benchmark showed that adding uvicorn workers does not raise
throughput. Aggregate throughput cannot say whether completions are *waiting*
for the single `primary` audit-chain-head row lock or doing work *while holding*
it, so the `postgres-scale` completion path carries an opt-in timing
instrument. It is inert by default: with the flag absent no aggregator is
constructed, no timing call does work, and responses, headers, and status codes
are unchanged.

Enable it only on a local, task-owned instance:

```bash
export SECURESWIPE_SCALE_TIMING_DIAGNOSTIC=1
export SECURESWIPE_SCALE_TIMING_OUTPUT_DIR=/path/to/task-owned/timing
```

The flag is honoured only for the exact value `1`. Each worker process writes
`scale-timing-<pid>.json` into the output directory, replaced atomically every
25 completions and again at process exit. Nine durations are recorded per
successful completion:

| Metric | Span |
| --- | --- |
| `idempotency_lock_wait_ms` | transaction open → idempotency row locked |
| `head_lock_wait_ms` | chain-head `FOR UPDATE` issued → row locked |
| `head_lock_hold_ms` | chain-head locked → commit returned |
| `event_build_ms` | chain-head locked → canonical event built |
| `event_insert_ms` | event built → audit event inserted |
| `idempotency_update_ms` | event inserted → completion row updated |
| `head_update_ms` | completion updated → chain head updated |
| `commit_ms` | chain head updated → commit returned |
| `total_completion_ms` | transaction open → commit returned |

Only counts, medians, p95, and p99 are published. Individual samples never
leave the process, and the recorder accepts nothing but declared duration
names carrying real numbers, so request identifiers, payloads, features,
decisions, scores, model output, headers, DSNs, credentials, SQL text, and
exception text cannot reach the output.

Reading the result: `head_lock_wait_ms` dominating means completions are queued
behind the global chain-head lock and the critical section itself is cheap;
`head_lock_hold_ms` (and its `commit_ms` component) dominating means the work
done under the lock is the cost. Only the second case makes group commit the
indicated remedy. The diagnostic measures; it authorizes no throughput claim.

Never enable this against a shared or production database, and never leave the
flag set outside a diagnostic run.

## Full request-lifecycle timing diagnostic (opt-in, local only)

The lifecycle diagnostic measures the remaining server-side path for the
single-item `postgres-scale` `POST /v2/predict` route. It is a separate,
strict opt-in from the completion critical-section recorder above and is inert
for `local-default`. Enable it only with the exact value `1`:

```bash
export SECURESWIPE_SCALE_LIFECYCLE_TIMING=1
export SECURESWIPE_SCALE_LIFECYCLE_TIMING_OUTPUT_DIR=/path/to/task-owned/lifecycle-timing
```

Any other flag value, including an unset value or whitespace around `1`, is
disabled. If the output directory is omitted, the local default is
`reports/benchmarks/p1-scale-results/lifecycle-timing/`; the parent results
directory is Git-ignored. Each API worker atomically replaces one
`scale-lifecycle-timing-<pid>.json` file every 25 classified requests and at
shutdown.

The artifact contains only count, minimum, median, p95, p99, and maximum
durations for validation/handler work before reservation, reservation pool
checkout and transaction, reservation outcome handling, model scoring,
bounded-response construction and durable serialization, completion pool
checkout, the existing completion-transaction duration, and total handler
time. Reservation outcomes are counts only: owner, completed replay, or
pending/fail-closed. The completion span is supplied by the existing
transaction checkpoint recorder rather than measured by a second overlapping
clock.

Every worker also runs one low-overhead process-level event-loop observation.
It sleeps on a monotonic clock at a fixed 100 ms interval and aggregates the
non-negative drift between the scheduled and actual wake-up. This is a
process-level observation only: it cannot be assigned to an individual
request, and unexplained request time must not be labelled event-loop
scheduling without corroborating measurements.

No per-request samples are written. The recorder cannot accept plaintext
request or idempotency identifiers, payloads, features, response bodies,
scores, decisions, model values, DSNs, SQL, exception text, secrets, or stack
traces. Metrics with unknown names, non-numeric values, booleans, negative
values, NaN, or infinity are discarded. A metric's count can be lower than the
classified-request count when that path was not executed (for example, a
completed replay does not score or complete again). Unexpected owner-path
failures discard that request's partial timing so incomplete spans are not
presented as a completed lifecycle.

These timings are diagnostic observations, not an SLO, causality proof, or
scalability claim. Pool checkout includes only the wait until a connection is
acquired; model scoring includes admission and threadpool scheduling around
the synchronous estimator call; total handler time also includes framework
work not represented by the named spans. The named spans are non-overlapping
where the implementation exposes safe boundaries, so their sum may explain
only part of total handler time.

After a local diagnostic, stop the API workers before removing the task-owned
output directory, and unset both lifecycle variables. Never enable this
recorder against shared or production infrastructure.
