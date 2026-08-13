# Three-minute demonstration script

This script works from a clean clone without the private CSV or historical model.
It demonstrates controls and synthetic behavior, not fraud-model performance.

## 0:00–0:35 — Set the evidence boundary

Say:

> SecureSwipe is a portfolio fraud-risk reference, not a bank authorization
> system. The dashboard is static, the old test result is locked and never reused,
> and no raw rows or model artifact are committed.

Show `docs/ARCHITECTURE.md`, then point to the four paths: development,
historical lock, verified ModelBundle/API, and static export.

## 0:35–1:10 — Prove the tracked evidence is intact

```bash
.venv/bin/python scripts/verify_historical_observation.py
.venv/bin/python scripts/export_web_data.py --check
```

Explain that these commands verify hashes and cross-artifact invariants; they do
not rerun or tune on the observed test.

## 1:10–1:50 — Show safe failure and a verified synthetic bundle

With no bundle configured, start the API and show live-but-unready behavior:

```bash
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
curl --fail-with-body http://127.0.0.1:8000/health/live
curl --fail-with-body http://127.0.0.1:8000/health/ready
```

Readiness should be 503. That is intentional—missing artifacts never silently
select a fallback model. Stop the process, then generate a data-free fixture:

```bash
.venv/bin/python scripts/create_synthetic_bundle.py --output /tmp/secureswipe-demo
```

Explain that the manifest couples preprocessing, model, schema, operating point,
runtime metadata, training fingerprint, and payload checksums. The synthetic
logistic regression is only a smoke fixture.

## 1:50–2:30 — Show API semantics

```bash
SECURESWIPE_ARTIFACT_ROOT=/tmp \
SECURESWIPE_BUNDLE_MANIFEST=/tmp/secureswipe-demo/manifest.json \
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl --fail-with-body http://127.0.0.1:8000/health/ready
curl --fail-with-body http://127.0.0.1:8000/v1/model-info
curl --fail-with-body http://127.0.0.1:8000/v1/predict \
  --header 'Content-Type: application/json' \
  --data @/tmp/secureswipe-demo/smoke_request.json
```

Point out `raw_score`, nullable `calibrated_probability`, threshold, decision
basis, model version, and request ID. Say that a review signal is not an approval
or decline.

## 2:30–3:00 — Close with adversarial evidence

```bash
.venv/bin/python -m pytest
cd web && npm test && npm run build && npm run test:e2e
```

Say that tests cover corrupt artifacts before deserialization, exact
evaluation/service parity, finite/bounded API contracts, redacted logs, atomic
evidence, forward/calibration/cost protocols, monitoring, and a production
Chromium WCAG/static-boundary scan.

Close with the honest blockers: original-data analysis needs the local Kaggle
CSV; container smoke/scan/SBOM needs Docker Desktop; remote CI or deployment
needs explicit push/deployment approval.
