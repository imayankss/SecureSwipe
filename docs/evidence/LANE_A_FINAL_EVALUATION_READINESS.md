# Lane A final-evaluation readiness (MT3g-prep)

**This record contains aggregates, digests, and design description only.** It
holds no row, identifier, amount, domain, device string, label, score, private
path, or private filename.

`final_test` was **not** read, opened, counted, materialised, scored, predicted,
hashed, or evaluated while preparing any artifact described here. This document
records that the machinery now exists — not that it has been used.

## 1 — Why this task existed

MT3g was stopped before final-test access. The reviewed MT3f freeze contained no
Lane A final-evaluation runner, no one-time lifecycle mechanism, no fully
predeclared final-test metric protocol, and no reachable private authorization
manifest. Every Lane A path failed closed on `final_test`, which was correct but
left the authorised one-time evaluation impossible to perform.

This preparation task supplies exactly those four missing prerequisites and
binds them to a reviewed freeze commit.

## 2 — Order of authorship

The protocol was written **before** the runner existed. At the moment the
protocol was hashed, the repository contained zero final-evaluation runner files
and zero lifecycle modules. The protocol digest is bound into the private
authorization manifest that the runner verifies, so the ordering is checkable
rather than asserted.

| Artifact | Role |
| --- | --- |
| `LANE_A_FINAL_EVALUATION_PROTOCOL.md` | Predeclares model, policy, metrics, uncertainty, and claim boundaries |
| `src/lane_a/final_lifecycle.py` | Atomic one-time lifecycle record |
| `src/lane_a/final_evaluation.py` | Protocol-bound aggregate metrics |
| `scripts/lane_a_run_final_evaluation.py` | The single guarded runner |
| `scripts/lane_a_build_final_authorization.py` | Builds the private authorization manifest |

## 3 — Runner architecture

The runner is the **only** module permitted to read the `final_test` role, and
only once per freeze commit. Every ordinary Lane A builder, materialiser, and
experiment runner still fails closed on `final_test`; nothing here relaxes the
existing allowlist in `src/lane_a/roles.py`.

**Required, with no defaults:** `--execute-final-test`, the expected freeze SHA,
the private authorization-manifest path, that manifest's expected SHA-256, and
an authorised private output directory outside the repository.

**Pre-access gates, in order.** Repository HEAD matches the expected freeze;
the manifest's own digest matches before any field in it is trusted; schema
version, bound freeze commit, authorised role, one-run-only rule, and the
post-result-tuning prohibition are all present; the protocol digest, runner
digest, and four module digests match; the eight frozen MT3e digests match
constants embedded in the runner, so a tampered manifest cannot relax them; the
the declared source and role-assignment digests match the embedded constants
**without opening those files**; the pipeline and calibrator artifacts match
their frozen digests; the environment contract is satisfied; the selected
variant, frozen tiers, and predeclared metric set validate; and no lifecycle
record of any kind already exists.

**Raw-data access boundary.** Before `STARTED`, the transaction, identity and
role-assignment files are validated by **path metadata only** — existence,
regular-file check, symlink rejection, canonical resolution. Byte-level
verification of those files happens only *after* the atomic `STARTED`
transition, so a failed gate always leaves a terminal lifecycle record rather
than a silently repeatable raw read. See
`LANE_A_FINAL_EVALUATION_PROTOCOL_BOUNDARY_AMENDMENT_1.md`, which corrected an
implementation defect found by a read-only audit before any final-test access.

**Lifecycle.** `PREPARED` is created with `O_EXCL`, so two concurrent runners
cannot both believe they are first. `STARTED` is written atomically immediately
before the first final-role access. Terminal states are `SEALED` and
`FAILED_AFTER_ACCESS`; neither has any outgoing transition. Any existing record
refuses a new run outright.

**Ordering guarantee.** Features are built in a pass that never indexes the
label column, scored through the frozen pipeline and Platt calibrator, written
privately, and hashed into a score seal. The label loader takes the seal as a
required argument and refuses to run without it, so "scores before labels" is a
precondition rather than a convention.

**Outputs.** Row-level features, row order, raw scores, calibrated outputs,
labels, lifecycle state, and the detailed result manifest are all written
outside the repository. Only aggregates are exported publicly, and the export is
screened for absolute paths, home shortcuts, domains, device strings,
identifiers, e-mail-like values, and prohibited claim language before it is
written.

## 4 — Refusal boundaries

The runner has **no** `--force`, `--retry`, `--rerun`, `--skip`, `--no-verify`,
`--fallback`, `--variant`, `--tier`, `--threshold`, or `--overwrite`. Those
tokens are rejected before argument parsing, so a future flag cannot silently
become an escape hatch. There is no fallback model, no integrity check that can
be skipped, and no second execution.

It cannot train, refit, tune, search, or select. Variants **A–D** are refused
outright on final data. Altered capacity tiers are refused. Undeclared metrics
are refused. A non-frozen bootstrap seed, resample count, confidence level, or
ECE bin count is refused. Any failure after `STARTED` moves the lifecycle to
`FAILED_AFTER_ACCESS` and re-raises; it is never patched and retried.

## 5 — Synthetic validation

All validation is synthetic or uses already-observed permitted-role evidence. No
IEEE-CIS source file was opened, no real model artifact was loaded, and no
`final_test` row was read.

| Suite | Tests | Result |
| --- | --- | --- |
| `test_lane_a_final_lifecycle.py` | 21 | pass |
| `test_lane_a_final_evaluation.py` | 52 | pass |
| `test_lane_a_final_runner_guards.py` | 69 | pass |
| `test_lane_a_final_authorization_builder.py` | 14 | pass |

Coverage includes: the missing execute flag; every override flag; a short or
mismatched freeze SHA; absent, malformed, mis-digested, wrongly bound, and
incomplete manifests; each of the eight frozen digests, the protocol digest, the
runner digest, all four module digests, all three source digests, and the
role-assignment digest mutated independently; environment mismatch; every prior
lifecycle state refusing a new run; failure after `STARTED` landing in
`FAILED_AFTER_ACCESS`; labels refused without a score seal; label misalignment;
feature construction never indexing the label column; variants A–D refused;
altered tiers and undeclared metrics refused; deterministic ranking and
ascending-source-position tie handling; public exports rejecting paths, domains,
device strings, identifiers and prohibited claims; and a private output
directory inside the repository being refused.

Boundary coverage additionally installs read sentinels over `open`,
`Path.open`, `Path.read_bytes` and the hashing helper, and fails if any
transaction, identity or role-assignment file is touched during manifest
preparation, or at any point before the lifecycle state is `STARTED`. The
sentinels are themselves tested to fire on a deliberate read, so a clean result
is meaningful rather than vacuous.

A complete end-to-end **synthetic rehearsal** drives the whole runner path and
confirms the sealed lifecycle, the score-seal-before-labels ordering, capacity
reconciliation across all five tiers, a 15-bin calibration table, private
artifacts written outside the repository, and a second execution being
impossible.

## 6 — Claim boundaries

Nothing in this task produces a performance number of any kind. The frozen
protocol governs all future public evidence and requires the terminology
`IEEE-CIS Lane A final evaluation`, `programmatically held out`, `evaluated
exactly once`, `Platt-calibrated benchmark output`, and
`merchant-configurable illustrative review capacity`, together with the
limitations `not Razorpay economics`, `not live-merchant performance`,
`not a production SLO`, and `not directly comparable with Lane B`.

Lane A may not be described as `programmatically held out` in the past tense
until the authorised evaluation has actually run, and may **never** be described
as human-blind or externally blind.

## 7 — Status

The prerequisites exist and are frozen. The evaluation itself has **not** been
performed. The next step is owner approval for a separate one-time MT3g
final-test evaluation using this runner.
