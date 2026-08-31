# P1-S4f state-store verification evidence

Verdict: **DIAGNOSTIC OR CORRECTNESS GATE FAILED**

P1-S4f reproduced and classified the P1-S4e service failure, then applied one
minimal connection-lifecycle repair. The repair and focused PostgreSQL
regressions passed, but the first pre-registered postfix load run failed the
unchanged S4e scheduler-queue harness gate. The protocol therefore stopped
before postfix runs two and three, the 36-cell matrix, and the 10,000-event
audit-growth stage. P1-S4 remains incomplete and no worker-scaling claim is
authorized.

## 1. Identity

| Item | Identity |
| --- | --- |
| P1-S4e evidence commit | `fe4a7c78fc053819f37ab9d7395175e6d3c02ea6` |
| P1-S4f diagnosis protocol commit | `41f4e70d41934f150b88b869d9bead1a0a7459a7` |
| [Diagnosis protocol](P1_S4F_STATE_STORE_DIAGNOSIS_PROTOCOL.md) SHA-256 | `a214287636ffd05b5ad685eaa8cf84b930a2c829f7bbaccf34d94aa558d28d5f` |
| Valid reproduction source | `749dc7dcbdb5bbe5bf97ac13d70b1a703ebf3196` |
| Reproduction artifact | `reports/benchmarks/p1-scale-results/p1-s4f-reproduction-1788168873.json` |
| Reproduction artifact SHA-256 | `a9a75f9c58ba9580c27a7dc60bed05eeabfd04120fe0ffc275cd3347ae162f11` |
| State-store repair commit | `f4d38c249045796f05815aac6c244d6432cf703a` |
| Postfix protocol commit / attempt source | `b6e4bb3a81c7b5f8c30b13fde2b8da33d7dc6bd8` |
| [Postfix protocol](P1_S4F_POSTFIX_VERIFICATION_PROTOCOL.md) SHA-256 | `2961ac242fd0a4199dc6015d8b12023030c023456f0a0cdf025fd15d759dd74a` |
| Model fingerprint | `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3` |

P1-S4b/c/d/e evidence remains preserved and unchanged. P1-S4e's validated
persistent-client and bounded-scheduler design remains the required harness;
its incomplete performance numbers remain invalid for scaling claims.

## 2. Original failure boundary

P1-S4e stopped at workers 4 / concurrency 64 / repeat 2:

| Observation | P1-S4e result |
| --- | ---: |
| HTTP 200 / expected HTTP 422 / HTTP 503 | 848 / 100 / 52 |
| Structured HTTP 503 code | `state_store_unavailable` |
| Client timeout / transport error | 0 / 0 |
| Audit events | 726 |
| Full-chain verification | Pass |

The cell was not retried. Repeat 3 and the separate 10,000-event audit-growth
stage were not run. The valid audit chain contained only committed events, but
the frozen exact response and audit-growth contract failed.

## 3. Diagnostic activation and qualification

The state-store diagnostic activates only for the exact value
`SECURESWIPE_P1_S4F_STATE_STORE_DIAGNOSTIC=1`. Missing, blank, `0`, `true`, or
any other value creates no collector. It records per-process aggregate counts,
duration distributions, sanitized categories/SQLSTATEs, and failure-boundary
pool counters. It never accepts exception text, DSNs, credentials, SQL,
request identifiers, bodies, features, scores, labels, PAN, CVV, or raw
database/audit content.

Before the valid reproduction, three diagnostic-wrapper defects were found and
fixed without treating their runs as evidence:

1. direct execution initially lacked the repository import path;
2. the wrapper initially omitted the already-required exact S4e client-timing
   flag; and
3. success-path file flushes and pool-stat queries perturbed the scheduler gate.

The final diagnostic persists failures immediately and successful aggregates
only at graceful close/exit. Pool counters are sampled only at a failure
boundary; a separate task-owned read-only PostgreSQL sampler records server
aggregates. Unit tests prove the opt-in, allowlists, safe persistence, and inert
success path.

## 4. Controlled reproduction

Three independent fresh attempts used four workers, concurrency 64, repeat 2,
the unchanged persistent client, 70/20/10 warm-up, 700/200/100 measured mix,
ten-second client timeout, model fingerprint, pool settings, and PostgreSQL
16.10 at `127.0.0.1:55432`.

| Attempt | HTTP result | Audit growth | Chain | Decision |
| ---: | --- | --- | --- | --- |
| 1 | Warm-up 90/10; measured 900/100 | 70 / 700 | Pass | Correctness passed |
| 2 | Warm-up 90/10; measured 900/100 | 70 / 700 | Pass | Correctness passed |
| 3 | Measured 834×200, 100×422, 66×503 | 720 total events | Pass | Failure reproduced |

Attempt 3 produced 56 `state_store_unavailable` and 10 subsequent
`idempotency_failed` responses. Across all four workers, the earliest low-level
failure stage was `connection_checkout`:

| Aggregate | Observed |
| --- | ---: |
| Checkout failures categorized `checkout_timeout` | 56 |
| Reserve operations ending in checkout timeout | 33 |
| Completion/outcome operations ending in checkout timeout | 23 |
| SQLSTATEs | None; timeout occurred in the client-side pool |
| Per-worker pool size / available at failure | 4 / 0 |
| Waiting checkout requests at failure | 4–20 |

PostgreSQL remained healthy during the failing attempt:

- 155 successful readiness samples and zero sampler failures;
- at most 16 task connections against `max_connections=100`;
- up to 14 waiting database locks, consistent with contention on the one
  transactional audit-chain head;
- zero postmaster restart, fatal-session, killed-session, or abandoned-session
  evidence; and
- explicit full-chain verification passed for all 720 committed events.

This rejects PostgreSQL connection refusal, server restart, global connection
exhaustion, client transport failure, and corrupt audit-chain alternatives.
The supported cause is per-worker pool starvation: completion transactions
acquired all four local pool connections and then waited for the globally
serialized audit-chain head, leaving later reservations/completions to hit the
unchanged two-second pool checkout boundary.

## 5. Minimal repair

Commit `f4d38c2` adds one per-worker completion gate before pool checkout. The
audit-chain head already enforces one global completion transaction at a time;
the repair moves redundant same-worker waiting outside the pool so a worker no
longer occupies all four connections while waiting on that head.

The repair does not change:

- pool minimum/maximum size or any timeout;
- retry, worker, concurrency, queue-depth, PostgreSQL, Uvicorn, fsync,
  database-lock-policy, or operating-system setting;
- request mix, model, threshold, scoring, audit, idempotency, or fail-closed
  semantics;
- API route, body, header, schema, database schema, or public behavior; or
- the benchmark harness.

The deterministic regression launches 32 concurrent completion admissions and
requires a maximum of one completion checkout in that store. Reservations and
completed replay reads do not use the gate. Fresh S2/S3 PostgreSQL integration
tests preserve one outcome/event, exact replay, conflict/failure behavior, and
full-chain verification.

## 6. Postfix gate result

The postfix protocol binds repaired source `f4d38c2`. Measurement ran from its
documentation-only descendant `b6e4bb3`, which adds only the committed postfix
protocol.

The first fresh four-worker/concurrency-64 postfix invocation completed far
enough to reach the unchanged S4e harness validator, then failed:

```text
S4e scheduler queue p99 exceeds the pre-registered harness gate.
```

The generic harness gate stopped before a safe result artifact was emitted, so
its exact queue p99 and correctness aggregate are unavailable and are not
inferred. This run is invalid evidence. Under the pre-registered stop rule:

- postfix runs 2 and 3: **NOT RUN**;
- final 36-cell matrix: **NOT RUN**; and
- 100/1,000/10,000-event audit-growth stage: **NOT RUN**.

No run was retried, selected, tuned, or replaced after this postfix gate. The
root-cause repair remains supported by the deterministic and PostgreSQL
regressions, but three-run load proof is absent.

## 7. Verification

| Check | Result |
| --- | --- |
| Focused diagnostic/state-store/idempotency/audit/API/benchmark tests | PASS — 175 passed |
| Fresh PostgreSQL S2/S3 integration tests | PASS — 22 passed |
| Ruff over `api`, `src`, `scripts`, and `tests` | PASS |
| Canonical and S4f Mypy set | PASS — 29 source files |
| Python compilation | PASS |
| `pip check` | PASS — no broken requirements |
| Diagnosis/postfix documentation links | PASS — 3 checked, zero failures |
| P1-S4e/P1-S4f aggregate artifact privacy validation | PASS — 2 checked |
| `git diff --check` | PASS |
| Full Python suite | 1,390 passed, 21 skipped, 2 failed, 655 warnings |

The two full-suite failures are the preserved unrelated conditions authorized
for this task: the untracked recovered-demo packager uses an obsolete
`ModelBundle` constructor, and the unchanged README lacks an older project
setup assertion for `--source-kind historical_kaggle_reference`. Neither path
was edited or staged.

## 8. Claim boundary and status

P1-S4 is **not complete**. No worker-scaling, throughput, capacity, production,
SLO, external-network, multi-region, Razorpay-scale, savings, ROI, or cost claim
is authorized. No P1-S4g is created or proposed.

All P1-S4f traffic was local loopback on one Apple M2 host using synthetic-only
inputs. It does not establish held-out fraud-detection quality or production
fitness. Core XGBoost scoring uses zero LLM tokens.

## 9. Cleanup

Every task-owned API process, PostgreSQL container, volume, schema,
role/credential, raw log, and temporary diagnostic was removed after aggregate
capture. Port 55432 was closed after each run. Port 5432 was never inspected or
modified. Existing ignored artifacts and unrelated untracked paths remain
preserved; nothing was pushed or deployed.
