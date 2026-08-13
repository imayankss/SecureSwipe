# Model card

## Current status

No verified trained fraud model is present in this checkout or deployed by this
work. The API starts live but remains unready until a locally trusted, complete
bundle is configured. The optional `synthetic-smoke-1` logistic model exists only
to test packaging and must never be described as a fraud model.

## Historical observation

The repository records an XGBoost evaluation at threshold 0.53 on a random
held-out partition: 62 true positives, 27 false positives, 12 false negatives,
and 42,621 true negatives; average precision was recorded as 0.8287849. Derived
precision, recall, and F1 are internally consistent with those counts. The
threshold and model were selected before the recorded test observation according
to Git history.

This result is quarantined as `historical_reported_test`. It is not an unbiased,
out-of-time, real-world, or production estimate. The data/model/score artifacts
and original runtime are absent, and possible duplicate cross-split leakage
cannot be measured. It must not be used for new tuning.

## Inputs and output

A deployable bundle accepts ordered raw fields `Time`, `V1`–`V28`, and `Amount`.
It contains the fitted training-only preprocessor, model, optional calibrator,
operating threshold, schema, training-data fingerprint, versions, payload types,
sizes, and checksums. The API returns:

- `raw_score`: the model's bounded class score;
- `calibrated_probability`: present only if development evidence selected and
  packaged a calibrator;
- `decision_score`, threshold, and a `review`/`pass` demonstration signal.

The signal is not an approval, decline, or payment authorization.

## Evaluation and selection policy

New evidence must use a genuinely new authorized corpus. The executable workflow
uses chronological model-training, calibration-fit, operating-point-selection,
and untouched-evaluation roles with content-hash isolation. Model comparisons
use unrounded AP, a paired stratified bootstrap, a predeclared simplicity margin,
calibration diagnostics, and a threshold selected before untouched evaluation.
Cost scenarios remain a separate explicit analysis; no example scenario is a
business policy.

## Limitations and risks

- There is no current OOT result, calibration result, business cost model,
  throughput result, drift baseline, or real artifact in this checkout.
- Class weighting changes score semantics; uncalibrated output is not labelled a
  real fraud probability.
- Fraud patterns and base rates drift. Drift is a diagnostic signal, not by
  itself proof of model failure.
- SHAP attribution is noncausal and PCA features reduce human interpretability.
  The tracked historical ranking lacks retained output-unit/additivity/cohort
  evidence and is explicitly unit-unverified. New runs must explain XGBoost raw
  margin/log-odds, pass native-output additivity, and report purposeful cohort
  label/score composition; that protocol does not retroactively validate history.
- Protected-group fairness cannot be evaluated because protected attributes are
  absent. This system must not be used to infer them.
- Human review capacity, appeal/override, recovery, and customer-harm processes
  are unspecified; no operational decision should depend on this reference.
