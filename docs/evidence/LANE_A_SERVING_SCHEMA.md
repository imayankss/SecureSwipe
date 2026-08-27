# Lane A — locked serving-core schema and conservative feature builder

**Status: `VERIFIED` / `CURRENT/MEASURED`.** Schema, aggregate counts and
digests only. **No rows, no `TransactionID` values, no email domains, no device
strings, no amounts.**

- **Lane:** A (IEEE-CIS). **Lane B untouched** — not read, not modified.
- **Recorded at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle` (branch-local; not on `main`).
- **Built from:** the `training` role of the MT3a frozen partition only.
- **`isFraud` never read. No `final_test` row read. No Kaggle `test_*` file
  opened.** Nothing trained, tuned, calibrated, predicted, or evaluated.

## 1 — The locked 13-field serving core

| # | Field | Kind | Source | Notes |
|--:|---|---|---|---|
| 1 | `TransactionAmt` | numeric | transaction | validated finite and non-negative |
| 2 | `ProductCD` | categorical | transaction | |
| 3 | `card1` | numeric | transaction | |
| 4 | `card2` | numeric | transaction | |
| 5 | `card3` | numeric | transaction | |
| 6 | `card4` | categorical | transaction | |
| 7 | `card5` | numeric | transaction | |
| 8 | `card6` | categorical | transaction | |
| 9 | `addr1` | numeric | transaction | |
| 10 | `addr2` | numeric | transaction | |
| 11 | `P_emaildomain` | categorical | transaction | values never exported |
| 12 | `DeviceType` | categorical | **identity join** | optional |
| 13 | `identity_record_present` | boolean | **derived** | the only derived field |

11 transaction-sourced + 1 identity-sourced + 1 derived = **13 model inputs**.

Internal model inputs use Lane A-qualified names (`ieee_cis::TransactionAmt`),
so the Lane A and Lane B namespaces cannot collide even though both corpora
contain columns named `V1`…`V28`.

**Forbidden, and rejected rather than merely absent:** `TransactionID`,
`isFraud`, `TransactionDT`, `R_emaildomain`, `DeviceInfo`, and every `M*`, `C*`,
`D*`, `V*`, `dist*`, and `id_*` column. Each is covered by a test that asserts
rejection, because absence could be an oversight while explicit rejection cannot.

Widening this schema is a protocol amendment, not a code change.

## 2 — What the builder deliberately does not do

No encoder is fitted. No aggregation, ranking, count, or window is computed. No
target encoding exists — the builder never receives a label, and supplying one
raises. No history or entity-level feature is constructed. No value is imputed.

Each output row is a pure function of one transaction row plus the presence or
absence of its identity record. The builder holds no cross-row state, so it
cannot leak information between rows or across role boundaries. A test asserts
the module source contains no `.fit(`, `groupby`, `rolling(`, `expanding(`,
`cumsum`, or target-encoding construct.

**Non-training rows are skipped on the identifier alone.** The CSV reader splits
each line — unavoidable for a CSV — but for a non-training row no field other
than `TransactionID` is read, validated, transformed, or retained.

## 3 — Missingness handling

**Categorical missing → one reserved token.** A single sentinel represents
missing for every categorical field, so downstream code has exactly one case to
handle.

**Collision protection.** A real value equal to the reserved token would
silently merge genuine data into the missing bucket. The builder refuses: by
default it raises on any real value equal to the token, and an explicit
`escape` policy is available that prefixes such values so they remain
distinguishable. Values that already carry the escape prefix are also rejected,
so the encoding cannot be spoofed from either direction. Both paths are tested.

**Numeric missing → null, never filled.** No zero, no mean, no forward-fill.

**Identity absence is a first-class signal.** `identity_record_present` records
it as a boolean, and a `DeviceType` value arriving on the transaction row is
**ignored** in favour of the identity join, so a stray value cannot manufacture
an identity record that does not exist.

## 4 — Build results (training role only)

| Quantity | Value |
|---|---:|
| Training rows built | **324,797** |
| Non-training rows skipped on identifier only | 265,743 |
| Model inputs per row | 13 |
| `identity_record_present` = true | 92,874 |
| `identity_record_present` = false | 231,923 |
| `DeviceType` = reserved missing token | 234,089 |
| Encoders fitted | 0 |
| Aggregations computed | 0 |

**Feature-matrix content digest:**
`992cea539e6d17b0f2326d3a32986df276c2beb7fb989cb5906a8b57fd70bf80`

The digest is publishable; the matrix it summarises is not.

**Cross-checks against earlier frozen evidence — all consistent:**

- 324,797 built + 265,743 skipped = **590,540**, the full corpus.
- 324,797 built equals the MT3a frozen `training` count **exactly**.
- 92,874 identity records equals the MT3b training-role profile **exactly**.
- `DeviceType` missing 234,089 / 324,797 = **72.07 %**, matching the MT3b
  profile to two decimal places.
- The 2,166-row gap between `DeviceType` missing (234,089) and identity absent
  (231,923) is the set of rows that **have** an identity record whose
  `DeviceType` value is itself blank. Both are represented by the same reserved
  token, and the boolean keeps the two situations distinguishable.

**Determinism:** the build was run twice against identical inputs and produced a
byte-identical output file. No RNG and no seed are involved.

## 5 — Data handling

The row-level feature matrix is written to a private directory **outside the
repository**; its path is not recorded here and the runner refuses to write
inside the repository. Per `DATA_INTAKE_IEEE_CIS.md` §5 it is a **derived
row-level export** and must never be committed, published, or shared with
non-participants. No raw CSV was moved, copied, or altered.

## 6 — Standing constraints unchanged

`final_test` remains frozen and unread. No labels examined, so the
`calibration_eval` positive count is still unknown and the calibration
power floor (`SCIENTIFIC_PROTOCOL.md` §5.2) remains unevaluated. This corpus and
any result from it are never human-blind; the only permitted description of the
frozen partition is "programmatically held out". No Lane A metric may be
compared with any Lane B metric. **This document authorises no model** — no
estimator, dashboard, or API surface was created or changed.
