# Submission blurb — Track 02, AI Risk Manager

Razorpay AI Buildathon 2026. Two renderings of one text: plain for submission
forms, markdown for GitHub surfaces. Every figure traces to the frozen capacity
frontier in `docs/evidence/LANE_A_FINAL_EVALUATION.md` (line 103) and was
reconciled on 2026-09-04. If a figure here ever disagrees with that record,
the record wins.

---

## Plain text — submission forms, email, plain-text fields

```
SECURESWIPE — Track 02 · AI Risk Manager
A capacity-aware detector for card-transaction fraud, built against the
constraint every merchant actually has: a review team of fixed size.

THE WRONG CONSTRAINT
Fraud is 3,083 of 88,581 transactions in the held-out set. Call every row
legitimate and you score 96.52% accuracy while catching nothing. Accuracy, AUC
and F1 hide the number that decides whether a fraud desk pays for itself:
false-positive cost — legitimate customers pulled into review per fraud caught.

MEASURED — one sealed held-out run, pre-declared protocol, 30.78-day window
- Average precision 0.208660, 6.0x the 0.034804 no-skill baseline.
- At 1,000 reviews/day: 80.18% recall, 8.03% alert precision.
- Its false-positive cost: 28,306 legitimate customers reviewed, 611 fraud
  missed — eleven innocents per fraud caught.
- Doubling to 2,000/day buys 421 more fraud and 30,357 more innocents.
- No tier is marked optimal; that needs merchant costs this data lacks.
Public IEEE-CIS research data — offline ranking evidence, not live Razorpay
performance.

WHAT RUNS — bounded execution, not the sealed model's serving chain
FastAPI scorer, Next.js reviewer dashboard, deterministic walkthrough on a local
reference bundle. Never authorizes, captures, blocks or declines: every outcome
is human_review, below_review_threshold, or fail-closed unavailable.
Hash-chained redacted receipt per decision, idempotent replay, 422 on malformed
input, and no decision at all without a checksum-verified bundle. Deterministic
XGBoost — same input, same score, every time.

A decision problem, not a prediction problem: given fixed headcount, which cases
does a human open, and what does that cost the customers who did nothing wrong?
```

---

## Markdown — README, GitHub, any rich-text field

### SecureSwipe — Track 02 · AI Risk Manager

A capacity-aware detector for card-transaction fraud, built against the
constraint every merchant actually has: a review team of fixed size.

**The wrong constraint.** Fraud is 3,083 of 88,581 transactions in the held-out
set. Call every row legitimate and you score 96.52% accuracy while catching
nothing. Accuracy, AUC and F1 hide the number that decides whether a fraud desk
pays for itself: **false-positive cost** — legitimate customers pulled into
review per fraud caught.

**Measured** — one sealed held-out run, pre-declared protocol, 30.78-day window:

| | |
| --- | ---: |
| Average precision | **0.208660** (6.0x the 0.034804 no-skill baseline) |
| Recall at 1,000 reviews/day | **80.18%** |
| Alert precision at that tier | **8.03%** |
| False-positive cost at that tier | **28,306** legitimate customers reviewed, **611** fraud missed |

That is about eleven innocents per fraud caught. Doubling to 2,000 reviews/day
buys 421 more fraud and 30,357 more innocents. No tier is marked optimal; that
needs merchant costs this data lacks. Public IEEE-CIS research data — offline
ranking evidence, not live Razorpay performance.

**What runs** — bounded execution, not the sealed model's serving chain. FastAPI
scorer, Next.js reviewer dashboard, deterministic walkthrough on a local
reference bundle. Never authorizes, captures, blocks or declines: every outcome
is `human_review`, `below_review_threshold`, or fail-closed unavailable.
Hash-chained redacted receipt per decision, idempotent replay, `422` on
malformed input, and no decision at all without a checksum-verified bundle.
Deterministic XGBoost — same input, same score, every time.

> A decision problem, not a prediction problem: given fixed headcount, which
> cases does a human open, and what does that cost the customers who did
> nothing wrong?

---

## Hardest problem — short form

For a "biggest technical challenge" form field, or minute 4 of the pitch video.
Supporting artifact, not the Track 02 headline. Every figure is sourced in
`docs/BUILD_CHALLENGES.md`; the forensic record is in `docs/benchmarks/`.

```
MY BENCHMARK BROKE, NOT MY SERVICE
Accepting that was the hard part.

The frozen 36-cell load matrix cleared 34 cells, then fail-closed at four workers
and concurrency 64 — and persisted results only after the final cell, so it
aborted with no artifact. A real failure, no record of its cause.

THE FIX I DECLINED
Widen the pool, add a retry, re-run until green — knowably wrong before
collecting a sample. The waiters were not short of connections; they held them
while queued behind the audit chain head, a single serialized writer. In a fraud
system that writer is what makes a decision reconstructable. Removing it improves
the metric by deleting the product.

WHAT THE INSTRUMENTS SAID
I built evidence preservation, then timed waiting for the lock separately from
holding it. They indicted me: 87-98% of each request's lifetime was queueing
inside my own load generator. I rebuilt the harness and retired every prior
number as harness-constrained. The real defect was narrow — completions held all
four pool connections while waiting on the chain head — and the repair is one
per-worker gate. No pool size, timeout, retry, schema, or behaviour changed.

WHAT I DID NOT CLAIM
The matrix later failed at its tenth cell on a different gate. Host load hit
13.96 against a pre-run 5.11, and I still did not void the run: the protocol
defined no per-cell health criterion, and inventing one after seeing the result
is what it forbids. No multi-worker scaling claim exists anywhere in the
repository.

Return 503 and refuse to decide. Never emit a decision the system cannot audit.
For a risk system, that is the right way to break.
```
