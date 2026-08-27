# MT7 — order-integrity verifier decision and evidence

**Decision: `ADOPT SYNTHETIC ORDER-INTEGRITY REFERENCE`.**

> A synthetic, deterministic pre-model order-integrity reference. It
> demonstrates server-side amount reconstruction and invariant checking. It is
> not a live Razorpay integration, not evidence about any real incident, and not
> part of SecureSwipe's fraud-model metrics.

Protocol: `docs/evidence/MT7_ORDER_INTEGRITY_PROTOCOL.md`, pre-registered and
hashed before any verifier code existed.

## 1 — Rationale against the pre-registered criteria

| Criterion | Assessment |
| --- | --- |
| Isolated from the fraud model and its evidence | **Yes.** Own namespace, no import of any model or threshold, no touch of `/v1/predict`, and a source-level test asserts the module references no model, network, database, or gateway symbol. |
| No external integration or credentials | **Yes.** Pure functions, standard library only, synthetic test-only secret, no network. |
| Every invariant demonstrable synthetically | **Yes.** All eleven, in 69 tests. |
| A distinct deterministic lesson | **Yes.** *Never trust a client-supplied total.* The client may send a SKU and a quantity, nothing else. |
| Explainable with clear limitations | **Yes.** §5 and §6 below. |
| Does not create a second claimed loss class | **Yes.** It makes no loss claim, computes no rate, and is excluded from every fraud metric. It is a pre-model input-contract guardrail, not a competing detector. |

The sixth criterion was the one that could have failed. It is satisfied only
because the reference is deliberately bounded: it produces no rate, no saving,
no prevented-loss figure, and no dashboard headline.

## 2 — System boundary

```
synthetic client request (SKU + quantity only)
  → trusted synthetic catalog
  → server-side amount reconstruction in integer minor units
  → versioned quote/invariant verifier
  → synthetic confirmation verification
  → integrity outcome for downstream/manual handling
```

Everything above is synthetic and in-process. There is no database, queue,
external service, package installation, or network request; no integration with
the fraud endpoint; and no model call, score, threshold, or ML feature. The
catalog uses generic synthetic SKUs (`SKU_ALPHA`, `SKU_BETA`, `SKU_GAMMA`), a
synthetic settlement currency `XTS`, and an explicitly stated
`MINOR_UNITS_PER_MAJOR = 100` so nothing is assumed.

## 3 — Allowed outcomes

- `integrity_verified_for_downstream_handling`
- `integrity_mismatch_review_required`
- `integrity_unavailable_fail_closed`
- `integrity_invalid_request`

No other outcome can be constructed — the result type refuses anything outside
the allowlist. None is named "approved", "payment accepted", or "fraudulent",
and `fulfilment_eligible` is a read-only property that authorises nothing.

## 4 — Invariants and test matrix

All 69 tests pass. Every row is demonstrated, not asserted.

| # | Invariant | Demonstrated by |
| --- | --- | --- |
| 1 | Client price/discount/tax/shipping/total/currency/status is **rejected, not ignored** | every forbidden field parameterised; a client `total` raises rather than being dropped |
| 2 | Integer minor units only; no floating-point currency arithmetic | reconstruction returns `int`; a float captured amount is `integrity_invalid_request` |
| 3 | A quote binds items, quantities, catalog version, currency, amount | quote construction and mutation-detection tests |
| 4 | `expected == quoted == captured` required | amount-mismatch and happy-path tests |
| 5 | Currency must match exactly | currency-mismatch test |
| 6 | Quantity positive, bounded, overflow-safe | zero/negative/boolean/over-bound/overflow tests |
| 7 | Unknown, expired, modified, or stale quote is never fulfilment-eligible | unknown, expired, stale-version, mutated-quote, repriced-catalog tests |
| 8 | Duplicate confirmation event IDs are idempotent | duplicate event returns the identical recorded result; ledger holds one event |
| 9 | Out-of-order events and unavailable state fail closed | out-of-order and unavailable-catalog tests |
| 10 | HMAC-SHA256 over raw bytes with `compare_digest` | round-trip, tampered-body, wrong-secret, non-bytes, and a source-level constant-time assertion |
| 11 | Never authorises payment, capture, refund, shipping, or fulfilment | source scan finds no payment-action verb in module code |

Additional coverage: major-vs-minor unit confusion (paying 1,299 against 129,900
does not verify), deterministic canonicalisation (line order and duplication
cannot change the digest), and output privacy (no result object carries a raw
payload, secret, SKU, or personal value; `detail` is restricted to
`amount_minor` and `currency`).

### Property evidence: client prices cannot influence the total

Across **300 generated synthetic carts**, a random price-like field is injected
into a random line. In every case the request is refused outright; stripping the
injected field then reproduces the honest server-reconstructed total exactly. A
client-supplied monetary value never reaches arithmetic.

### A real bypass the property test caught

The first implementation bounded quantity **per line** while canonicalisation
merges quantities **per SKU**. A caller could therefore split 300 units across
three lines of 100 and pass the cap. The property test surfaced this, and the
**contract was fixed rather than the test**: the bound now applies to the merged
per-SKU quantity, with a dedicated regression test. This is recorded because it
is exactly the class of bug the reference exists to illustrate.

## 5 — Limitations

- **No real payment gateway, fulfilment system, merchant catalogue, credential,
  or incident data was used.** None was needed and none is simulated.
- The confirmation ledger is in-memory and exists only so duplicate and
  out-of-order events can be demonstrated. It is not durable and not a
  production component.
- The catalog is a fixed synthetic fixture, not a price list.
- Quote validity uses an injected integer sequence, not a real clock.
- The module is not wired into any HTTP route. No public endpoint was added.

## 6 — Non-claims

This reference does **not** prevent real fraud or loss, does **not** describe
Razorpay behaviour, does **not** describe any gateway failure, is **not**
production-ready, is **not** PCI-relevant, and is **not** compatible with any
real webhook signing scheme. It is **not** a second claimed loss class.

**It is separate from fraud-model performance and from false-positive cost.** It
contributes nothing to average precision, ROC-AUC, precision, recall, Brier
score, calibration, capacity tiers, or the Lane A cost explorer, and no number
from it may appear alongside those metrics.

No anecdote is treated as fact. No ₹12,000-to-₹1 story, or any similar account,
is asserted here as a real event or as a gateway failure.

`final_test` was not accessed. Every fixture, SKU, price, event ID, and secret is
synthetic.
