# P1-S4d client transport and ingress-wait attribution evidence

Verdict: **CLIENT TASK QUEUE IDENTIFIED**

This local diagnostic identifies load-generator scheduling and client setup as
material measurement constraints. It did not tune the client, API, PostgreSQL,
workers, pools, operating system, model, or workload. It does not authorize a
scalability, capacity, SLO, production, or Razorpay-scale claim, and every
[P1-S1 scale gate](P1_SCALE_PROTOCOL.md) remains unchanged.

## 1. Measurement identity and preflight

- Authoritative starting commit:
  `c7175a6022af55295493b7011efb0076dd2fdc4d`
- Pre-registration commit:
  `5b91ea8fe884cb4e346f658e3453e482fd87c229`
- Measurement source commit:
  `5b91ea8fe884cb4e346f658e3453e482fd87c229`
- Exact instrumentation-file digest:
  `7cc374624db166c4555de4cb382660bdd641bb82eabb4417704befbc16d2d712`
- [Pre-registered protocol](P1_S4D_CLIENT_TRANSPORT_PROTOCOL.md), hashed before
  implementation:
  `d8fde6108af5e7cf0b1771c77f9ace71778b155102ed1071d38e379742253f6e`
- Parent P1-S4c artifact:
  `reports/benchmarks/p1-scale-results/p1-s4c-lifecycle-1788130435.json`,
  SHA-256
  `403dc5907c5c71838f9a7d118c68d088685178cc68f20ab44a22aacb5725d73f`
- Result artifact:
  `reports/benchmarks/p1-scale-results/p1-s4d-client-transport-1788153293.json`,
  SHA-256
  `aefa8a5a48e5bb94c0577ba9438ed8c1f487ddeaadc707de3a2398a9a30861ee`
- Model fingerprint:
  `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3`
- Synthetic bundle-manifest SHA-256:
  `b3123da086cdc79374db1f68d815a82102c0da38a63755ac80ceacec1fe14d74`

Initial tracked and staged state was clean. The branch was
`codex/p1-core-checkpoint`; the required P1-S4c code and parent artifact were
present and the parent hash matched. Port 55432 was free. The diagnostic never
inspected, bound, or modified port 5432. Preserved unrelated untracked paths
remained outside staging.

The measurement source commit identifies the pre-registration boundary. The
instrumentation digest hashes, in path order, the exact bytes of the benchmark
runner, dedicated diagnostic runner, and client-timing module used for the
measurement. This mirrors the established P1-S4c evidence procedure and avoids
claiming that an uncommitted instrumentation file was present in the source
commit.

## 2. Implementation and activation boundary

| File | Purpose |
| --- | --- |
| `src/operations/p1_scale_client_timing.py` | Exact opt-in, monotonic transient timers, supported HTTP trace parsing, thread-safe aggregate reducer |
| `scripts/run_p1_scale_benchmark.py` | Keeps the default request path unchanged; enables timing only for exact opt-in |
| `scripts/run_p1_s4d_client_diagnostic.py` | Runs only the four frozen cells, retains safe incremental aggregates, verifies correctness and cleanup |
| `tests/test_p1_scale_client_timing.py` | Activation, timing, trace, aggregation, privacy and correctness tests |
| `docs/OPERATIONS.md` | Operator boundary and limitations |

Only exact `SECURESWIPE_SCALE_CLIENT_TIMING=1` activates client timing. Missing,
blank, `0`, `true`, and whitespace-padded values are inert. No API source file,
response, header, route, schema, database column, audit event, model behavior,
timeout, or `local-default` path changed.

## 3. Environment and observed client configuration

| Field | Observed value |
| --- | --- |
| Host | Apple M2 arm64, 8 logical CPUs, 8 GiB RAM |
| OS | macOS 26.5.2 arm64 |
| Python / FastAPI / Uvicorn | 3.12.10 / 0.141.1 / 0.52.2 |
| HTTPX / HTTPcore | 0.28.1 / 1.0.9 |
| Psycopg / Psycopg Pool | 3.3.4 / 3.3.1 |
| PostgreSQL | 16.10, task-owned `postgres:16-alpine` digest `029660…42297` |
| Target | local `postgres-scale`, `POST /v2/predict`, `127.0.0.1:55432` |
| Timeout | 10 seconds, unchanged |
| Client | synchronous HTTP/1.1; HTTP/2 and redirects disabled; `trust_env=true` |
| Client lifetime | one new `httpx.Client` for every request |
| Per-client defaults | max 100 connections, max 20 keep-alive connections, 5 s keep-alive expiry |

The public HTTPX/HTTPcore trace interface exposed TCP connect and HTTP/1.1
send/receive spans. It did not expose connection-pool acquisition. Pool wait is
therefore `not_observable`; no private monkey-patch or percentile subtraction
was used.

## 4. Four-cell results

These are the measured 1,000-request repeats. Warm-up remained separate at the
frozen 70 owner / 20 replay / 10 malformed mix.

| Workers | Concurrency | Repeat | Successful RPS | E2E p50 ms | E2E p95 ms | E2E p99 ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 1 | 37.546 | 189.879 | 318.487 | 395.724 |
| 4 | 32 | 1 | 29.626 | 949.941 | 1,548.051 | 1,856.861 |
| 4 | 64 | 1 | 29.938 | 1,951.271 | 2,910.096 | 3,215.156 |
| 4 | 64 | 2 | 29.049 | 1,992.294 | 2,959.048 | 3,354.976 |

Instrumentation E2E count was 1,000 in every measured cell and its p50 exactly
reconciled, at the published precision, with the pre-existing benchmark E2E
distribution.

## 5. Client phase timing

Each entry is measured-phase median / p95 / p99 in milliseconds. Values are
aggregates of the same per-request phase; no percentiles were subtracted.

| Workers / concurrency / repeat | Executor queue | Client setup | TCP connect | Request send | Combined response headers | Body read | Client E2E |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 / 8 / 1 | 11,822.842 / 22,869.568 / 23,655.085 | 141.382 / 225.139 / 266.847 | 0.675 / 9.305 / 33.714 | 0.211 / 5.521 / 32.413 | 45.206 / 120.408 / 174.594 | 0.496 / 6.807 / 30.056 | 189.879 / 318.487 / 395.724 |
| 4 / 32 / 1 | 13,835.438 / 27,906.504 / 28,938.426 | 784.615 / 1,139.004 / 1,333.108 | 3.670 / 74.280 / 165.577 | 0.232 / 40.808 / 90.464 | 135.426 / 521.630 / 832.236 | 0.581 / 30.809 / 99.699 | 949.941 / 1,548.051 / 1,856.861 |
| 4 / 64 / 1 | 13,528.017 / 25,621.238 / 27,327.819 | 1,564.748 / 2,222.233 / 2,334.151 | 18.133 / 136.135 / 263.609 | 0.334 / 67.239 / 167.044 | 343.166 / 1,062.701 / 1,267.530 | 0.569 / 36.563 / 80.306 | 1,951.271 / 2,910.096 / 3,215.156 |
| 4 / 64 / 2 | 15,496.512 / 28,426.884 / 30,228.059 | 1,639.949 / 2,360.007 / 2,644.404 | 15.450 / 153.588 / 221.040 | 0.313 / 80.115 / 150.699 | 324.514 / 970.599 / 1,252.212 | 0.572 / 33.415 / 108.019 | 1,992.294 / 2,959.048 / 3,354.976 |

“Combined response headers” is request execution start through response headers
available. The narrower HTTPcore receive-header trace medians were 40.488,
101.028, 280.019, and 270.507 ms respectively. Neither measure is named
precise ingress time.

The same-request median ratios establish:

| Cell | Executor queue / scheduled total | Client setup / E2E | TCP / E2E | Send / E2E | Combined headers / E2E |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 / 8 / 1 | 98.443% | 73.751% | 0.405% | 0.128% | 24.595% |
| 4 / 32 / 1 | 93.544% | 83.681% | 0.383% | 0.029% | 15.230% |
| 4 / 64 / 1 | 87.155% | 80.695% | 0.910% | 0.023% | 18.902% |
| 4 / 64 / 2 | 89.008% | 82.315% | 0.764% | 0.021% | 17.118% |

Connection-pool acquisition was `not_observable` in every cell. Every measured
request was traced as a new connection: 1,000 new, zero reused, zero unknown in
each cell. Each warm-up likewise recorded 100 new, zero reused, zero unknown.
This is consistent with, but does not add causation beyond, the frozen
one-client-per-request policy. TCP connect never approached the 50% dominance
gate.

## 6. Correctness reconciliation

Every cell passed all frozen correctness gates:

- measured: exactly 900 HTTP 200 and 100 expected HTTP 422;
- combined warm-up/measured lifecycle: 770 owners, 220 completed replays, zero
  pending/fail-closed outcomes;
- audit growth: 70 warm-up and 700 measured events;
- full audit-chain verification: verified;
- zero unexpected statuses, timeouts, transport errors, response mismatches,
  duplicate audit events, and diagnostic-recording failures; and
- malformed requests created no audit events, as proved by audit growth matching
  owner requests only.

## 7. Supported diagnosis and limits

The pre-registered client-task-queue rule is satisfied in all four cells:
executor wait exceeds 50% of the same request's scheduled lifetime at the
median. The harness submits all requests to an executor whose worker count
equals concurrency, so most scheduled lifetime is spent waiting for a client
task to begin. This identifies the load-generator scheduling path as a
measurement constraint; it does not authorize changing executor sizing here.

The formerly unexplained legacy E2E window is also substantially attributed to
the existing client-setup boundary: creating a new synchronous HTTPX client and
building its request represents 73.8–83.7% median of same-request E2E. This
boundary is directly measured but does not separate HTTPX initialization,
environment processing, transport construction, or request construction. It
must not be relabelled as connection-pool wait or server ingress.

TCP connect, request send, and body read do not dominate. Combined response
headers also do not cross the 50% median rule. Because pool acquisition is not
observable and the response-header path remains combined, no precise ingress,
socket-backlog, worker-dispatch, or pre-handler attribution is claimed. A
separately versioned harness-validation task is the only evidence-supported
next investigation. No server tuning or architecture change is justified by
this result.

## 8. Verification and cleanup

| Check | Result |
| --- | --- |
| Focused client/harness/lifecycle/timing tests | PASS — 84 passed |
| Fresh task-owned PostgreSQL S2/S3 integration tests | PASS — 22 passed |
| Relevant broader scale test set without configured external DSN | PASS — expected 21 integration skips |
| Ruff on changed Python | PASS |
| Repository-accurate Mypy (`--ignore-missing-imports`) on three critical files | PASS — no issues |
| Compilation of changed Python | PASS |
| `pip check` | PASS — no broken requirements |
| Diagnostic artifact privacy/forbidden-field scan | PASS — zero findings; no per-request arrays |
| Markdown relative-link check | PASS |
| `git diff --check` | PASS |
| Full Python suite | 1,368 passed, 21 skipped, 2 known unrelated failures; 1,391 collected |

An initial accidental system-interpreter check stopped during collection with
`ModuleNotFoundError: No module named 'psycopg'`. No dependency was installed;
all authoritative checks used the existing Python 3.12.10 `.venv`.

The full Python suite reproduced the two known unrelated failures: the
preserved untracked recovered-demo packager uses an obsolete `ModelBundle`
constructor (`test_packages_hash_verified_recovered_demo_with_limited_provenance`),
and the unchanged README lacks an older project-setup string
(`test_readme_separates_reference_corpus_new_development_and_audit_modes`).
Neither path overlaps P1-S4d.

The runner removed its task-owned API processes, PostgreSQL container, volume,
schemas, credentials, raw logs, and transient lifecycle files. Port 55432 was
closed afterward. Only the Git-ignored aggregate result remains. Nothing was
pushed or deployed.
