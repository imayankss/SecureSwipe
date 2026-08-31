# P1-S4e validated load-harness protocol

Status: **pre-registered final P1-S4 measurement; no result or claim yet**

Protocol version: `p1-s4e-validated-harness-v1`

Source boundary:
`9e5cd1d43e470c4454de67113dcd789a6e99cea1`

Parent evidence:

- P1-S4d protocol commit:
  `5b91ea8fe884cb4e346f658e3453e482fd87c229`
- P1-S4d diagnostic commit:
  `9e5cd1d43e470c4454de67113dcd789a6e99cea1`
- [P1-S4d protocol](P1_S4D_CLIENT_TRANSPORT_PROTOCOL.md), SHA-256
  `d8fde6108af5e7cf0b1771c77f9ace71778b155102ed1071d38e379742253f6e`
- P1-S4d ignored result
  `reports/benchmarks/p1-scale-results/p1-s4d-client-transport-1788153293.json`,
  SHA-256
  `aefa8a5a48e5bb94c0577ba9438ed8c1f487ddeaadc707de3a2398a9a30861ee`

This protocol freezes the only final P1-S4 matrix permitted to evaluate local
multi-worker behavior. P1-S4b, P1-S4c, and P1-S4d remain historical diagnostics.
Their files and numbers are not overwritten or relabelled. P1-S4d proved the
legacy load generator was constrained by unbounded executor backlog and one new
HTTP client/TCP connection per request. The legacy P1-S1 matrix is therefore
`HARNESS-CONSTRAINED / NOT SERVER-SCALING EVIDENCE`.

## 1. Scope and immutable boundaries

S4e replaces load-generator lifecycle, scheduling, and request timing only. It
does not change FastAPI, Uvicorn, PostgreSQL, idempotency, audit, migrations,
model behavior, admission, response schemas, routes, headers, server pools,
Docker settings, or operating-system settings.

The expected host is Apple M2 arm64 with eight logical CPUs and 8 GiB RAM,
Python 3.12.10, FastAPI 0.141.1, HTTPX 0.28.1, HTTPcore 1.0.9, and PostgreSQL
16.10. The required model fingerprint is
`a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3`.

Only a task-owned PostgreSQL 16.10 container may bind
`127.0.0.1:55432`. Port 5432 and external services are outside scope. Every
repeat retains the existing fresh schema and API-cluster lifecycle, migration,
readiness, resource sampler, audit checks, and cleanup guard.

## 2. Frozen matrix, fixture, and server configuration

Run all 36 cells without omission, retry, tuning, or best-run selection:

| Dimension | Frozen values |
| --- | --- |
| Uvicorn workers | `1`, `2`, `4` |
| Client concurrency | `1`, `8`, `32`, `64` |
| Repeats | `1`, `2`, `3` |
| Total cells | 36 |
| Endpoint/profile | `POST /v2/predict`, `postgres-scale` |
| Client/API prediction timeout | 10 seconds |
| API admission limit | 256 concurrent predictions |
| API PostgreSQL pool | minimum 1, maximum 4 per worker |
| Uvicorn command | existing repository `python -m uvicorn api.main:app`, loopback, frozen worker count, warning log level, no access log |
| PostgreSQL | task-owned 16.10 at `127.0.0.1:55432` |

The deterministic fixture remains `p1-scale-fixture-v1`, seed 42, with the
existing per-cell seed and manifest SHA-256. Request IDs, bodies, repeat
identity, and the committed deterministic shuffle are unchanged.

| Phase | Unique valid owners | Same-ID completed replays | Malformed | Attempts |
| --- | ---: | ---: | ---: | ---: |
| Warm-up | 70 | 20 | 10 | 100 |
| Measured | 700 | 200 | 100 | 1,000 |

Warm-up is never included in measured request latency or RPS. The same client
and executor continue from warm-up into measurement. The audit-growth procedure
remains separate: 10,000 sequential unique synthetic events with checkpoints
at 100, 1,000, and 10,000 and explicit full-chain verification.

## 3. Frozen client topology

One synchronous `httpx.Client` is shared by the fixed executor threads for an
entire cell. HTTPX 0.28.1 documents `Client` as thread-safe. The client and
executor are created after API readiness but before warm-up and close only
after measured traffic, audit reconciliation, and result capture for that cell.
No per-request function may construct or close a client.

The explicit client limits are:

```text
max_connections = concurrency
max_keepalive_connections = concurrency
keepalive_expiry_seconds = 30.0
HTTP/1.1 = enabled
HTTP/2 = disabled
follow_redirects = false
trust_env = true
```

These are client-harness limits, not server tuning. Supported public
HTTPX/HTTPcore trace hooks observe TCP connect and HTTP/1.1 operations.
Connection-pool acquisition remains `not_observable`; private monkey-patching,
API changes, and inferred pool wait are prohibited.

## 4. Bounded scheduler and timing clocks

The executor has exactly `concurrency` threads. At most `concurrency` futures
may be submitted or in flight. The scheduler initially submits at most that
many attempts, waits for one or more completions, then submits exactly one
replacement per completed future until the unchanged shuffled schedule is
exhausted. It never queues all 1,000 attempts at once.

All request durations use one client-process monotonic clock:

| Field | Frozen boundary |
| --- | --- |
| `scheduler_queue_wait_ms` | immediately before bounded `submit` to task start |
| `client_setup_ms` | client construction outside traffic; per-request value is zero and excluded from E2E |
| `request_preparation_ms` | task start through request construction to immediately before `client.send` |
| `request_e2e_ms` | immediately before `client.send` to complete response-body read |
| `run_wall_seconds` | earliest measured `client.send` start to latest measured body completion |
| Successful RPS | measured HTTP 2xx count divided by measured `run_wall_seconds` |

Executor construction, client construction, database/API startup, readiness,
warm-up, validation after response-body completion, and teardown are outside
measured E2E and RPS. Client-timing diagnostics remain inert unless the exact
existing opt-in `SECURESWIPE_SCALE_CLIENT_TIMING=1` is used. S4e measurement
requires that opt-in and persists only aggregate observations.

## 5. Harness gates before full mode

A dedicated smoke uses the committed 10-attempt smoke warm-up and 10-attempt
smoke measured mix with one worker and concurrency eight. Full mode is forbidden
until all gates pass:

1. static and runtime proof finds no per-request `httpx.Client` construction;
2. the client and executor are created before warm-up and shared through the
   measured phase;
3. maximum submitted/in-flight futures is no greater than and reaches the
   applicable `min(concurrency, attempts)` bound;
4. no unbounded executor backlog exists;
5. scheduler queue p99 is no more than
   `max(10 ms, 5% of request-E2E p50)`;
6. per-request client setup is zero and excluded from E2E;
7. measured connection reuse is at least 95%;
8. new + reused + unknown connection counts equal measured attempts;
9. warm-up opens persistent connections before measured traffic;
10. status, bounded-response, replay, audit, idempotency, model, readiness, and
    privacy contracts reconcile; and
11. normal API and diagnostics-off behavior remain unchanged.

If reuse is below 95%, only client lifecycle may be diagnosed and repaired.
Private hooks or server changes are prohibited. Any other failed harness gate
blocks the matrix and yields `HARNESS GATE FAILED — NOT A SERVER RESULT`.

## 6. Correctness gates for every repeat

Every warm-up/measured pair must prove:

- measured: exactly 900 HTTP 200 and 100 expected HTTP 422;
- combined lifecycle: 770 owners, 220 completed replays, zero pending and zero
  fail-closed outcomes;
- exactly 70 warm-up and 700 measured audit events;
- one original response and one shared bounded response/audit receipt per
  repeated logical group;
- full audit-chain verification passes; and
- zero unexpected statuses, timeouts, transport errors, mismatches, duplicate
  audit events, and diagnostic-recording failures.

Failure stops performance interpretation. Only a defect introduced in the new
client harness may be repaired; service behavior remains frozen.

## 7. Aggregate result schema and privacy

The Git-ignored JSON/CSV namespace is
`reports/benchmarks/p1-scale-results/p1-s4e-*`. It records:

- schema/purpose/non-claim, exact source SHA, protocol path/hash, P1-S4d parent
  identities, model/bundle fingerprints, synthetic classification;
- OS, CPU, RAM, Python, FastAPI, Uvicorn, HTTPX, HTTPcore, Psycopg, Psycopg
  Pool, and PostgreSQL version/image/settings;
- cell dimensions, exact client topology/limits, bounded scheduler maximum,
  warm-up separation, request manifests, and frozen counts;
- per-repeat status/error totals, run wall time, successful RPS, completed and
  successful E2E p50/p95/p99, CPU/RSS, audit counts, and verifier status;
- count/minimum/median/p95/p99/maximum for allowlisted queue, preparation,
  transport, response-header, body-read, and E2E timings; and
- aggregate new/reused/unknown connections, smoke-gate results, audit-growth
  checkpoints, pass/fail evaluation, limitations, and cleanup result.

Per-request arrays, IDs, bodies, features, scores, labels, decisions, raw
responses, raw audit/database content, DSNs, credentials, secrets, PAN, CVV,
and unnecessary PII are prohibited. Phase shares, if used, are calculated per
request before aggregation; unrelated percentiles are never subtracted.

## 8. Scaling evaluation and allowed conclusions

Medians use all three repeats at a fixed worker/concurrency cell. Existing
P1-S1 gates remain unchanged:

- zero correctness failures and the exact expected status mix;
- no replay-race duplicate score or audit event;
- no full-chain rescan during normal append;
- at concurrency 32 and 64, two-worker median successful RPS is at least 15%
  above one worker;
- at concurrency 32 and 64, four-worker median successful RPS is at least 25%
  above one worker;
- corresponding p99 increase is no more than 25%; and
- non-2xx increase is no more than one percentage point.

If every harness/correctness gate passes and scaling gates pass, the only
allowed conclusion is that the legacy matrix was harness-constrained and S4e
is current local loopback evidence for this exact SHA, host, client topology,
and synthetic workload.

If harness/correctness gates pass but worker gates fail, the required conclusion
is: “With a bounded, connection-reusing client harness, this local loopback
implementation did not demonstrate horizontal scaling across the measured
worker levels.” This negative result still completes P1-S4. It authorizes no
S4f, server tuning, or further scalability investigation.

P1-S4b/c/d remain historical diagnostics. S4e results are local loopback,
single-machine, synthetic traffic and are unrelated to held-out fraud-detection
quality. No result authorizes production capacity, multi-region, public-network,
Razorpay-scale, SLO, cost-saving, ROI, or universal-throughput claims. Core
XGBoost scoring uses zero LLM tokens.

## 9. Cleanup

On success or failure, stop only task-owned API process groups, drop only
registered task schemas, remove only the labelled task-owned PostgreSQL
container and volume, delete temporary credentials/logs/timing files after safe
aggregate capture, and confirm port 55432 is closed. Port 5432 is never touched.
Ignored S4e aggregate evidence is retained; all earlier artifacts are preserved.
Nothing is pushed or deployed.
