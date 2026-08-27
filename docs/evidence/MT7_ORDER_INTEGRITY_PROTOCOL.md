# MT7 — order-integrity verifier protocol and decision rule

**Pre-registered before any verifier code was written.** This document is hashed
and its digest recorded before implementation begins.

## 0 — Framing (used verbatim throughout)

> A synthetic, deterministic pre-model order-integrity reference. It
> demonstrates server-side amount reconstruction and invariant checking. It is
> not a live Razorpay integration, not evidence about any real incident, and not
> part of SecureSwipe's fraud-model metrics.

No anecdote is treated as fact, and no gateway or merchant behaviour is
characterised. This document describes a reference design only.

## 1 — Read-only scope assessment

| Question | Assessment |
| --- | --- |
| Deterministic pre-model guardrail with synthetic inputs only? | **Yes.** Reconstructing an amount from a fixed synthetic catalog in integer minor units is pure arithmetic — no model, no network, no credential, no clock dependence beyond an injected quote timestamp. |
| Visibly separate from the fraud model and its metrics? | **Yes.** It lives in its own namespace, never touches `/v1/predict`, never calls a model or threshold, and its outcome names cannot be confused with fraud decisions. It contributes nothing to AP, ROC-AUC, precision, recall, or false-positive cost. |
| All important invariants testable without a real gateway or credential? | **Yes.** Every invariant below is reachable with pure functions and synthetic fixtures. Signature verification uses a test-only synthetic secret. |
| Clear reviewer lesson in under a minute? | **Yes.** "Never trust a client-supplied total — the server reconstructs it from a trusted catalog in integer minor units and compares." One sentence, demonstrable in one test. |

**No stop condition fires.** The design needs no real credential, no external
service, no real payment workflow, no incident claim, and no modification of the
sealed fraud path. The repository contains no existing order, cart, or catalog
code, so nothing is displaced.

## 2 — Allowed architecture

```
synthetic client request (SKU + quantity only)
  → trusted synthetic catalog
  → server-side amount reconstruction in integer minor units
  → versioned quote/invariant verifier
  → synthetic confirmation verification
  → integrity outcome for downstream/manual handling
```

The client may supply **only** SKU and quantity. Nothing downstream of the
catalog accepts a client-supplied monetary value.

## 3 — Pre-registered invariants

1. Client-supplied price, discount, tax, shipping, total, currency, payment
   status, or fulfilment status is **rejected, not ignored**.
2. The server computes every amount from an allowlisted synthetic catalog using
   **integer minor units only**. No floating-point currency arithmetic anywhere.
3. A quote binds its canonical item set, quantities, catalog version, currency,
   and expected amount.
4. `expected_amount_minor == quoted_amount_minor == captured_amount_minor` is
   required for an integrity match.
5. Currency must match exactly.
6. Quantity must be positive, bounded, and overflow-safe.
7. A confirmation for an unknown, expired, modified, or stale quote must not
   produce a fulfilment-eligible outcome.
8. Duplicate confirmation event IDs are idempotent: no duplicate
   fulfilment-eligible outcome.
9. Out-of-order events and unavailable trusted state fail closed into an
   integrity-review or unavailable outcome.
10. Any synthetic signature verification uses HMAC-SHA256 with
    `hmac.compare_digest` over **raw bytes**, with test-only synthetic secrets.
11. The module never authorises payment, capture, refund, shipping, fulfilment,
    approval, or blocking of a real transaction.

## 4 — Allowed outcomes

Exactly four, and no others:

- `integrity_verified_for_downstream_handling`
- `integrity_mismatch_review_required`
- `integrity_unavailable_fail_closed`
- `integrity_invalid_request`

No outcome may be named "approved", "payment accepted", or "fraudulent".

## 5 — Decision rule

Adopt the synthetic reference **only if all** hold:

- it is isolated from the fraud model and its evidence;
- it requires no external integration or credentials;
- every invariant is demonstrable with synthetic tests;
- it adds a distinct deterministic lesson — never trust client-supplied totals;
- it can be explained with clear limitations;
- **it does not create a second claimed loss class or distract from the
  fraud-risk detector.**

If any criterion fails, the decision is `DEFER ORDER-INTEGRITY VERIFIER`, only
the protocol and decision record are committed, and no verifier is implemented.
Building it because it sounds impressive is explicitly out of bounds.

## 6 — Non-claims

This reference does not prevent real fraud or loss, does not describe Razorpay
behaviour, does not describe any gateway failure, is not production-ready, is not
PCI-relevant, and is not compatible with any real webhook. It is not a second
claimed loss class, and it never appears in fraud-model metrics.

`final_test` is not accessed by anything this protocol authorises, and every
fixture, SKU, price, event ID, and secret is synthetic.
