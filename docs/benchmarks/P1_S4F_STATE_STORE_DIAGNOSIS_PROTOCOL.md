# P1-S4f state-store failure diagnosis protocol

Status: **pre-registered before diagnostic implementation or reproduction**

This protocol governs the bounded reproduction, diagnosis, and possible repair
of the `state_store_unavailable` correctness failure recorded by
[P1-S4e](P1_S4E_VALIDATED_HARNESS_EVIDENCE.md). It is a correctness protocol,
not a performance-tuning exercise. The P1-S4e harness validation remains valid,
but its incomplete performance matrix is not publishable evidence.

## 1. Frozen identity and failed cell

| Item | Frozen value |
| --- | --- |
| P1-S4e evidence commit | `fe4a7c78fc053819f37ab9d7395175e6d3c02ea6` |
| P1-S4e measurement source | `7e81b8041b6244af1f7620e8d6145403f436124c` |
| P1-S4e protocol SHA-256 | `d40ef3e36bdd7fb2f0a26df494fddaca11b92698383893fd5811cd4f64ecf062` |
| Model fingerprint | `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3` |
| API profile and route | local `postgres-scale`, `POST /v2/predict` only |
| PostgreSQL | task-owned 16.10 at `127.0.0.1:55432` only |
| Failed cell | 4 workers, concurrency 64, repeat 2 |
| Failure | 52 HTTP 503 `state_store_unavailable`; zero client timeout/transport error |

Port 5432, external services, V1, batch, `local-default`, real transaction
data, `final_test`, and all model/evidence artifacts are out of scope.

## 2. Frozen reproduction workload

Each fresh attempt uses the committed P1-S4e persistent-client topology and
unchanged ten-second request timeout:

1. start a fresh task-owned PostgreSQL 16.10 container, volume, database,
   schema, role, and four API worker processes;
2. create one shared thread-safe HTTPX client for the cell with 64 maximum and
   64 keep-alive connections and 30-second keep-alive expiry;
3. send a separate warm-up of 70 synthetic valid owners, then 20 replays of
   completed owners, then 10 malformed requests;
4. send a measured phase of 700 synthetic valid owners, then 200 replays of
   completed owners, then 100 malformed requests; and
5. verify the complete audit chain explicitly before cleanup.

The bounded-refill scheduler, deterministic fixture `p1-scale-fixture-v1`,
request ordering, client limits, timeouts, API workers, pool configuration,
model settings, audit/idempotency semantics, and expected status mix must not
change. The original failed cell is not retried or relabelled. P1-S4f may run
at most three independent fresh reproductions.

Every attempt must reconcile exactly:

| Invariant | Required result |
| --- | ---: |
| HTTP 200 | 900 |
| Expected HTTP 422 | 100 |
| Owners | 770 |
| Completed replays | 220 |
| Pending/fail-closed outcomes | 0 |
| Warm-up audit growth | 70 |
| Measured audit growth | 700 |
| Unexpected status / timeout / transport error / mismatch / duplicate event | 0 |
| Full-chain verification | Pass |

## 3. Inert diagnostic boundary

State-store diagnostics activate only when
`SECURESWIPE_P1_S4F_STATE_STORE_DIAGNOSTIC=1` exactly. Missing, blank, `0`,
`true`, or any other value must instantiate no diagnostic collector, produce no
diagnostic artifact, and leave normal API behavior unchanged.

The diagnostic records aggregate observations by operating-system worker PID
and allowlisted operation stage:

- `initialize_open`;
- `connection_checkout`;
- `reserve`;
- `complete_outcome`;
- `commit`;
- `rollback`; and
- `close`.

For each stage it may retain only attempt, success, and failure counts; duration
count/min/median/p95/p99/max; sanitized failure category; sanitized SQLSTATE or
SQLSTATE class; and aggregate connection/pool counters. Allowed categories are
`pool_closed`, `connection_closed`, `checkout_timeout`, `connection_refused`,
`postgres_operational_error`, `postgres_interface_error`, `transaction_error`,
`serialization_error`, `resource_limit`, and `unknown_state_store_error`.

The task-owned PostgreSQL sampler may use read-only diagnostic SQL to retain
only server readiness, total active/idle task connections, aggregate
`pg_stat_activity` state/wait-event categories, aggregate granted/waiting lock
counts, configured `max_connections`, and backend termination/restart counts.
Application names or worker tags may be counted but not stored verbatim.

No diagnostic or result may contain an exception message, traceback, DSN,
credential, SQL text, plaintext request identifier, request/response body,
feature, score, label, PAN, CVV, raw audit row, or raw database content. Raw
task-owned logs exist only until their allowlisted aggregate is captured, then
are removed during cleanup.

## 4. Root-cause decision rules

- A cause is supported only when at least one fresh attempt reproduces
  `state_store_unavailable` and the earliest failing state-store stage has a
  sanitized exception category or SQLSTATE/class consistent with the
  task-owned PostgreSQL and pool aggregates.
- A pool lifecycle cause requires direct evidence of checkout timeout, closed
  pool, closed connection, or reuse-after-close at the failing stage.
- A server availability cause requires matching connection refusal, backend
  termination/restart, failed readiness, or PostgreSQL resource evidence.
- A transaction cause requires an allowlisted transaction/serialization
  SQLSTATE class and corresponding rollback/lock evidence.
- Timing correlation alone is insufficient. No failure message or private
  value may be retained to make a diagnosis appear more precise.
- If all three fresh attempts pass, the result is exactly `FAILURE NOT
  REPRODUCED UNDER THREE CONTROLLED ATTEMPTS`; no repair and no P1-S4 completion
  claim are permitted.
- If the diagnostic changes API behavior, leaks prohibited data, or fails to
  reconcile the ordinary correctness contract, only the diagnostic may be
  repaired before further reproduction.

## 5. Allowed repair scope

A repair is allowed only after the preceding decision rules support one exact
cause. It must be the smallest correction to an incorrect connection/pool
lifecycle, transaction cleanup, deterministic cross-worker initialization, or
error translation. It must preserve fail-closed behavior, bounded idempotency,
one committed outcome and audit event per key, exact replay, and chain
verification.

Changing pool sizes, checkout/request timeouts, retry counts, worker count,
concurrency, queue depth, PostgreSQL/Uvicorn/OS settings, locks, fsync, model
threads, admission limits, workload, public response behavior, schema, model,
or audit/idempotency policy is prohibited. A fallback store, swallowed
exception, or approval-like response on state failure is prohibited.

Any repair requires a deterministic regression test that fails for the proven
defect and passes for the correction. The repair is committed separately with
an exact root-cause commit subject.

## 6. Postfix and final verification sequence

After a supported repair, a separate committed postfix protocol must bind the
repaired source SHA before measurement. Three consecutive fresh 4-worker /
concurrency-64 runs must each produce zero HTTP 503,
`state_store_unavailable`, timeout, transport error, mismatch, and duplicate
event, with the exact 900/100 response mix, 770/220 owner/replay mix, 70/700
audit growth, and a valid chain.

If all three pass, the unchanged complete 36-cell P1-S4e matrix runs from
scratch: workers 1/2/4, concurrency 1/8/32/64, and three repeats. No run may be
selected, retried, or tuned. Only if all 36 pass may the frozen 10,000-event
audit-growth stage run. Any correctness failure stops performance
interpretation and authorizes no worker-scaling claim.

Verification then includes focused diagnostic/regression tests, state-store,
idempotency, audit, API and benchmark regressions, fresh task-owned PostgreSQL
S2/S3 integration tests, Ruff, canonical Mypy, compilation, `pip check`, links,
artifact privacy validation, `git diff --check`, and the full Python suite.

## 7. Cleanup and claims

Every success and failure path removes only P1-S4f-owned API processes,
PostgreSQL container, volume, schema, role/credentials, raw logs, and temporary
diagnostics. Port 55432 must be closed afterward; port 5432 is untouched.
Existing P1-S4b/c/d/e evidence and unrelated untracked paths remain preserved.

Until every postfix, 36-cell, and audit-growth correctness gate passes, P1-S4
remains incomplete and no worker-scaling claim is authorized. Even a complete
result may describe only measured local-loopback behavior on the exact recorded
source and machine. Production scale, SLO, external-network, multi-region,
Razorpay-scale, savings, and ROI claims are prohibited.
