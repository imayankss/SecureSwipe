# P1-S4 terminal closeout: forensic note and pre-registered protocol

Status: **pre-registered before terminal measurement**

This document closes P1-S4. It is a protocol amendment and final closeout, not a
new diagnostic phase. It inherits every workload, privacy, cleanup, correctness,
and claim rule from the
[validated P1-S4e harness protocol](P1_S4E_VALIDATED_HARNESS_PROTOCOL.md), the
[P1-S4f diagnosis protocol](P1_S4F_STATE_STORE_DIAGNOSIS_PROTOCOL.md), and the
[P1-S4f postfix verification protocol](P1_S4F_POSTFIX_VERIFICATION_PROTOCOL.md).

No successor task (P1-S4g or later) is created or proposed. At completion P1-S4
reaches exactly one of two terminal states:

1. `VALIDATED — MEASURED SCALE EVIDENCE AVAILABLE`; or
2. `CLOSED WITHOUT SCALE CLAIM — EVIDENCE INSUFFICIENT OR GATES FAILED`.

## 1. Bound identity

| Item | Bound value |
| --- | --- |
| Closeout branch | `codex/p1-core-checkpoint` |
| `HEAD` at closeout start | `8951e1a1cf76f15f15aa81f04ca96bc1d0d77c26` |
| Repaired state-store source | `f4d38c249045796f05815aac6c244d6432cf703a` |
| Prior postfix attempt source | `b6e4bb3a81c7b5f8c30b13fde2b8da33d7dc6bd8` |
| P1-S4e protocol SHA-256 | `d40ef3e36bdd7fb2f0a26df494fddaca11b92698383893fd5811cd4f64ecf062` |
| P1-S4f diagnosis protocol SHA-256 | `a214287636ffd05b5ad685eaa8cf84b930a2c829f7bbaccf34d94aa558d28d5f` |
| P1-S4f postfix protocol SHA-256 | `2961ac242fd0a4199dc6015d8b12023030c023456f0a0cdf025fd15d759dd74a` |
| Model fingerprint | `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3` |
| Fixture | `p1-scale-fixture-v1`, deterministic synthetic only |
| PostgreSQL | task-owned `postgres:16-alpine` at `127.0.0.1:55432` only |

Port 5432 is never inspected or modified. All nine referenced P1-S4e/P1-S4f
commits were verified present and ancestors of `HEAD` before this protocol was
written.

## 2. Forensic note on the failed postfix proof

This section separates proven fact, supported inference, and unresolved
question. It was written before any new measurement.

### 2.1 Proven fact

1. **Invocation.** Postfix run 1 was driven by
   `scripts/run_p1_s4f_state_store_diagnostic.py` from source `b6e4bb3`, the
   documentation-only descendant of repair `f4d38c2`. That runner is the only
   single-cell entry point for workers 4 / concurrency 64 / repeat 2, and its
   `--attempts` default is `MAX_ATTEMPTS = 3`.
2. **Instrumentation was fully enabled.** The runner unconditionally sets
   `SECURESWIPE_P1_S4F_STATE_STORE_DIAGNOSTIC=1`,
   `SECURESWIPE_P1_S4F_STATE_STORE_DIAGNOSTIC_OUTPUT_DIR`, and
   `SECURESWIPE_SCALE_CLIENT_TIMING=1`, and starts an additional
   `PostgresAggregateSampler` thread that issues catalog queries every 100 ms
   for the whole run.
3. **The unchanged S4e harness already runs two 10 Hz samplers.**
   `ResourceSampler` in `_run_repeat` spawns `ps -axo ...` and
   `docker exec <container> sh -c ...` every 100 ms for the duration of every
   measured phase. These are subprocess spawns on the measuring host, not
   in-process counters.
4. **The scheduler-queue gate is adaptive, not fixed.**
   `_validate_harness_gates` computes
   `queue_limit_ms = max(10.0, request_e2e_p50_ms * 0.05)` and fails when
   `scheduler_queue_wait_ms.p99 > queue_limit_ms`. The 10 ms floor dominates
   whenever measured E2E p50 is below 200 ms.
5. **`scheduler_queue_wait_ms` measures client-side dispatch only.** It is the
   interval from `ClientRequestTimer.submitted_now()` — taken immediately before
   `executor.submit` — to the `task_started` mark set as the first action inside
   the worker thread. It contains no server, database, or network time.
6. **Failure-artifact loss is a structural code defect, not a policy.**
   `_run_repeat` catches `BenchmarkValidationError` and enriches it with safe
   diagnostics, and both `run_harness` and the S4f runner persist that class.
   `_validate_harness_gates` instead raises a bare `ScaleBenchmarkError`, and it
   is invoked *after* the `except BenchmarkValidationError` block. No handler in
   `run_harness`, `main`, or the S4f runner catches it. The run therefore aborts
   with no aggregate artifact even though every aggregate already exists in the
   completed `record`.
7. **A post-repair run at the failed cell passed every frozen gate, and was
   retained.** Artifact
   `reports/benchmarks/p1-scale-results/p1-s4f-reproduction-1788169650.json`
   (SHA-256 `b0a94e6bb1deaa5f241d29a3003ad98fe23c74d103e27a06ae0b6e5b2e67ac08`),
   recorded at source `b6e4bb3`, contains one attempt at workers 4 /
   concurrency 64 / repeat 2 with:

   | Observation | Value |
   | --- | ---: |
   | Measured HTTP 200 / expected HTTP 422 | 900 / 100 |
   | Unexpected non-2xx / timeouts / transport errors | 0 / 0 / 0 |
   | Server original / server replay responses | 700 / 200 |
   | Warm-up / measured audit growth | 70 / 700 |
   | Full-chain verification | verified |
   | Measured connection reuse | 100% (0 new, 1000 reused) |
   | Maximum outstanding / limit | 64 / 64 |
   | Per-request client setup max | 0.0 ms |
   | Scheduler queue p99 / limit | 12.3143 ms / 26.8471 ms — passed |
   | Measured E2E p50 | 536.942 ms |
   | Harness validation status | `passed` |

   The artifact carries no `decision` and no `cleanup` block. Both are written
   only after the attempt loop completes, which proves the invocation aborted in
   a later attempt of the same run rather than in this one.
8. **The repair measurably reduced database-side contention.** In the same
   artifact the task PostgreSQL sampler observed at most 2 waiting locks and at
   most 6 active connections, against up to 14 waiting locks and per-worker pool
   exhaustion (size 4, available 0) in the pre-repair reproduction
   `p1-s4f-reproduction-1788168873.json`.

### 2.2 Supported inference

1. The aborted attempt was attempt 2 or 3 of the same three-attempt invocation.
   Attempt 1 was persisted and passed; a later attempt raised
   `ScaleBenchmarkError` from `_validate_harness_gates`, which is unhandled and
   suppressed both the remaining attempts and the final `decision`/`cleanup`
   write.
2. The failure is most consistently explained by client-side dispatch variance
   on a saturated measuring host, not by a service or database defect. At
   concurrency 64 the retained S4e matrix shows scheduler queue p99 ranging from
   5.116 ms to 17.7096 ms across otherwise passing cells, so this metric is
   already within a factor of two of the 10 ms floor before any repair.
3. Host oversubscription is the mechanism. Eight logical CPUs are shared by 64
   client threads, four Uvicorn workers, the Docker Desktop VM hosting
   PostgreSQL, and three 10 Hz sampler threads, two of which spawn subprocesses.
4. The gate is coupled to server latency in a direction that penalises
   improvement: because the limit is `max(10 ms, 5% of E2E p50)`, any repair that
   lowers measured E2E p50 tightens the harness gate toward its 10 ms floor while
   client-side dispatch cost is unchanged.

### 2.3 Unresolved question

1. The exact scheduler queue p99, queue limit, correctness counts, and audit
   growth of the aborted attempt are unrecoverable. They are not inferred, not
   reconstructed, and not reported anywhere in this closeout.
2. Whether the aborted attempt would have failed a correctness gate as well as
   the harness gate cannot be determined, because the harness gate is evaluated
   after correctness and aborted first.

### 2.4 Rejected explanations

Diagnostic-induced perturbation is **not** established as the cause. The three
known perturbing defects — missing import path, missing client-timing flag, and
success-path flushes and pool-stat queries — were already found and fixed in
`187e558`, `bdae3ba`, and `749dc7d` before the valid reproduction. With the
diagnostic disabled, `PostgresIdempotencyStore._observe` returns `None` on a
single identity check, so the disabled path is genuinely inert. The retained
passing attempt above ran with the diagnostic *enabled* and still passed the
scheduler gate, which is direct evidence against a deterministic
diagnostic-caused gate failure.

## 3. Frozen closeout configuration

### 3.1 Environment identity

| Field | Frozen value |
| --- | --- |
| Host | Apple M2 arm64, 8 logical CPUs, 8 GiB RAM |
| OS | macOS 26.5.2 arm64 |
| Python / FastAPI / Uvicorn | 3.12.10 / 0.141.1 / 0.52.2 |
| HTTPX / Psycopg / Psycopg Pool | 0.28.1 / 3.3.4 / 3.3.1 |
| Docker | Docker Desktop 27.3.1, 8 CPUs, 3.83 GiB VM |
| PostgreSQL | task-owned `postgres:16-alpine`, `127.0.0.1:55432` |
| API | local `postgres-scale` bundle, `POST /v2/predict` |
| Request timeout | 10 seconds, unchanged |
| Client keep-alive expiry | 30 seconds, unchanged |

### 3.2 Failed-cell workload

Workers 4, concurrency 64, repeat 2. Warm-up 70 owner + 20 completed replay +
10 malformed. Measured 700 owner + 200 completed replay + 100 malformed. One
shared thread-safe HTTPX client per cell, constructed before warm-up, with
`max_connections` and `max_keepalive_connections` both equal to concurrency.

### 3.3 Instrumentation policy for performance proofs

- The opt-in P1-S4f state-store diagnostic is **disabled**. It is enabled only
  for one controlled reproduction if a service correctness gate fails.
- The S4f `PostgresAggregateSampler` is **not started** during postfix proofs.
- `SECURESWIPE_SCALE_CLIENT_TIMING=1` remains enabled; the frozen gates require
  it.
- The validated S4e `ResourceSampler` remains unchanged and enabled. It is part
  of the harness that produced the 34 passing S4e cells; removing it would
  change the harness being validated. Its 10 Hz subprocess sampling is recorded
  as a known measurement limitation, not corrected here.
- No diagnostic disk write, pool-stat query, or aggregate flush occurs on the
  request or scheduler hot path.

### 3.4 Unchanged frozen gates

Every gate below is inherited verbatim. None is weakened, reinterpreted,
recalculated, or bypassed.

| Gate | Required value |
| --- | ---: |
| Measured HTTP 200 / expected HTTP 422 | 900 / 100 |
| Server original / server replay | 700 / 200 |
| HTTP 503 / `state_store_unavailable` | 0 / 0 |
| `idempotency_failed` / `idempotency_in_progress` | 0 / 0 |
| Client timeout / transport error | 0 / 0 |
| Contract mismatch / duplicate audit event | 0 / 0 |
| Warm-up / measured audit growth | 70 / 700 |
| Full-chain verification | Pass |
| Scheduler queue p99 | `<= max(10 ms, 5% of measured E2E p50)` |
| Measured connection reuse | `>= 95%` |
| Maximum outstanding requests | `== concurrency`, `<=` configured limit |
| Per-request client setup | `0.0 ms`, count equals attempted |
| Artifact privacy validation | Pass |

### 3.5 Machine-health observation and the only permitted invalidation

Machine health is sampled outside the request hot path: once immediately before
the API cluster starts and once after the measured phase and cleanup complete.
Samples are `sysctl -n vm.loadavg`, free-memory percentage, and thermal warning
level. No unrelated process is killed, niced, or modified.

A run may be declared environmentally invalid **only** if at least one of these
pre-registered, independently measured conditions fails:

- **M1** — 1-minute load average immediately before the run exceeds `8.00`, i.e.
  above 1.00 per logical CPU. The recorded closeout baseline is `4.79`.
- **M2** — a thermal or CPU power warning level is recorded during the run.
- **M3** — task infrastructure fails: Docker daemon unreachable, task container
  unhealthy or restarted, PostgreSQL readiness failure, task PostgreSQL sampler
  failure count above zero, or port 55432 already occupied before setup.

**A failed benchmark gate is not an environment invalidation.** Exceeding the
scheduler-queue gate, any correctness gate, or any harness gate while M1–M3 all
pass is a genuine failed proof and is reported as such. At most **one**
protocol-authorized replacement attempt is permitted, and only when M1, M2, or
M3 is proven to have failed.

### 3.6 Artifact naming, versioning, and privacy

- Postfix proof artifacts: `p1-s4-postfix-<epoch>.json`, benchmark version
  `p1-s4-terminal-closeout-v1`.
- Matrix artifacts: `p1-s4-final-<epoch>.json` / `.csv` plus incremental
  `-progress` files.
- Harness-gate failures persist `p1-s4-postfix-<epoch>-failure.json` with schema
  `p1_scale_harness_gate_failure_v1`.
- No existing P1-S4b/c/d/e/f artifact is overwritten, relabelled, moved, or
  deleted. New schemas are added; old schemas are never reinterpreted.
- Every persisted document passes `validate_safe_result`. No per-request timing
  array, request identifier, body, feature, score, label, secret, DSN, SQL,
  PAN, CVV, raw audit row, or raw database content is written.

### 3.7 Abort and cleanup

Each run removes only its task-owned API process group, PostgreSQL container,
volume, schema, role and credentials, raw logs, and temporary directories. Port
55432 is confirmed closed after each run. Port 5432 is never touched. Unrelated
untracked paths are preserved byte-for-byte. Nothing is pushed or deployed.

## 4. Decision tree

**A — service correctness fails.** Enable the opt-in state-store diagnostic for
exactly one controlled reproduction of that failure. If a new root cause is
proven, implement the smallest correctness repair, add a deterministic
regression, run focused and PostgreSQL integration tests, freeze a new source,
and restart the postfix proofs from run 1. At most one additional proven repair
cycle is allowed. If correctness still fails, close P1-S4 without scale claims.
Pool sizes, timeouts, retries, and worker counts are never tuned as a substitute
for a correctness repair.

**B — a harness gate fails while M1–M3 pass.** The proof is failed. The gate is
not weakened and the matrix is not entered. P1-S4 closes without scale claims,
preserving the repair and the negative evidence.

**C — an independent machine-health gate fails.** Only if M1, M2, or M3 is
proven, classify the run environmentally invalid, clean up, restore a fresh
task-owned environment, and perform the single authorized replacement attempt.

**D — all three postfix proofs pass.** Authorize the frozen 36-cell matrix
(workers 1/2/4 × concurrency 1/8/32/64 × 3 repeats) under identical gates,
stopping at the first correctness or harness failure. Only after all 36 cells
are valid may the frozen 100/1,000/10,000-event audit-growth stage run.

## 5. Claim boundary

No claim of Razorpay production scale, global horizontal scalability, capacity,
production SLO, multi-region behaviour, external-network performance, merchant
savings, ROI, cost, real-world fraud probability, autonomous payment
authorization, or global `O(1)` event sourcing is authorized by this protocol
under any outcome.

If every gate passes, evidence is limited to reproducible, environment-specific,
local-loopback, synthetic-workload behaviour on the recorded Apple M2 and
task-owned PostgreSQL environment at the bound source commit.

Constant-time append mechanics, serialized audit-head coordination, full-chain
verification cost, and end-to-end request complexity are reported as four
distinct measurements. A narrow constant-time append result is never restated as
a system-wide complexity claim.
