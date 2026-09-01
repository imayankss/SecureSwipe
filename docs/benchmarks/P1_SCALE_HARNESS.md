# P1 scalability benchmark harness

Status: **P1-S4f repaired the reproduced state-store defect; postfix harness gate failed; P1-S4 remains incomplete**

The runner implements the workload and measurement contract in
[P1 scale protocol](P1_SCALE_PROTOCOL.md). It benchmarks only the explicit
`postgres-scale` profile through single-item `POST /v2/predict`. It never sends
prediction traffic to V1, batch routes, `local-default`, an external service,
or PostgreSQL on host port 5432.

P1-S4d proved that the earlier P1-S4b client submitted every attempt at once
and created a new HTTPX client for every request. That legacy matrix is
`HARNESS-CONSTRAINED / NOT SERVER-SCALING EVIDENCE`. Its artifacts remain
historical diagnostics and are not overwritten. The corrected topology and
final interpretation rules are frozen in the
[P1-S4e protocol](P1_S4E_VALIDATED_HARNESS_PROTOCOL.md).

## Safety boundary

The runner creates one temporary Docker container and named volume with the
prefix `secureswipe-p1-s4-` and label `secureswipe.task=p1-s4`. PostgreSQL
16.10 is published only on `127.0.0.1:55432`. A task-owned non-superuser role
with a generated run-only credential and a fresh schema are created for each
repeat. The database is initialized with data checksums. The API cluster uses a temporary
synthetic reference bundle created by the existing bundle smoke-test helper.

Startup fails closed when any of these checks fails:

- host port 55432 is already occupied;
- Docker, PostgreSQL 16.10, or the pinned image digest is unavailable;
- explicit migrations or role grants fail;
- the V2 API cluster does not become ready with the requested worker count;
- the model bundle or bounded response contract cannot be verified;
- the expected `2xx`/`422` mix, audit growth, or explicit full-chain verifier
  does not reconcile;
- a required CPU/RSS sample is absent.

Cleanup is guarded by the ownership prefix. On success or failure, the runner
terminates its API process group, drops only the schema it registered, and
removes only its named container and volume. It neither lists nor operates on
other containers, volumes, databases, schemas, services, or port 5432.

## Frozen workload

| Phase | Valid | Same-ID replay | Malformed | Attempts |
| --- | ---: | ---: | ---: | ---: |
| Warm-up | 70 | 20 | 10 | 100 |
| Each measured repeat | 700 | 200 | 100 | 1,000 |
| Non-publishable smoke warm-up | 7 | 2 | 1 | 10 |
| Non-publishable smoke measured | 7 | 2 | 1 | 10 |

The full matrix is workers `1, 2, 4`, concurrency `1, 8, 32, 64`, and three
repeats: 36 measured configurations. The harness emits a SHA-256 manifest of
each deterministic schedule before traffic but never saves the underlying
request IDs or bodies. Malformed requests are counted separately as expected
HTTP `422`; they are not successful requests.

Full mode also runs the separately defined sequential audit-growth procedure
at 100, 1,000, and 10,000 events. It reports the median and p99 of the frozen
ten-event windows and times the explicit full-chain verifier at each checkpoint.

## Results and metrics

Generated JSON and CSV are written under:

```text
reports/benchmarks/p1-scale-results/
```

That directory is ignored by Git. Results contain only environment metadata,
source and fixture fingerprints, aggregate request outcomes, latency and RPS,
CPU/RSS aggregates, and audit counts/timings. They exclude DSNs, secrets,
environment-variable values, paths to temporary artifacts, request bodies,
feature values, plaintext request IDs, scores, and raw database rows.

Every result records:

- API schema/profile, source SHA, protocol/fixture version, and bundle/manifest
  fingerprints;
- OS, CPU, RAM, Python/runtime, PostgreSQL version, image and digest;
- workers, concurrency, phase separation, deterministic schedule digest, and
  exact request counts;
- successful RPS, p50/p95/p99 for completed and successful requests, status
  counts, expected non-2xx, unexpected non-2xx, timeouts, transport errors;
- aggregate API and PostgreSQL CPU/RSS samples; and
- warm-up/measured audit growth plus full-chain verification status and time.

## Validated client lifecycle and scheduler

Each cell creates one synchronous, thread-safe `httpx.Client` and one fixed
executor before warm-up. The same client and executor continue through the
measured phase and close only after the cell finishes. Client limits are
explicitly equal to the cell concurrency for both maximum connections and
maximum keep-alive connections, with a 30-second keep-alive expiry. No
per-request function constructs or closes a client.

The scheduler initially submits at most `concurrency` attempts. It waits for
completed futures and submits one replacement per completion, so outstanding
work never exceeds concurrency and no 1,000-future executor backlog exists.
Request E2E begins immediately before `client.send` and ends after the complete
response body is read. Run wall time begins at the first actual network send
and ends at the final body completion. Client/executor construction, readiness,
warm-up, validation after body completion, and teardown are excluded.

Exact `SECURESWIPE_SCALE_CLIENT_TIMING=1` opt-in adds aggregate scheduler,
request, public HTTP trace, and connection evidence. Missing or non-exact flag
values remain inert. Full S4e mode requires this evidence and fails closed
unless scheduler queue, zero per-request setup, bounded outstanding work,
connection reconciliation, and at least 95% measured reuse pass.

The committed S4e harness and smoke passed these gates. The final run completed
34 cells, then stopped without retry at four workers / concurrency 64 / repeat
2 when 52 requests received the fail-closed `state_store_unavailable` response.
The valid chain contained only the committed events. Because the frozen exact
status/audit counts did not reconcile, the run is a correctness failure and no
S4e performance matrix or worker-scaling conclusion is authorized. See the
[S4e evidence report](P1_S4E_VALIDATED_HARNESS_EVIDENCE.md).

P1-S4f subsequently reproduced the failure as connection-checkout timeout and
proved that completion transactions waiting on the globally serialized audit
head had exhausted each worker's four-connection pool. A minimal lifecycle
repair queues completion before checkout without changing pool size, timeout,
retry, workload, schema, or public behavior. The first bound postfix run then
failed the unchanged scheduler-queue harness gate, so its result was invalid,
the remaining postfix and full-matrix runs were not executed, and P1-S4 remains
incomplete. See the [S4f evidence report](P1_S4F_STATE_STORE_VERIFICATION_EVIDENCE.md).

Smoke results are always marked `publishable: false`. Full mode refuses a
tracked dirty tree and requires an explicit flag. Publication remains subject
to every correctness and claim gate in the protocol.

## Operator commands

Prerequisites are Docker with the locally pinned `postgres:16-alpine` image,
the repository Python 3.12 environment with locked API/quality dependencies,
and free loopback port 55432. Do not start or reuse another database manually.

Run focused unit checks:

```bash
.venv/bin/python -m pytest tests/test_p1_scale_benchmark.py
```

Run the small non-publishable smoke:

```bash
SECURESWIPE_SCALE_CLIENT_TIMING=1 \
  .venv/bin/python scripts/run_p1_scale_benchmark.py --mode smoke
```

The final P1-S4e matrix must run from the clean committed harness SHA:

```bash
SECURESWIPE_SCALE_CLIENT_TIMING=1 \
  .venv/bin/python scripts/run_p1_scale_benchmark.py \
  --mode full \
  --confirm-full-matrix
```

The full command performs 36 measured configurations plus the separate 10,000
event audit-growth procedure. It must not be used merely as a smoke test.

## Concurrency-safe replay validation

Client task scheduling does not determine which concurrent same-ID request
commits first. The validator therefore treats `X-Idempotent-Replay: true` as
server evidence and never predicts the winner from submission order. For every
successful anonymous request group it requires exactly one response without
the replay header, all remaining responses with the replay header, one shared
bounded-response SHA-256, and one shared committed audit receipt. Aggregate
audit growth must still equal the number of unique valid groups. Schema/profile
errors, score or request-ID leakage, missing or malformed receipts, invalid
replay headers, changed responses, changed receipts, duplicate events, and the
frozen status-mix violations continue to fail closed.

If response validation fails, the harness writes an ignored `*-partial.json`
before task resource cleanup. It contains the source SHA, runtime, model
fingerprint when available, worker/concurrency/repeat, anonymous group class,
status and server-header interpretation, schema/profile, failure reasons, and
safe response/audit counts. It excludes DSNs, secrets, plaintext request IDs,
bodies, features, and scores. Temporary API and PostgreSQL logs remain under
the task-owned temporary directory only until this safe summary is captured;
normal cleanup then removes them.

## Interpreting the output

A zero exit status means only that the requested harness mode reconciled its
frozen request mix, harness gates, and audit chain. It does not establish
production scale, universal throughput, a 1,000-RPS or 10,000-RPS claim,
availability, or WORM immutability. If the valid S4e matrix remains flat, P1-S4
still completes with a bounded negative local result; no S4f or server tuning
follows. All results are single-machine loopback synthetic traffic, unrelated
to held-out fraud-detection quality. Core XGBoost scoring uses zero LLM tokens.
