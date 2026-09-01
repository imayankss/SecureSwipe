# P1-S4e validated harness and final-run evidence

Verdict: **CORRECTNESS FAILURE — RESULTS INVALID**

The bounded, connection-reusing client harness passed its deterministic and
live smoke gates. The exact full run then completed 34 cells and failed closed
at four API workers, concurrency 64, repeat 2. Fifty-two measured requests
returned HTTP 503 with structured code `state_store_unavailable`; committed
audit events still formed a valid chain, but the exact request/audit contract
did not reconcile. Performance interpretation stopped, the failed cell was not
retried, repeat 3 was not run, and no service or database setting was changed.

## 1. Identity and preserved evidence

| Item | Identity |
| --- | --- |
| Starting P1-S4d commit | `9e5cd1d43e470c4454de67113dcd789a6e99cea1` |
| S4e protocol commit | `13b1190e1fddf90826f036a1a80a3bcbbc1412fd` |
| Harness commit | `4ef9bda9a0f9c715fdeefc62477328f4b588833a` |
| Timing-rounding repair commit | `7e81b8041b6244af1f7620e8d6145403f436124c` |
| Full-run source SHA | `7e81b8041b6244af1f7620e8d6145403f436124c` |
| [S4e protocol](P1_S4E_VALIDATED_HARNESS_PROTOCOL.md) SHA-256 | `d40ef3e36bdd7fb2f0a26df494fddaca11b92698383893fd5811cd4f64ecf062` |
| S4e smoke artifact | `reports/benchmarks/p1-scale-results/p1-s4e-smoke-1788155246.json` |
| S4e smoke SHA-256 | `ad3299d5b705727e9027faebc20e16a34df70b7a65702ba020d611f50c9d1996` |
| S4e full partial artifact | `reports/benchmarks/p1-scale-results/p1-s4e-full-1788155851-partial.json` |
| S4e full partial SHA-256 | `6870e59520807a2695ed38ecfae6be98fd2ca8be83ccc62f7fea8145a64f2349` |
| S4e incremental progress SHA-256 | `e543b10beb8bcfb5318f728cf3adbd413e4a0c78aa1747510bf1c1b61a7c6f7e` |
| Model fingerprint | `a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3` |

P1-S4b, P1-S4c, and P1-S4d artifacts remain preserved historical
diagnostics. They were not overwritten, deleted, or relabelled. The legacy
P1-S1 matrix is `HARNESS-CONSTRAINED / NOT SERVER-SCALING EVIDENCE` and must
not support README, pitch, deployment, or release performance claims.

An initial S4e full invocation at source `4ef9bda` stopped in the first cell
because identical underlying E2E samples passed through a four-decimal aggregate
and three-decimal published representation. A focused repair allows only the
maximum 0.0011 ms publication-rounding delta. The exact affected full-sized
one-worker/concurrency-one repeat then passed all gates before the complete run
restarted from clean source `7e81b80`. This repair did not alter request timing,
workload, service behavior, or pass/fail thresholds.

## 2. Environment and frozen run

| Field | Observed value |
| --- | --- |
| Host | Apple M2 arm64, 8 logical CPUs, 8 GiB RAM |
| OS | macOS 26.5.2 arm64 |
| Python / FastAPI / Uvicorn | 3.12.10 / 0.141.1 / 0.52.2 |
| HTTPX / HTTPcore | 0.28.1 / 1.0.9 |
| Psycopg / Psycopg Pool | 3.3.4 / 3.3.1 |
| PostgreSQL | 16.10, pinned `postgres:16-alpine` image digest `029660…42297` |
| API | local `postgres-scale`, `POST /v2/predict` |
| PostgreSQL endpoint | task-owned `127.0.0.1:55432`; port 5432 untouched |
| Workload | deterministic synthetic-only `p1-scale-fixture-v1` |
| Timeout | 10 seconds, unchanged |

The intended matrix was workers 1/2/4, concurrency 1/8/32/64, and three
repeats: 36 cells. Each repeat retained 70 owner + 20 completed replay + 10
malformed warm-up attempts, followed by 700 owner + 200 completed replay + 100
malformed measured attempts. No result was retried, selected, or tuned.

## 3. Harness validation

The live one-worker/concurrency-eight smoke passed:

| Gate | Evidence |
| --- | --- |
| Client topology | One shared thread-safe HTTPX client per cell, created before warm-up |
| Limits | 8 maximum connections, 8 keep-alive connections, 30-second expiry |
| Outstanding work | Maximum 8, configured bound 8 |
| Scheduler queue | p99 1.6104 ms; limit 10 ms |
| Per-request client setup | Zero; cell setup 32.2563 ms remained outside E2E |
| Warm-up connections | 8 new, 2 reused, 0 unknown |
| Measured connections | 0 new, 10 reused, 0 unknown |
| Measured reuse | 100% |
| Smoke correctness | 9 HTTP 200, 1 expected HTTP 422, audit growth 7/7, chain verified |

Across all 34 completed full-run cells:

- every measured phase used exactly its configured concurrency as the maximum
  outstanding-work count;
- scheduler queue p99 ranged from 0.3283 to 17.7096 ms and passed each cell's
  pre-registered `max(10 ms, 5% of E2E p50)` limit;
- measured connection totals were 0 new, 34,000 reused, 0 unknown: 100% reuse;
- warm-up totals were 817 new, 2,583 reused, 0 unknown;
- per-request client setup was zero in every cell; and
- source inspection and deterministic tests prove `_run_workload` contains no
  `httpx.Client` construction; the sole cell client is constructed in
  `_run_repeat` before either warm-up or measured traffic.

Connection-pool acquisition remained `not_observable` through supported public
HTTPX/HTTPcore hooks. No private monkey-patch or API/header change was used.

## 4. Final matrix execution status

No final median RPS/latency matrix exists because the correctness gate failed.
Calculating worker-scaling gates from a partial matrix would violate the
[pre-registered protocol](P1_S4E_VALIDATED_HARNESS_PROTOCOL.md).

| Workers | Concurrency | Completed repeats | Status |
| ---: | ---: | ---: | --- |
| 1 | 1 | 3/3 | Correctness and harness gates passed |
| 1 | 8 | 3/3 | Correctness and harness gates passed |
| 1 | 32 | 3/3 | Correctness and harness gates passed |
| 1 | 64 | 3/3 | Correctness and harness gates passed |
| 2 | 1 | 3/3 | Correctness and harness gates passed |
| 2 | 8 | 3/3 | Correctness and harness gates passed |
| 2 | 32 | 3/3 | Correctness and harness gates passed |
| 2 | 64 | 3/3 | Correctness and harness gates passed |
| 4 | 1 | 3/3 | Correctness and harness gates passed |
| 4 | 8 | 3/3 | Correctness and harness gates passed |
| 4 | 32 | 3/3 | Correctness and harness gates passed |
| 4 | 64 | 1/3 passed | Repeat 2 failed; repeat 3 not run |

The separately frozen 10,000-event audit-growth stage was not reached and is
`NOT RUN` for S4e. Earlier audit-growth evidence remains historical only.

## 5. Correctness failure

The failing cell was workers 4 / concurrency 64 / repeat 2, measured phase:

| Observation | Result |
| --- | ---: |
| HTTP 200 | 848 |
| Expected HTTP 422 | 100 |
| HTTP 503 | 52 |
| Structured 503 code | `state_store_unavailable` (52) |
| Structured category | `database_state_store` (52) |
| Client timeout / transport error | 0 / 0 |
| Audit events after warm-up and measured traffic | 726 |
| Full-chain verifier | Passed over committed events |

The code was not `idempotency_in_progress`; this was not a replay-winner
classification problem. The exact 900/100 response and 70/700 audit-growth
contract failed. The fail-closed responses and valid chain are truthful safety
behavior, but they do not satisfy the frozen benchmark correctness gate.

The harness had already demonstrated bounded outstanding work, zero per-request
client creation, and 100% measured reuse. Therefore no load-generator defect
was established that could truthfully repair this result. The service,
PostgreSQL, server pool, Uvicorn, audit, idempotency, and operating-system
settings were not changed. The cell was not retried.

## 6. Claim boundary and P1-S4 status

S4e would be the only current performance evidence only after all 36 cells and
correctness gates pass. They did not. Consequently:

- S4e RPS, latency, CPU, and RSS values are not authorized performance evidence;
- no worker-scaling or flat-scaling conclusion is authorized;
- P1-S4 is **not complete** under the S4e completion rule;
- no scalability, production-capacity, multi-region, public-network,
  Razorpay-scale, SLO, savings, ROI, or cost claim is authorized; and
- no S4f is proposed or begun by this task.

All traffic was local loopback, single-machine, and synthetic, and is unrelated
to held-out fraud-detection quality. Core XGBoost scoring uses zero LLM tokens.

## 7. Cleanup and evidence safety

The harness removed its task-owned API process group, PostgreSQL container,
volume, schemas, role/credentials, raw logs, and temporary bundle after safe
partial aggregate capture. Port 55432 was closed afterward. Port 5432 was never
inspected or modified. The ignored partial/progress artifacts contain no raw
per-request timings, IDs, bodies, features, scores, labels, secrets, DSNs, PAN,
CVV, or raw audit/database content.

## 8. Verification

| Check | Result |
| --- | --- |
| Focused S4e harness, timing, lifecycle, scale-contract, API, audit, and durable-idempotency tests | PASS — 158 passed |
| Fresh task-owned PostgreSQL S2/S3 integration tests | PASS — 22 passed; task-owned database removed and port 55432 closed |
| Ruff over `api`, `src`, `scripts`, and `tests` | PASS |
| Canonical Mypy set (27 files) and focused S4e source set | PASS |
| Python compilation | PASS |
| `pip check` | PASS — no broken requirements found |
| S4e artifact privacy scan | PASS — three artifacts, zero forbidden fields and no per-request arrays |
| Modified-document relative links | PASS — five checked, zero failures |
| `git diff --check` | PASS |
| Full repository test suite | PRE-EXISTING / OUT OF SCOPE — 1,373 passed, 21 skipped, 2 failed |

The two full-suite failures are unchanged unrelated working-tree conditions:
the preserved untracked recovered-demo packager constructs `ModelBundle`
without three now-required metadata arguments, and the unchanged README omits
an older project-setup assertion for `--source-kind historical_kaggle_reference`.
Neither path was edited or included in S4e. The S4e-focused and PostgreSQL
verification sets passed.
