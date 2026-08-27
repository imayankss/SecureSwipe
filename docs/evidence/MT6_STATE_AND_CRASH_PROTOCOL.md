# MT6 — state, invariants and crash-recovery protocol

**Pre-registered before any fault-injection harness or state code was written.**
This document is hashed and its digest recorded before implementation begins.

Scope: local, single-process state behaviour. Nothing here claims production
durability, ACID across services, immutability, high availability, multi-region
resilience, or multi-replica safety.

## 1 — Observed request ordering

Read from `api/main.py` `/v1/predict`:

1. derive `request_id` from the `X-Request-ID` header;
2. compute the canonical `input_digest_sha256`;
3. **idempotency reservation** (`registry.reserve`);
4. if not owner → **replay** the first result and return;
5. **scoring** through the admission gate, threadpool and timeout;
6. metrics observation;
7. **audit append + fsync** (`append_audit_evidence`);
8. **idempotency completion** (`registry.complete`);
9. **HTTP response**.

On any exception the owner calls `registry.fail`, which **deletes** the entry so
the key becomes retryable, then re-raises.

Audit append therefore precedes idempotency completion, and idempotency state is
never written to disk.

## 2 — State-ownership map

| State item | Owner | Persistence boundary | Restart behaviour | Concurrent-request behaviour | Privacy class | Current limitation |
| --- | --- | --- | --- | --- | --- | --- |
| Idempotency entries | `IdempotencyRegistry` on `app.state` | In-memory dict, process-local | **Lost entirely** | `asyncio.Lock` on reserve/fail; waiters block on a ready event | Hashed key + input digest only | Not durable; grows unboundedly for completed entries |
| Admission slots | `ConcurrencyGate` on `app.state` | In-memory counter, process-local | Reset to zero | `threading.Lock`, non-blocking, no queue | No request data | Not shared across processes |
| Audit chain | `AuditLog` writer | NDJSON file + head anchor, fsync per append | Re-verified on open; refuses to open a broken chain | `threading.Lock`; whole chain re-verified per append | Hashed key, input digest, score, decision, model metadata | O(n) per append, O(N²) long-run (MT4) |
| Model bundle | `ModelService` | Read-only artifact, verified by digest | Reloaded and re-verified | Global inference lock (retained, MT4) | No request data | Single process |
| Metrics | in-process registry | In-memory | Reset | Counter updates | Aggregate only | Not durable |

## 3 — Pre-registered invariants

1. Same idempotency key + identical canonical body returns the original completed
   result and creates **exactly one** audit event.
2. Same idempotency key + different body returns a conflict and creates no
   additional scoring result and no additional audit event.
3. No approval-like or below-threshold-success response is emitted when the
   model, audit sink, or state integrity fails.
4. Every completed observable decision has exactly one valid, redacted audit
   event.
5. Audit mutation, deletion, or reordering is detected.
6. A restart cannot silently convert an incomplete or unknown request into a
   successful response.
7. **"Exactly once" means exactly one completed observable decision and audit
   record.** It does not claim that model computation itself is exactly once
   across a process crash.
8. No raw request payload is persisted. Only allowlisted metadata and
   cryptographic digests may be stored.
9. A local process or file is **not** durable across host loss and **not** a
   multi-replica guarantee.

## 4 — Pre-registered crash and fault points

1. before idempotency reservation;
2. after reservation, before scoring;
3. after scoring, before durable completion;
4. during audit or state commit;
5. after durable completion, before the HTTP response;
6. process restart followed by a duplicate retry;
7. corrupted or truncated audit/state store;
8. unavailable or unwritable audit/state sink.

For each point the harness must demonstrate, by test rather than assertion: the
HTTP/result outcome; idempotency state after the failure; audit-chain state after
the failure; restart/retry behaviour; whether rescoring can occur; whether
duplicate audit events can occur; and whether any unsafe approval-like response
is possible.

A scenario is **not** reported as handled unless a test demonstrates it.

## 5 — SQLite decision rule

A local SQLite prototype may be adopted **only if all** hold:

- it repairs at least one **demonstrated** crash/restart invariant gap;
- it stores no raw payload and no private data;
- it preserves fail-closed behaviour;
- synthetic crash tests prove correct recovery;
- it introduces no distributed, immutable, or high-availability claim;
- it uses only the standard-library `sqlite3` with an explicit local-file path;
- it stays small enough to follow in a reviewer walkthrough.

Otherwise the current design is **retained** and its limitation documented
honestly. Adopting SQLite because it is available, rather than because a gap was
demonstrated, is explicitly out of bounds.

If a simpler in-process repair fully closes every demonstrated gap, that repair
is preferred over adding a storage engine, and the reasoning must be recorded.

## 6 — Non-claims

SQLite, if adopted, would be **local single-node durability only**. It is not
immutable or WORM storage, not a multi-writer scale solution, not a cross-host
failover mechanism, and not a distributed transaction system. Multi-worker
serving remains incompatible with current state ownership (MT4).

No performance claim is made by MT6. MT4's audit-growth measurement stands as
evidence for the implementation it measured; any new benchmark belongs to a
separate versioned task.

`final_test` is not accessed by anything this protocol authorises, and every
fixture is synthetic.
