# Scientific validity protocol

SecureSwipe separates three evidence namespaces. Mixing them is a release-blocking
error:

1. `historical_reported_test` is the already-observed random held-out result in
   the repository. Its metrics are preserved, but it is unavailable for every
   new model, calibration, feature, and threshold choice. The source dataset and
   score vector are absent, so AP/ROC cannot currently be independently rerun.
2. `development_validation` is used for fitting and choosing models,
   calibrators, thresholds, and cost assumptions. Decisions here are provisional.
3. `development_blocked` uses expanding training windows and later validation
   blocks. Equal timestamps stay together; preprocessing and the estimator are
   refit inside each fold. It measures temporal robustness on development data,
   not deployment performance.

No current artifact is called an out-of-time result because the original data
is unavailable and no new blocked run has been executed on it.

## Duplicate and leakage policy

The canonical contract is `Time`, `V1`–`V28`, `Amount`, then `Class`. Columns
must be numeric, finite, ordered, and complete; Time and Amount are non-negative.
Unknown columns and duplicate transaction feature vectors are rejected, including
identical features carrying conflicting labels. Feature-only row hashes must be
disjoint across splits. Scaling is fit on training rows only.

## Uncertainty and model selection

- Fixed-threshold precision, recall, and false-positive rate use Wilson intervals.
- Model AP differences use a paired, class-stratified bootstrap. The same sampled
  rows are applied to both models, which preserves pairing under imbalance.
- Unrounded metrics drive selection. The simpler model wins when its AP is no
  more than a predeclared margin below the complex model. The example default in
  code is 0.005, but a real run must record the chosen margin before comparison.
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

The executable development analysis accepts an exact CSV schema of
`row_id,partition,y_true,raw_score`. Row IDs must be globally unique and the
only permitted partitions are `calibration_train` and `development_validation`:

```bash
.venv/bin/python scripts/run_development_analysis.py \
  --scores artifacts/development/scores.csv \
  --cost-scenarios configs/cost_scenarios.example.yaml \
  --output-dir reports/development/run-001 \
  --minimum-brier-improvement 0.001
```

The command refuses historical/test namespaces and non-empty output directories.
It writes calibration, threshold, Wilson-interval, and multi-scenario cost
artifacts plus a timestamp-free manifest containing input/output hashes, code
state, parameters, seeds, and exact runtime versions.

## Explainability and fairness

SHAP values describe model attribution, not causation. Their output units/link
must be checked against the fitted model before a report labels them. Global
plots must disclose cohort class/score composition and include relevant alert
cohorts rather than relying on a prevalence-blind random sample.

Protected-group fairness cannot be evaluated from this dataset: the anonymized
PCA fields contain no declared protected attributes, and treating PCA axes as
proxies would be unsupported. This limitation does not establish fairness.
