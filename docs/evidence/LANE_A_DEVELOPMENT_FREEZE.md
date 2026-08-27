# Lane A — development, selection, calibration, and freeze

**Status: `VERIFIED` / `CURRENT/MEASURED`.** Aggregate metrics, decisions and
digests only. **No rows, identifiers, email domains, device values, amounts,
scores, or row-level exports.**

- **Lane:** A (IEEE-CIS). **Lane B untouched** — code, contract, artifacts, API,
  dashboard and historical metrics all unread and unmodified.
- **Recorded at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle` (branch-local; not on `main`).
- **Seed:** 42 throughout. No RNG outside the declared seeds.
- **`final_test` was never read, materialised, scored, counted, or evaluated.**

> ## Outcome in one line
> A champion model and a calibration method are **frozen**. The threshold is
> **not frozen**: the pre-registered recall target and the declared synthetic
> review capacity are **jointly unsatisfiable** on this data, which is a
> mandatory stop condition. No rule was relaxed to manufacture a threshold.

## 1 — Preflight (Phase 0)

Every accepted digest and count re-verified before any change:

| Check | Result |
|---|---|
| `train_transaction.csv` SHA-256 | MATCH `3a5c83ab…` |
| `train_identity.csv` SHA-256 | MATCH `b63c725d…` |
| MT3a assignment digest | MATCH `f375cf71…` |
| training / validation_threshold / calibration_fit / calibration_eval / final_test | 324,797 / 70,865 / 53,148 / 53,149 / 88,581 — **all MATCH** |
| 13-field schema lock | valid |

## 2 — Feature materialisation (Phase 1)

Roles are governed by a positive allowlist. `final_test` and any unknown or
misspelled role are refused **before any file is opened**.

| Role | Rows | Expected | Identity present | Feature content digest |
|---|---:|---:|---:|---|
| `training` | 324,797 | 324,797 ✓ | 92,874 | `992cea53…` |
| `validation_threshold` | 70,865 | 70,865 ✓ | 12,724 | `ad18d451…` |
| `calibration_fit` | 53,148 | 53,148 ✓ | 10,500 | `d0aab179…` |
| `calibration_eval` | 53,149 | 53,149 ✓ | 9,467 | `70610b4d…` |
| **`final_test`** | **not materialised** | 88,581 | — | — |

501,959 materialised + 88,581 untouched = 590,540 ✓. The `training` digest
reproduces the MT3c value exactly, confirming the builder is unchanged.

Identity coverage declines across chronological roles — 28.6 %, 18.0 %, 19.8 %,
17.8 % — confirming the MT3b drift finding on additional roles.

## 3 — Models (Phase 2)

Trained on `training` only. All preprocessing and encoders fitted on `training`
only, inside one pipeline object so nothing can be fitted twice.

Preprocessing, identical for all four models: numeric columns median-imputed
**with an explicit missing indicator** so missingness survives as signal, then
standardised; categorical columns one-hot encoded with rare categories folded
into one bucket (`min_frequency=100`) and unseen categories routed there at
scoring time; the boolean passed through. The reserved missing token is simply
another category.

Training prevalence 0.033870 (11,001 positives of 324,797). Positive class
weight **28.524**, computed from training labels only.

| Model | Fixed parameters (no search of any kind) | Fit |
|---|---|---:|
| `dummy_majority` | `strategy=most_frequent` | 1.3 s |
| `logistic_regression` | `lbfgs`, `max_iter=1000`, `class_weight=balanced` | 6.4 s |
| `random_forest` | 100 trees, `max_depth=12`, `min_samples_leaf=25`, `class_weight=balanced_subsample`, `n_jobs=4` | 10.3 s |
| `xgboost` | 300 rounds, `max_depth=6`, `lr=0.1`, `subsample=0.8`, `colsample_bytree=0.8`, `hist`, `scale_pos_weight=28.524`, `n_jobs=4` | 4.5 s |

**Model failures: none.** All four trained serially within the resource bound.

## 4 — Validation-only selection (Phase 3)

`validation_threshold` only: 70,865 rows, 2,668 positives.

| Model | AP | ROC-AUC | Confusion at 0.5 (tp/fp/fn/tn) |
|---|---:|---:|---|
| `dummy_majority` | 0.0376 | 0.5000 | 0 / 0 / 2,668 / 68,197 |
| `logistic_regression` | 0.1487 | 0.7561 | 1,673 / 14,399 / 995 / 53,798 |
| `random_forest` | 0.1909 | 0.7848 | 1,505 / 10,295 / 1,163 / 57,902 |
| **`xgboost`** | **0.2136** | 0.8043 | 1,558 / 9,243 / 1,110 / 58,954 |

**Champion: `xgboost`**, by highest validation average precision.

Stratified paired bootstrap, 2,000 resamples, seed 42, 95 % percentile:

| Difference | Point | 95 % CI | Verdict |
|---|---:|---|---|
| xgboost − dummy_majority | +0.1759 | [+0.1629, +0.1897] | distinguishable |
| xgboost − logistic_regression | +0.0649 | [+0.0546, +0.0758] | distinguishable |
| xgboost − random_forest | +0.0227 | [+0.0122, +0.0327] | distinguishable |

The dummy baseline's AP equals the partition prevalence and its ROC-AUC is
0.5000 — a property of a majority-class estimator, not a competitive result.

**Validation performance is development-optimistic**: this same partition also
supports threshold selection, so its operating point is biased upward relative
to an independent selection set and is not an unbiased estimate of deployed
performance.

## 5 — Calibration (Phase 4)

Champion only. Fitted on `calibration_fit`, compared on `calibration_eval`. The
two are disjoint by construction. `validation_threshold` and `final_test` were
not used for fitting or selection.

`calibration_eval` positives: **1,811**, comfortably above the pre-registered
floor of 40, so the power floor did **not** bind and a genuine comparison ran.

| Method | Brier | ECE | improvement vs identity | 95 % CI | Margin ≥ 0.005 | CI lower > 0 | Eligible |
|---|---:|---:|---:|---|:--:|:--:|:--:|
| identity | 0.113083 | 0.231571 | — | — | — | — | baseline |
| isotonic | 0.030459 | 0.001887 | +0.082624 | [+0.081392, +0.083897] | yes | yes | yes |
| **platt** | **0.030362** | 0.003989 | +0.082721 | [+0.081499, +0.084003] | yes | yes | yes |

`improvement = Brier(identity) − Brier(candidate)`, positive when the candidate
is better.

**Decision: Platt.** Both candidates cleared the margin and the CI condition;
Platt won on the primary criterion, Brier score. Isotonic has the better ECE, but
the pre-registered order is **Brier → ECE → operational impact**, and switching
to the secondary criterion after seeing that it favours the other candidate is
exactly the post-hoc selection the pre-registration exists to prevent.

Identity's Brier of 0.113 is high because the raw XGBoost scores are inflated by
`scale_pos_weight`; calibration corrects that, which is why the improvement is
large.

**Because a non-identity calibrator won under the pre-registered rule, the
served score type for Lane A is `calibrated_probability`.** This is the one
condition under which the accepted protocol permits probability language, and it
applies to Lane A only — Lane B remains `raw_score`.

## 6 — Threshold (Phase 5) — **UNSATISFIABLE, and not relaxed**

Applied Platt calibration to `validation_threshold` scores.

- Pre-registered rule: maximise precision subject to **recall ≥ 0.80**.
- Declared **`SYNTHETIC`** review capacity: **100 reviews/day**.
- Partition span: 22.1988 days → **2,220 reviews** permitted.

**No threshold satisfies both constraints.** The best operating point that meets
the recall target requires **27,352 reviews**, or **1,232 reviews/day** — about
**12×** the declared capacity. At that point precision is 0.0786 and recall
0.8062.

Per the accepted protocol this outcome is reported as-is. The capacity
constraint was **not** relaxed, the recall target was **not** lowered, and no
threshold was frozen. This is a listed **mandatory stop condition**.

The review capacity and any cost figures are **`SYNTHETIC` illustrative
assumptions**. They are not Razorpay economics, not a real analyst capacity, and
not a savings, ROI, or production claim.

## 7 — Frozen artifact chain

| Element | Digest |
|---|---|
| Source `train_transaction.csv` | `3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642` |
| Source `train_identity.csv` | `b63c725d8377be90a995268d97f347c17d456b95db45807adcf9f59cd603c37c` |
| MT3a partition assignment | `f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4` |
| `training` features | `992cea539e6d17b0f2326d3a32986df276c2beb7fb989cb5906a8b57fd70bf80` |
| `validation_threshold` features | `ad18d451498a576cfd3d4ae9c1e6552a…` |
| `calibration_fit` features | `d0aab179ddc5fee70c089c85dd56c06d…` |
| `calibration_eval` features | `70610b4db7a48fe1319851cee3c2334a…` |
| Champion pipeline (private artifact) | `74e8e2ec817bd8629fc5f9f71107cbeb…` |

**Frozen:** the 13-field schema, the preprocessing definition, the champion
model family and its parameters, and the calibration decision.
**Not frozen:** the threshold — see §6.

**Determinism.** The full development run was executed twice. Champion,
calibration decision, threshold outcome, and every metric were identical to ten
decimal places.

## 8 — Standing constraints

- **`final_test` remains frozen and unread.** It must be evaluated exactly once,
  in a separate future task, after every remaining choice is settled.
- **Lane A is never human-blind.** It may be described as *"programmatically
  held out"* only after the final test is evaluated in that separate task —
  not now.
- **No Lane A metric may be compared with any Lane B metric.** Different
  populations, base rates, label definitions, and feature spaces.
- **Any later change** to code, data, feature contract, configuration, or any
  hash **invalidates this run** and requires a new versioned protocol and run,
  not an informal rerun.
- **Never committed or published:** IEEE-CIS raw data, rows, row-level exports,
  trained model artifacts, calibrators, scores, and Kaggle test predictions.
- **Not claimed:** Razorpay, Indian, live-merchant, production, ROI, capacity,
  savings, real-world fraud-probability performance, or a blind holdout.
