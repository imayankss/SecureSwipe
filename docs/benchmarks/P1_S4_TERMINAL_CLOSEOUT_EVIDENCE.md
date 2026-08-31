# P1-S4 terminal closeout evidence

Verdict: **CLOSED WITHOUT SCALE CLAIM — EVIDENCE INSUFFICIENT OR GATES FAILED**

The reproduced state-store checkout-exhaustion defect is repaired, and the
repair was independently confirmed by three consecutive postfix proofs at the
exact cell that failed in P1-S4e. The frozen 36-cell matrix then failed closed
at its tenth cell on a service correctness gate. The single authorized rule-A
reproduction of that failure did not reproduce it and proved no new root cause,
so no repair cycle is justified and no multi-worker scaling claim is authorized.

P1-S4 infrastructure work ends here. No successor task is created or proposed.

## 1. Identity

| Item | Identity |
| --- | --- |
| Branch | `codex/p1-core-checkpoint` |
| `HEAD` at closeout start | `8951e1a1cf76f15f15aa81f04ca96bc1d0d77c26` |
| `HEAD` at closeout end | `29288292f802746adab5b2defffde29599a3d7c2` |
| Closeout protocol commit | `1227231c8b531500afc8951f3b4e8491f885e17b` |
| Evidence-preservation commit | `5416305f15519f3f8f7d49762288c7331374570e` |
| Rule-A classification-mode commit | `2928829` |
| State-store repair commit (unchanged) | `f4d38c249045796f05815aac6c244d6432cf703a` |
| [Closeout protocol](P1_S4_TERMINAL_CLOSEOUT_PROTOCOL.md) SHA-256 | `7180826766dfa65334865f3f4dee1b60c308d94a70ad0fce586730742b409856` |
| Model fingerprint | `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3` |
| Benchmark version | `p1-s4-terminal-closeout-v1` |

All nine referenced P1-S4e/P1-S4f commits were verified present and ancestors of
`HEAD` before any change. P1-S4b/c/d/e/f artifacts and evidence remain
unmodified, unmoved, and unrelabelled.

### Artifact digests

| Artifact | SHA-256 |
| --- | --- |
| `p1-s4e-smoke-1788172294.json` | `c494682bb3a96e04daa5134ff3d3139f4e814f23ad4c9a27e72f7875525e7c09` |
| `p1-s4-postfix-1788172334.json` | `4a39d1a21c31294a56c5f4889c11b0fa69d38f06bc74e3a9882c5660c930ad8b` |
| `p1-s4e-full-1788172447-progress.json` | `ab0f265cd36302e84f751550309926dd92c5a28b3253bb53f994e11ff544f9aa` |
| `p1-s4e-full-1788172447-partial.json` | `e56f5c507e8d7d6c45565566603404dde81a0d8666e0154965d18ef61572c791` |
| `p1-s4-classify-1788173022.json` | `6792b6e98fbe64f2db6617a574fe791d01d402c73da1eb533d9d699062ef797c` |

Matrix artifacts carry the harness's own `p1-s4e-full-<epoch>` run-id rather
than the `p1-s4-final-<epoch>` name written into the closeout protocol. The
run-id is hardcoded in the frozen harness and was not edited purely for
naming. The timestamp is unique and no existing artifact was overwritten.

### Environment

Apple M2 arm64, 8 logical CPUs, 8 GiB RAM, macOS 26.5.2. Python 3.12.10,
FastAPI 0.141.1, Uvicorn 0.52.2, HTTPX 0.28.1, Psycopg 3.3.4 / Pool 3.3.1.
Docker Desktop 27.3.1 with an 8-CPU, 3.83 GiB VM. Task-owned PostgreSQL 16.10
(`postgres:16-alpine`) at `127.0.0.1:55432`. Port 5432 never inspected or
modified. All traffic local loopback with the deterministic synthetic
`p1-scale-fixture-v1` workload.

## 2. Forensic explanation of the postfix scheduler failure

The full forensic note, separated into proven fact, supported inference, and
unresolved question, is in the
[closeout protocol](P1_S4_TERMINAL_CLOSEOUT_PROTOCOL.md) §2. Summary:

1. Postfix run 1 was driven by `scripts/run_p1_s4f_state_store_diagnostic.py`
   from source `b6e4bb3` with `--attempts` defaulting to 3, with the S4f
   state-store diagnostic, its PostgreSQL sampler, and client timing all on.
2. **The prior evidence's account was incomplete.** Retained artifact
   `p1-s4f-reproduction-1788169650.json` shows attempt 1 *passed* every frozen
   gate: 900/100 responses, 700 original / 200 replay, audit growth 70/700,
   chain verified, 100% connection reuse, queue p99 12.3143 ms against a
   26.8471 ms limit. Its `decision` and `cleanup` blocks are absent, which
   proves the invocation aborted in a *later* attempt, not the first.
3. The abort discarded all evidence because `_validate_harness_gates` raised a
   bare `ScaleBenchmarkError`, while every persistence path — the driver, the
   S4f runner, and `main()` — catches only `BenchmarkValidationError`. Every
   aggregate already existed in the completed record; nothing wrote it.
4. The gate is `max(10 ms, 5% of measured E2E p50)`, so it tightens toward its
   10 ms floor exactly when the service gets faster, while client-side dispatch
   cost is unchanged. Across the retained S4e matrix, scheduler queue p99 at
   concurrency 64 already ranged 5.116–17.7096 ms in otherwise passing cells.
5. Diagnostic-induced perturbation is **not** established as the cause. The
   retained passing attempt ran with the diagnostic enabled.

The exact queue p99, limit, and correctness counts of the aborted attempt are
unrecoverable and are not inferred anywhere in this document.

## 3. Repair status

The repair at `f4d38c2` is unchanged and remains supported. Verified by code
inspection and deterministic regression:

- completion admission occurs before pool checkout — the gate is acquired in
  `_completion_connection` before `_connection(pool)`;
- at most one active completion checkout per store/worker — the deterministic
  regression launches 32 concurrent completion admissions and requires no more
  than one active completion checkout;
- reservation and replay paths are not serialized — `reserve` uses the plain
  `_connection` path, and the gate appears only in the `complete_outcome` path;
- public API route, body, headers, schema, and database schema are unchanged;
- fail-closed behaviour, audit semantics, and idempotency semantics intact.

No pool size, timeout, retry count, worker count, concurrency, PostgreSQL
setting, Uvicorn setting, model, threshold, dataset, feature schema, request
mix, or gate was changed at any point in this closeout.

## 4. Harness qualification

Smoke qualification at one worker / concurrency 8 passed with the S4f
diagnostic disabled:

| Gate | Observed |
| --- | ---: |
| Maximum outstanding / configured limit | 8 / 8 |
| Measured connection reuse | 100% (0 new, 10 reused) |
| Scheduler queue p99 / limit | 1.2592 ms / 10 ms |
| Per-request client setup max | 0.0 ms, count equals attempted |
| Client constructed before warm-up | Yes |
| Warm-up / measured audit growth | 7 / 7, chain verified |
| Diagnostic recording failures | 0 |
| Per-request timing arrays persisted | None |

Machine health before: 1-minute load average 5.53, 28% free memory, no thermal
warning. After: 4.99, 27% free, no thermal warning. Port 55432 closed after the
run.

## 5. Postfix proof results — 3 of 3 passed

Artifact `p1-s4-postfix-1788172334.json`, decision
`POSTFIX_PROOFS_PASSED_MATRIX_AUTHORIZED`. Workers 4, concurrency 64, repeat 2,
S4f state-store diagnostic disabled, S4f PostgreSQL sampler not started, S4e
resource sampler unchanged.

| Gate | Proof 1 | Proof 2 | Proof 3 |
| --- | ---: | ---: | ---: |
| Measured HTTP 200 / expected 422 | 900 / 100 | 900 / 100 | 900 / 100 |
| Server original / server replay | 700 / 200 | 700 / 200 | 700 / 200 |
| Unexpected non-2xx | 0 | 0 | 0 |
| `state_store_unavailable` / `idempotency_failed` | 0 / 0 | 0 / 0 | 0 / 0 |
| `idempotency_in_progress` | 0 | 0 | 0 |
| Client timeout / transport error | 0 / 0 | 0 / 0 | 0 / 0 |
| Warm-up / measured audit growth | 70 / 700 | 70 / 700 | 70 / 700 |
| Full-chain verification | Pass | Pass | Pass |
| Scheduler queue p99 (ms) | 11.3735 | 13.3655 | 14.6820 |
| Scheduler queue limit (ms) | 30.7866 | 33.8907 | 27.4810 |
| Measured connection reuse | 100% | 95.1% | 96.6% |
| Maximum outstanding / limit | 64 / 64 | 64 / 64 | 64 / 64 |
| Per-request client setup max (ms) | 0.0 | 0.0 | 0.0 |
| Measured E2E p50 (ms) | 615.733 | 677.813 | 549.619 |
| Successful RPS | 89.369 | 70.423 | 102.916 |
| Machine health M1–M3 | Valid | Valid | Valid |

All three independently satisfied every frozen invariant. Connection reuse in
proofs 2 and 3 passed the 95% gate with little margin (95.1% and 96.6%), which
is recorded as measured variability rather than smoothed over.

## 6. 36-cell matrix — failed closed at cell 10

Artifacts `p1-s4e-full-1788172447-progress.json` (9 completed cells) and
`p1-s4e-full-1788172447-partial.json` (preserved failure). The run stopped at
the first correctness failure exactly as pre-registered.

Failing cell: workers 1, concurrency 64, repeat 1, measured phase.

| Observation | Result |
| --- | ---: |
| HTTP 200 / expected 422 / HTTP 503 | 868 / 100 / 4 |
| Structured 503 code | `idempotency_in_progress` (4) |
| Structured category | `idempotency_reservation` (4) |
| Client timeouts | 28 |
| Transport errors | 0 |
| Invalid contracts | 4 |
| Unexpected-response latency p50 / max (ms) | 7008.452 / 7676.060 |
| Audit events / full-chain verifier | 770 / verified |

The failure is **not** `state_store_unavailable`: the repaired P1-S4f defect did
not recur. `idempotency_in_progress` is not expected by the frozen protocol, so
this is a genuine correctness gate failure.

The failure artifact exists only because of the evidence-preservation repair
committed in this closeout; under the previous code this run would have aborted
with no artifact at all.

Nine cells completed before the failure. Their aggregates are retained but are
**not** valid scaling evidence, for two independent reasons: the matrix is
incomplete, and host conditions degraded materially during the run. Two
`ResourceSampler` PostgreSQL threads died with
`subprocess.TimeoutExpired` after `docker exec` exceeded 5 seconds, and the
1-minute load average reached 13.96 by the end of the run against a pre-run
sample of 5.11.

**This run is not declared environmentally invalid.** The closeout protocol
measures M1 once before the run, and the matrix path has no per-cell
machine-health criterion. Inventing one after seeing the result is exactly what
the protocol forbids. The matrix is therefore recorded as a genuine failure.

Comparison with historical P1-S1 is limited to its documented purpose: the
legacy per-request-client harness is `HARNESS-CONSTRAINED / NOT SERVER-SCALING
EVIDENCE` and cannot support server-scale claims. Legacy and corrected
measurements are never merged, and no RPS or latency comparison across the two
harnesses is published here.

## 7. Rule-A classification reproduction

Artifact `p1-s4-classify-1788173022.json`, `diagnostic_kind`
`p1_s4_rule_a_classification`, `publishable_as_proof: false`. One controlled
reproduction of the exact failing cell (workers 1, concurrency 64) with the
opt-in state-store diagnostic enabled, on a settled host (1-minute load average
3.94 before, 4.50 after).

| Observation | Result |
| --- | ---: |
| HTTP 200 / expected 422 / unexpected non-2xx | 900 / 100 / 0 |
| Server original / server replay | 700 / 200 |
| Client timeout / transport error | 0 / 0 |
| Warm-up / measured audit growth | 70 / 700 |
| Full-chain verification | Pass |
| Scheduler queue p99 / limit (ms) | 4.4127 / 40.4550 |
| Measured connection reuse | 100% |
| Measured E2E p50 (ms) / successful RPS | 809.101 / 86.516 |

**The failure did not reproduce and no new root cause was proven.** Under
decision rule A this authorizes no repair cycle, and the matrix was not rerun:
re-running a failed proof until it passes is explicitly prohibited.

The `decision` field in this artifact reads
`POSTFIX_PROOF_FAILED_NO_SCALE_CLAIM` because the runner's decision label
requires three passing proofs and this run requested one. The label is an
artefact of running the tool in classification mode; the recorded per-run result
is `passed`. The terminal verdict rests on the matrix failure, not on this
label.

## 8. 10,000-event audit-growth stage — NOT RUN

The frozen protocol authorizes the 100/1,000/10,000-event audit-growth stage
only after all 36 matrix cells are valid. The matrix failed at cell 10, so
`_run_audit_growth` was never reached. No audit-growth measurement, no
constant-time append claim, and no complexity claim of any kind is made from
this closeout. Earlier audit-growth evidence remains historical only.

## 9. Verification

| Check | Result |
| --- | --- |
| New focused closeout tests | PASS — 14 passed |
| Focused harness, timing, S4f diagnostic, idempotency, audit, concurrency tests | PASS — 126 passed |
| State-store repair regression | PASS — 2 passed |
| Fresh task-owned PostgreSQL S2/S3 integration suite | PASS — 22 passed |
| Full Python suite | 1,404 passed, 21 skipped, 2 failed |
| Ruff over `api`, `src`, `scripts`, `tests` | PASS |
| Canonical plus closeout Mypy set | PASS — 33 source files |
| Python compilation (`compileall`) | PASS |
| `pip check` | PASS — no broken requirements |
| Closeout documentation links | PASS — 3 checked, 0 failures |
| Artifact schema and privacy scan | PASS — 6 artifacts, 0 forbidden fields, 0 per-request arrays |
| `git diff --check` | PASS |

### Known unrelated failures

The two full-suite failures are the same preserved, unrelated working-tree
conditions recorded in P1-S4e and P1-S4f, neither edited nor staged here:

1. `tests/test_package_recovered_demo_bundle.py` — the untracked recovered-demo
   packager constructs `ModelBundle` without three now-required metadata
   arguments;
2. `tests/test_project_setup.py::test_readme_separates_reference_corpus_new_development_and_audit_modes`
   — the unchanged README omits an older `--source-kind
   historical_kaggle_reference` assertion.

## 10. Cleanup

Every task-owned API process group, PostgreSQL container, volume, schema, role,
credential, raw log, and temporary directory was removed after aggregate
capture. Zero containers remain under label `secureswipe.task=p1-s4` and zero
task volumes remain. Port 55432 is closed. Port 5432 was never inspected or
modified.

Two pre-existing containers, `secureswipe-overflow-diag-0569aa8` (up 3 days) and
`secureswipe-api-final-local` (up 11 days), predate this session, are unrelated
to it, and were left untouched. They contribute to the host load against which
these measurements were taken.

All unrelated untracked paths are preserved exactly as found. Nothing was
pushed, deployed, or published.

## 11. Claim ledger

### Authorized wording

> SecureSwipe reproduced and repaired a PostgreSQL state-store connection
> checkout-exhaustion defect, and verified the repair with deterministic
> regressions, a fresh PostgreSQL integration suite, and three consecutive
> pre-registered load proofs at the exact four-worker, concurrency-64 cell that
> previously failed. A subsequent full 36-cell benchmark matrix failed closed on
> an unrelated correctness gate, so no multi-worker scalability or
> production-capacity claim is made.

Specific figures that may be cited, always with the environment named and always
as environment-specific:

- three postfix proofs at four workers and concurrency 64, each reconciling
  exactly 900 successful and 100 validation-error responses, 700 original and
  200 replay responses, zero unexpected 503, zero timeout, zero transport error,
  audit growth of 70 and 700 events, and full audit-chain verification;
- measured connection reuse of 100%, 95.1%, and 96.6% across those proofs;
- the repair reduced observed database lock waiting from up to 14 waiting locks
  to at most 2 at the same cell.

Every such statement must carry: measured on one Apple M2 host over local
loopback, against a task-owned PostgreSQL 16.10 instance, using a deterministic
synthetic fixture, at the named commit.

### Prohibited claims

Not authorized under any reading of this evidence:

- Razorpay production scale, or any production-scale comparison;
- global or horizontal scalability, worker scaling, or flat-scaling conclusions;
- 1,000 or 10,000 RPS, or any throughput or capacity figure as a system
  capability;
- production SLOs, latency targets, or availability commitments;
- multi-region behaviour or external-network performance;
- merchant savings, ROI, or cost results;
- global `O(1)` event sourcing, or any system-wide complexity claim;
- constant-time audit append, since the audit-growth stage did not run;
- real-world fraud-detection probability or held-out detection quality;
- autonomous payment authorization.

The nine completed matrix cells must not be quoted as performance evidence. The
legacy P1-S1 matrix remains `HARNESS-CONSTRAINED / NOT SERVER-SCALING EVIDENCE`.

## 12. Handoff

P1-S4 infrastructure work is complete and frozen. The repair is preserved with
positive deterministic and load evidence; the scale claim is withheld with
preserved negative evidence. No P1-S4g or successor diagnostic task is created
or proposed.

READY FOR README AND ARCHITECTURE REFINEMENT — SCALE CLAIMS FROZEN
