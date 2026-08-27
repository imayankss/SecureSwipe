# Lane A final-evaluation protocol — boundary amendment 1

**This amendment corrects an implementation defect in the data-access boundary.
It changes no scientific decision.** The frozen model, schema, preprocessing,
calibrator, capacity policy, tiers, metric set, uncertainty procedure, ranking
rule, tie handling, and claim boundaries of
`LANE_A_FINAL_EVALUATION_PROTOCOL.md` remain **unchanged**.

- **Written at:** `8c0d3bdd634cb427dcc05301ae1e3df5b5e26d01`, branch
  `codex/recovered-demo-bundle`. Branch-local; not on `main`.
- **Written before the implementation was edited.** This document is authored
  and hashed first, and its digest is bound into both the corrected
  authorization-manifest builder and the corrected runner, so the ordering is
  verifiable rather than asserted.

## 1 — How the defect was found

A **read-only path audit** of the MT3g-prep freeze found the defect **before any
final-test access occurred**. No evaluation had been run, no authorization
manifest had been built with real inputs, and the runner had never been invoked
with `--execute-final-test`.

**No final-test data was accessed** — not by the audit, not by the original
defect, and not by this correction.

## 2 — The defect

Two places read raw files that identify or contain final-role rows, at a point
in the lifecycle where reading them was not authorised.

1. **Authorization-manifest builder.** `build()` called `sha256_file()` on the
   supplied role-assignment CSV. Preparation therefore opened and read a file
   whose contents identify which rows belong to `final_test`.
2. **Final-evaluation runner.** `verify_sources()` ran **before** the private
   lifecycle existed — before `PREPARED` and before the atomic transition to
   `STARTED` — and byte-hashed all three of the transaction, identity, and
   role-assignment files.

The second is the more serious of the two. Because no lifecycle record existed
at that point, a failing pre-access gate left no terminal state behind, so the
raw-data read could be repeated indefinitely without the one-time guard ever
engaging.

Neither defect ever read `isFraud`, constructed features, produced a score, or
counted final-role rows.

## 3 — The corrected boundary

### 3.1 — Preparation is metadata-only

Final-authorization preparation may validate **only path metadata** for the
transaction, identity, and role-assignment paths:

- existence;
- regular-file check;
- symlink rejection;
- canonical path resolution;
- size;
- modification timestamp.

Preparation must **never** open, read, hash, parse, preview, count, or load
these three files, by any mechanism.

Their frozen digests are **carried from the verified frozen record**, never
recomputed during preparation. The builder verifies the private MT3e aggregate
manifest by its own digest and binds it; the transaction, identity, and
role-assignment digests themselves come from the committed, reviewed intake and
partition freeze records, because the MT3e aggregate manifest does not carry
source-file digests. Preparation performs no hashing of raw data of any kind.

### 3.2 — Byte-level verification happens only after `STARTED`

Any byte-level verification of the raw transaction, identity, or role-assignment
files may occur **only after** the private lifecycle has atomically entered
`STARTED`. Before `STARTED`, the runner may verify only:

- the freeze commit;
- the protocol hash and this boundary-amendment hash;
- the authorization-manifest hash and structure;
- the frozen digests embedded in the runner;
- the pipeline and calibrator artifacts;
- the environment contract;
- **path metadata only** for transactions, identity, and role assignment;
- the absence of any earlier lifecycle state.

Before `STARTED`, the runner must not hash or open those three files, parse
final-role assignments, read `TransactionDT`, read `isFraud`, construct final
feature matrices, produce scores, or count final-role rows.

The role-assignment file is verified after `STARTED` using the frozen canonical
assignment digest — SHA-256 over `TransactionID,role` lines sorted ascending by
identifier — rather than a raw file digest, matching the value recorded in the
partition freeze.

### 3.3 — The label boundary is unchanged and still stricter

`isFraud` remains **semantically unread** until the frozen scores have been
sealed. Feature construction never indexes the label column, and the label
loader still requires the score-seal artifact as a precondition. This amendment
does not relax that ordering in any way.

## 4 — What this amendment does not change

No change is made to: features, the 24-input schema, preprocessing, model
settings, the calibrator, the calibration decision, capacity tiers, the budget
formula, ranking, tie handling, the metric set, bootstrap procedure, ECE bins,
confidence levels, reporting precision, required terminology, or prohibited
claims.

No retraining, refitting, tuning, calibration, materialisation, scoring,
prediction, or evaluation is authorised by this amendment. Lane B is untouched.

`final_test` remains frozen, unread, unmaterialised, unscored, and uncounted.
