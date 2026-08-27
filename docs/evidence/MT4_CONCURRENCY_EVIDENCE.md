# MT4 — concurrency and latency evidence

> **HISTORICAL-SERVING / NOT COMPARABLE TO MT3 HELD-OUT METRICS**

This is a **serving-plumbing** experiment. It measures request-path mechanics
on local loopback. It says **nothing** about fraud-detection quality, and no
number here may be connected to any Lane A held-out metric.

Protocol: `docs/evidence/MT4_CONCURRENCY_BENCHMARK_PROTOCOL.md`, pre-registered
and hashed before any benchmark or serving code existed.

## 1 — What was served, and what that means

| Item | Value |
| --- | --- |
| Model version | `historical-reference-xgboost-20260624-demo-v1` |
| Artifact fingerprint | `5ce63f1a7efa5625fbaa61177e76a548fd9ccc1c3f0a1530ccff835cf8b1dc73` |
| Operating threshold | `0.53` |
| Score type | `raw_score` |
| Bundle size on disk | 490,948 bytes |
| Is the sealed Lane A bundle? | **No** |

The benchmark serves a **historical demo bundle**, not the sealed Lane A
variant E model. Measuring this bundle's serving path proves nothing about the
quality of any other bundle. The two are unrelated claims.

## 2 — Environment (measured loopback facts)

| Item | Value |
| --- | --- |
| Python | 3.12.10 |
| Platform | Darwin 25.5.0, arm64, 8 CPUs |
| FastAPI / Starlette / Uvicorn | 0.141.1 / 1.3.1 / 0.52.2 |
| NumPy / scikit-learn / XGBoost | 2.5.2 / 1.9.0 / 3.3.0 |
| Workers | 1 (single process) |
| Thread env vars | all unset (MKL_NUM_THREADS, OMP_NUM_THREADS, OPENBLAS_NUM_THREADS) |
| Scope | local loopback, single machine, single worker, no external network |
| Requests per repeat | 200 after 25 discarded warm-up |
| Repeats per level | 3 |
| Client timeout | 10.0 s |

A fresh server process and a fresh audit log were used for **each** concurrency
level, so audit-chain growth from earlier levels cannot contaminate later ones.

## 3 — Concurrency matrix

Medians across 3 repeats. Every per-repeat value is in the companion JSON; the
best run was not selected.

| Variant | Concurrency | RPS | p50 ms | p95 ms | p99 ms | max ms | Successes | non-2xx | Timeouts | Transport errors | RSS MB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `baseline` | 1 | 75.9 | 12.43 | 18.40 | 23.55 | 43.30 | 600 | 0 | 0 | 0 | 126.1 |
| `baseline` | 2 | 80.7 | 24.33 | 30.16 | 35.15 | 43.77 | 600 | 0 | 0 | 0 | 127.4 |
| `baseline` | 4 | 80.5 | 49.39 | 62.27 | 81.57 | 88.13 | 600 | 0 | 0 | 0 | 126.3 |
| `baseline` | 8 | 80.0 | 96.87 | 134.70 | 150.24 | 161.05 | 600 | 0 | 0 | 0 | 132.3 |
| `baseline` | 16 | 80.6 | 189.74 | 257.24 | 286.10 | 301.94 | 600 | 0 | 0 | 0 | 138.4 |
| `lock_free` | 1 | 79.7 | 12.36 | 15.09 | 17.35 | 20.95 | 600 | 0 | 0 | 0 | 126.4 |
| `lock_free` | 2 | 73.5 | 24.36 | 38.62 | 53.45 | 59.51 | 600 | 0 | 0 | 0 | 128.1 |
| `lock_free` | 4 | 80.0 | 50.17 | 61.93 | 65.66 | 65.79 | 600 | 0 | 0 | 0 | 205.6 |
| `lock_free` | 8 | 78.4 | 100.51 | 140.41 | 163.62 | 165.03 | 600 | 0 | 0 | 0 | 128.3 |
| `lock_free` | 16 | 73.3 | 211.76 | 288.35 | 363.17 | 405.71 | 600 | 0 | 0 | 0 | 210.1 |

**Every request is accounted for.** Across all 6,000 measured requests there
were zero non-2xx responses, zero timeouts, and zero transport errors; totals
reconcile as `completed + timeouts + transport_errors == attempted`.

### Cold start

| Variant | Process ready (ms) | First scored request (ms) |
| --- | --- | --- |
| `baseline` | 1516 | 7.33 |
| `lock_free` | 1783 | 7.26 |

## 4 — What the numbers say

**Throughput does not scale with concurrency.** Successful RPS stays in a flat
~73–81 band from 1 to 16 concurrent clients, while p50 latency rises almost
exactly linearly (12 → 24 → 49 → 97 → 190 ms on the baseline). That is the
signature of a **fully serialised request path**: extra concurrency buys no
additional work, it only adds queueing delay.

## 5 — Lock-free candidate: REJECTED

The protocol's decision rule required **all** correctness checks to pass plus
either a ≥20 % median RPS gain or a ≥20 % p99 reduction, **with no p99
worsening at any level**.

Correctness passed. The performance bar did not.

| Concurrency | RPS change | p99 change |
| --- | --- | --- |
| 1 | +5.0 % | -26.3 % |
| 2 | -8.9 % | +52.1 % |
| 4 | -0.6 % | -19.5 % |
| 8 | -2.0 % | +8.9 % |
| 16 | -9.1 % | +26.9 % |

Median RPS **fell** at four of five levels, and p99 **worsened** at concurrency
2 (+52.1 %), 8 (+8.9 %) and 16 (+26.9 %). The rule is violated outright.

**The baseline is retained. The global inference lock stays exactly as shipped.**
This is a measured negative result and is reported as such.

## 6 — Why removing the lock did not help

The inference lock is **not** the binding constraint. The audit writer
re-verifies the entire hash chain from genesis before every append, so append
cost grows with log length:

| Events already in log | Append latency (ms) |
| --- | --- |
| 1 | 0.981 |
| 25 | 0.829 |
| 50 | 1.327 |
| 100 | 2.351 |
| 200 | 5.626 |
| 400 | 8.695 |
| 600 | 12.746 |

Mean of the first 50 appends: **0.895 ms**. Mean of the last 50: **12.518 ms** — a **13.99×** increase across 600 events.

That is linear per-append cost, so N appends cost O(N²) in total, plus one
`fsync` each. Because this work is serialised inside the audit writer's own
lock, removing the *inference* lock only relocates contention — which is
precisely what the matrix shows.

**This is a deliberate tamper-evidence property, not a defect.** Verifying the
chain before each append is what makes out-of-band mutation detectable. The
honest statement is that this design trades sustained append throughput for
tamper evidence, and that trade is currently unbounded in log length.

## 7 — Correctness results

All checks passed **before** any performance number was accepted.

| Check | Result |
| --- | --- |
| Concurrent semantic parity (2/8/16 threads, both variants) | bit-exact, zero mismatches |
| Baseline vs lock-free agreement | identical raw score, decision score, decision |
| Idempotent replay | duplicate id replays the first response, exactly one audit event |
| Idempotency under race (8 concurrent duplicates) | one response body, one audit event |
| Same id, different body | `409 idempotency_conflict` |
| Audit chain after concurrent load | verifies, event count exact |
| Audit tamper detection | mutation rejected |
| Admission limit | deterministic refusal, never unbounded queueing |
| Admission gate under 512 concurrent cycles | no slot leak, in-flight returns to 0 |
| Fail-closed when model unavailable | `503`, never an approve-like decision |
| Default service unchanged | still holds a real `threading.Lock` |

## 8 — Excluded by pre-registration

**Multi-worker serving was not adopted.** Idempotency, admission control and
audit state are all **process-local**. Additional workers would each hold their
own registry and gate, so duplicate suppression and the audit chain would break
across processes. This is recorded as **incompatible with current state
ownership** unless a separate durable-state task proves otherwise. It is not a
performance fix available today.

**Server-side micro-batching was not added.** It was not pre-registered, it
would need a bounded maximum wait time and its own correctness proof, and on a
path whose p99 already scales linearly it would most likely worsen tail latency.
Rejecting it as unjustified is the pre-registered outcome.

## 9 — Limitations

- **Loopback only.** No external network, no TLS, no proxy, no real client
  distance. These numbers are a floor, not a forecast.
- **Single machine, single process, single worker.** No multi-replica, no load
  balancer, no horizontal scaling evidence whatsoever.
- **No durable state.** Idempotency and audit state live in one process.
- **Synthetic requests only.** The corpus is deterministic filler with no real
  transaction data, labels, identifiers, card data, email domains or device
  strings. No response was compared against any ground truth.
- **Historical demo bundle**, not the sealed Lane A model.
- **No live-merchant evidence** of any kind.
- Matrix numbers are measured with a near-empty audit log per level and are
  therefore **optimistic** relative to a long-running server, whose append cost
  grows as section 6 shows.

## 10 — Prohibited claims

MT4 evidence may never be used to claim Razorpay-scale performance, a production
SLO or capacity guarantee, live-merchant or production throughput, external
network performance, multi-replica or durable-state behaviour, or **any**
relationship between serving throughput and fraud-detection quality.

`final_test` was not accessed at any point in this experiment.
