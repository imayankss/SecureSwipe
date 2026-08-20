# Contributing

SecureSwipe is a portfolio reference for fraud-risk engineering, not a payment
authorization system. Changes must preserve that boundary and must not introduce
real transaction data, credentials, model artifacts, or unsupported performance,
security, compliance, or deployment claims.

## Local setup

Use Python 3.12.10 and Node 22.13.1. Create an isolated environment; never install
project packages system-wide:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/quality.lock
cd web && npm ci && cd ..
```

The Kaggle CSV and trained bundles are intentionally absent. Synthetic tests do
not require them. If original-data work is authorized, obtain `creditcard.csv`
through Kaggle's official process, place it under `data/raw/`, and never commit
the CSV or Kaggle credentials.

Regenerate dependency locks only with the isolated hash-locked tool environment;
pip-tools is not part of the ordinary quality runtime. Run from the indicated
directory so provenance comments and digests remain stable:

```bash
lock_env=$(mktemp -d /tmp/secureswipe-lock-tools.XXXXXX)
python3 -m venv "$lock_env"
"$lock_env/bin/python" -m pip install --require-hashes \
  -r requirements/lock-tools.lock
cd requirements
"$lock_env/bin/python" -m piptools compile \
  --generate-hashes --allow-unsafe --strip-extras \
  --output-file=quality.lock quality.in
cd ..
```

Run the compile twice and require identical SHA-256 output, then run pip-audit
against the result. Updates to the generator itself change `lock-tools.in` and
`lock-tools.lock` in a separate reviewed diff.

## Required checks

```bash
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
cd web && npm test && npm run build
npx playwright install --no-shell chromium && npm run test:e2e
```

Container build/smoke/scan commands are in `docs/CONTAINER.md`. Do not call a
change complete when a relevant gate was skipped; record the blocker in
`docs/industrialization/STATE.md`.

## ML evidence rules

- The historical random test result has already been observed and is unavailable
  for feature, model, calibration, or threshold choices.
- New decisions use development/forward blocked protocols and generated outputs.
- Fit preprocessing and calibration only on their declared training partitions.
- Report uncertainty and use average precision terminology accurately.
- SHAP attribution is noncausal. Protected-group fairness is unevaluable without
  protected attributes; do not claim otherwise.

Keep commits coherent and review generated diffs for stale metrics, raw data,
artifacts, secrets, and formatting noise. Pushes, releases, and deployments are
separate maintainer decisions.
