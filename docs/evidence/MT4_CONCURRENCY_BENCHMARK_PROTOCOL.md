# MT4 concurrency and latency benchmark protocol

**Pre-registered before any benchmark or serving code was written.** This
document is hashed and its digest recorded before implementation begins, so the
order of events is verifiable rather than asserted.

This is a **serving-plumbing experiment**. It measures request-path mechanics.
It says nothing about fraud-detection quality, and no result here may be
connected to any Lane A held-out metric.

## 1 — Provenance and comparability

The benchmark serves the committed `historical-reference-demo-v1` bundle,
verified through the normal bundle loader with artifact fingerprint
`5ce63f1a7efa5625fbaa61177e76a548fd9ccc1c3f0a1530ccff835cf8b1dc73`.

**This is not the sealed Lane A variant E bundle.** Every MT4 result therefore
carries the label:

> `HISTORICAL-SERVING / NOT COMPARABLE TO MT3 HELD-OUT METRICS`

Benchmarking this bundle proves nothing about the quality of any other bundle,
and no MT4 number may be presented as evidence about Lane A performance.

## 2 — Scope

- **Local loopback only**, single machine, single process, no external network.
- No public-network, multi-replica, or live-merchant claim may be derived.
- Latency excludes real network transit; results are a floor, not a forecast.

## 3 — Synthetic request corpus

Requests are generated deterministically from a fixed seed. The corpus contains
**no real transaction data, labels, identifiers, card data, email domains,
device strings, amounts drawn from real records, or any private value**. Feature
names are the published PCA component names (`Time`, `V1`–`V28`, `Amount`);
values are arithmetic functions of the row index only.

No label is present in any request, and no response value is compared against
any ground truth. The corpus is fixed across every configuration and repeat so
that configurations are compared on identical input.

## 4 — Measured matrix

- **Concurrency levels:** `1, 2, 4, 8, 16`.
- **Repeats:** at least **3** measured repeats per configuration and level.
- **Warm-up:** a fixed warm-up burst is issued and discarded before each
  measured repeat, so cold-start cost never contaminates steady-state numbers.
- **Fixed request count** per repeat, identical at every level.
- **Fixed per-request timeout.** A timeout is a counted outcome, never a retry.

### Measured fields

Successful RPS; total, completed, and in-flight-at-end request counts; non-2xx
responses by status; timeouts; transport errors; p50/p95/p99/max latency; CPU
time; peak RSS; cold-start (first-request) latency; bundle size on disk; and the
full environment fingerprint.

### Counting rule

**Every request is accounted for.** Successes, non-2xx responses, admission
rejections, timeouts, and transport errors are counted and reported. No request
is silently dropped, retried, or excluded, and totals must reconcile:
`completed + timeouts + transport_errors == attempted`.

## 5 — Correctness checks

Correctness is verified **before** performance is reported, and a performance
gain never overrides a correctness failure.

1. **Deterministic response parity** — identical synthetic input yields
   identical decision and score across configurations and concurrency levels.
2. **Duplicate-event / idempotency** — a repeated request identifier replays the
   first response and appends exactly one audit event, never two.
3. **Audit-chain validity** — the append-only hash chain verifies after every
   configuration, with event count reconciling against accepted requests.
4. **Admission-limit behaviour** — beyond the configured limit the service
   rejects deterministically with its capacity error rather than queueing
   unboundedly or crashing.
5. **Failure-safe behaviour** — an unavailable or failing model path fails
   closed, never returning an approve-like decision.

## 6 — Configurations, in order

1. **Baseline** — the existing admission limit and the existing global inference
   lock, exactly as shipped. This is the correctness reference.
2. **Lock-free candidate** — evaluated **only if** concurrent parity, audit
   correctness, idempotency correctness, and failure behaviour all pass first.

### Lock-removal decision rule

The lock-free configuration is **accepted only if all** of the following hold:

- concurrent semantic parity is exact, with zero mismatches;
- audit-chain validity and event counts are unchanged;
- idempotency behaviour is unchanged;
- admission and failure behaviour are unchanged;
- **and** it delivers a material improvement — at least a **20 % increase in
  median successful RPS** or at least a **20 % reduction in p99 latency** at one
  or more concurrency levels, with no worsening of p99 at any level.

If any correctness check fails, or if the throughput and tail-latency gains fall
below that bar, the **baseline is retained and the negative result is reported**.
A measured negative result is a valid and publishable outcome.

## 7 — Excluded by pre-registration

- **Multi-worker serving is not a permitted performance fix.** Idempotency,
  admission control, and audit state are process-local, so multiple workers
  would break replay and audit guarantees. It is recorded as **incompatible with
  current state ownership** unless a separate durable-state task proves
  otherwise.
- **Server-side micro-batching is not pre-registered here** and will not be
  added in MT4. Adding it would require its own pre-registration with a bounded
  maximum wait time and its own correctness proof. Rejecting it as unjustified
  is an acceptable and preferred outcome if it would worsen p99 latency.
- **Default service behaviour stays unchanged** unless the experiment proves a
  safe replacement and every existing contract test still passes.

## 8 — Instrumentation and privacy

Stage timing may be recorded for request validation, preprocessing, inference,
decision policy, idempotency, audit append, and response serialization. All
instrumentation is **low-cardinality aggregate timing only**.

Never recorded, logged, or exported: request bodies, feature values, scores tied
to a record, identifiers, private paths, or any user information. Preserved
benchmark records must be public-safe aggregate JSON containing no request data.

## 9 — Reporting rules

- Report **medians across repeats and every per-repeat value**. Cherry-picking
  the best run is prohibited.
- Report bottlenecks honestly, including where the serving path is limited by
  the interpreter, the lock, or per-request model overhead.
- Loopback findings are **not** public-network or production claims.

## 10 — Prohibited claims

MT4 evidence may never be used to claim Razorpay-scale performance, a production
SLO or capacity guarantee, live-merchant or production throughput, external
network performance, multi-replica or durable-state behaviour, or **any**
relationship between serving throughput and fraud-detection quality.

`final_test` is not read, opened, counted, materialised, scored, or evaluated by
anything this protocol authorises.
