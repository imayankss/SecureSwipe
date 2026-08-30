# Model card

This card distinguishes the sealed Lane A evaluation object from models that can
be loaded by the local reference API. They are not interchangeable.

## Model and evidence objects

| Object | Current evidence | Serving status |
| --- | --- | --- |
| Lane A variant E | Frozen 24-input XGBoost pipeline with Platt calibration; one sealed aggregate IEEE-CIS evaluation | Exact serving chain is unavailable or cryptographically unproven; not served by `/demo` |
| Historical/reference bundle | Locally ignored bundle when available; 30-field API schema, raw-score semantics, historical taint, no historical-metric claim | Eligible only for bounded local reference inference after complete bundle verification |
| `synthetic-smoke-1` | Deterministically generated logistic-regression fixture | Packaging, readiness, audit, replay, and validation checks only; not a fraud model |

Lane A is the sole headline evaluation. Its metrics and protocol are canonical in
[LANE_A_FINAL_EVALUATION.md](evidence/LANE_A_FINAL_EVALUATION.md). P0.4 found no
complete cryptographic binding from all required serving artifacts to that
sealed result, so SecureSwipe does not reconstruct or substitute a bundle.

## Intended use

SecureSwipe is a defense-only research and portfolio reference for ranking
transactions into a human-review workflow and inspecting review-capacity
trade-offs.

Appropriate uses are:

- reviewing the sealed aggregate Lane A evidence;
- exploring illustrative review workload and cost assumptions;
- testing verified local bundle loading and bounded API semantics with synthetic
  or separately authorized local inputs; and
- studying fail-closed, provenance, audit, and monitoring controls.

It is not intended for payment authorization, autonomous blocking, real customer
transactions, or an unreviewed public service.

## Inputs and outputs

The Lane A evaluated pipeline uses its frozen 24-input schema recorded in the
sealed provenance. That schema and model are not exposed through the local API.

The current API contract accepts ordered semantic fields `Time`, `V1`–`V28`, and
`Amount`. The bundle owns the canonical order; JSON object order does not control
feature order.

The API returns:

- `raw_score`, a bounded model score;
- nullable `calibrated_probability`, populated only for a bundle with verified
  calibration provenance;
- `decision_score` and the bundle's operating threshold;
- `human_review` or `below_review_threshold`;
- model, bundle, schema, request, and evidence provenance; and
- an audit receipt when a configured audit append commits successfully.

The historical/reference bundle's raw score is not labelled a real-world fraud
probability. Neither bounded decision is an approval or decline.

## Evaluation and selection policy

New model decisions require a genuinely new authorized corpus. The executable
development workflow separates model training, calibration fitting,
operating-point selection, and reusable forward analysis with content-hash
isolation.

Lane A's final role was programmatically held out through development and
evaluated exactly once. Its result is closed and cannot be used for further
selection. Lane B's older random holdout is historical reference only.

Review-capacity tiers rank sealed scores deterministically under a fixed budget.
They are illustrative analyses, not universal thresholds, staffing defaults, or
merchant recommendations.

## Bundle provenance and loading

A loadable bundle binds its preprocessor, estimator, optional calibrator,
ordered schema, score semantics, operating point, intended use, training-data
fingerprint, runtime metadata, payload types, sizes, and checksums.

The service accepts neither model uploads nor request-supplied artifact paths.
An operator selects a local manifest under a configured trusted root; verification
occurs before joblib deserialization. Missing artifacts leave the API
live-but-unready, while a configured invalid bundle prevents startup.

Checksum verification does not make arbitrary pickle/joblib safe. Only locally
produced and reviewed bundles are eligible.

## Evidence boundary

The local `/demo` route may demonstrate genuine execution for its configured
reference bundle, including audit receipt and idempotent replay. It is explicitly
separate from Lane A and may not inherit Lane A metrics.

Use [EVIDENCE_GUIDE.md](EVIDENCE_GUIDE.md) for category navigation,
[API.md](API.md) for the response contract, and
[LIMITATIONS.md](LIMITATIONS.md) for scientific, fairness, serving, security,
and deployment constraints.
