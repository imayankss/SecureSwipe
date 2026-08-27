# MT6 — state, invariants and crash-recovery decision record

**Decision: `ADOPT LOCAL SQLITE PROTOTYPE`** — as an optional, non-default
backend. The existing in-memory registry remains the default and the shipped API
behaviour is unchanged.

Protocol: `docs/evidence/MT6_STATE_AND_CRASH_PROTOCOL.md`, pre-registered and
hashed before any harness or state code existed.

## 1 — Observed request ordering

`reserve → score → audit append + fsync → complete → HTTP response`, with
`registry.fail()` on any exception. **Audit append precedes idempotency
completion, and idempotency state is never written to disk.**

## 2 — State-ownership map

| State item | Owner | Persistence | Restart | Concurrency | Privacy class | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| Idempotency entries | `IdempotencyRegistry` | In-memory dict | **Lost** | `asyncio.Lock`; waiters block on a ready event | Hashed key + input digest | Not durable; completed entries grow unboundedly |
| Admission slots | `ConcurrencyGate` | In-memory counter | Reset | `threading.Lock`, non-blocking, no queue | No request data | Process-local |
| Audit chain | `AuditLog` | NDJSON + head anchor, fsync per append | Re-verified on open; refuses a broken chain | `threading.Lock`; full chain re-verified per append | Hashed key, input digest, score, decision, model metadata | O(n) per append, O(N²) long-run (MT4) |
| Model bundle | `ModelService` | Read-only artifact, digest-verified | Reloaded and re-verified | Global inference lock (retained, MT4) | No request data | Single process |
| Metrics | in-process registry | In-memory | Reset | Counter updates | Aggregate only | Not durable |

## 3 — Invariant and crash-recovery matrix

Every row is demonstrated by a test in
`tests/test_operations_state_recovery.py`. Nothing is asserted without a test.

| # | Fault point | Outcome | Idempotency state | Audit chain | Rescoring? | Duplicate event? | Unsafe approval? | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Before reservation | `422` | none created | 0 events | no | no | no | **OK** |
| 2 | After reservation, before scoring | `5xx` | key released | 0 events | on honest retry only | no | no | **OK** |
| 3 | After scoring, before durable commit | `5xx` (audit unavailable) | key released | 0 events | on retry | no | no | **OK** |
| 4 | Crash after audit fsync, before completion | `5xx` | key released | **1 event, orphaned** | — | — | no | partial |
| 4b | …then a retry of the same key | **`200`** | new entry | **2 events → chain unverifiable** | **yes** | **yes** | no | **GAP G1** |
| 5 | Crash after completion, before response | `5xx`, then retry `200` | key released | **2 events → chain unverifiable** | **yes** | **yes** | no | **GAP G2** |
| 6 | Restart + duplicate retry | `200` | registry empty | **2 events → chain unverifiable; log cannot reopen** | **yes** | **yes** | no | **GAP G3** |
| 6b | Same-process replay | `200`, `X-Idempotent-Replay: true` | replayed | 1 event | no | no | no | **OK** |
| 6c | Same key, different body | `409` | conflict | 1 event | no | no | no | **OK** |
| 7 | Mutation / truncation / corruption | refuses at open | n/a | detected | no | no | no | **OK** |
| 8 | Unwritable sink | `5xx` | key released | 0 events | no | no | no | **OK** |
| 8b | Missing model fingerprint | **refuses to start** | n/a | 0 events | no | no | no | **OK** |

**No fault point produced an approval-like or below-threshold-success response.**
Fail-closed behaviour held everywhere, including two paths that refuse startup
outright rather than serving unauditable decisions.

## 4 — Observed gaps

Three gaps, one root cause.

- **G1** — a crash after the audit event is durable but before completion
  releases the idempotency key. The retry rescores, returns **`200`**, and writes
  a duplicate event.
- **G2** — a crash after completion but before the response takes the same
  failure path, with the same result.
- **G3** — after a process restart the registry is empty while the audit log is
  not. A duplicate retry rescores and writes a second event.

In all three the chain then contains two events sharing a `request_id`, so
`verify_audit_log` fails permanently and **the service can no longer reopen its
own audit log**. That is fail-closed rather than wrong, but it converts a
recoverable retry into total unavailability.

**Root cause:** the audit event is durable; the idempotency record is not, and is
discarded on failure. The durable and non-durable halves disagree.

Violated invariants: 1 and 4 (exactly one audit event per completed decision).

## 5 — Decision rationale

The protocol requires a simpler in-process repair to be preferred if it fully
closes every demonstrated gap.

- **G1 and G2 can** be closed in-process, by not releasing the key once the audit
  event is durable.
- **G3 cannot.** After a restart the in-memory registry is gone. Closing it
  requires durable keyed state. The audit log is durable, but it is an
  append-only chain with no lookup index, and MT4 measured its verification as
  O(n) per append and O(N²) long-run — so rebuilding idempotency from it at
  startup would inherit that cost and hold every historical request in memory.

A durable keyed store is therefore necessary, not merely convenient. Against the
pre-registered criteria:

| Criterion | Met |
| --- | --- |
| Repairs ≥1 demonstrated gap | Yes — G1, G2 and G3 |
| Stores no raw payload or private data | Yes — verified by direct database-byte inspection |
| Preserves fail-closed behaviour | Yes — `UNRESOLVED` never rescores |
| Synthetic crash tests prove recovery | Yes — 25 tests |
| No distributed/immutable claim | Yes — scanned |
| Standard-library `sqlite3`, explicit local file | Yes |
| Small enough for a reviewer walkthrough | Yes — one module, eight columns |

## 6 — What was built

An **optional** `SqliteIdempotencyStore`. The in-memory registry remains the
default; `api/` is unchanged.

- **Configuration safety:** absolute path required; symlinks refused; a path
  inside the repository refused; missing parent refused.
- **Stored columns, and nothing else:** `key_sha256`, `input_digest_sha256`,
  `state`, `decision`, `model_version`, `audit_event_hash`, `created_utc`,
  `resolved_utc`. No payload, feature, per-record score, label, or plaintext
  identifier. `decision` is restricted to a three-value allowlist.
- **Lifecycle:** `PENDING → COMPLETED | FAILED | UNRESOLVED`.
- **Recovery:** any `PENDING` row found at open becomes `UNRESOLVED`. An
  `UNRESOLVED` key is **never rescored** — a retry fails closed and points the
  operator at the audit evidence.
- **Honest retryability:** a failure with **no** durable audit event is marked
  `FAILED` and may be retried; a failure **with** a durable audit event becomes
  `UNRESOLVED`, which is what closes G1 and G2.
- **Atomicity:** completion runs in a `BEGIN IMMEDIATE` transaction and rolls
  back on injected failure, leaving the row `PENDING` — which then recovers to
  `UNRESOLVED` on the next open.

## 7 — Non-claims

This is **local single-node durability only**. It is **not** immutable or WORM
storage, **not** ACID across services, **not** a multi-writer scale solution,
**not** high availability, **not** multi-region resilience, and **not** a
cross-host failover mechanism. Concurrent multi-process writing is explicitly
unsupported and untested. Multi-worker serving remains incompatible with current
state ownership (MT4).

**No performance claim is made.** MT4's audit-growth measurement stands as
evidence for the implementation it measured. This prototype does not change the
audit writer, and any new benchmark belongs to a separate versioned task.

## 8 — Relationship to MT4's audit-growth trade-off

MT4 measured audit append cost growing from 0.895 ms to 12.518 ms across 600
events, because the writer re-verifies the whole chain before each append. That
same property is what makes the audit log unsuitable as an idempotency index,
and it is why the duplicate-event gaps are so damaging: once two events share a
`request_id`, every future append and every restart fails. The durable store
avoids adding load to that path — it records only a digest of the audit event.

## 9 — Future architecture note

A production system would not scale this prototype up. It would need separately
designed durable shared state with an explicit outbox or two-phase publication
between the decision record and the audit sink, designed for multiple writers and
host failure. That is a distinct design task, not an informal SQLite extension,
and nothing here should be read as a step toward one.

`final_test` was not accessed. Every fixture is synthetic.
