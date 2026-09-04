# Build challenges

This page is the readable narrative of the hardest engineering problem in
SecureSwipe. It summarises, and does not replace, the forensic records in
[`docs/benchmarks/`](benchmarks/) — every figure below is sourced in
[§ Source index](#source-index).

The short version: a load benchmark fail-closed, the obvious fix would have
hidden the defect, the instruments proved my own test harness was the dominant
cost, and the task ultimately closed **without** the scaling claim it was
created to establish.

---

## 1 — The failure

After landing durable PostgreSQL idempotency and a transactional audit chain, the
frozen 36-cell load matrix ran 34 cells and then fail-closed at four workers /
concurrency 64, with 52 requests returning `state_store_unavailable`.

Two problems, not one. The service had a real defect, and the harness could not
describe it: results were persisted only after the final cell, so the run aborted
with no artifact at all, and unexpected responses were recorded as bare HTTP
statuses. Because the frozen status and audit counts did not reconcile, the run
was recorded as a correctness failure and **no performance matrix or
worker-scaling conclusion was authorised** from it.

## 2 — The repair I did not make

The available fix was to widen the connection pool, add a retry, and re-run until
green.

That was wrong, and it was possible to know so before collecting any data. The
waiters were not *short* of connections — they were *holding* connections while
queued behind the audit chain head. That head is a single serialized writer, and
in a fraud system it is not an inefficiency to be tuned away: it is the property
that makes a decision reconstructable after the fact. Widening the pool would
have raised the throughput number by admitting more work into the same queue,
while removing the serialization would have improved the metric by deleting the
product.

Neither is a fix. Both are ways of not finding out.

## 3 — Instrumenting instead

Three changes, in order:

1. **Evidence preservation** — persist safe partial results and structured
   failure detail so a fail-closed run leaves a usable artifact.
2. **Request lifecycle timing** — attribute each request across executor queue,
   client setup, TCP connect, send, and response headers.
3. **Critical-section timing** — measure time spent *waiting for* the chain-head
   lock separately from time spent *holding* it, because those two have
   different remedies and aggregate throughput cannot distinguish them.

## 4 — The harness was the dominant cost

The instruments contradicted the premise of every measurement taken to that
point. Same-request median ratios:

| Cell (workers / concurrency / repeat) | Executor queue ÷ scheduled total | Client setup ÷ E2E |
| --- | ---: | ---: |
| 1 / 8 / 1 | 98.443% | 73.751% |
| 4 / 32 / 1 | 93.544% | 83.681% |
| 4 / 64 / 1 | 87.155% | 80.695% |
| 4 / 64 / 2 | 89.008% | 82.315% |

Between 87% and 98% of each request's scheduled lifetime was queueing inside the
load generator, and per-request client construction accounted for 74–84% of
median end-to-end. Every measured request opened a new connection: 1,000 new,
zero reused, in every cell.

The harness was rebuilt around one shared persistent client per cell, created
before warm-up, gated on ≥95% measured connection reuse. Every earlier
performance number was retired as `HARNESS-CONSTRAINED / NOT SERVER-SCALING
EVIDENCE` rather than quietly reused, and legacy and corrected measurements are
never merged or compared.

## 5 — The real defect

With a valid harness the failure reproduced and resolved to a specific mechanism.
Earliest failure stage `connection_checkout`:

| Observation | Value |
| --- | ---: |
| Checkout failures categorised `checkout_timeout` | 56 |
| Reserve / completion operations ending in checkout timeout | 33 / 23 |
| Per-worker pool size / available at failure | 4 / 0 |
| Waiting checkout requests at failure | 4–20 |
| SQLSTATEs | none — timeout occurred in the client-side pool |

PostgreSQL was **ruled out rather than assumed**: 155 successful readiness
samples with zero sampler failures, at most 16 task connections against
`max_connections=100`, and zero postmaster restarts, fatal sessions, killed
sessions, or abandoned sessions. That evidence rejects connection refusal, server
restart, and global connection exhaustion, and leaves per-worker pool starvation
as the supported cause: completion transactions acquired all four of a worker's
local pool connections and then waited on the globally serialized audit head,
against an unchanged two-second checkout boundary.

## 6 — The fix

One per-worker gate that makes completions wait **before** pool checkout instead
of after, so redundant same-worker waiting happens outside the pool. Unchanged:
pool minimum and maximum size, every timeout, retry policy, worker and
concurrency configuration, queue depth, PostgreSQL configuration, schema, audit
semantics, idempotency semantics, and all public behaviour.

Supporting evidence:

- a deterministic regression launching 32 concurrent completion admissions and
  requiring at most one completion checkout in the store;
- fresh PostgreSQL integration tests (22 passed) and the focused suite
  (175 passed), with ruff, mypy, compilation, and `pip check` clean; and
- three consecutive load proofs at the exact cell that had failed, all three
  satisfying every frozen invariant.

The connection-reuse gate is worth stating precisely: proofs 2 and 3 cleared the
95% threshold at **95.1% and 96.6%** — thin margins, recorded as measured
variability rather than smoothed over.

Note the intermediate step that did *not* succeed: the first bound postfix run
failed the unchanged scheduler-queue harness gate before emitting a safe
artifact. Under the pre-registered stop rule it was recorded as invalid evidence
and postfix runs 2 and 3 were **not run**. No run was retried, selected, tuned,
or replaced to obtain a better one.

## 7 — What was not claimed

The repaired defect did not recur. The frozen 36-cell matrix nonetheless failed
closed at its **tenth cell**, on a different gate — four `idempotency_in_progress`
responses, a structured outcome the frozen protocol does not expect, and
therefore a genuine correctness failure. The single authorised reproduction did
not reproduce it and proved no new root cause, so no further repair cycle was
justified.

During that run the host degraded materially: the one-minute load average reached
13.96 against a pre-run sample of 5.11, and two `ResourceSampler` PostgreSQL
threads died on `subprocess.TimeoutExpired`. The run was **not** declared
environmentally invalid. The closeout protocol measures machine health once
before the run and defines no per-cell criterion, and inventing one after seeing
the result is precisely what the protocol forbids. The matrix is recorded as a
genuine failure, and the nine completed cells are retained but explicitly are not
valid scaling evidence.

P1-S4 therefore closed as **CLOSED WITHOUT SCALE CLAIM — EVIDENCE INSUFFICIENT OR
GATES FAILED**. No multi-worker scaling or throughput claim appears anywhere in
this repository, and no successor task was created to keep chasing one.

Throughout, the failure mode stayed correct: the service returned 503 and refused
to decide rather than emitting a decision it could not audit.

## 8 — Smaller obstacles

**arm64 container builds.** Under QEMU user-mode emulation on GitHub-hosted
runners the container reaches `Waiting for application startup.` and never
completes startup, so the smoke readiness loop exhausts. It reproduced
deterministically three times and did not reproduce on native arm64 or
Rosetta-emulated amd64, and was not root caused. A speculative thread-pinning
change was written, tested, and then **reverted rather than shipped on an
unproven diagnosis**. The release target is scoped to `linux/amd64` and arm64 is
documented as deferred; no multi-architecture support is claimed.

**A gate that failed on identical samples.** A benchmark gate rejected runs whose
samples were the same, caused by 4-decimal aggregation compared against 3-decimal
publication. The rounding was reconciled — not the threshold.

**An unfixed SQLite CVE.** Recorded as a bounded, demo-only disposition with an
explicit scope rather than suppressed or ignored.

---

## Source index

| Claim | Source |
| --- | --- |
| 34 cells, fail-close, no authorised matrix | [P1 scale harness](benchmarks/P1_SCALE_HARNESS.md) · [S4e evidence](benchmarks/P1_S4E_VALIDATED_HARNESS_EVIDENCE.md) |
| Transport attribution ratios, connection reuse | [S4d client transport evidence](benchmarks/P1_S4D_CLIENT_TRANSPORT_EVIDENCE.md) |
| Checkout timeouts, pool state, PostgreSQL exclusion, repair, 3 proofs | [S4f state-store verification](benchmarks/P1_S4F_STATE_STORE_VERIFICATION_EVIDENCE.md) · [terminal closeout](benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md) |
| Matrix failure at cell 10, host degradation, terminal verdict | [terminal closeout](benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md) |
| arm64 disposition | [submission package](evidence/SUBMISSION_PACKAGE.md#container-architecture-scope) |

The repair and evidence-preservation commits are identified by hash in the
[S4f verification record](benchmarks/P1_S4F_STATE_STORE_VERIFICATION_EVIDENCE.md)
and the [terminal closeout record](benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md).
