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
```

The tracked lock resolves the complete test/training toolchain. The smaller
`requirements/api.lock` is the service runtime closure. `configs/config.yaml`
is parsed by strict frozen Pydantic models; unknown keys, invalid thresholds,
unsafe artifact paths, and inconsistent split settings fail closed. Active
day-by-day runners derive their data, artifact, report, and seed defaults from
that contract.

## Checks that require no private data

```bash
.venv/bin/python -m compileall -q api src scripts tests
.venv/bin/python -m ruff check api src scripts tests
.venv/bin/python -m pytest
.venv/bin/python scripts/verify_historical_observation.py
.venv/bin/python scripts/export_web_data.py --check
cd web
npm ci
npm test
npm run build
npm audit --audit-level=high
```

The historical verifier checks the recorded final JSON, report, and selected
validation threshold against `reports/final/historical_observation.lock.json`.
It never loads rows or a model. `scripts/run_final_evaluation.py` is deliberately
disabled because the test result has already been observed.

## New development evidence

Obtain Kaggle's Credit Card Fraud Detection `creditcard.csv` through Kaggle's
official process and place it at `data/raw/creditcard.csv`. Never commit the CSV
or `kaggle.json`. Validate the canonical schema and duplicate policy before any
split. New decisions must use development/forward scopes:

```bash
.venv/bin/python scripts/run_development_analysis.py --help
```

The command requires explicit, disjoint development inputs and writes a
deterministic run manifest containing the Git commit/dirty digest, parameters,
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
