# P1-S4d client transport attribution protocol

Status: **pre-registered diagnostic; no scalability or capacity claim**

Protocol version: `p1-s4d-client-transport-v1`

Source baseline: `c7175a6022af55295493b7011efb0076dd2fdc4d`

Parent diagnostic:
`reports/benchmarks/p1-scale-results/p1-s4c-lifecycle-1788130435.json`
(`403dc5907c5c71838f9a7d118c68d088685178cc68f20ab44a22aacb5725d73f`)

This protocol freezes a local, synthetic-only measurement intended to locate
the large gap between P1-S4c client end-to-end latency and measured API-handler
latency. It authorizes diagnosis only. It does not authorize tuning, a revised
benchmark, publication, an SLO, or a scalability claim.

Canonical correctness and workload rules remain in the
[P1 scale protocol](P1_SCALE_PROTOCOL.md). Harness operation remains in the
[P1 scale harness](P1_SCALE_HARNESS.md), and the server lifecycle recorder is
documented in [Operations](../OPERATIONS.md#full-request-lifecycle-timing-diagnostic-opt-in-local-only).

## 1. Frozen environment and boundaries

The diagnostic runs from the committed implementation produced after this
protocol is committed. Results must record both that exact source SHA and this
file's pre-implementation SHA-256.

The expected local host is Apple M2 arm64 with eight logical CPUs, 8 GiB RAM,
Python 3.12.10, FastAPI 0.141.1, HTTPX 0.28.1, HTTPcore 1.0.9, and PostgreSQL
16.10. The model must report fingerprint
`a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3`.

Only a task-owned PostgreSQL 16.10 container may bind
`127.0.0.1:55432`. Port 5432 and external services are outside scope. Each cell
uses a fresh migrated task-owned schema and API process cluster. No setting is
tuned between cells.

The diagnostic is enabled only by the exact value:

```text
SECURESWIPE_SCALE_CLIENT_TIMING=1
```

Unset, blank, whitespace-padded, `0`, `true`, or any other value is inert. The
existing server lifecycle diagnostic remains independently opt-in. Neither
diagnostic may change routes, status codes, headers, bodies, schemas, database
records, audit events, model behavior, or `local-default` behavior.

## 2. Frozen cells and workload

Run exactly these cells, in this order, without retrying or selecting results:

| Workers | Concurrency | Repeat |
| ---: | ---: | ---: |
| 1 | 8 | 1 |
| 4 | 32 | 1 |
| 4 | 64 | 1 |
| 4 | 64 | 2 |

Every cell uses the committed deterministic P1 fixture and its normal process,
database, readiness, idempotency, audit, and resource-sampling lifecycle.

| Phase | Valid owners | Completed replays | Malformed | Attempts |
| --- | ---: | ---: | ---: | ---: |
| Warm-up | 70 | 20 | 10 | 100 |
| Measured | 700 | 200 | 100 | 1,000 |

The existing client and prediction timeout remains exactly 10 seconds. The
request order, IDs, bodies, manifest digest, endpoint (`POST /v2/predict`),
`postgres-scale` profile, pool sizes, readiness checks, audit checks, and model
are unchanged.

## 3. Observed client configuration

The committed harness currently submits work to
`ThreadPoolExecutor(max_workers=concurrency)`. Existing end-to-end latency
starts when the executor task begins; it does not include executor queue wait.
The opt-in recorder timestamps immediately before each submission and again at
task start, while retaining the existing E2E definition unchanged.

Each task constructs a new synchronous `httpx.Client(timeout=10.0)` and closes
it after one request. HTTPX defaults are HTTP/1.1 enabled, HTTP/2 disabled,
redirects disabled, environment trust enabled, maximum connections 100,
maximum keep-alive connections 20, and keep-alive expiry 5 seconds **per
client**. These defaults are observed and recorded; they are not changed.
Because each client sends one request, connection reuse is expected to be zero,
but the result must use trace evidence rather than assume that outcome.

HTTPX request extensions and HTTPcore 1.0.9 provide trace events for TCP
connection establishment and HTTP/1.1 header/body send and receive operations.
They do not provide a stable pool-acquisition start/end event. Pool acquisition
is therefore pre-registered as `not_observable`; no TTFB subtraction or private
monkey-patch may replace it.

## 4. Measurement definitions

All durations use one process-local monotonic clock. No absolute timestamps are
compared across threads or processes. Per-request observations exist only in
memory until reduced to aggregate statistics.

| Field | Boundary | Status |
| --- | --- | --- |
| `executor_queue_wait_ms` | immediately before `submit` → task starts | observed |
| `client_setup_ms` | task starts → request execution begins | observed |
| `pool_acquisition_ms` | connection-pool wait start → acquisition | `not_observable` |
| `tcp_connect_ms` | `connection.connect_tcp.started` → `.complete` | observed when a new connection is traced |
| `request_headers_send_ms` | HTTP/1.1 request-header send start → complete | observed |
| `request_body_send_ms` | HTTP/1.1 request-body send start → complete | observed |
| `request_transmission_ms` | same-request header-send plus body-send durations | observed |
| `response_headers_wait_ms` | HTTP/1.1 receive-response-headers start → complete | observed combined transport/ingress/server wait |
| `request_to_response_headers_ms` | request execution begins → response headers available | observed TTFB-like combined phase |
| `response_body_read_ms` | response headers available → response body fully read | observed |
| `client_teardown_ms` | body complete → client context closes | observed |
| `client_e2e_ms` | existing task-start boundary → client context closes | observed; must match existing completed-latency distribution |
| `scheduled_total_ms` | pre-submission timestamp → client context closes | observed; explicitly not the legacy E2E definition |

Trace callbacks ignore their event payloads. Only allowlisted event names and
monotonic arrival times may be inspected. A completed TCP-connect trace counts
one new connection. A completed request with no TCP-connect event counts one
reused connection. Failed or ambiguous traces count as unknown rather than
inventing reuse.

Each duration field publishes only `count`, `min_ms`, `median_ms`, `p95_ms`,
`p99_ms`, and `max_ms`. Connection results publish counts only. Requested
phases also publish one of `observed`, `not_observable`, or `unsupported`.

Where phase shares are needed for a decision, each request's phase duration is
divided by that same request's denominator before aggregation. Executor queue
uses scheduled total as its denominator; client phases use existing client E2E.
No result subtracts aggregate medians or percentiles, and overlapping phases
are never summed as if they were independent.

## 5. Aggregate result contract

The ignored diagnostic JSON must contain:

- schema version, diagnostic purpose, explicit non-claim, exact code SHA, this
  protocol path and hash, and the parent P1-S4c path and hash;
- model and bundle fingerprints; OS, CPU, RAM, Python, FastAPI, HTTPX,
  HTTPcore, Uvicorn, Psycopg, and PostgreSQL versions/image digest;
- worker, concurrency, repeat, deterministic request manifest, warm-up and
  measured counts, timeout, endpoint, and profile;
- the observed executor and HTTP client configuration, including the
  per-request client construction/reuse policy and documented default limits;
- phase availability, aggregate durations, aggregate same-request shares,
  new/reused/unknown connection counts, statuses, timeouts, transport errors,
  and unexpected outcomes;
- existing P1-S4c server lifecycle aggregates, API/PostgreSQL CPU and RSS,
  audit growth, and full-chain verification; and
- limitations plus task-owned cleanup status.

The report must be written atomically into the existing Git-ignored
`reports/benchmarks/p1-scale-results/` boundary. A later failure must not erase
already completed cell aggregates.

## 6. Privacy and safety gates

Saved output must not include individual samples, raw timings, request bodies,
features, scores, labels, decisions, response bodies, plaintext request or
idempotency identifiers, DSNs, credentials, secrets, SQL, exception text,
stack traces, PAN, CVV, or unnecessary PII. It may include aggregate counts,
durations, phase availability, status counts, safe runtime versions, source and
artifact hashes, and anonymous correctness totals.

Unknown event names, unsafe metric names, booleans, strings, negative values,
NaN, and infinity are rejected or ignored without influencing the request.
Diagnostic recording failure must never change a response, status, financial
decision, idempotency result, or audit result.

## 7. Correctness gates

Every cell must satisfy all of these before performance interpretation:

- measured result: exactly 900 HTTP 200 and 100 expected HTTP 422;
- combined warm-up/measured lifecycle: 770 owners, 220 completed replays, and
  zero pending/fail-closed outcomes;
- exactly 70 warm-up and 700 measured audit events;
- one original response and one shared response/audit receipt per logical
  request group, with 700 measured scoring/audit owners;
- zero unexpected statuses, timeouts, transport errors, response mismatches,
  duplicate audit events, and diagnostic contract failures; and
- explicit full-chain verification succeeds.

Any failure stops attribution. Privacy-safe partial evidence is retained; the
system is not tuned or retried.

## 8. Decision rules

All dominance decisions use the median of per-request shares, not ratios of
aggregate percentiles:

1. `CLIENT TASK QUEUE IDENTIFIED` only if executor queue wait is more than 50%
   of scheduled total.
2. `CONNECTION POOL IDENTIFIED` only if pool acquisition is directly observed
   and exceeds 50% of client E2E. With the installed stable hooks this field is
   pre-registered `not_observable`.
3. `CONNECTION REUSE/TCP IDENTIFIED` only if TCP connect exceeds 50% of client
   E2E. A high new-connection count alone is reported as configuration evidence,
   not latency causation.
4. `COMBINED TTFB PATH IDENTIFIED — SERVER INGRESS DIAGNOSTIC NEXT` only if
   request-to-response-headers exceeds 50% of client E2E while queue, connect,
   and send do not exceed 50%. The conclusion remains combined: socket backlog,
   ingress, worker dispatch, pre-handler scheduling, handler execution, and
   response-header transport are not separated by this client trace.
5. Otherwise report `NO DOMINANT PHASE ESTABLISHED`.

Counts, maxima, and individual outliers cannot override these rules. A
`not_observable` critical phase remains an explicit limitation.

## 9. Cleanup and prohibited claims

After preserving ignored aggregate evidence, stop only task-owned API
processes and remove only the task-owned PostgreSQL container, volume, schemas,
credentials, logs, and temporary directories. Confirm port 55432 is closed.
Never inspect, stop, or modify port 5432 or unknown resources.

This diagnostic prohibits production-scale, universal-throughput, SLO,
Razorpay-scale, solved-scalability, and multi-worker-improvement claims. It
does not change the P1-S1 gates. No tuning, redesign, deployment, push, or
external configuration change belongs to P1-S4d.
