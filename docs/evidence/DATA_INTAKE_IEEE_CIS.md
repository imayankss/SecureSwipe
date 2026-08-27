# IEEE-CIS Fraud Detection — data intake record

**This is an intake record. It is not a model result, not an evaluation, and not
permission to begin training.** No model was trained, tuned, calibrated,
benchmarked, or used to predict while producing it. No held-out outcome was
inspected. Nothing was moved, renamed, copied, uploaded, committed, or published.

- **Status:** `VERIFIED` / `CURRENT/MEASURED` for every measured quantity below.
- **Recorded at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle` (branch-local; not on `main`).
- **Intake date:** 2026-08-26.
- **Method:** streaming, read-only. Files were opened once each and read
  sequentially through Python's `csv` reader; only aggregate counts and column
  names were retained. No row was printed, stored, or copied.
- **Lane:** this corpus is the candidate **Lane A** primary-evaluation dataset
  under `SCIENTIFIC_PROTOCOL.md`. Lane B (the historical PCA-anonymised corpus)
  is unaffected and unchanged.

---

## 1 — File identity

| File | Bytes | SHA-256 |
|---|---:|---|
| `train_transaction.csv` | 683,351,067 | `3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642` |
| `train_identity.csv` | 26,529,680 | `b63c725d8377be90a995268d97f347c17d456b95db45807adcf9f59cd603c37c` |

Both files reside in the owner's local downloads folder. **The absolute path is
deliberately not recorded in this document.** Neither file is inside the
repository, and neither may ever be placed inside it (§5).

**Filesystem timestamps do not establish the retrieval date.** Both files carry
`mtime` and birth time `2019-12-11 23:12:38`, which is the timestamp preserved
from the original distributed archive, not the date the owner downloaded them.
The download date is therefore **owner-asserted and not independently verifiable
from the filesystem**; only the intake date above is verified. If a precise
retrieval date is needed for the provenance chain, the owner must supply it from
their Kaggle account activity.

---

## 2 — Schema

### `train_transaction.csv` — 394 columns

Column names, in file order, expressed as exact contiguous groups:

`TransactionID`, `isFraud`, `TransactionDT`, `TransactionAmt`, `ProductCD`,
`card1`–`card6`, `addr1`–`addr2`, `dist1`–`dist2`, `P_emaildomain`,
`R_emaildomain`, `C1`–`C14`, `D1`–`D15`, `M1`–`M9`, `V1`–`V339`.

Arithmetic check: 5 + 6 + 2 + 2 + 2 + 14 + 15 + 9 + 339 = **394** ✓

### `train_identity.csv` — 41 columns

`TransactionID`, `id_01`–`id_38`, `DeviceType`, `DeviceInfo`.

Arithmetic check: 1 + 38 + 2 = **41** ✓

### Required-column presence

| Column | `train_transaction.csv` | `train_identity.csv` |
|---|---|---|
| `TransactionID` | present | present |
| `TransactionDT` | present | — |
| `TransactionAmt` | **present** | — |
| `TransactionAMT` | **absent** | — |
| `isFraud` | present | — |

**Naming caveat, recorded because it will bite otherwise.** The amount column is
spelled **`TransactionAmt`**, not `TransactionAMT`. A case-sensitive lookup for
`TransactionAMT` returns nothing, and prior planning documents used the
upper-case spelling. Any integration code must use `TransactionAmt`.

**Namespace-collision warning.** This corpus contains columns named `V1`–`V339`.
They are Vesta-engineered features and have **no relationship whatsoever** to the
`V1`–`V28` PCA components of the Lane B historical corpus. The two feature
spaces must never be merged, aligned, or renamed into one another. Today the
mismatch fails closed, because this corpus has no `Class`, no `Time`, and no
`Amount` column and so cannot satisfy the existing `REQUIRED_COLUMNS`
validation — but renaming three columns would make the `V1`–`V28` subset align
silently and produce a model trained on semantically unrelated inputs.

---

## 3 — Measured contents

### `train_transaction.csv`

| Quantity | Value |
|---|---:|
| Data rows (excluding header) | 590,540 |
| Ragged rows (field count ≠ 394) | 0 |
| `isFraud` = 0 | 569,877 |
| `isFraud` = 1 | 20,663 |
| Other / missing `isFraud` values | none |
| Labelled total | 590,540 |
| Fraud rate | 0.034990 (**3.4990 %**) |

Every row carries a valid binary label; there are no unlabelled or malformed
rows in this file.

### `train_identity.csv`

| Quantity | Value |
|---|---:|
| Columns | 41 |
| Data rows (excluding header) | 144,233 |
| Unique `TransactionID` | 144,233 |

`TransactionID` is unique across every row — no duplicate identity records.

### Aggregate cross-file and temporal facts

| Quantity | Value |
|---|---:|
| Transaction rows with a matching identity row | 144,233 |
| Identity coverage of the transaction file | **24.42 %** |
| `TransactionDT` minimum (relative seconds) | 86,400 |
| `TransactionDT` maximum (relative seconds) | 15,811,131 |
| Span | 15,724,731 s = **182.00 days** |

These are aggregates only; no individual value, identifier, or row is recorded.

**Consequences for Lane A design, recorded now so they are not discovered late:**

- **Identity data is missing for 75.58 % of transactions.** Any feature built
  from `id_*`, `DeviceType`, or `DeviceInfo` is absent for roughly three
  transactions in four. Missingness itself may correlate with the label, so it
  must be modelled explicitly as a category rather than imputed silently, and
  never dropped in a way that changes the evaluated population.
- **`TransactionDT` is a relative offset, not a calendar timestamp.** Its minimum
  of exactly 86,400 — one day in seconds — is consistent with the published
  description of the field as a timedelta from an undisclosed reference point.
  No calendar date, and therefore no real-world seasonality claim, can be derived
  from it.
- **The 182-day span supports the chronological split** that
  `SCIENTIFIC_PROTOCOL.md` requires for this lane. Splitting must be by
  `TransactionDT` order, never randomly.

---

## 4 — Source and terms

- **Source:** IEEE-CIS Fraud Detection competition, hosted on Kaggle.
- **Acquisition:** manually downloaded by the owner from their own Kaggle
  account, after joining the competition and accepting its rules. No credential
  was requested, seen, stored, or used in producing this record, and no
  automated download was performed.
- **Retrieval date:** owner-asserted; not independently verifiable from
  filesystem timestamps (§1). Intake recorded 2026-08-26.
- **Data-use restriction as recorded by the owner:** non-commercial purposes
  only, including competition, academic research, and education.
- **Redistribution restriction as recorded by the owner:** no transmission,
  duplication, publication, redistribution, or sharing of Competition Data with
  non-participants.

### 4.1 Retained verbatim rule excerpts

Retained by the owner from the **IEEE-CIS Competition Rules, Section 7**, and
recorded here verbatim so the terms this project operates under are on the
record rather than paraphrased:

> "You may access and use the Competition Data for non-commercial purposes only,
> including for participating in the Competition and on Kaggle.com forums, and
> for academic research and education."
>
> — IEEE-CIS Competition Rules, Section 7

> "You agree not to transmit, duplicate, publish, redistribute or otherwise
> provide or make available the Competition Data to any party not participating
> in the Competition."
>
> — IEEE-CIS Competition Rules, Section 7

**How this project reads these two clauses.** The first permits the use
SecureSwipe makes of the corpus — non-commercial academic research and
education — and does not extend to any commercial use. The second forbids
making the Competition Data available to non-participants, which a public
repository plainly would; it is the direct basis for the handling rules in §5.
This is a record of the terms and of the project's compliance posture. **It is
not legal advice**, and it does not certify that this project's use is
permitted; that determination rests with the owner.

**Provenance status.** The excerpts above are now retained from the primary
rules document, so the two restrictions are no longer only a paraphrase. The
competition rules page remains login-gated and was not machine-readable during
this intake, so this record depends on the owner's transcription rather than an
independent fetch. What is verified is the wording as retained; what remains
unverified is whether Section 7 contains further material terms not excerpted
here. Any public claim resting on permitted use should cite the complete
section, not these two clauses alone.

---

## 5 — Handling rules

1. **Raw files remain local and must never enter the public repository.** The
   following must **never** be committed, staged, pushed, attached, published,
   or otherwise made available to anyone not participating in the Competition:
   - the **raw CSVs**, in whole or in part;
   - **row samples** of any size, including single illustrative rows, head/tail
     excerpts, fixtures, and test doubles built from real rows;
   - **derived row-level exports** — any artifact retaining one record per
     transaction, including per-row scores, per-row features, embeddings,
     joined extracts, and error-analysis tables;
   - **Kaggle test predictions**, submission files, and any scored output over
     the competition test partition.

   This follows directly from the Section 7 clause in §4.1: a public repository
   makes its contents available to non-participants, so publishing any of the
   above would breach the retained terms. Aggregate statistics, column names,
   file digests, and model-level metrics are **not** row-level exports and
   remain publishable.

   The repository's `.gitignore` already excludes `*.csv` and `*.zip`; that is a
   safety net, not a licence to place files inside the working tree. Do not copy
   the source files into the repository at all.
2. **Only the labelled `train_*` files are approved for SecureSwipe Lane A** —
   specifically `train_transaction.csv` and `train_identity.csv`, at the exact
   SHA-256 digests in §1. A file with any other digest is a different artifact
   and requires a new intake record.
3. **The Kaggle `test_*` files are prohibited from SecureSwipe evaluation.**
   They are unlabelled, their ground truth is not available, and no metric
   computed against them could be verified. They were not read during this
   intake, and no `test_*` file was present in the folder inspected. SecureSwipe
   must never describe a Kaggle competition test partition as a final test; the
   frozen final test is an internal chronological partition carved from the
   labelled corpus, per `SCIENTIFIC_PROTOCOL.md`.
4. **No raw values appear in this document** — no rows, no `TransactionID`
   values, no email domains, no device strings, no amounts. Only column names,
   aggregate counts, and file digests.
5. **This record grants no training permission.** It satisfies one part of the
   MT2 §8.7 preconditions — the raw SHA-256 — and evidences file identity and
   shape. It does not by itself unlock MT3.

---

## 6 — Precondition status after this intake

`SCIENTIFIC_PROTOCOL.md` §8.7 requires three things before execution. After this
intake and the MT2.6a correction, **all three are satisfied for Lane A**.

| Precondition | Status after intake |
|---|---|
| Approved corpus present locally | **SATISFIED** for Lane A — both files present, hashed, shape verified |
| Raw SHA-256 recorded | **SATISFIED** — §1 |
| Retained licence and terms | **SATISFIED** — verbatim Section 7 excerpts retained at §4.1, with the residual limitation recorded there: the excerpts are the owner's transcription, and it is not established that Section 7 contains no further material terms |

**Lane A's data preconditions are now met; Lane B's are not.** Lane B still has
none of the three — the historical corpus is absent from the repository, its
licence is named nowhere, and its raw digest is unrecorded. Lane B therefore
remains unexecutable, and nothing here changes that.

**This record does not by itself unlock MT3.** Satisfying §8.7 removes the
*data* blocker for Lane A; it is not an acceptance decision. Unlocking MT3
remains a reviewer and owner call, and it should account for the constraints
this intake surfaced — the mandatory partition-before-features freeze order
(§6), the 24.42 % identity coverage, the chronological-split requirement, and
the schema-isolation work that Lane A needs before any model is fitted.

**Lane A blindness — resolved conservatively, and settled.** Under
`SCIENTIFIC_PROTOCOL.md`, a Lane A final test may be called held out and blind
**only** on a positive owner attestation that the corpus has never been observed
— its labels, its predictions, or its outcomes. The owner has now made the
following attestation, and it is recorded verbatim:

> "The owner does not recall any prior training, tuning, prediction, or model-result
> review on IEEE-CIS before this intake. Because this is not a positive certainty,
> SecureSwipe will not describe this corpus or any result from it as human-blind.
> A future final partition may be described only as 'programmatically held out'
> after it is frozen before feature development."

**This settles the question in the conservative direction, permanently.** Absence
of recall is not the positive certainty the protocol requires, so the Lane A
blindness condition is **not** met and will not be revisited by reinterpretation.
Binding consequences:

- **"Human-blind", "blind holdout", and "unseen" are prohibited** for this corpus
  and for every result derived from it, in every document, panel, pitch, and
  summary, at any level of abstraction.
- The **only** permitted description of a future final partition is
  **"programmatically held out"**, and it may be used **only after** that
  partition has been frozen **before** feature development begins. A partition
  frozen after features were designed does not qualify even for that weaker
  label.
- This is a **stricter** standard than Lane B's. Lane B carries "programmatically
  quarantined but historically observed; not human-blind" because its corpus was
  demonstrably observed. Lane A carries "programmatically held out" because its
  observation status is *unknown*. Neither is a blind-holdout claim, and the two
  labels are not interchangeable.
- The freeze order is therefore a hard sequencing constraint on MT3, not a
  presentational choice: **partition first, then engineer features.** Reversing
  that order forfeits even the weaker label.
