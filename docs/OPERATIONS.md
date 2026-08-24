# Operations, local service objectives, and incident response

No public backend deployment is authorized or present. This runbook covers the
local/container reference and must be extended with provider ownership,
authentication, TLS, rate limits, storage, paging, retention, and recovery tests
before any public service exists.

## Measured local baseline

The tracked [M2 load result](../reports/operations/local_m2_load_baseline.json)
was measured on macOS 26.5.2, Apple M2 arm64, CPython 3.12.10, using the
deterministic synthetic logistic-regression bundle—not the historical XGBoost
artifact. The loopback Uvicorn process used one worker; synchronous inference
was offloaded from the event loop and model access remained serialized.

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
| `error_breakdown` | `non_2xx_count`, `timeout_count`, `transport_error_count` — a non-2xx/invalid-contract response, a client-side timeout, and any other transport failure are counted separately. |
| `warm_up` | `latency_ms`/`status` of the single warm-up request, kept separate from the steady-state stats below. |
| `cold_start_seconds` | Only measured if `--server-start-epoch` was supplied; otherwise `null` with `cold_start_note` explaining why. A client-only harness cannot observe true process cold start on its own. |
| `latency_ms` | `max`/`p50`/`p95`/`p99` over all requests via `compute_latency_percentiles()` (numpy linear interpolation), plus `percentile_method`. |
| `throughput_requests_per_second` | `request_count / wall_seconds` (all attempted requests). |
| `successful_throughput_requests_per_second` | `successful_count / wall_seconds` (successful only). |
| `health_probe` | Liveness probe issued concurrently with the load wave. |
| `peak_memory_kib` | Only measured if `--server-pid` was supplied (sampled every 50ms via `ps -o rss=`); otherwise `null` with `peak_memory_note`. |
| `environment` | `cpu_count` (`os.cpu_count()`) and `total_memory_bytes` (dependency-free: `/proc/meminfo` on Linux, `sysctl hw.memsize` on macOS; `null` elsewhere). |
| `runtime` | `httpx`/Python/platform versions, unchanged from the original schema. |
| `model_versions`, `wall_seconds` | Unchanged from the original schema. |

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
