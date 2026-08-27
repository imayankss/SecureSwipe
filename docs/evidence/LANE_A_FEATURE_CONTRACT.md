# Lane A — feature-eligibility contract and training-role profile

**Status: `VERIFIED` / `CURRENT/MEASURED`.** Aggregates, counts and rates only.
This document contains **no rows, no `TransactionID` values, no email domains,
no device strings, and no amounts.**

- **Lane:** A (IEEE-CIS). **Lane B is untouched** — not read, not modified.
- **Recorded at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle` (branch-local; not on `main`).
- **Inputs:** `train_transaction.csv` (`3a5c83ab…`), `train_identity.csv`
  (`b63c725d…`), and the private MT3a role assignment (`f375cf71…`).
- **Rows used:** the `training` role only — 324,797 rows, matching the MT3a
  freeze exactly.
- **`isFraud` was never read.** **No `final_test` row was read.** Nothing was
  trained, tuned, predicted, calibrated, or evaluated. No Kaggle `test_*` file
  was opened.

## 1 — Namespace separation from Lane B

Both lanes contain columns literally named `V1`…`V28`. They are unrelated:
Lane B's are PCA components of a different corpus; Lane A's are vendor-engineered
aggregates. The raw names collide **by coincidence**, and a rename could make
that collision silent.

Separation is therefore structural, not conventional. Lane A model inputs are
addressed by qualified name — `ieee_cis::V1` — so the two namespaces cannot
overlap even when raw names do. `src/lane_a/feature_contract.py` imports nothing
from Lane B, and a test asserts both halves of this: that the raw names **do**
collide (proving the hazard is real) and that the qualified names **do not**.

## 2 — Eligibility classification

434 columns classified: 394 transaction + 41 identity − 1 shared join key.

| Class | Count | Meaning |
|---|---:|---|
| `candidate_snapshot` | 23 | Plausibly available at transaction time |
| `benchmark_only` | 408 | Useful offline; decision-time availability or semantics unverified |
| `prohibited` | 3 | Never a model input under any mode |

**Prohibited (3).** `isFraud` — the label. `TransactionID` — row identifier and
identity join key, monotonic with time. `TransactionDT` — the frozen partition
key; as a raw feature it encodes each row's position relative to the frozen role
boundaries. Derived point-in-time quantities such as hour-of-day are a separate
proposal and are not covered by that exclusion.

**`candidate_snapshot` (23).** `TransactionAmt`, `ProductCD`, `card1`–`card6`,
`addr1`–`addr2`, `P_emaildomain`, `R_emaildomain`, `M1`–`M9`, `DeviceType`,
`DeviceInfo`. Each is either part of the authorisation request itself or a match
computed between attributes inside it.

**`benchmark_only` (408), all requiring point-in-time proof.**

| Family | Columns | Why not serving-eligible |
|---|---:|---|
| `C1`–`C14` | 14 | Documented only as counts over entities associated with the card. The aggregation window and its anchor are unpublished, so they cannot be shown to exclude information created after the transaction. |
| `D1`–`D15` | 15 | Documented only as timedeltas. Whether every instance looks strictly backwards from the transaction instant is unpublished. |
| `V1`–`V339` | 339 | Vendor-engineered aggregates covering ranking, counting and entity relations; construction is masked. |
| `dist1`–`dist2` | 2 | Masked distance quantity; endpoints and units undocumented. |
| `id_01`–`id_38` | 38 | Identity signals with undocumented semantics. |

**No `C*`, `D*` or `V*` column can reach a served bundle.** The serving whitelist
is computed as *candidates that carry no outstanding documentation
requirement*, so exclusion is by construction rather than by a hand-maintained
denylist. A test asserts the resulting whitelist contains no such column, and
that selecting one for serving raises.

The 23 serving-eligible columns are exactly the 23 `candidate_snapshot` columns:
none of them carries an outstanding proof requirement today.

## 3 — Identity is optional, and its absence is a signal

Identity records exist for a minority of transactions. There are 40
identity-derived columns in total: `id_01`–`id_38`, `DeviceType`, and
`DeviceInfo`. This contract marks all 40 as **optional**, and the
profiler counts a transaction with **no identity record at all** as *missing*
for every identity column rather than excluding it from the denominator. The
published missing rates therefore reflect real availability, not the availability
of rows that happen to have identity data.

Missingness must be represented explicitly downstream — as its own category or
indicator — never silently imputed and never used to drop rows, since dropping
would change the evaluated population.

**A drift signal worth recording now.** Identity coverage measured on the
`training` role is **28.59 %** (92,874 identity records for 324,797 training
rows). Corpus-wide coverage recorded at intake was **24.42 %**. Coverage is
therefore **not uniform over time**, and the earliest 55 % of the corpus is
better covered than the corpus average. Any identity-derived feature will have a
shifting availability profile across the chronological roles. This was measured
without reading any `final_test` row and must be re-checked later on permitted
roles only.

## 4 — Training-role aggregate profile

324,797 rows. 431 columns profiled — the 434 total minus the 3 prohibited
columns, which are never parsed.

### Serving-eligible candidates

| Column | dtype | Missing | Cardinality | Invalid-value violations |
|---|---|---:|---:|---|
| `TransactionAmt` | float | 0.00 % | ≥2000 | — |
| `ProductCD` | text | 0.00 % | 5 | — |
| `card1` | integer | 0.00 % | ≥2000 | — |
| `card2` | float | 1.78 % | 499 | — |
| `card3` | float | 0.25 % | 101 | — |
| `card4` | text | 0.25 % | 4 | — |
| `card5` | float | 0.78 % | 108 | — |
| `card6` | text | 0.25 % | 4 | — |
| `addr1` | float | 11.10 % | 300 | — |
| `addr2` | float | 11.10 % | 62 | — |
| `P_emaildomain` | text | 15.73 % | 59 | — |
| `R_emaildomain` | text | 73.20 % | 60 | — |
| `M1`–`M3` | text | 60.20 % | 2 each | — |
| `M4` | text | 49.67 % | 3 | — |
| `M5` | text | 61.57 % | 2 | — |
| `M6` | text | 33.07 % | 2 | — |
| `M7`–`M9` | text | 74.01 % | 2 each | — |
| `DeviceType` | text | 72.07 % | 2 | — |
| `DeviceInfo` | mixed | 75.85 % | 1408 | `mixed_types_observed` |

Cardinality is exact up to 2,000 distinct values and reported as `≥2000` beyond
that, which bounds profiler memory. Values themselves are never retained.

### Whole-profile aggregates

| Missing-rate band | Columns |
|---|---:|
| 0 % | 60 |
| < 10 % | 49 |
| 10–50 % | 92 |
| 50–75 % | 154 |
| 75–90 % | 64 |
| ≥ 90 % | 12 |

| Eligibility | Columns | Median missing | Max missing |
|---|---:|---:|---:|
| `candidate_snapshot` | 23 | 33.07 % | 75.85 % |
| `benchmark_only` | 408 | 71.41 % | 99.04 % |

Fully empty columns in the training role: **0**.

### Invalid-value checks

Exactly **one** column shows a violation across all 431: `DeviceInfo` carries
**mixed types**, meaning some values parse as numbers and others do not. It must
be treated as categorical text, never coerced to numeric.

No non-finite values were found anywhere. `TransactionAmt` shows no negative
values. Note that a bare `nan` token is counted as *missing*, while `inf` would
be counted as an *invalid value* — the two are deliberately not conflated, so
real corruption cannot hide inside a missingness rate.

## 5 — Standing constraints

- **`final_test` remains frozen and unread.** No row from it was opened here.
- **No labels examined.** The `calibration_eval` positive count is still
  unknown, so the calibration statistical-power floor
  (`SCIENTIFIC_PROTOCOL.md` §5.2) remains unevaluated.
- **Blindness wording unchanged.** Per `DATA_INTAKE_IEEE_CIS.md` §6, this corpus
  and any result from it are never human-blind; the only permitted description
  of the frozen partition is "programmatically held out".
- **No Lane A metric may be compared with any Lane B metric.**
- **Nothing here authorises a model.** This is a contract and a profile; no
  estimator, dashboard, or API surface was created or changed.
