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
  --requests 500 --concurrency 8 --timeout-seconds 5
```

## Operational signals

- Readiness non-200: no verified bundle or failed startup verification. Keep the
  instance out of traffic; liveness alone is insufficient.
- HTTP errors or latency regression: inspect bounded metrics and request-ID JSON
  logs; do not log or request transaction vectors.
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
