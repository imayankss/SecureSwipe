# P1-S4f postfix verification protocol

Status: **pre-registered before postfix measurement**

This protocol binds verification of the minimal state-store lifecycle repair to
one exact source. It inherits the workload, privacy, cleanup, correctness, and
claim rules from the
[P1-S4f diagnosis protocol](P1_S4F_STATE_STORE_DIAGNOSIS_PROTOCOL.md) and the
[validated P1-S4e harness protocol](P1_S4E_VALIDATED_HARNESS_PROTOCOL.md).

## 1. Bound identity

| Item | Bound value |
| --- | --- |
| Repaired source SHA | `f4d38c249045796f05815aac6c244d6432cf703a` |
| Repair commit | `fix(state-store): prevent completion lock-wait pool starvation` |
| Reproduction source | `749dc7dcbdb5bbe5bf97ac13d70b1a703ebf3196` |
| Reproduction artifact | `reports/benchmarks/p1-scale-results/p1-s4f-reproduction-1788168873.json` |
| Reproduction SHA-256 | `a9a75f9c58ba9580c27a7dc60bed05eeabfd04120fe0ffc275cd3347ae162f11` |
| Model fingerprint | `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3` |
| PostgreSQL | task-owned 16.10 at `127.0.0.1:55432` only |

The repair queues completion transactions within each worker before acquiring a
pool connection. The global audit-chain head already serializes those
transactions. No pool size, timeout, retry, worker, concurrency, PostgreSQL,
model, audit, idempotency, request, response, schema, or harness setting changed.

## 2. Three-run postfix gate

Run three consecutive independent fresh environments. Every run uses the
unchanged P1-S4e harness at four API workers, concurrency 64, repeat 2, one
shared persistent client, and the frozen ten-second request timeout.

Each run contains:

- warm-up: 70 owners, 20 completed-record replays, and 10 malformed requests;
- measured: 700 owners, 200 completed-record replays, and 100 malformed
  requests; and
- explicit full-chain verification after the measured phase.

Every run must reconcile exactly:

| Gate | Required value |
| --- | ---: |
| HTTP 200 / expected HTTP 422 | 900 / 100 |
| Owner / completed replay | 770 / 220 |
| HTTP 503 / `state_store_unavailable` | 0 / 0 |
| Timeout / transport error | 0 / 0 |
| Contract mismatch / duplicate audit event | 0 / 0 |
| Warm-up / measured audit growth | 70 / 700 |
| Full-chain verification | Pass |
| Persistent-client and bounded-scheduler gates | Pass |

No run may be retried, selected, tuned, or replaced. A failure stops the task
before the complete matrix.

## 3. Final verification gate

Only after all three postfix runs pass, run the complete frozen matrix from a
fresh task-owned database: workers 1/2/4, concurrency 1/8/32/64, and three
repeats for all 36 cells. Preserve the same warm-up/measured mix, client,
timeout, model, database, audit/idempotency semantics, and harness gates.

All 36 cells must satisfy the exact response, replay, audit-growth, chain,
privacy, and harness contracts. No best-run selection or retry is permitted.
Only after all 36 pass may the unchanged 100/1,000/10,000-event audit-growth
procedure run. Its final 10,000-event chain and bounded-growth gates must pass.

Any correctness failure invalidates performance interpretation and authorizes
no worker-scaling claim. If every gate passes, evidence is limited to measured
local-loopback behavior on the bound source and recorded Apple M2 environment;
it does not support production, SLO, external-network, multi-region,
Razorpay-scale, savings, or ROI claims.

## 4. Evidence, privacy, and cleanup

Generated aggregate JSON/CSV remains Git-ignored until a concise evidence
report records hashes. No request-level timing, identifier, body, feature,
score, label, secret, DSN, SQL, PAN, CVV, raw audit row, or raw database content
may persist. Exact diagnostic mode may remain enabled for postfix runs but must
remain aggregate-only and inert otherwise.

Every run removes only its task-owned API processes, PostgreSQL container,
volume, schema, role/credentials, raw logs, and temporary diagnostics. Port
55432 must be closed afterward. Port 5432 and unrelated untracked files remain
untouched. Nothing is pushed or deployed.
