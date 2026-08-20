# Scientific validity protocol

SecureSwipe separates three evidence namespaces. Mixing them is a release-blocking
error:

1. `historical_reported_test` is the already-observed random held-out result in
   the repository. Its metrics are preserved, but it is unavailable for every
   new model, calibration, feature, and threshold choice. The source dataset and
   score vector are absent, so AP/ROC cannot currently be independently rerun.
2. Operator-attested new development data uses four ordered roles: model
   training, calibration fit, operating-point selection, and a reusable forward
   development backtest. Fingerprint intersections are prohibited. Backtest
   intervals are descriptive development evidence, not a locked release claim.
3. `development_blocked` uses expanding training windows and later validation
   blocks. Equal timestamps stay together; preprocessing and the estimator are
   refit inside each fold. It measures temporal robustness on development data,
   not deployment performance.

No current artifact is called an out-of-time result because the original data
is unavailable and no new blocked run has been executed on it.

## Duplicate and leakage policy

The canonical contract is `Time`, `V1`–`V28`, `Amount`, then `Class`. Columns
must be numeric, finite, ordered, and complete; Time and Amount are non-negative.
Unknown columns and unresolved duplicate transaction feature vectors are
rejected. `curate_dataset.py` fails on identical features carrying conflicting
labels and otherwise keeps the first exact feature vector in source order while
recording raw/curated fingerprints and removed class counts. Content-derived row
hashes—not caller IDs—must be disjoint across roles. Scaling is fit on model-
training rows only.

The exact known Kaggle corpus is already test-observed. Its original historical
holdout identities were not retained, so exclusion cannot be reconstructed
honestly. The configured file and known 284,807-row/492-fraud signature are
reference-only, and project-created derivatives propagate `historical_taint`
when verified lineage remains attached. A detached derivative cannot be
identified from bytes alone. Decision-eligible curation therefore also requires
an operator-reviewed exact-checksum source approval using `SOURCE_APPROVAL.md`.
This is an auditable human trust boundary, not proof of origin.

## Uncertainty and model selection

- Fixed-threshold precision, recall, and false-positive rate use Wilson intervals.
- Model AP differences use a paired, class-stratified bootstrap. The same sampled
  rows are applied to both models, which preserves pairing under imbalance.
- Unrounded metrics drive selection. For every candidate, the paired bootstrap
  estimates best-candidate AP uncertainty. The first/simplest candidate wins only
  when both its point deficit and upper confidence bound stay within the
  predeclared margin. The default is 0.005 and every run records it.
- The random diagnostic uses exactly the chronological training and selection
  row/class budgets and excludes calibration/backtest rows. It is descriptive;
  repeated blocked comparisons remain preferable on a larger real corpus.
- With only 74 fraud cases in the historical validation partition, the recorded
  0.0004 AP difference does not establish XGBoost superiority. This observation
  does not retroactively select a replacement.

## Calibration

Class-weighted model output is a bounded `raw_score`, not an asserted fraud
probability. Calibration analysis reports Brier score, quantile reliability
bins, expected calibration error, and maximum calibration error. Platt and
isotonic calibrators are fit only on a dedicated calibration-training partition;
comparison row IDs must be unique and disjoint from the development evaluation
partition. Identity wins ties and any minimum Brier-improvement margin is
declared before selection. The historical test is never used here.

## Thresholds and cost scenarios

Threshold tables expose average precision separately from literal PR-curve area,
and include recall under precision and false-positive-rate constraints. A recall
point estimate at 0.53 is not a guarantee of at least 80% future recall.

Cost analysis accepts explicit false-positive cost, full missed-fraud cost,
review cost, and caught-fraud recovery rate. It reports every component, total
cost, review volume, and cost per input row. The example YAML contains synthetic,
unitless ratios only and must not be used as a policy recommendation. A domain
owner must supply currency, time horizon, review capacity, recovery definition,
and sensitivity bounds before a cost-selected threshold can be approved.

The executable post-training analysis accepts an exact CSV schema of
`row_fingerprint,partition,y_true,raw_score`. Fingerprints must be global,
content-derived SHA-256 values. The score CSV must be a hashed output of the
supplied training manifest. The command reloads its verified bundle, recomputes
every score from curated features, and refuses parity drift or attempts to
change calibration policy. The permitted roles are disjoint
`calibration_fit`, `operating_point_selection`, and
`forward_development_backtest`:

```bash
.venv/bin/python scripts/run_development_analysis.py \
  --scores artifacts/development/scores.csv \
  --curated-data artifacts/development/curated-v1/curated.csv \
  --curation-record artifacts/development/curated-v1/curation.json \
  --training-run-manifest artifacts/development/run-v1/run_manifest.json \
  --cost-scenarios configs/cost_scenarios.example.yaml \
  --output-dir reports/development/run-001
```

The command refuses historical/test namespaces, invented/tampered scores, and
non-empty output directories. It writes selection-partition calibration,
threshold, and cost diagnostics plus a timestamp-free manifest. The source
forward backtest remains frozen in its training artifact; this command does not
relabel repeated analysis as new evaluation evidence.

## Explainability and fairness

SHAP values describe model attribution, not causation. Their output units/link
must be checked against the fitted model before a report labels them. Global
plots must disclose cohort class/score composition and include relevant alert
cohorts rather than relying on a prevalence-blind random sample.

The current implementation supports fitted binary-logistic XGBoost only. It
requests TreeExplainer's raw output and verifies that the base value plus every
row's SHAP sum reconstructs native `output_margin=True` within a declared
tolerance. The purposeful explanation cohort is disjoint: labelled-fraud rows,
highest remaining raw-score rows, and a deterministic random remainder. Reports
state that this is not prevalence-representative and persist only aggregate
composition and cohort importance, never row vectors. The historical ranking
predates this evidence and is labelled unit/additivity/cohort-unverified because
the original model and row identities are absent.

Protected-group fairness cannot be evaluated from this dataset: the anonymized
PCA fields contain no declared protected attributes, and treating PCA axes as
proxies would be unsupported. This limitation does not establish fairness.
