# Reproducibility guide

SecureSwipe separates three kinds of evidence: the already-observed historical
random holdout, new development/forward analyses, and serving bundles. They are
not interchangeable.

## Clean environment

Use CPython 3.12.10 on CPU. Apple Silicon is supported and CUDA is not required.

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

The Darwin locks (`requirements/quality.lock` and `requirements/api.lock`)
resolve Apple Silicon CPU environments. Linux CI and the container use the
separately compiled `requirements/quality-linux.lock` and
`requirements/api-linux.lock`; those closures use `xgboost-cpu` and contain no
NVIDIA packages. `configs/config.yaml`
is parsed by strict frozen Pydantic models; unknown keys, invalid thresholds,
unsafe artifact paths, and inconsistent split settings fail closed. Active
day-by-day runners derive their data, artifact, report, and seed defaults from
that contract.

Dependency resolution uses a separate disposable environment so the resolver is
not part of ordinary test/training execution:

```bash
lock_env=$(mktemp -d /tmp/secureswipe-lock-tools.XXXXXX)
python3 -m venv "$lock_env"
"$lock_env/bin/python" -m pip install --require-hashes \
  -r requirements/lock-tools.lock
cd requirements
for target in api api-linux quality quality-linux; do
  PIP_DEFAULT_TIMEOUT=120 "$lock_env/bin/python" -m piptools compile \
    --reuse-hashes --generate-hashes --allow-unsafe --strip-extras \
    --output-file="$target.lock" "$target.in"
done
cd ..
```

Compile twice and compare all four SHA-256 digests. The current generator lock
uses pip 26.2.1 and pip-tools 7.6.1; the generator and platform closures are
reviewed. `--reuse-hashes` avoids re-downloading every platform wheel while the
resolver still validates the dependency graph.

## Checks that require no private data

```bash
.venv/bin/python -m compileall -q api src scripts tests
.venv/bin/python -m ruff check api src scripts tests
.venv/bin/python -m pytest
.venv/bin/python scripts/verify_historical_observation.py
.venv/bin/python scripts/export_web_data.py --check
.venv/bin/python -m pip_audit -r requirements/quality.lock --disable-pip \
  --progress-spinner off
.venv/bin/python -m build --no-isolation
.venv/bin/python scripts/verify_wheel_contents.py dist/*.whl
cd web
npm ci
npm test
npm run build
npx playwright install --no-shell chromium
npm run test:e2e
npm audit --audit-level=high
```

The frontend contract requires Node.js 22.13.1. The browser installation is a
local/CI test tool, not a dashboard runtime dependency.

The historical verifier checks the recorded final JSON, report, and selected
validation threshold against `reports/final/historical_observation.lock.json`.
It never loads rows or a model. `scripts/run_final_evaluation.py` is deliberately
disabled because the test result has already been observed.

## New development evidence

The known Kaggle `creditcard.csv` may be restored through the official process
at `data/raw/creditcard.csv` for reference curation/stages only. Never commit it
or `kaggle.json`. Its holdout was already observed and original row identities
were not retained, so renaming/restoring it cannot make it new evidence.

New decisions require a separately authorized corpus and the checksum-bound
operator approval described in `SOURCE_APPROVAL.md`. First run
`scripts/curate_dataset.py --source-kind new_authorized_development
--source-approval <reviewed.json>`, then run the four-role training/bundle
workflow:

```bash
.venv/bin/python scripts/run_development_training.py --help
.venv/bin/python scripts/run_development_analysis.py --help
```

The analysis command also requires the originating training `run_manifest.json`
and recomputes every declared score through its verified bundle. These commands
require a checksum-matched, decision-eligible curation record and content-derived
row fingerprints. They write deterministic run manifests containing the Git
commit/dirty digest, parameters,
seed, runtime versions, input hashes, and output hashes. It rejects names that
claim test or historical scope. The original historical AP/ROC-AUC cannot be
independently regenerated in a clean clone because the original rows, score
vector, and fitted model were intentionally not committed.

The Day 2–7 modules remain reusable implementation libraries, but their direct
CLIs refuse unmanifested execution. `scripts/run_reference_stage.py` publishes
one legacy stage into a new directory via a sibling temporary directory and an
atomic rename. Failures leave no apparently complete target; existing targets,
including empty ones, are never overwritten. These runs use explicit
`legacy_random_*_reference` scopes and are not eligible for new decisions.

## Serving artifact proof

Only bundles created locally by the project are eligible. A bundle couples the
preprocessor, estimator, optional calibrator, ordered schema, score semantics,
operating point, runtime metadata, training-data fingerprint, and checksums.
Loading is restricted to a configured trusted root and verification happens
before joblib deserialization. Never load an artifact submitted by an API user.

For a data-free smoke fixture:

```bash
.venv/bin/python scripts/create_synthetic_bundle.py --output /tmp/secureswipe-smoke
```

See `docs/CONTAINER.md` for the exact build and container smoke commands. Those
checks require a running Docker daemon; a static Dockerfile check is not
container execution evidence.

## Determinism boundary

Deterministic files omit wall-clock timestamps, use sorted strict JSON, fixed
seeds, stable row identities, and SHA-256 hashes. Hardware and threaded
estimators can still introduce floating-point variation, so any future model
training claim must record the actual platform and verify golden predictions
within its declared precision. Public metrics must come from executable report
artifacts; documentation must not invent or manually alter results.
