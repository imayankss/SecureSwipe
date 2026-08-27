# Lane A — chronological partition freeze record

**Status: `VERIFIED` / `CURRENT/MEASURED`.** This record contains aggregate
counts, timestamp boundaries, and digests only. It contains **no rows, no
`TransactionID` values, no labels, and no row-level export of any kind.**

- **Lane:** A (IEEE-CIS). **Lane B is untouched by this task** — no Lane B
  artifact, config, model, metric, or document was read or modified.
- **Frozen at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle` (branch-local; not on `main`).
- **Freeze date:** 2026-08-26.
- **Nothing was trained, tuned, calibrated, predicted, or evaluated.**

## 1 — Inputs

| Item | Value |
|---|---|
| Source file | `train_transaction.csv` |
| Source SHA-256 | `3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642` |
| Columns read | `TransactionID`, `TransactionDT` — **only these two** |
| Label column read | **No.** `isFraud` exists in the source and was deliberately not read |
| Identity data joined | No. `train_identity.csv` was not opened |
| Feature engineering | None |
| Kaggle `test_*` files | Not read; none present in the inspected folder |
| Shuffling | None. Ordering is chronological by `TransactionDT` |
| Randomness | **None.** No RNG, no seed — the partition is a pure function of the source file |

The source digest matches the value recorded in `DATA_INTAKE_IEEE_CIS.md`, so
this freeze is bound to that exact intake.

## 2 — Method

Roles are assigned by `TransactionDT` alone. All rows sharing one timestamp are
kept in a single role, so every boundary falls strictly between two distinct
timestamps. Given that constraint, each cumulative boundary is placed at the
distinct timestamp whose cumulative row fraction is closest to its declared
cumulative target; ties in that search resolve to the earlier index. Roles are
chronological — earliest rows train, latest rows are the frozen final test.

Implementation: `src/lane_a/partition.py`. Runner:
`scripts/lane_a_freeze_partition.py`. Synthetic-only tests:
`tests/test_lane_a_partition.py`.

The partition module is deliberately isolated from Lane B: it imports nothing
from `src/preprocessing/feature_config.py`, and the two feature spaces must
never be merged, aligned, or renamed into one another.

## 3 — Frozen roles

Total rows partitioned: **590,540**. Distinct timestamps: **573,349**.

| Role | Rows | Target | Actual | Deviation | Timestamp range (inclusive) |
|---|---:|---:|---:|---:|---|
| `training` | 324,797 | 55 % | 55.000000 % | 0.0 | 86,400 – 8,022,306 |
| `validation_threshold` | 70,865 | 12 % | 12.000034 % | +3.4e-07 | 8,022,314 – 9,940,286 |
| `calibration_fit` | 53,148 | 9 % | 8.999898 % | −1.02e-06 | 9,940,296 – 11,449,871 |
| `calibration_eval` | 53,149 | 9 % | 9.000068 % | +6.8e-07 | 11,449,894 – 13,151,840 |
| `final_test` | 88,581 | 15 % | 15.000000 % | 0.0 | 13,151,880 – 15,811,131 |

Sum: 324,797 + 70,865 + 53,148 + 53,149 + 88,581 = **590,540** ✓

The largest deviation from target is **1.02e-06**, under one row. `TransactionDT`
is a relative offset in seconds, not a calendar timestamp; no calendar date or
seasonality claim may be derived from these bounds.

**Assignment digest (SHA-256 over canonical `TransactionID,role` lines sorted
ascending by id):**
`f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4`

This digest is publishable; the pairs it summarises are not.

## 4 — Verification results

Re-derived independently from the source time axis and cross-checked against the
private membership file:

| Check | Result |
|---|---|
| Every transaction assigned exactly once | **PASS** — 590,540 source ids, 590,540 membership rows, 590,540 unique ids; id sets identical |
| Roles exhaustive | **PASS** — role counts sum to 590,540 |
| Roles disjoint | **PASS** — independent recount from the source equals the membership-file counts for all five roles |
| Roles contiguous in time | **PASS** — each role occupies one unbroken timestamp interval |
| Strict time ordering | **PASS** — each role's minimum timestamp is strictly greater than the previous role's maximum; the four inter-role gaps are 8, 10, 23, and 40 seconds |
| Upper bounds strictly increasing | **PASS** |
| Determinism | **PASS** — the assignment digest recomputed from the private file reproduces the recorded value exactly |
| Synthetic-only tests | **PASS** — 16 tests, `tests/test_lane_a_partition.py` |

## 5 — Data-handling compliance

- **No raw rows, identifiers, labels, or row-level exports entered the
  repository.** This record and the source code contain aggregates and digests
  only.
- The row-level role-membership file is stored **outside the repository**, in a
  private local directory. Its path is not recorded here. The runner refuses to
  write it inside the repository.
- Neither raw CSV was moved, copied, renamed, or altered.
- Per `DATA_INTAKE_IEEE_CIS.md` §5, the membership file is a **derived
  row-level export** and must never be committed, published, or shared with
  non-participants.

## 6 — Standing constraints this freeze does not relax

- **`final_test` is now frozen and is off limits.** No feature, model,
  hyperparameter, calibration, threshold, or cost decision may be selected or
  revised using it, and it is evaluated exactly once, after every other choice
  is locked (`SCIENTIFIC_PROTOCOL.md` §6.3).
- **Blindness wording is unchanged and conservative.** Per
  `DATA_INTAKE_IEEE_CIS.md` §6, this corpus and any result from it must never be
  described as human-blind. The only permitted description of this partition is
  **"programmatically held out"**, and it is available because the partition was
  frozen **before** any feature development — which this record establishes.
- **No labels have been examined for any role.** In particular, the positive
  count of `calibration_eval` is unknown, so the calibration statistical-power
  floor (`SCIENTIFIC_PROTOCOL.md` §5.2, ≥ 40 positives) is **not yet evaluated**.
  It must be checked on `calibration_eval` only, never on `final_test`.
- **No metric from Lane A may be compared with any Lane B metric.** Different
  populations, base rates, label definitions, and feature spaces.
