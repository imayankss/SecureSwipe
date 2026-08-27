# Lane A v2 — feature improvement and capacity-policy freeze

**Status: `VERIFIED` / `CURRENT/MEASURED`.** Aggregate metrics, decisions,
formulas and digests only. **No rows, identifiers, email domains, device
strings, amounts, labels, scores, or private paths.**

> **Framing, stated exactly as required.** Lane A development protocol v2,
> motivated by the observed v1 feature limitations and review-capacity conflict;
> final-test data remained untouched. **This is a versioned amendment made after
> observing v1 results — not an untouched pre-registration.**

- **Lane:** A (IEEE-CIS). **Lane B untouched** in code, meaning and metrics.
- **At:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle` (branch-local; not on `main`).
- **Amendment:** [`LANE_A_PROTOCOL_V2_AMENDMENT.md`](LANE_A_PROTOCOL_V2_AMENDMENT.md),
  SHA-256 `f53bcb7df3a3187b840687e03b0b4d071c21a2936bd72cf46d991a5107591021`,
  written and hashed **before** any v2 metric was computed and carried inside
  the private run manifest, so the ordering is verifiable rather than asserted.
- **Temporal evidence:** the amendment was created at `2026-08-26T22:38:36+0530`;
  the first v2 superset was created later at `22:40:59+0530`, and the first v2
  run manifest later again at `22:47:29+0530`. The final provenance-complete
  deterministic rerun finished at `23:21:47+0530` with every reported metric,
  gate, selected artifact digest, and frontier digest unchanged.
- **`final_test` was never read, opened, materialised, scored, counted, or
  evaluated.**

## 1 — Preflight

Every accepted digest re-verified before any change: both source SHA-256s, the
MT3a assignment digest, all five role counts (324,797 / 70,865 / 53,148 /
53,149 / 88,581), the MT3c training-matrix byte digest, and the 13-field schema
lock — **all MATCH**. `final_test` refusal was re-proved by execution before any
source file was opened. No private artifact exists in tracked content; Lane B
tracked files show a zero-line diff.

## 2 — Contract verification for every added feature

All eleven proposed columns are classified `candidate_snapshot` with **no**
outstanding point-in-time proof requirement in the accepted MT3b contract:
`R_emaildomain`, `M1`–`M9`, `DeviceInfo`. No field was reinterpreted, and no
field outside the accepted contract was introduced.

`DeviceInfo` is handled as **categorical text only** and is never coerced to a
number; MT3b recorded it as mixed-type.

**A precision note on the prohibition rule.** The v1 helper `is_forbidden`
encodes membership of the *locked 13-field serving core*, which is a different
question from decision-time eligibility for a candidate variant — it correctly
rejects `R_emaildomain` from the v1 core. v2 therefore uses a separate,
numeric-suffix-anchored predicate so that `dist1`/`dist2` are caught by the
`dist*` family while `DeviceInfo` and `DeviceType` are **not** swept up by the
`D*` family. Both behaviours are covered by tests.

## 3 — Variants and input counts

| Variant | Definition | Inputs | Expected |
|---|---|---:|---:|
| A — base13 | accepted v1 baseline | 13 | 13 ✓ |
| B — base_plus_r_email | A + `R_emaildomain` | 14 | 14 ✓ |
| C — base_plus_match_flags | A + `M1`–`M9` | 22 | 22 ✓ |
| D — base_plus_email_and_match | A + both | 23 | 23 ✓ |
| E — full_candidate_snapshot | D + `DeviceInfo` | 24 | 24 ✓ |

Every variant is a column subset of one 24-field superset materialised once per
role, so all variants provably see byte-identical inputs. Role row counts and
label digests reproduce the v1 values exactly.

## 4 — Controlled experiment

XGBoost only, at exactly the accepted v1 parameters, seed 42, identical
preprocessing definitions, fitted on `training` only, trained serially, scored
on `validation_threshold` only. **All five variants trained; no failures.**

**Positive control.** Variant A reproduced the v1 recorded AP `0.2135817754` to
an absolute difference of **2.65 × 10⁻¹¹**, far inside the 1 × 10⁻⁶ tolerance.

| Variant | Inputs | AP | ROC-AUC | Fit |
|---|---:|---:|---:|---:|
| A — base13 | 13 | 0.213582 | 0.8043 | 4.5 s |
| B — base_plus_r_email | 14 | 0.228857 | 0.8111 | 6.5 s |
| C — base_plus_match_flags | 22 | 0.243231 | 0.8348 | 7.2 s |
| D — base_plus_email_and_match | 23 | 0.254362 | 0.8380 | 8.5 s |
| **E — full_candidate_snapshot** | **24** | **0.275929** | **0.8410** | 10.2 s |

Serialized preprocessing/model artifact sizes were also recorded for the final
tie-break: A `1,049,768`, B `1,021,113`, C `1,071,713`, D `1,017,940`, and E
`1,053,964` bytes. The complete predeclared order is AP → fewer inputs → smaller
artifact → alphabetic variant ID. No tie occurred, so the added provenance
measurement did not affect selection.

Gates versus A — stratified paired bootstrap, 2,000 resamples, seed 42, 95 %
percentile. Both conditions required: improvement ≥ 0.01 **and** CI lower > 0.

| Variant | AP improvement | 95 % CI | Margin | CI > 0 | Eligible |
|---|---:|---|:--:|:--:|:--:|
| B | +0.015275 | [+0.009441, +0.021106] | yes | yes | **yes** |
| C | +0.029649 | [+0.021864, +0.036849] | yes | yes | **yes** |
| D | +0.040780 | [+0.031425, +0.049947] | yes | yes | **yes** |
| E | +0.062347 | [+0.051447, +0.073070] | yes | yes | **yes** |

**Selected: variant E**, highest validation AP among those clearing both gates.
The 13-feature baseline is **not** retained. AP rises from 0.2136 to 0.2759, a
+0.0623 absolute and ≈29 % relative improvement, using only columns the accepted
contract already classified decision-time available.

**Deterministic rerun:** after completing the missing provenance hashes and the
declared artifact-size tie-break implementation, the permitted development run
was repeated. All five AP values, all four bootstrap intervals, the selected
variant, calibration metrics and decision, capacity frontier, pipeline digest,
calibrator digest, and frontier digest matched the first run exactly.

**Development-optimism.** `validation_threshold` has now been used for v1 model
selection, v1 threshold work and v2 feature selection. Repeated development
against one partition inflates apparent performance. These are development
estimates, not unbiased estimates of deployed performance.

## 5 — Calibration

Variant E only. Platt fitted on `calibration_fit`, evaluated against identity on
`calibration_eval`. **Isotonic was not reopened** — v1 already compared it, and
re-running that comparison on new scores would be a second bite at the same
decision.

| Method | Brier | ECE | Improvement | 95 % CI | Margin ≥ 0.005 | CI > 0 | Accepted |
|---|---:|---:|---:|---|:--:|:--:|:--:|
| identity | 0.100475 | 0.201371 | — | — | — | — | baseline |
| **platt** | **0.029750** | 0.004406 | +0.070724 | [+0.069460, +0.072052] | yes | yes | **yes** |

`calibration_eval` holds 1,811 positives, far above the floor of 40, so the
power floor did not bind.

**Decision: Platt accepted.** Permitted terminology is therefore
**"calibrated probability"** for Lane A only. Lane B remains `raw_score`.

**Disclosure:** `calibration_eval` was already used during v1 calibration
selection, so this v2 result is **not** an untouched independent estimate.

## 6 — Merchant-configurable capacity policy

The universal "100 reviews/day" assumption is **withdrawn as unsupported**.
Merchants differ by orders of magnitude in review staffing, so no single global
number was defensible.

```
review_budget = floor(daily_capacity × evaluation_period_days)
```

Transactions are ranked by score descending; the budget is spent on the
highest-risk ones. **Ties resolve by ascending stable source position** — a
deterministic, non-label field — so allocation is reproducible. Row identifiers
and orderings are never published.

Emitted vocabulary is bounded to `below_review_threshold`, `human_review`, and
`unavailable_fail_closed`. **The system never approves, blocks, declines, steps
up, makes chargeback decisions, or manages cases.** A future architecture may
mention step-up verification as a possible downstream *merchant* action; this is
a human-review prioritisation system.

**The frozen operating policy is this capacity-to-allocation function, not a
single universal threshold.** Policy version `lane_a_capacity_policy_v2`.

## 7 — Capacity frontier

`validation_threshold` only: 70,865 transactions, 2,668 fraudulent, 22.1988 days.

| Capacity/day | Budget | Alerts | Reviews/day | Alert rate | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | Utilisation | Min selected score | Recall ≥ 0.80 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|:--:|
| 100 | 2,219 | 2,219 | 100.0 | 3.13% | 783 | 1,436 | 1,885 | 66,761 | 0.3529 [0.3332, 0.3730] | 0.2935 [0.2765, 0.3110] | 100% | 0.239590 | no |
| 250 | 5,549 | 5,549 | 250.0 | 7.83% | 1,295 | 4,254 | 1,373 | 63,943 | 0.2334 [0.2224, 0.2447] | 0.4854 [0.4665, 0.5044] | 100% | 0.126249 | no |
| 500 | 11,099 | 11,099 | 500.0 | 15.66% | 1,751 | 9,348 | 917 | 58,849 | 0.1578 [0.1511, 0.1647] | 0.6563 [0.6381, 0.6741] | 100% | 0.055855 | no |
| 1,000 | 22,198 | 22,198 | 1000.0 | 31.32% | 2,165 | 20,033 | 503 | 48,164 | 0.0975 [0.0937, 0.1015] | 0.8115 [0.7962, 0.8259] | 100% | 0.022062 | **yes** |
| 2,000 | 44,397 | 44,397 | 2000.0 | 62.65% | 2,503 | 41,894 | 165 | 26,303 | 0.0564 [0.0543, 0.0586] | 0.9382 [0.9284, 0.9467] | 100% | 0.009950 | **yes** |

**Illustrative development scenario — not Razorpay economics, not a production
SLO, and not a universal merchant policy.**

Reading the frontier honestly: capacity buys recall and costs precision. The
100/day tier is **preserved rather than hidden** — it gives the *best* precision
(35.29 %) but reaches only 29.35 % recall, missing 1,885 of 2,668 frauds. Recall
≥ 0.80 first becomes reachable at the 1,000/day tier, where precision falls to
9.75 %. There is no capacity at which both are comfortable, and that trade-off
is the finding, not a defect to tune away.

**Derived coverage reference.** Reaching recall ≥ 0.80 needs **21,420 reviews**
(≈ 965/day) at 9.97 % precision. This is a **reference figure only** — it is
explicitly **not** adopted as a merchant default, and **no merchant default is
set** by this freeze.

## 8 — Frozen provenance chain

| Element | Digest / value |
|---|---|
| v2 protocol amendment | `f53bcb7df3a3187b840687e03b0b4d071c21a2936bd72cf46d991a5107591021` |
| Source `train_transaction.csv` | `3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642` |
| Source `train_identity.csv` | `b63c725d8377be90a995268d97f347c17d456b95db45807adcf9f59cd603c37c` |
| MT3a partition assignment | `f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4` |
| Selected schema | variant E, 24 inputs (12 base source + `R_emaildomain` + `M1`–`M9` + `DeviceInfo` + derived boolean) |
| Selected-schema canonical JSON | `66cfbea1db1fc2c78512de5c15345acbedcdc737b10c4d1bf2ff0b5a0f82ca8d` |
| `training` superset content | `c28f3a9695f0967910be7d18…` |
| `validation_threshold` superset content | `87ebaf6f699aa4174969aa3e…` |
| `calibration_fit` superset content | `bd1fa53fec2298cf183110f6…` |
| `calibration_eval` superset content | `1c1dc123396794491329c2ca…` |
| Preprocessing | median impute + missing indicator + standardise; one-hot with `min_frequency=100`, `handle_unknown=infrequent_if_exist`; boolean passthrough |
| Preprocessing-configuration canonical JSON | `0b7168d4a557a4df45a48a4ff886679a6aa3127b0839d255d67c79df2160d3e3` |
| Model | XGBoost, 300 rounds, `max_depth=6`, `lr=0.1`, `subsample=0.8`, `colsample_bytree=0.8`, `hist`, `scale_pos_weight=28.524`, seed 42 |
| XGBoost-configuration canonical JSON | `8fbd438bd15dbec97357798efbe5fb97cb709e457c96419cba520347a8072343` |
| Champion pipeline (private) | `b6a1429c234bb24a991b685dec9539ce3c5839bff9348947539d68a5ab0d42a0` |
| Calibration | Platt, accepted |
| Platt calibrator (private) | `5055ca05fab5b490dbb77999774196050ce8b00d9c91166164740b566fadd655` |
| Calibration decision + aggregate evaluation | `876db378c94d006f8d6381f9f5b9efca20cfc837bedfec92c969f802055239cf` |
| Capacity policy | `lane_a_capacity_policy_v2`; canonical contract `6726d4262b84174bc1ed26aafbebbc84c8d512e568880f4f18adc460f45573c3` |
| Capacity-policy implementation | `0ef9c51f97b8115ae65cc5e55f6ccfc04a548203546546923d5b1aa17f32d738` |
| Capacity-frontier aggregate | `2da03943d3ebbf6548c1326589b74bd76e9e77783aed976e323ab040355d7575` |
| v2 experiment runner | `181de86fe00bd80ebff67160c62090e976c094c7795cdef7fabeb7934bdd1073` |
| v2 variant definitions | `bae7cc545b44259e98fd1e097ec9cda84bb1c96ca4ebbbb92cd6199e6901fa5f` |
| Private aggregate run manifest | `67aba752995e49537acae09befedde489aaf3937f3042e338321296a0c4ad410` |
| Working tree | `501d8a6…` plus uncommitted MT1/MT2/MT3 work; nothing committed |

Canonical JSON digests use UTF-8 JSON with sorted keys, compact separators and
ASCII escaping. The private run manifest carries the complete canonical objects,
full code hashes, HEAD/branch, dirty-tree state, staged count and untracked count;
the repository record publishes only safe aggregate descriptions and digests.

## 9 — Limitations and prohibited claims

- **v2 is a post-hoc amendment**, not an untouched pre-registration.
- Validation figures are **development-optimistic**; `validation_threshold` has
  been reused across three decisions.
- `calibration_eval` was used in v1, so the v2 calibration result is not
  independent.
- No final evaluation exists. **Lane A is not "programmatically held out" yet**
  and is **never** human-blind.
- **No Lane A metric may be compared with any Lane B metric** — different
  corpora, base rates, label definitions and feature spaces.
- Capacity tiers and any cost figure are illustrative development scenarios.
- **Never claimed:** Razorpay, Indian, or live-merchant performance; production
  readiness or SLO; ROI, savings, or capacity commitments; real-world
  fraud-probability performance; autonomous approve/block/decline; a
  production-optimal threshold; a correct capacity for any merchant; immutable
  audit, ACID, exactly-once, distributed durability; Vulcan.
- IEEE-CIS raw data, rows, row-level exports, model artifacts, calibrators,
  scores, and Kaggle test predictions are **never** committed or published.

## 10 — Final-test status

`final_test` remains frozen, unread, unopened, unmaterialised, unscored,
uncounted and unevaluated. It must be evaluated **exactly once**, in a separate
future task, only after this freeze is independently reviewed.
