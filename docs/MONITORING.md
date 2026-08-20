# Offline monitoring and drift interpretation

SecureSwipe compares a trusted reference batch with a later current batch
offline. It emits aggregate diagnostics only; no transaction rows are copied to
the report or logs. This is a portfolio reference, not a live fraud-operations
or automatic-retraining system.

## Contract and signals

Both inputs must use the exact ordered `Time`, `V1`–`V28`, `Amount` schema, with
an optional final `Class` delayed-label column. Empty, missing, extra, reordered,
non-numeric, non-finite, negative Time/Amount, duplicate, or over-limit batches
are reported invalid and are never scored.

For valid batches the report contains:

- schema status, missingness counts, row counts, and non-reversible fingerprints;
- per-feature PSI and two-sample KS distance using deterministic reference bins;
- decision-score distribution drift from the same verified `ModelBundle` path
  used by serving;
- fixed-threshold precision, recall, average precision, confusion counts, Brier
  diagnostic, and calibration error when delayed labels contain both classes;
- explicit unavailable reasons for unlabeled or one-class windows;
- model version, threshold, score semantics, training fingerprint, runtime,
  thresholds, and report version.

PSI/KS thresholds are operational investigation triggers, not hypothesis-test
p-values. A signal does not prove model failure, changed fraud behavior, or
customer harm. Investigate schema changes, pipeline changes, selection effects,
base-rate shifts, delayed-label quality, and model behavior before acting.

## Run with local authorized data

Inputs and artifacts remain ignored local files:

```bash
.venv/bin/python scripts/run_offline_monitoring.py \
  --reference data/monitoring/reference.csv \
  --current data/monitoring/current.csv \
  --artifact-root artifacts \
  --bundle-manifest artifacts/bundles/model-1/manifest.json \
  --output reports/local/monitoring/model-1-current.json
```

The command refuses to overwrite an existing report and promotes a fully written
temporary file atomically. Re-run verification without changing bytes:

```bash
.venv/bin/python scripts/run_offline_monitoring.py \
  --reference data/monitoring/reference.csv \
  --current data/monitoring/current.csv \
  --artifact-root artifacts \
  --bundle-manifest artifacts/bundles/model-1/manifest.json \
  --output reports/local/monitoring/model-1-current.json \
  --check
```

Never put raw batches in `reports/`, commit them, or include their values in an
issue. A report fingerprint supports identity checking; it cannot recover rows.

## Synthetic demonstration

The tracked [synthetic shifted report](../reports/monitoring/synthetic_shift_report.json)
uses only generated fixture data. Reproducibility is checked with:

```bash
.venv/bin/python scripts/create_synthetic_monitoring_demo.py \
  --output reports/monitoring/synthetic_shift_report.json \
  --check
```

The demo shifts `Amount` and `V1`; both feature signals fire while score drift
does not. That outcome deliberately demonstrates why feature drift and model
failure are not synonyms.

## Triage order

1. Schema invalid: quarantine the batch from monitoring/scoring and inspect the
   producer contract. Do not coerce or impute silently.
2. Feature signal only: verify collection/population changes and compare related
   windows before model action.
3. Score signal: confirm bundle/version/threshold identity, then inspect feature
   signals and decision-rate changes.
4. Delayed-label degradation: validate label completeness and delay first, then
   compare enough blocked windows with uncertainty.
5. Calibration degradation: interpret Brier/ECE as probability calibration only
   when the bundle declares `calibrated_probability`; a raw-score diagnostic is
   not evidence that the score is a real probability.

No monitoring signal automatically changes a threshold, retrains, deploys, or
rolls back a model.
