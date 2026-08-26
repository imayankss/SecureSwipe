# Lane A development protocol — v2 amendment

**This is a versioned protocol amendment made *after* observing the v1
development results. It is not an untouched pre-registration, and it must never
be described as one.**

The honest framing, to be reproduced wherever this work is summarised:

> Lane A development protocol v2, motivated by the observed v1 feature
> limitations and review-capacity conflict; final-test data remained untouched.

- **Written at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle`. Branch-local; not on `main`.
- **Written before any v2 metric was computed.** This document's SHA-256 is
  recorded in the private run manifest produced by the experiment, so the order
  of events is verifiable rather than asserted.
- **`final_test` remains forbidden** and is not read, opened, materialised,
  scored, counted, or evaluated by anything this amendment authorises.

## 1 — Why v2 exists, and what was already seen

Two v1 outcomes motivate it. Both were observed before this document was
written, and pretending otherwise would be the exact post-hoc selection the
original pre-registration guards against.

1. **Feature limitation.** v1 locked a deliberately conservative 13-input
   serving core and reached validation average precision ≈ `0.2136` with
   XGBoost. Eleven further columns had already been classified
   `candidate_snapshot` — decision-time available — in the accepted MT3b
   contract but were left out of the v1 lock. Whether they carry signal was
   never tested.
2. **Capacity conflict.** The single synthetic constraint of 100 reviews/day
   could not reach recall ≥ 0.80; the requirement was roughly 12× that budget.
   No operating threshold was frozen. A universal fixed capacity was the wrong
   abstraction: real merchants differ by orders of magnitude in review staffing.

v2 therefore does two bounded things: it tests a small, closed set of
already-eligible feature groups, and it replaces the universal capacity number
with a merchant-configurable policy.

**v2 is not an attempt to raise a score.** Retaining the 13-feature baseline is
an acceptable and pre-committed outcome.

## 2 — Feature variants, fixed in advance

Only columns the accepted MT3b contract already classifies `candidate_snapshot`
with no outstanding point-in-time proof requirement may be used. No other
feature may be introduced by this amendment.

| Variant | Definition | Inputs |
|---|---|---:|
| **A — base13** | the accepted v1 13-input baseline | 13 |
| **B — base_plus_r_email** | A + `R_emaildomain` | 14 |
| **C — base_plus_match_flags** | A + `M1`–`M9` | 22 |
| **D — base_plus_email_and_match** | A + `R_emaildomain` + `M1`–`M9` | 23 |
| **E — full_candidate_snapshot** | D + `DeviceInfo` | 24 |

Every count includes the derived boolean `identity_record_present`.

**Permanently forbidden in every variant:** `TransactionID`, `isFraud`,
`TransactionDT`, and every `C*`, `D*`, `V*`, `dist*`, and `id_*` column. Also
forbidden: aggregates, target encoding, history or velocity features, future
information, external joins, labels, and post-transaction outcomes.

`DeviceInfo` is treated as **categorical text only** and is never coerced to a
number; the MT3b profile recorded it as mixed-type.

If any proposed field turns out not to be contract-eligible, its entire variant
is excluded and the exclusion is documented. The contract is not reinterpreted
to make a field eligible.

## 3 — Model, fixed and not reopened

XGBoost only, at exactly the accepted v1 parameters, seed 42. **No model-family
search, no hyperparameter search, no seed search, no threshold tuning during
feature selection.** Parameters are identical across variants so the experiment
isolates feature-set value and nothing else.

All preprocessing and encoders are fitted on `training` only. Class-imbalance
handling is derived from `training` labels only. Variants train serially.
Only `validation_threshold` is scored during selection; the calibration roles
are not used for feature selection.

**Variant A is a positive control.** It must reproduce the accepted v1 metrics
within deterministic tolerance. If it cannot, the experiment stops.

## 4 — Selection metric and improvement gate

Primary metric: average precision on `validation_threshold`.

An expanded variant may replace the baseline **only if both** hold against
variant A:

1. absolute AP improvement ≥ **0.01**; and
2. the **lower bound** of the stratified paired-bootstrap 95 % confidence
   interval (2,000 resamples, seed 42, percentile method) is **> 0**.

Among eligible variants the highest validation AP wins. Tie-breaks, in order:
fewer input features → smaller artifact → alphabetic variant ID.

**If no expanded variant passes both gates, variant A is retained.** That is a
valid result, not a failure.

Every attempted variant is reported, including failures. No variant is omitted
and the experiment is not altered after a score is seen.

**Development-optimism disclosure.** `validation_threshold` has now been used
for v1 model selection, v1 threshold work, and v2 feature selection. Repeated
development against one partition inflates its apparent performance. These
figures are development estimates, not unbiased estimates of deployed
performance.

## 5 — Calibration rule

For the selected variant only, and only after selection is final:

Fit Platt on `calibration_fit` only; evaluate Platt against identity on
`calibration_eval` only. **Isotonic and any other calibrator search are not
reopened** — v1 already compared them, and re-running that comparison after
seeing new scores would be a second bite at the same decision.

Platt is accepted only if all three hold: `calibration_eval` contains ≥ **40**
positives; Brier improvement ≥ **0.005**; and the paired-bootstrap 95 % CI lower
bound for that improvement is **> 0**, where
`improvement = Brier(identity) − Brier(candidate)`.

Otherwise identity is retained. The phrase **calibrated probability** may be
used only if Platt passes; otherwise the output is a **raw model score**.

`validation_threshold` and `final_test` are never used to fit or select a
calibrator.

**Disclosure:** `calibration_eval` was already used during v1 calibration
selection, so a v2 calibration result on it is **not** an untouched independent
estimate.

## 6 — Merchant-configurable capacity policy

The universal "100 reviews/day" assumption is withdrawn as unsupported. It is
replaced by a deterministic policy parameterised by merchant configuration.

Inputs: merchant-configured daily review capacity; evaluation-period duration in
days; the score type selected in §5; deterministic tie-handling information.

Offline budget:

```
review_budget = floor(daily_capacity × evaluation_period_days)
```

Transactions are ranked by score descending and the budget is allocated to the
highest-risk transactions. Equal scores are resolved by a documented
deterministic non-label field — stable private source order — so the allocation
is reproducible. **Row identifiers and orderings are never published.**

Permitted decision vocabulary, and nothing else:
`below_review_threshold`, `human_review`, `unavailable_fail_closed`.

**Never claimed or implemented:** autonomous approval, autonomous blocking,
payment rejection, step-up authentication, chargeback decisions, or production
case management. A future architecture note may mention step-up verification as
a possible downstream *merchant* action; this implementation remains a
human-review prioritisation system.

**The frozen operating policy is the capacity-to-allocation function, not a
single universal threshold.**

## 7 — Capacity frontier

Computed on `validation_threshold` only, for five clearly illustrative tiers:
100, 250, 500, 1,000 and 2,000 reviews/day.

Per tier: review budget, alerts selected, average reviews/day, alert rate,
TP/FP/FN/TN, precision, recall, Wilson intervals for precision and recall,
capacity utilisation, the threshold boundary or minimum selected score, and
whether recall ≥ 0.80 is reached.

The minimum validation workload required to reach recall ≥ 0.80 is reported as a
**derived coverage reference only**. It is explicitly **not** adopted as a
merchant default, and no merchant default is set by this amendment.

The 100/day tier is preserved as an honest low-capacity reference even where
recall is poor.

Every tier and any cost figure carries the label:
**"Illustrative development scenario — not Razorpay economics, not a production
SLO, and not a universal merchant policy."**

## 8 — Prohibited claims

Razorpay, Indian, or live-merchant performance · production readiness or SLO ·
ROI, savings, or capacity commitments · real-world fraud-probability performance
· autonomous approve/block/decline · any comparison between Lane A and Lane B
metrics · describing Lane A as human-blind · describing any threshold as
production-optimal · claiming any capacity is correct for Razorpay or any
merchant · immutable audit, ACID, exactly-once, distributed durability · Vulcan.

## 9 — Mandatory stop conditions

Stop and report, without touching `final_test`, if: an accepted digest,
partition, role count, or control metric cannot be reproduced; a proposed
feature lacks decision-time eligibility; a prohibited field reaches a matrix or
model; preprocessing is fitted outside `training`; variant A cannot reproduce
v1; private row-level information enters a repository artifact; completing the
task would require modifying Lane B's evidence, serving contract, or metrics; or
any operation would require reading or materialising `final_test`.

Failure of an expanded variant to improve AP is **not** a stop condition.
Failure to reach 80 % recall at a given capacity is **not** a stop condition.

## 10 — Final-test status

`final_test` remains frozen, unread, and unmaterialised. Nothing in this
amendment authorises reading it. It must be evaluated exactly once, in a
separate future task, after this freeze is independently reviewed. Lane A may
not be called "programmatically held out" until that evaluation happens, and may
never be called human-blind.
