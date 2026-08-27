# Lane A final evaluation

**IEEE-CIS Lane A final evaluation.** This record contains aggregates, counts,
intervals and digests only. It contains no row, identifier, amount, domain,
device string, label, score, prediction, private path or private filename.

The `final_test` role was **programmatically held out** for the whole of Lane A
development and was **evaluated exactly once**, under a protocol predeclared
before any final-test row was read. There is no second run, and no result below
may be used to tune, refit, reselect or re-report anything.

## 1 — Provenance

| Item | Value |
| --- | --- |
| Freeze commit | `154f69b54a286f428a5b2db9aed2a9ec7a83d4dd` |
| Final-evaluation protocol | `55ce3f192322391a39e4a14764d69aac38cf8aa2a4773bf55457d91356a17238` |
| Boundary amendment 1 | `0c07c274d1196f2df4702b649fb6523c688d273d04ccc69210895c8f96f3ef4a` |
| Guarded runner | `f2f0436c1093ae320c6fd78ef9e576d7e3b581f74f56bfca1f4a053dcf94bc09` |
| Selected schema (24 inputs) | `66cfbea1db1fc2c78512de5c15345acbedcdc737b10c4d1bf2ff0b5a0f82ca8d` |
| Preprocessing | `0b7168d4a557a4df45a48a4ff886679a6aa3127b0839d255d67c79df2160d3e3` |
| XGBoost configuration | `8fbd438bd15dbec97357798efbe5fb97cb709e457c96419cba520347a8072343` |
| Frozen pipeline | `b6a1429c234bb24a991b685dec9539ce3c5839bff9348947539d68a5ab0d42a0` |
| Frozen Platt calibrator | `5055ca05fab5b490dbb77999774196050ce8b00d9c91166164740b566fadd655` |
| Calibration decision | `876db378c94d006f8d6381f9f5b9efca20cfc837bedfec92c969f802055239cf` |
| Capacity policy | `6726d4262b84174bc1ed26aafbebbc84c8d512e568880f4f18adc460f45573c3` |
| Role-assignment digest | `f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4` |
| Score seal (written before labels) | `117d188a7900ed2a3bd8e631d05b7afb105f4284cce266d388a38a541b1de215` |
| Sealed private result manifest | `65fd02bb26f7e2cec909840f41855fc4af7589028e7a59fda7b5d41cd401d20c` |
| Evaluation started (UTC) | `2026-08-27T07:06:40Z` |
| Evaluation completed (UTC) | `2026-08-27T07:08:02Z` |
| Selected variant | `E` |

Scores were computed and hashed into an immutable seal **before any label was
loaded**; the label loader takes that seal as a precondition. Byte-level
verification of the source and role-assignment files occurred only after the
one-time lifecycle atomically entered `STARTED`.

## 2 — Dataset composition

| Quantity | Value |
| --- | --- |
| Rows | 88,581 |
| Positives | 3,083 |
| Negatives | 85,498 |
| Prevalence | 0.034804 |
| Evaluation-period duration (days) | 30.7784 |

## 3 — Aggregate metrics

Uncertainty is a stratified bootstrap with 2,000 resamples, seed 42, 95 %
percentile intervals, resampled independently within each class so the original
class counts are preserved.

| Metric | Point | 95 % CI |
| --- | --- | --- |
| Average precision | 0.208660 | [0.195700, 0.222711] |
| ROC-AUC | 0.814975 | [0.806402, 0.822899] |
| Brier score | 0.030468 | [0.030220, 0.030732] |
| Log loss | 0.124252 | [0.122785, 0.125815] |
| Expected calibration error (15 bins) | 0.003556 | not predeclared |

Scores are **Platt-calibrated benchmark output**. Expected calibration error is
descriptive only: it did not select, reject or re-fit the frozen calibrator.

## 4 — Calibration table (15 equal-width bins)

| Bin | Range | Count | Mean predicted | Observed positive rate |
| --- | --- | --- | --- | --- |
| 1 | [0.0000, 0.0667] | 76,825 | 0.016509 | 0.017429 |
| 2 | [0.0667, 0.1333] | 5,780 | 0.094260 | 0.090311 |
| 3 | [0.1333, 0.2000] | 2,641 | 0.164650 | 0.130254 |
| 4 | [0.2000, 0.2667] | 1,645 | 0.231739 | 0.181763 |
| 5 | [0.2667, 0.3333] | 1,240 | 0.300129 | 0.308871 |
| 6 | [0.3333, 0.4000] | 450 | 0.351920 | 0.435556 |
| 7 | [0.4000, 0.4667] | 0 | — | — |
| 8 | [0.4667, 0.5333] | 0 | — | — |
| 9 | [0.5333, 0.6000] | 0 | — | — |
| 10 | [0.6000, 0.6667] | 0 | — | — |
| 11 | [0.6667, 0.7333] | 0 | — | — |
| 12 | [0.7333, 0.8000] | 0 | — | — |
| 13 | [0.8000, 0.8667] | 0 | — | — |
| 14 | [0.8667, 0.9333] | 0 | — | — |
| 15 | [0.9333, 1.0000] | 0 | — | — |

Bin counts sum to the full row count. No calibrated output reached bin 7 or
above: the frozen calibrator never emits a value at or above 0.40 on this
population, so the upper nine bins are empty. That is a property of the frozen
model as observed, reported as found.

## 5 — Capacity results

Five frozen tiers of **merchant-configurable illustrative review capacity**.
Review budget is `floor(daily_capacity x evaluation_period_days)`; transactions
are ranked by frozen score descending with ties resolved by ascending stable
source position. Intervals are Wilson 95 %.

| Capacity/day | Budget | Alerts | Alert rate | TP | FP | FN | TN | Precision (95 % CI) | Recall (95 % CI) | Utilisation | Min selected score | Recall >= 0.80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 3,077 | 3,077 | 0.0347 | 838 | 2,239 | 2,245 | 83,259 | 0.2723 [0.2569, 0.2883] | 0.2718 [0.2564, 0.2878] | 1.0000 | 0.209484 | no |
| 250 | 7,694 | 7,694 | 0.0869 | 1,409 | 6,285 | 1,674 | 79,213 | 0.1831 [0.1746, 0.1919] | 0.4570 [0.4395, 0.4746] | 1.0000 | 0.105895 | no |
| 500 | 15,389 | 15,389 | 0.1737 | 1,985 | 13,404 | 1,098 | 72,094 | 0.1290 [0.1238, 0.1344] | 0.6439 [0.6268, 0.6606] | 1.0000 | 0.047637 | no |
| 1,000 | 30,778 | 30,778 | 0.3475 | 2,472 | 28,306 | 611 | 57,192 | 0.0803 [0.0773, 0.0834] | 0.8018 [0.7874, 0.8155] | 1.0000 | 0.020188 | yes |
| 2,000 | 61,556 | 61,556 | 0.6949 | 2,893 | 58,663 | 190 | 26,835 | 0.0470 [0.0454, 0.0487] | 0.9384 [0.9293, 0.9463] | 1.0000 | 0.009039 | yes |

Every row reconciles exactly: `TP+FP` equals the selected review count, `TP+FN`
equals total positives, `TN+FP` equals total negatives, all four cells sum to the
row count, and no tier exceeds its frozen budget. All rates reproduce from the
counts shown.

## 6 — Recall >= 0.80 workload diagnostic

Reaching recall >= 0.80 required **30,459 reviews** over the
evaluation period (~989.62 reviews/day), achieving
recall 0.800195 at precision 0.080994.

This is a **retrospective benchmark diagnostic only**. It is not a selected
threshold, not a merchant default, not a production capacity, not a
recommendation, and not a Razorpay capacity claim.

## 7 — Limitations

- This is an **IEEE-CIS Lane A final evaluation** on a public research dataset.
- It is **not Razorpay economics**.
- It is **not live-merchant performance**.
- It is **not a production SLO**.
- It is **not directly comparable with Lane B**, which uses a different dataset,
  partitioning and serving contract. No comparison is made or implied.
- The role was **programmatically held out** by a frozen partition, not withheld
  by an independent party. This evaluation is **not** human-blind and **not**
  externally blind, and must never be described as either.
- `TransactionDT` is a relative offset in seconds. The evaluation-period duration
  derives from it; no calendar, seasonal or holiday claim may be drawn.
- Capacity tiers are illustrative and merchant-configurable. No tier is adopted
  as a default, and no operating threshold is selected by this evaluation.

## 8 — Prohibited claims

This evaluation may never be used to claim human-blind or externally blind
evaluation; Razorpay, Indian-payment, live-merchant or production fraud
performance; guaranteed savings, ROI or cost reduction; a universal or
recommended operating threshold; autonomous approve, block or reject behaviour;
or any final-test result for variants A-D, which were never evaluated on this
role.

## 9 — Status

Evaluated exactly once. The result is sealed and immutable. No retraining,
refitting, recalibration, threshold selection, feature change, capacity change or
rerun occurred, and none is permitted on the basis of these numbers.

This record was reviewed and accepted by the project owner and published
unchanged from the sealed candidate: every figure, interval, count and digest
below reconciles exactly against the sealed private result manifest
`65fd02bb26f7e2cec909840f41855fc4af7589028e7a59fda7b5d41cd401d20c`. Only the
title and this paragraph differ from the candidate text.
