# Lane A one-time final-evaluation protocol

**This is a post-MT3e, pre-final-test protocol.** It is written *after* the Lane
A v2 development freeze and *before* any final-test evaluation exists. It is not
an untouched pre-registration of the whole project, and it must never be
described as one.

The honest framing, to be reproduced wherever this work is summarised:

> Lane A final-evaluation protocol, predeclared after the MT3e development
> freeze was independently reviewed and before `final_test` was ever read.

- **Written at:** `8f8e36955c1d7b0ca4ee233ac4864d5fcc6428b9`, branch
  `codex/recovered-demo-bundle`. Branch-local; not on `main`.
- **`final_test` is unread at the time of authorship.** Nothing in this
  repository has read, opened, materialised, scored, predicted, counted, or
  hashed a `final_test` row, label, or feature. This document is written before
  the guarded runner it authorises exists, and its SHA-256 is bound into that
  runner's private authorization manifest, so the order of events is verifiable
  rather than asserted.
- **This document may not be edited** once implementation or rehearsal of the
  runner begins. A change after that point invalidates the freeze.

## 1 — Why this protocol exists

The MT3e freeze deliberately shipped a positive role allowlist and **no**
final-test execution path: every Lane A code path fails closed on `final_test`.
That was correct at the time, but it means a one-time final evaluation cannot be
performed without first predeclaring exactly what will be measured and building
a runner that can be audited before it is armed.

This protocol supplies the missing predeclaration. It fixes the model, the
policy, the metric set, the uncertainty procedure, and the claim boundaries
**before** any final-test row is visible, so that no result can retroactively
influence what gets reported.

## 2 — Frozen model and policy

The evaluation is bound to the MT3e selection. Nothing may be re-derived.

| Frozen element | Binding |
| --- | --- |
| Selected variant | **E only** — the selected 24-input schema |
| Selected schema digest | `66cfbea1db1fc2c78512de5c15345acbedcdc737b10c4d1bf2ff0b5a0f82ca8d` |
| Preprocessing digest | `0b7168d4a557a4df45a48a4ff886679a6aa3127b0839d255d67c79df2160d3e3` |
| XGBoost configuration digest | `8fbd438bd15dbec97357798efbe5fb97cb709e457c96419cba520347a8072343` |
| Pipeline artifact digest | `b6a1429c234bb24a991b685dec9539ce3c5839bff9348947539d68a5ab0d42a0` |
| Platt calibrator digest | `5055ca05fab5b490dbb77999774196050ce8b00d9c91166164740b566fadd655` |
| Calibration-decision digest | `876db378c94d006f8d6381f9f5b9efca20cfc837bedfec92c969f802055239cf` |
| Capacity-policy contract digest | `6726d4262b84174bc1ed26aafbebbc84c8d512e568880f4f18adc460f45573c3` |
| Capacity-frontier digest (development) | `2da03943d3ebbf6548c1326589b74bd76e9e77783aed976e323ab040355d7575` |
| MT3e amendment digest | `f53bcb7df3a3187b840687e03b0b4d071c21a2936bd72cf46d991a5107591021` |
| Source transaction digest | `3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642` |
| Source identity digest | `b63c725d8377be90a995268d97f347c17d456b95db45807adcf9f59cd603c37c` |
| Role-assignment digest | `f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4` |

**Forbidden in the final evaluation, without exception:**

- retraining or refitting the model;
- refitting, replacing, or re-selecting the calibrator;
- changing, adding, or dropping any feature;
- model-family or hyperparameter search of any kind;
- threshold tuning or selection of a new operating threshold;
- changing, adding, or removing a capacity tier;
- changing the ranking or tie-breaking rule;
- evaluating variants **A–D** on `final_test`;
- any comparison between Lane A and Lane B;
- any subgroup or slice search not predeclared here;
- using final labels to select or alter anything whatsoever.

### 2.1 — Capacity policy

Frozen tiers, unchanged from MT3e: **100, 250, 500, 1,000 and 2,000
reviews/day**.

Review budget per tier:

```
review_budget = floor(daily_capacity × evaluation_period_days)
```

Transactions are ranked by **frozen calibrated score descending**. Equal scores
are resolved by **ascending stable private source position**, so the ordering is
deterministic and reproducible without exposing any identifier.

### 2.2 — `TransactionDT` handling

`TransactionDT` is **never a model input**. It may be read for exactly one
purpose — computing the evaluation-period duration:

```
evaluation_period_days = (max(TransactionDT) - min(TransactionDT)) / 86400
```

`TransactionDT` is a relative offset in seconds, not a calendar timestamp. No
calendar date, season, or holiday claim may be derived from it.

## 3 — Exact final metric set

**Only** the metrics below may be computed. No metric may be added after any
result is seen.

### 3.1 — Dataset-level

- final row count;
- positive count;
- negative count;
- prevalence.

### 3.2 — Aggregate discrimination and calibration

- average precision;
- ROC-AUC;
- Brier score;
- log loss;
- expected calibration error (ECE) over **exactly 15 equal-width bins on
  `[0, 1]`**;
- a calibration table reporting, per bin: **bin count, mean predicted value, and
  observed positive rate**.

**ECE is descriptive only.** It does not select, reject, replace, or re-fit the
frozen Platt calibrator. A poor ECE is an evidence result, not a trigger to
change the model.

### 3.3 — Capacity table

Per frozen tier: daily capacity, evaluation-period duration, total review
budget, selected review count, alert rate, **TP, FP, FN, TN**, precision,
recall, capacity utilisation, minimum selected score, and whether recall ≥ 0.80
is reached.

**Wilson 95 % confidence intervals** are reported for precision and recall at
every tier.

### 3.4 — Predeclared workload diagnostic

The **minimum workload required to reach recall ≥ 0.80** on `final_test` is
computed and reported. It is explicitly a **retrospective benchmark
diagnostic**, not a policy recommendation, not a selected threshold, not a
merchant default, not a production capacity, and not a Razorpay capacity claim.

### 3.5 — Uncertainty procedure

For **average precision, ROC-AUC, Brier score, and log loss**:

- **2,000 stratified bootstrap resamples**;
- **seed `42`**;
- **95 % percentile confidence intervals**;
- resampling is performed **independently within the positive and negative
  classes, preserving the original class counts** in every resample.

Wilson intervals (§3.3) are computed analytically from the confusion counts,
not by bootstrap.

### 3.6 — Reconciliation requirements

Every reported capacity row must satisfy, exactly:

- `TP + FP = selected review count`;
- `TP + FN = total positives`;
- `TN + FP = total negatives`;
- `TP + FP + FN + TN = final row count`;
- `selected review count ≤ review_budget`.

All rates and intervals must reproduce from the reported counts.

## 4 — Execution rules

1. The evaluation runs **exactly once** for a given freeze commit.
2. Scores are computed and **sealed by digest before any label is loaded**.
3. Labels are opened only after the score seal exists.
4. Row-level features, scores, predictions, labels, and lifecycle state are
   written **outside the repository**. Only aggregates are exported publicly.
5. If anything fails after final-role access begins, the run is **not** retried,
   patched, or rerun. Evidence is preserved and the lifecycle moves to a
   terminal failure state.
6. No source, configuration, dependency, model, or policy change is permitted
   once final-role access has begun.

## 5 — Claim boundaries

### 5.1 — Required terminology

All public evidence derived from this evaluation must use:

- `IEEE-CIS Lane A final evaluation`;
- `programmatically held out`;
- `evaluated exactly once`;
- `Platt-calibrated benchmark output`;
- `merchant-configurable illustrative review capacity`;
- `not Razorpay economics`;
- `not live-merchant performance`;
- `not a production SLO`;
- `not directly comparable with Lane B`.

### 5.2 — Prohibited claims

The evaluation may **never** be described as, or used to claim:

- **human-blind** or **externally blind** evaluation;
- Razorpay performance, Indian-payment performance, live-merchant performance,
  or production fraud performance;
- guaranteed savings, ROI, or cost reduction;
- a universal or recommended operating threshold;
- autonomous approve, block, or reject behaviour;
- any `final_test` result for variants **A–D**.

## 6 — Result-handling rule

Whatever the evaluation shows, it is reported exactly as observed.

A lower final average precision than development, weaker calibration, a wider
confidence interval, or failure to reach 80 % recall at any capacity tier is an
**evidence result**. It is not permission to rerun, retune, refit, reselect a
tier, change a reporting definition, search for a better subgroup, or soften the
public claim set.

## 7 — Final-test status at authorship

`final_test` remains frozen, unread, unmaterialised, unscored, and uncounted.
This document authorises a single future evaluation performed by a dedicated,
digest-bound, one-time runner. It authorises nothing else, and it does not
itself read any final-test data.

Lane A may not be called `programmatically held out` in the past tense until
that evaluation has actually happened, and may **never** be called human-blind.
