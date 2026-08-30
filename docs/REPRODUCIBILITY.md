# Reproducibility

This is the canonical guide to local environments, deterministic checks,
artifact boundaries, and expected behavior. It does not claim that the sealed
Lane A evaluation can be rerun from a clean clone: its private rows, score seal,
and exact serving chain are not committed.

Use [EVIDENCE_GUIDE.md](EVIDENCE_GUIDE.md) to decide which category a command
can support and [CONTRIBUTING.md](../CONTRIBUTING.md) for the maintained quality
gate.

## Prerequisites

| Tool | Required version/source |
| --- | --- |
| Python | CPython 3.12.10 |
| Python dependencies | `requirements/quality.lock` for local quality work |
| Node.js | 22.13.1, enforced by `web/package.json` |
| Frontend dependencies | `web/package-lock.json` with `npm ci` |
| Browser tests | Repository Playwright dependency and Chromium test browser |

Use isolated environments. Do not install project packages globally, commit
environment files, or place data/model artifacts inside tracked paths.

The Darwin Python locks target Apple Silicon CPU environments. Linux CI and the
container use their separate `*-linux.lock` closures and `xgboost-cpu`.

## Clean setup

```bash
git clone https://github.com/imayankss/SecureSwipe.git
cd SecureSwipe

python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/quality.lock
.venv/bin/python -m pip check

cd web
nvm install 22.13.1
nvm use 22.13.1
test "$(node --version)" = "v22.13.1"
npm ci
npx playwright install --no-shell chromium
cd ..
```

Dependency-lock regeneration is a maintainer workflow, not part of ordinary
verification. Its disposable-environment procedure is documented in
[CONTRIBUTING.md](../CONTRIBUTING.md#local-setup).

## Data-free deterministic checks

These checks require no raw dataset or trained fraud bundle:

```bash
.venv/bin/python -m compileall -q api src scripts tests
.venv/bin/python -m ruff check api src scripts tests
.venv/bin/python -m mypy --ignore-missing-imports api src/artifacts \
  src/inference/risk_scoring.py src/evaluation/statistical_metrics.py \
  src/evaluation/calibration.py src/evaluation/cost_analysis.py \
  src/evaluation/temporal_validation.py src/evaluation/historical_lock.py \
  src/utils/config.py src/utils/run_manifest.py \
  scripts/run_development_analysis.py scripts/verify_historical_observation.py
.venv/bin/python -m pytest
.venv/bin/python -m mypy --no-incremental --ignore-missing-imports \
  --follow-imports=skip scripts/run_reference_stage.py
.venv/bin/python scripts/export_web_data.py --check
.venv/bin/python scripts/verify_historical_observation.py
.venv/bin/python -m pip_audit -r requirements/quality.lock --disable-pip \
  --progress-spinner off
.venv/bin/python -m build --no-isolation
.venv/bin/python scripts/verify_wheel_contents.py dist/*.whl

cd web
npm test
npm run build
npm run test:e2e
npm audit --audit-level=high
```

Expected evidence boundaries:

- `verify_historical_observation.py` checks the older committed historical lock;
  it does not rerun a model.
- `export_web_data.py --check` verifies that the checked-in aggregate dashboard
  data matches its canonical inputs; it must not rewrite files.
- `pytest` includes tracked and untracked files under `tests/`. A pre-existing
  untracked work-in-progress test can therefore affect a working-directory run
  without being part of the committed suite.
- A local pass is not remote CI evidence for an unpushed commit.

## Static dashboard

The reviewer interface can run without an API:

```bash
cd web
nvm use 22.13.1
npm test
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

Open:

- `http://127.0.0.1:3000/` for the product route;
- `http://127.0.0.1:3000/evidence` for evidence navigation; and
- `http://127.0.0.1:3000/demo` for the local walkthrough.

Without `NEXT_PUBLIC_SECURESWIPE_API_URL` at build time, `/demo` must show an
explicit unavailable state and must not fabricate a model result.

## Local reference-model demonstration

This data-free procedure uses a deterministic synthetic smoke bundle. It proves
packaging, readiness, bounded API output, audit receipt, replay, and validation
mechanics. It does **not** prove fraud-model quality and does not serve the sealed
Lane A model.

Create a temporary bundle and audit location outside the repository:

```bash
demo_root=$(mktemp -d /tmp/secureswipe-reference-demo.XXXXXX)
.venv/bin/python scripts/create_synthetic_bundle.py \
  --output "$demo_root/bundle"
mkdir "$demo_root/audit"
printf 'Temporary demo root: %s\n' "$demo_root"
```

Keep that terminal open and start the API:

```bash
export SECURESWIPE_ARTIFACT_ROOT="$demo_root"
export SECURESWIPE_BUNDLE_MANIFEST="$demo_root/bundle/manifest.json"
export SECURESWIPE_AUDIT_LOG="$demo_root/audit/prediction-events.ndjson"
export SECURESWIPE_CORS_ORIGINS="http://127.0.0.1:3000"
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, build the browser application with that explicit local
origin:

```bash
cd web
nvm use 22.13.1
NEXT_PUBLIC_SECURESWIPE_API_URL=http://127.0.0.1:8000 npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000/demo` and run the walkthrough.

Expected healthy behavior:

1. the fixed sanitized fixture loads;
2. readiness and model-info succeed;
3. the API returns one bounded review outcome;
4. the API exposes a genuine committed audit-event receipt;
5. an identical fixed-ID replay returns the same body and original receipt,
   carries `X-Idempotent-Replay: true`, and creates no second audit event; and
6. deliberately malformed input returns `422 validation_error` with no decision.

Verify the audit chain:

```bash
.venv/bin/python scripts/verify_api_audit_log.py \
  "$demo_root/audit/prediction-events.ndjson"
```

Expected unavailable behavior:

- stop the API or omit its build-time origin;
- run the walkthrough again; and
- confirm that the bounded outcome and audit confirmation are unavailable.

The browser must never hard-code a successful receipt or label a replay as a
new audit event.

## Direct API smoke

With the synthetic bundle configured as above:

```bash
curl --fail-with-body http://127.0.0.1:8000/health/live
curl --fail-with-body http://127.0.0.1:8000/health/ready
curl --fail-with-body http://127.0.0.1:8000/v1/model-info
curl --fail-with-body http://127.0.0.1:8000/v1/predict \
  --header 'Content-Type: application/json' \
  --header 'X-Request-ID: synthetic-smoke-001' \
  --data @"$demo_root/bundle/smoke_request.json"
```

See [API.md](API.md) for the response contract, error vocabulary, batch route,
and redaction boundary.

## Artifact boundaries

| Artifact | Tracked? | What a clean clone can do |
| --- | --- | --- |
| Lane A aggregate evidence | Yes | Verify documents and exported values; do not rerun final evaluation |
| Historical observation lock | Yes | Verify three committed historical artifacts by SHA-256 |
| Raw datasets | No | Nothing unless separately obtained and authorized |
| Exact Lane A model chain | No proven serving chain | Do not reconstruct, substitute, or relabel a bundle |
| Historical/reference bundle | Intentionally ignored local artifact when available | Verify and run only within its disclosed provenance |
| Synthetic smoke bundle | Generated locally | Exercise packaging and API mechanics only |
| Dashboard aggregate JSON | Yes | Verify deterministically with exporter `--check` |

File presence alone is not evidence. A bundle is eligible for loading only after
trusted-root, manifest, schema, type, runtime, and payload-hash verification.

## Historical reference data

The known Kaggle `creditcard.csv` is already test-observed. Restoring or copying
it cannot make it new evidence. If obtained through the official source, keep it
under the ignored `data/raw/` path and use only the declared historical curation
workflow.

Never commit the CSV, Kaggle credentials, derived row-level artifacts, or model
payloads.

## New authorized development

New decisions require a genuinely new corpus plus the exact-checksum human
approval in [SOURCE_APPROVAL.md](SOURCE_APPROVAL.md). The curation and training
commands reject historical-tainted or unmanifested inputs:

```bash
.venv/bin/python scripts/curate_dataset.py --help
.venv/bin/python scripts/run_development_training.py --help
.venv/bin/python scripts/run_development_analysis.py --help
```

The workflow records content fingerprints, roles, parameters, seed, runtime,
Git state, input hashes, and output hashes. Development and reusable forward
analysis remain development evidence; they do not become Lane A final evidence.

## Determinism boundary

Deterministic artifacts use stable JSON, fixed seeds, sorted fields,
content-derived row identities, and SHA-256 digests while omitting wall-clock
timestamps where they would create noise. Atomic publication prevents a failed
run from looking complete.

Hardware, native libraries, and threaded estimators can still introduce
floating-point variation. Any future training or benchmark claim must record the
actual platform, runtime, concurrency, and declared numeric tolerance.

Public metrics must be read from committed aggregate artifacts. Documentation
must never repair, round into a new value, or manually override evidence.

## Container verification

Container commands, architecture scope, restricted runtime checks, scan, and
SBOM generation are canonical in [CONTAINER.md](CONTAINER.md). A Dockerfile
inspection is not container execution evidence, and local native-arm results do
not imply a released multi-architecture image.
