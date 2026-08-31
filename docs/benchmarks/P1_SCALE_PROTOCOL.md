# P1 scalability protocol

Status: **P1-S3 correctness implemented and verified locally; P1-S4 benchmark gate remains**

Protocol version: `p1-scale-protocol-v1`

P1-Core checkpoint: `fd9fc3bba628d5a66c1479a0b93bf4ad9a29d38e`

This document freezes the correctness, workload, measurement, and claim rules
for P1-S2 through P1-S4 before shared state or multi-worker behavior is
implemented. It is not benchmark evidence. A later result may cite this
protocol only if the implementation and result are tied to an approved,
committed Git SHA.

Current architecture and limits remain canonical in
[Architecture](../ARCHITECTURE.md), [Limitations](../LIMITATIONS.md), the
[API contract](../API.md), [Reproducibility](../REPRODUCIBILITY.md), and
[Deployment](../DEPLOYMENT.md).

## 1. Scope and sequence

The work is divided into three gated stages:

| Stage | Allowed objective | Exit condition |
| --- | --- | --- |
| P1-S2 | Add an explicit PostgreSQL-backed state/audit mode and its migration boundary | All S2 prerequisites below exist and configuration fails closed |
| P1-S3 | Prove cross-worker idempotency, audit integrity, privacy, and crash recovery | Every mandatory correctness test passes with zero failures |
| P1-S4 | Run the frozen workload and publish or withhold the result | Complete environment record, three repeats, all claim gates applied |

No S4 performance result can compensate for an S3 correctness failure.

## 2. Current boundary

`local-default` is the existing supported mode for single-worker local use. It
uses in-process idempotency and the optional local NDJSON audit writer described
in [the API contract](../API.md#idempotency-and-audit-evidence). The current
writer verifies the whole chain before every append, and current state is not
shared across processes or preserved by the default registry after restart.

`local-default` must not be described as cross-worker, cross-process,
cross-restart, distributed, highly available, or exactly-once beyond its
documented same-process boundary. The optional SQLite prototype remains local,
single-node, non-default, and outside the API request path.

`postgres-scale` is the future shared-state mode. It must be selected explicitly:

```text
SECURESWIPE_STATE_BACKEND=postgres-scale
```

The default remains:

```text
SECURESWIPE_STATE_BACKEND=local-default
```

When `postgres-scale` is selected, a missing, unreachable, unauthenticated,
unmigrated, or incompatible PostgreSQL store must make readiness and inference
fail closed. It must never fall back to the in-memory registry, SQLite, or local
NDJSON. Selecting `postgres-scale` together with `SECURESWIPE_AUDIT_LOG` must be
rejected at startup because split state/audit commits cannot satisfy this
protocol.

## 3. Transaction and privacy contract

For one valid idempotent request, the shared-state transaction must own these
facts atomically:

1. the hashed idempotency key and canonical request digest;
2. the lifecycle state;
3. the replayable bounded response representation;
4. one audit-event record and its chain position/hash; and
5. the updated audit-chain head.

The transaction may publish `COMPLETED` only if the response representation,
audit event, and new chain head commit together. A process crash before commit
must expose no completed result or audit event. A crash after commit but before
the HTTP response must replay the committed response without rescoring or
appending another event.

Durable tables, indexes, database logs, test diagnostics, and migration records
must not contain raw request JSON, feature names or values, transaction data,
plaintext idempotency keys, or model scores. Only hashed identifiers/digests,
bounded decisions, non-sensitive model/schema provenance, lifecycle metadata,
audit hashes, and timestamps are eligible.

### Approved response-contract decision

The current API response contains `raw_score` and `decision_score`, while this
protocol forbids durable score storage and requires exact replay after restart.
The approved internal V2 representation is versioned, bounded, and score-free.
It persists the bounded decision plus bundle-derived model, schema, intended-use,
and threshold-policy provenance; it excludes the plaintext request ID and all
score fields. The caller's validated request ID can later be attached to the
HTTP envelope without entering durable state. Silently persisting current
score-bearing V1 response JSON remains prohibited.

P1-S3 exposes this representation only through single-item `POST /v2/predict`
when `postgres-scale` is selected. The original committed receipt is returned
with first and replay responses. Score-bearing V1 routes remain unavailable in
that profile, and V2 batch is not implemented.

### Approved V2 bounded-response provenance rule

Every V2 bounded-response provenance field must be derived at runtime from the
loaded bundle and its manifest. This includes `historical_taint`,
`decision_eligible`, `historical_metrics_claimed`, `evaluation_performed`, the
model fingerprint, and all policy provenance. Implementations must never
hard-code favorable provenance values. For the current reference bundle, V2
must preserve its actual reference/disqualifying metadata and must not imply
that `postgres-scale` serves the sealed Lane A headline model. If a response
returns a threshold, it must identify the threshold's actual provenance and
must not imply linkage to sealed evaluation when that linkage is unverified.

## 4. Mandatory correctness suite

All fixtures are synthetic and all tests use a dedicated isolated PostgreSQL
schema. Timing sleeps are not correctness evidence; races begin through a
barrier, and crash points use deterministic injected process boundaries.

| ID | Pre-registered test | Exact pass condition |
| --- | --- | --- |
| C1 | 64 identical concurrent requests across four workers | All 64 receive the same completed bounded result; exactly one test scoring-counter increment, one completed idempotency record, and one audit event exist; replay responses identify the original receipt and never claim a new event |
| C2 | Same idempotency key, different canonical request digest | The first request completes; the conflicting request returns HTTP `409 idempotency_conflict`; no second scoring invocation, completion, or audit event occurs |
| C3 | Restart after an ordinary completed request | A new worker cluster returns the exact committed response representation and original audit receipt without rescoring or appending |
| C4 | PostgreSQL becomes unavailable before reservation and during an otherwise valid request | Readiness is not ready and inference fails closed with a stable non-2xx state-store error; no bounded result is released and no local fallback is created |
| C5 | Durable-storage privacy inspection | Schema inspection and sentinel search find no raw JSON, feature name/value, transaction field, plaintext request ID, `raw_score`, `decision_score`, or calibrated score in durable rows or captured SQL diagnostics |
| C6 | 256 unique valid requests, four workers, concurrency 64 | Exactly 256 audit events form one gap-free sequence and one valid hash chain; full-chain verification succeeds |
| C7 | Deletion, mutation, and reordering | Each corruption is applied separately to an isolated copy; the full-chain verifier rejects all three and identifies a chain/count/hash violation |
| C8 | Crash immediately before the completion transaction commits | The client gets no completed response; after restart there is no completed row or audit event for that attempt, and no false replay is possible |
| C9 | Crash immediately after commit and before HTTP response | After restart, the same key/body returns the exact committed response and original audit receipt; scoring count and audit-event count both remain one |
| C10 | Normal audit append at histories of 100, 1,000, and 10,000 events | Statement tracing proves append reads/locks only bounded head/idempotency rows and never calls or performs a full-chain scan; the separately invoked full verifier still validates the complete chain |

For C1, the test-only synthetic estimator increments a process-shared atomic
counter stored outside the repository. The counter records only invocation
count, never inputs or scores. The 64 clients are released simultaneously by a
barrier after all workers are ready.

For C8 and C9, the test harness kills the owning worker at named injected
boundaries. An exception in an in-process mock is insufficient crash evidence.
The database and remaining workers stay available so post-crash state can be
observed independently.

## 5. Deterministic workload

### 5.1 Fixture definition

Fixture version: `p1-scale-fixture-v1`

Valid bodies are generated only by the existing deterministic arithmetic
generator `src.operations.benchmark.synthetic_corpus` with `seed=42`. The
measured corpus uses indices `0..699` and the existing ordered 30-field serving
contract (`Time`, `V1` through `V28`, `Amount`). These rows have no labels,
customer identifiers, card data, or evidentiary meaning.

Malformed bodies are exactly:

```json
{"Time": 0.0}
```

with `Time` replaced by the malformed index `0..99`. They are intentionally
missing the remaining required fields and must return HTTP `422` before scoring
or durable reservation.

### 5.2 IDs and request mix

Each measured repeat has exactly **1,000 attempted requests**:

| Class | Count | Share | ID/body rule | Expected result |
| --- | ---: | ---: | --- | --- |
| Unique valid | 700 | 70% | One body per corpus index; unique ID suffix `valid-0000` through `valid-0699` | 700 completed `2xx`, 700 score invocations, 700 audit events |
| Same-ID replay | 200 | 20% | Ten replay attempts for each of `valid-0000` through `valid-0019`, with byte-equivalent canonical input | 200 completed `2xx`, zero additional score invocations or audit events |
| Malformed | 100 | 10% | Unique ID suffix `invalid-0000` through `invalid-0099` | 100 HTTP `422`, zero score invocations or audit events |

The full ID template is:

```text
p1sf-v1-w{workers}-c{concurrency}-r{repeat}-{suffix}
```

The 1,000 logical attempts are deterministically shuffled with
`random.Random(20260830 + workers * 10000 + concurrency * 100 + repeat)`.
Repeat numbers are `1`, `2`, and `3`. Request bodies and ID mapping are frozen;
the harness must emit their SHA-256 manifest before sending traffic.

### 5.3 Matrix and isolation

| Dimension | Values |
| --- | --- |
| Uvicorn workers | `1`, `2`, `4` |
| Client concurrency | `1`, `8`, `32`, `64` |
| Measured repeats | `3` per worker/concurrency configuration |
| Attempts per measured repeat | `1,000` |
| Total measured configurations | `36` |
| Total measured attempts | `36,000` |

Each repeat uses a fresh migrated schema and freshly started worker cluster.
Before measurement, that cluster receives a separate 100-attempt warm-up with
the same 70/20/10 mix: 70 unique valid, ten replays each for the first two valid
IDs, and ten malformed requests. Warm-up IDs use `warmup` instead of the repeat
suffix. Warm-up latency, throughput, and outcome counts are excluded from the
measured result, but the warm-up outcome must reconcile before measurement.

The 1,000-attempt repeat is retained for the detected Apple M2/8 GB host. It is
bounded to 1,000 so the 36-configuration matrix, process sampling, and PostgreSQL
tracing remain safe on 8 GB without swap-driven test distortion. No required
concurrency level, worker level, repeat, correctness case, or 10,000-event audit
checkpoint is reduced.

### 5.4 Audit growth workload

Audit growth is measured separately from HTTP throughput in one clean schema.
Append exactly 10,000 unique synthetic bounded events sequentially and record
each append latency. Report the median and p99 of the ten-event windows ending
at events `100`, `1,000`, and `10,000`:

```text
91..100, 991..1000, 9991..10000
```

At each checkpoint, run and time the explicit full-chain verifier. Normal append
must not invoke that verifier or select the historical event set. The result
must distinguish O(1) append-path evidence from the intentionally O(n) full
verification operation.

## 6. Metrics and environment record

Every attempted request must reconcile to exactly one of: completed HTTP
response, client timeout, or transport error.

| Metric | Frozen definition |
| --- | --- |
| Successful RPS | Count of HTTP `2xx` responses divided by measured wall-clock seconds |
| p50/p95/p99 latency | Nearest-rank percentiles over all completed HTTP attempts; also report the same percentiles for successful responses only |
| Timeout count | Client deadline expirations, reported separately from HTTP status |
| Non-2xx count | Every completed non-2xx response, with status/code breakdown; the 100 expected `422` responses remain visible |
| Transport-error count | Connection/protocol failures; never merged into timeouts or non-2xx |
| CPU | 100 ms samples for each API worker and the aggregate API process group; report mean and peak percentage |
| RSS | 100 ms samples for each API worker and aggregate API process group; report median and peak MiB |
| PostgreSQL resources | PostgreSQL process/container CPU and RSS sampled separately at 100 ms |
| Audit growth | Append median/p99 at the three frozen checkpoints plus full-verifier duration |

The result manifest must record:

- exact source SHA and clean/dirty status;
- protocol and fixture versions plus fixture-manifest SHA-256;
- OS name/version/build, CPU model/core count, and physical RAM;
- Python, FastAPI, Uvicorn, Psycopg, and pool versions;
- PostgreSQL `server_version`, image digest or native package identity, and
  database settings relevant to connections/durability;
- worker count, concurrency, timeout, pool sizes, and admission limit;
- model version, bundle format, manifest SHA-256, and verified model-artifact
  fingerprint returned by `/v1/model-info`;
- every per-repeat result, not only aggregate medians; and
- whether the reference bundle is synthetic or historical/reference. No serving
  result inherits Lane A evaluation claims.

Secrets, DSNs, credentials, environment-variable values, payloads, feature
values, individual scores, and raw audit/database rows must not enter the result.

## 7. Pass/fail rules

| Gate | PASS | FAIL |
| --- | --- | --- |
| Correctness | C1 through C10 all pass with zero failures | Any skipped or failed correctness test |
| Expected workload outcomes | Per repeat: 900 `2xx`, 100 `422`, zero timeout/transport/unexpected status; 700 scoring invocations and 700 measured audit events | Any unreconciled attempt, duplicate score/event, missing completion, or unexpected outcome |
| Replay races | One completion and one audit event per idempotency key/digest | Duplicate scoring, completion, or audit event |
| Audit append complexity | Normal append performs bounded head/key operations and no full-chain rescan at all three history sizes | Append calls the full verifier or scans prior events |
| Store failure | `postgres-scale` readiness/inference fail closed and create no local state/audit fallback | Any result release or silent fallback while PostgreSQL is unavailable |
| Two-worker material improvement | At both concurrency 32 and 64, median successful RPS is at least 15% above one worker at the same workload | Either comparison is below 15% |
| Four-worker material improvement | At both concurrency 32 and 64, median successful RPS is at least 25% above one worker at the same workload | Either comparison is below 25% |
| Tail-latency guard | For each required worker comparison, median p99 is no more than 25% above the one-worker p99 at the same concurrency | Any required comparison exceeds 25% |
| Error-rate guard | Total non-2xx rate rises by no more than 1 percentage point versus one worker at the same concurrency | Any required comparison rises by more than 1 percentage point |
| Publication identity | Result is produced from an approved committed SHA with a clean tracked tree and complete manifest | Dirty tree, unapproved SHA, incomplete environment, or missing repeats |

Worker-improvement percentages are calculated from the median of the three RPS
repeats. Tail comparisons use the median of the three per-repeat p99 values.
Percentage-point error comparisons use all 3,000 attempts for each
worker/concurrency cell. The complete 1/8/32/64 matrix is always reported even
though the material-improvement gate is evaluated at concurrency 32 and 64.

Every correctness rule is mandatory. If this M2/8 GB machine does not meet a
performance threshold, report the actual result and mark the material-scaling
claim failed. Do not reduce correctness, discard repeats, cherry-pick a
concurrency, or change thresholds after measurement.

## 8. Claim policy

The following claims are prohibited unless the exact claim has direct,
reviewed evidence from this protocol or a separately pre-registered protocol:

- production-scale or production-ready;
- 1,000 RPS or 10,000 RPS;
- universal throughput, latency, capacity, or linear scaling;
- cross-worker safety for `local-default`;
- cross-host, multi-region, highly available, or disaster-recovery safety;
- immutable or WORM audit storage; and
- merchant, public-network, or cloud-provider capacity.

Even a passing local result is local loopback evidence for its recorded machine,
database, model bundle, process layout, and SHA. Audit hash chaining remains
tamper-evident, not immutable; an actor with sufficient database authority can
rewrite state unless an independently controlled anchor is proven.

A result from a dirty tree is **internal-only**. A benchmark is publishable only
when its source is an approved committed Git SHA, the working tree is clean for
all benchmark inputs, the protocol/fixture manifests are attached, and all
mandatory correctness gates pass. A later commit cannot retroactively confer
identity on an earlier run.

## 9. P1-S2 prerequisites

### 9.1 Detected local availability

| Requirement | Detected state on 2026-08-30 | S2 consequence |
| --- | --- | --- |
| Host | macOS 26.5.2, Apple M2, 8 cores, 8 GB RAM | Use the bounded workload above |
| Docker | Client/server 27.3.1 available | Available, but no container was started by P1-S1 |
| PostgreSQL image | Local arm64 PostgreSQL 16.10 image, digest `postgres@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297` | May be used only as a dedicated S2 test instance after approval |
| Port 5432 | Already occupied by unrelated running container `bls_postgres`; credentials unavailable | Must not be reused, stopped, inspected for data, or reconfigured |
| Native client/server binaries | Homebrew PostgreSQL 14.19 installed | Client is available; it is not the frozen S2 server version |
| Python database driver | Psycopg `3.3.4`, binary runtime `3.3.4`, and psycopg-pool `3.3.1` are pinned in every Darwin/Linux API and quality lock | S2 dependency boundary implemented; audit results remain local to the working tree until committed |
| Migrations | Numbered SQL, checksum history, advisory lock, explicit apply, and read-only check exist | S2 migration boundary implemented and tested locally |
| Database configuration | Explicit backend, DSN, schema, pool, timeout, and HMAC-secret validation exist | Invalid/unavailable/unmigrated scale state fails closed with no fallback |

### 9.2 Exact PostgreSQL isolation requirement

S2 must use a dedicated PostgreSQL 16.10 instance from the digest above, bound
only to `127.0.0.1:55432`. It must not reuse the unrelated service on port 5432.
The instance must use UTC, data checksums, a dedicated non-superuser role, a
dedicated `secureswipe_p1_scale_test` database, and a temporary run-owned volume
outside the repository. Connection capacity must be at least 32 plus PostgreSQL
reserved slots. Credentials must be generated for the run, kept outside the
repository, and never printed.

### 9.3 Exact driver and pool requirement

The implementation must use the Psycopg 3 async interface and
`psycopg_pool.AsyncConnectionPool`; synchronous `psycopg2`, SQLite, SQLAlchemy,
and an in-memory fallback are out of scope for `postgres-scale`. Before code is
merged, S2 must select audited concrete `psycopg` and `psycopg_pool` releases,
add them to the project dependency sources, regenerate every applicable
hash-locked Darwin/Linux closure, and record the installed versions. P1-S1 does
not select an unverified package release or alter dependencies.

Each API worker uses pool minimum `1` and maximum `4`; four workers therefore
open no more than 16 application connections. Pool initialization and checkout
failure must propagate to readiness/inference rather than constructing local
state.

### 9.4 Exact migration requirement

S2 must add a forward-only, transactional migration runner and numbered SQL
migration. The runner must:

1. take a PostgreSQL advisory lock;
2. maintain a schema-version table;
3. apply each pending migration exactly once in its own transaction;
4. refuse unknown, missing, reordered, checksum-changed, or newer migrations;
5. run only as an explicit operator/test command, never automatically at API
   startup; and
6. expose a read-only `--check` mode used by readiness and CI.

Migration tests must cover clean creation, repeated no-op application,
concurrent runners, rollback on injected failure, checksum mutation, and a
database newer than the code.

### 9.5 Exact environment contract

| Variable | Requirement |
| --- | --- |
| `SECURESWIPE_STATE_BACKEND` | Optional; default `local-default`; only `local-default` or `postgres-scale` accepted |
| `SECURESWIPE_POSTGRES_DSN` | Required only for `postgres-scale`; absolute PostgreSQL DSN; credentials never logged |
| `SECURESWIPE_POSTGRES_MIGRATION_DSN` | Required only for explicit `--apply`; identifies a migration owner distinct from the runtime role; never used by API startup |
| `SECURESWIPE_POSTGRES_APPLICATION_ROLE` | Required only for explicit `--apply`; names the non-superuser runtime role that receives bounded table privileges and no audit-event mutation privilege |
| `SECURESWIPE_POSTGRES_SCHEMA` | Required for `postgres-scale`; strict lowercase identifier; unique per test repeat |
| `SECURESWIPE_POSTGRES_POOL_MIN_SIZE` | Optional only with `postgres-scale`; frozen default `1` |
| `SECURESWIPE_POSTGRES_POOL_MAX_SIZE` | Optional only with `postgres-scale`; frozen default `4` per worker |
| `SECURESWIPE_POSTGRES_CONNECT_TIMEOUT_SECONDS` | Optional only with `postgres-scale`; frozen default `2.0` |
| `SECURESWIPE_IDEMPOTENCY_HMAC_SECRET` | Required only for `postgres-scale`; minimum 32 bytes; excluded from representations and errors |
| `SECURESWIPE_TEST_POSTGRES_DSN` | Test-harness-only DSN; tests must refuse non-loopback hosts or a database not ending in `_test` |
| `SECURESWIPE_AUDIT_LOG` | Existing `local-default` option; must be rejected when `postgres-scale` is selected |

Unknown backend values, missing required variables, a non-loopback test DSN,
invalid pool bounds, an unapplied migration, or store unavailability must fail
before a bounded result can be released.

### 9.6 Test isolation requirement

Every integration test and benchmark repeat gets a unique schema named from a
sanitized run UUID, worker count, concurrency, and repeat. The harness may drop
only the schema it created and must verify the prefix before cleanup. Tests may
not share idempotency keys, audit heads, tables, or connection pools across
cases. Parallel test workers must use distinct schemas.

The PostgreSQL instance and temporary volume persist across the two crash tests
but are destroyed only after their post-restart assertions finish. Failure
artifacts may retain aggregate counts and hashes, never raw rows or credentials.

## 10. Gate decision

P1-S3 implements the atomic audit event, chain-head advance, idempotency
completion, exact receipt replay, explicit verifier, and bounded single-item V2
route. The dedicated PostgreSQL correctness suite covers the approved P1-S3
reservation, conflict, restart, privacy, crash, tamper, permission, and
transaction-consistency gates and proves that normal append does not invoke the
full verifier. The frozen 256-request C6 worker workload, the 100/1,000/10,000
C10 growth measurements, and the complete S4 workload have not run.
Accordingly, no throughput, worker-improvement, public-capacity, or
production-scale claim is authorized until P1-S4 is tied to an approved clean
source SHA.
