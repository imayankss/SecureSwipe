# SecureSwipe architecture gallery

<p align="justify">
Seven diagrams of what SecureSwipe actually is: which parts are built and exercised, which parts
exist only as a local reference or demonstration, and which production capabilities are deliberately
left unproven. Each diagram is a picture of a <b>verified boundary</b> — not a claim of production
deployment, Razorpay integration, autonomous payment action, or benchmark-proven scale.
</p>

> These diagrams are documentation, not evidence. Where a diagram states a measured number or a
> frozen policy, the authoritative record is the linked evidence file — the diagram only points at it.

---

## How to read every diagram

All seven share one visual language, so the conventions are worth thirty seconds:

| Mark | Meaning |
| --- | --- |
| **Outlined box** | A component or state that exists in the repository today |
| **Blue-filled box** | A sealed artefact or a bounded outcome — the things SecureSwipe is allowed to claim |
| **Red outline** | A fail-closed terminal state, or a prohibited claim/linkage |
| **Red dashed edge with ✕** | A path that is explicitly *not* established (most importantly: sealed Lane A → served bundle) |
| **Grey dashed edge** | An optional path — present only when explicitly configured |
| **Lane / swimlane** | A trust boundary. Crossing a lane means crossing a boundary, not just a function call |

Diagrams are SVG and follow your system light/dark preference. They are wide; open one in its own tab
to read the small type. Every diagram is rendered from the same tokens as the
[methodology report](https://secure-swipe.vercel.app/secureswipe-methodology.html), which is where
five of them originate.

### The one boundary that governs all seven

<p align="justify">
The sealed Lane A model that produced the headline offline metrics is <b>not</b> proven to be the
bundle served by the local reference API or the <code>/demo</code> walkthrough. No diagram may be read
as connecting them. This is drawn explicitly as a crossed-out edge in diagram 01 and enforced as a
category firewall in diagram 02.
</p>

---

## 01 · System context

**Question it answers:** what are the three independent paths through SecureSwipe, and where does each one stop?

![SecureSwipe system context: offline science, static presentation, and opt-in local reference serving](diagrams/01-secureswipe-system-context.svg)

**How to read it.** Three lanes, top to bottom: offline science (private/local), static presentation
(no live inference), and the opt-in local reference demo. Follow a lane left to right; nothing
crosses between lanes except the deterministic exporter, which carries **aggregates and digests
only — never rows, model bytes, or score vectors**. The red crossed edge in the middle is the point
of the diagram: the sealed Lane A evaluation does not feed the served bundle.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| Curation, chronological role freeze, sealed Lane A evaluation, deterministic exporter, static `/` and `/evidence`, FastAPI V1 | The verified bundle behind `/demo`, and the local tamper-evident audit log | Any provenance link from sealed Lane A to a servable bundle; a public backend; live Razorpay traffic |

**Source:** [`scripts/lane_a_run_final_evaluation.py`](../../scripts/lane_a_run_final_evaluation.py) ·
[`scripts/export_web_data.py`](../../scripts/export_web_data.py) ·
[`api/main.py`](../../api/main.py) ·
[`web/app/demo/page.tsx`](../../web/app/demo/page.tsx)
**Evidence:** [Architecture](../ARCHITECTURE.md) ·
[Lane A final evaluation](../evidence/LANE_A_FINAL_EVALUATION.md) ·
[Model card](../MODEL_CARD.md)

---

## 02 · Evidence and serving boundaries

**Question it answers:** which category of evidence is allowed to support which claim — and which links are forbidden?

![Evidence category map showing that only the sealed Lane A category may support the headline offline metrics](diagrams/02-evidence-and-serving-boundaries.svg)

**How to read it.** Six evidence categories on the left; the headline claim on the right. Only one
edge is permitted — sealed Lane A → headline offline metrics and capacity counts. Every other edge
is drawn and then crossed out. This is a *firewall diagram*: its content is the edges that do not exist.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| All six categories are populated with committed records, and the claim-to-evidence matrix is maintained | Historical Lane B, synthetic demonstration, and reference local-bundle categories | That Lane B metrics transfer to Lane A; that illustrative INR cost arithmetic reflects real merchant economics or savings |

**Source:** [`scripts/export_web_data.py`](../../scripts/export_web_data.py) ·
[`web/app/evidence/page.tsx`](../../web/app/evidence/page.tsx)
**Evidence:** [Evidence guide](../EVIDENCE_GUIDE.md) ·
[Claim-to-evidence matrix](../evidence/CLAIM_TO_EVIDENCE_MATRIX.md) ·
[Cost-explorer contract](../evidence/MT5_COST_EXPLORER_EVIDENCE.md) ·
[Limitations](../LIMITATIONS.md)

---

## 03 · Bounded decision workflow

**Question it answers:** what does SecureSwipe actually do to one transaction, and where does its authority end?

![Bounded decision workflow from validated request through scoring, capacity ranking, routing, and audit](diagrams/03-bounded-decision-workflow.svg)

**How to read it.** The upper lane is everything inside SecureSwipe; the lower lane is everything it
refuses to do. A validated request is scored once, ranked under a **frozen** review budget *B*, and
routed by the recorded threshold into exactly two possible outcomes. Both outcomes are audited. Only
`human_review` is queued for a person. Note the red annotation: `below_review_threshold` is not an
approval, a safety judgement, or a statement that the transaction is legitimate.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| Strict schema validation, single deterministic scoring pass with **zero LLM tokens**, threshold from bundle provenance, two bounded outcomes, chained audit receipt | The bundle being scored, and the audit log location | Any autonomous payment action; a real analyst queue, staffing model, or SLA; that *B* = 1,000/day is a recommendation rather than one frozen analysis tier |

**Source:** [`api/main.py`](../../api/main.py) ·
[`api/schemas.py`](../../api/schemas.py) ·
[`api/audit.py`](../../api/audit.py) ·
[`src/lane_a/capacity.py`](../../src/lane_a/capacity.py)
**Evidence:** [API guide](../API.md) ·
[Model card](../MODEL_CARD.md) ·
[Capacity results](../evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results)

---

## 04 · Request, audit and replay sequence

**Question it answers:** in what exact order does a single `/demo` request touch validation, readiness, inference, audit and replay?

![Deterministic request, audit and idempotent replay sequence between the demo page, FastAPI, the bundle and the audit log](diagrams/04-request-audit-replay-sequence.svg)

**How to read it.** A sequence diagram, top to bottom in time. Three requests are shown: the first
bounded decision, an identical replay, and a malformed fixture. The replay returns the original
response *and the original receipt* without scoring again or appending a second audit event — that
is the property worth checking. The malformed fixture returns `422` and no decision at all.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| Readiness probe, schema validation, idempotency reservation, single scoring pass, optional chained audit append, exact replay, `422` rejection | The whole sequence runs against a verified **reference** bundle over loopback | Public-network latency or an SLO; multi-worker behaviour; that the audit log is immutable/WORM storage or establishes regulatory compliance |

**Source:** [`api/main.py`](../../api/main.py) ·
[`api/audit.py`](../../api/audit.py) ·
[`web/app/demo/page.tsx`](../../web/app/demo/page.tsx) ·
[`scripts/create_synthetic_bundle.py`](../../scripts/create_synthetic_bundle.py)
**Evidence:** [API guide](../API.md) ·
[Demo walkthrough](../DEMO.md) ·
[Reproducibility](../REPRODUCIBILITY.md#local-reference-model-demonstration)

---

## 05 · Fail-closed decision state machine

**Question it answers:** what happens when something goes wrong — and can a failure ever look like an approval?

![Fail-closed state machine: every failure path terminates without a decision, an audit event, or a payment action](diagrams/05-fail-closed-decision-state-machine.svg)

**How to read it.** The happy path runs left to right into a bounded outcome. Every red dashed edge
drops into the single terminal band at the bottom. The claim of the diagram is that the band has no
exit: a missing, corrupt, unverified, overloaded, or conflicting path returns a typed error and
**never degrades into an approve-like answer**. The blue dashed edge above is the idempotent replay.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| `422 validation_error`, `503 model_unavailable`, `409 idempotency_conflict`, `503 capacity_exceeded`, `503 audit_unavailable`, and exact replay on a matching digest | Failure behaviour measured over loopback against a reference bundle | Recovery-time objectives; behaviour under a real production incident; crash-consistency guarantees beyond the recorded local state decision |

**Source:** [`api/main.py`](../../api/main.py) ·
[`api/postgres_idempotency.py`](../../api/postgres_idempotency.py) ·
[`api/schemas.py`](../../api/schemas.py)
**Evidence:** [API guide](../API.md) ·
[State and crash decision](../evidence/MT6_STATE_AND_CRASH_DECISION.md) ·
[Terminal scale closeout](../benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md)

---

## 06 · Audit integrity and recovery

**Question it answers:** how is the audit chain kept consistent when two requests race, and what is the recovery boundary?

![Durable idempotency and transactional audit-chain integrity for the postgres-scale profile](diagrams/06-audit-integrity-and-recovery.svg)

**How to read it.** This is the **optional `postgres-scale` profile**, not the supported default. A
request is keyed by an HMAC of its request ID plus a canonical digest, then atomically reserved.
Scoring happens *outside* the database transaction; the append, the chain-head advance and the stored
response happen *inside a single* transaction. A different digest under the same ID is a `409`; a
stale or failed reservation fails closed with `503`.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| The PostgreSQL idempotency and transactional audit-chain implementation, plus its local multi-process correctness tests | The entire profile — `local-default` remains a single-process reference | A deployable replica fleet, load balancer, shared bundle distribution, public availability, or throughput scaling. The final P1-S4 matrix **failed closed**, so no scalability claim is made |

**Source:** [`api/postgres_idempotency.py`](../../api/postgres_idempotency.py) ·
[`api/postgres_audit.py`](../../api/postgres_audit.py) ·
[`api/migrations`](../../api/migrations)
**Evidence:** [Terminal scale closeout](../benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md) ·
[Concurrency evidence](../evidence/MT4_CONCURRENCY_EVIDENCE.md) ·
[Order-integrity decision](../evidence/MT7_ORDER_INTEGRITY_DECISION.md) ·
[Threat model](../THREAT_MODEL.md)

---

## 07 · Lane A evaluation lifecycle

**Question it answers:** how was leakage controlled, and what exactly was frozen before the final labels were opened?

![Lane A leakage-controlled evaluation lifecycle: development boundary, frozen pipeline, quarantined final test role, and one-time seal](diagrams/07-lane-a-evaluation-lifecycle.svg)

**How to read it.** Left to right in time. Everything inside the development boundary permitted
tuning. The `final_test` role sits in quarantine for the entire width of the diagram. A one-time
guarded runner computes and seals scores, *then* opens the labels, then emits aggregates, intervals,
counts and digests — after which the protocol is closed to further tuning or reruns.

> This diagram is not in your original six. It is included because leakage control is the single
> thing a fraud-modelling reviewer is most likely to probe, and the asset already existed.

| Exists today | Reference / demo only | Deliberately unproven |
| --- | --- | --- |
| Chronological partition freeze, frozen 24-input schema, frozen capacity policy bound to a digest, one-time guarded runner, sealed aggregates with bootstrap intervals | — | That the hold-out was human-blind or externally blind (it was **programmatically** held out); that the result transfers to Razorpay or Indian-payment traffic |

**Source:** [`scripts/lane_a_run_final_evaluation.py`](../../scripts/lane_a_run_final_evaluation.py) ·
[`src/lane_a/capacity.py`](../../src/lane_a/capacity.py)
**Evidence:** [Final evaluation](../evidence/LANE_A_FINAL_EVALUATION.md) ·
[Evaluation protocol](../evidence/LANE_A_FINAL_EVALUATION_PROTOCOL.md) ·
[Partition freeze](../evidence/LANE_A_PARTITION_FREEZE.md) ·
[Scientific validity](../SCIENTIFIC_VALIDITY.md)

---

## Provenance of these files

<p align="justify">
Diagrams 01, 02, 04, 06 and 07 are extracted verbatim from the hand-authored SVGs in
<code>web/public/secureswipe-methodology.html</code> and wrapped as standalone documents with an embedded
theme block, so the gallery and the published methodology report cannot drift apart. Diagrams 03 and
05 were authored here in the same visual language, with their state and error labels taken directly
from <code>api/main.py</code> and <code>api/schemas.py</code>.
</p>

SVG is the primary and only format. A 2× PNG fallback would only be added if a diagram were found to
render incorrectly on GitHub. Each file carries a `<title>` and a full `<desc>`, so screen readers get
the whole argument rather than a filename.

> **Colour-scheme caveat.** An SVG loaded through GitHub's image proxy follows the reader's
> *operating-system* light/dark setting, not their GitHub theme setting. Every diagram therefore
> paints its own opaque background, so it stays legible in either combination.

**Related:** [Architecture](../ARCHITECTURE.md) ·
[Diagram blueprint drafts](../DIAGRAM_BLUEPRINT_DRAFTS.md) ·
[Evidence guide](../EVIDENCE_GUIDE.md) ·
[Limitations](../LIMITATIONS.md)
