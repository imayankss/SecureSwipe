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

Regenerate the quality lock only from its directory so its provenance comments
and digest remain stable. `pip==25.3` is intentionally part of the quality input:
`pip-tools==7.5.2` is not compatible with pip 26's removed internal API.

```bash
cd requirements
../.venv/bin/pip-compile --generate-hashes --allow-unsafe --strip-extras \
  --output-file=quality.lock quality.in
cd ..
```

## Required checks

```bash
.venv/bin/python -m ruff check api src scripts tests
.venv/bin/python -m mypy --ignore-missing-imports api src/artifacts \
  src/inference/risk_scoring.py src/evaluation/statistical_metrics.py \
  src/evaluation/calibration.py src/evaluation/cost_analysis.py \
  src/evaluation/temporal_validation.py src/utils/run_manifest.py \
  scripts/run_development_analysis.py
.venv/bin/python -m pytest
.venv/bin/python scripts/export_web_data.py --check
cd web && npm test && npm run build
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
