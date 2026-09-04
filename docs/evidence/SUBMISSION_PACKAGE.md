# SecureSwipe submission package

Pitch script, form answers, and the final read-only checklist for Razorpay AI
Builder Internship Track 2 (AI Risk Manager).

> **Superseded — historical MT9 artifact.** This package was frozen before the
> sealed Lane A evaluation. Its headline figures are **Lane B historical**
> (random holdout, different corpus, feature space, label definition, and base
> rate); they are preserved here as a record and **must not be presented as the
> submission headline**.
>
> The authoritative result is the sealed
> [Lane A final evaluation](LANE_A_FINAL_EVALUATION.md): average precision
> **0.208660** — 6.0x the no-skill baseline of 0.034804 — over **88,581**
> transactions containing **3,083** fraud labels. At an illustrative capacity of
> 1,000 reviews/day across the 30.78-day evaluation window: recall **80.18%** at
> alert precision **8.03%**, being 2,472 fraud caught, 28,306 legitimate
> customers reviewed, and 611 fraud cases missed.
>
> Lane A and Lane B are not comparable. See the
> [evidence guide](../EVIDENCE_GUIDE.md#lane-a-and-lane-b-are-not-comparable).
> Build obstacles are recorded in [Build challenges](../BUILD_CHALLENGES.md).

Every claim below traces to [`CLAIM_TO_EVIDENCE_MATRIX.md`](CLAIM_TO_EVIDENCE_MATRIX.md);
the bracketed IDs are matrix rows. Nothing here may be spoken or submitted
unless its matrix row is satisfied.

**Container scope:** the release target is `linux/amd64`, which CI builds,
smoke-tests, scans, and produces an SBOM for. The emulated `linux/arm64` leg is
deferred and **no arm64 container support is claimed**. Nothing in this document
claims a deployment. See "Container architecture scope" at the end.

---

## 1 — Pitch script (target 4:30–5:00 spoken)

### Opening — the problem (~30s)

Card fraud is a needle-in-a-haystack problem. In the held-out data I evaluated
against, fraud is well under a fifth of one percent of transactions. That
imbalance creates a specific trap: a model can look excellent on accuracy while
being useless in production, and a reviewer has no way to tell the difference
from a dashboard number alone.

SecureSwipe is built for the reviewer, not for the leaderboard. It is a
defense-only fraud-risk signal and a human-review decision aid. It never
authorizes, captures, or blocks a payment. [1.1, 1.2]

### What it does (~45s)

Three pieces. A historical training and evaluation pipeline with one locked
held-out test result. A provenance-verified FastAPI scoring service. And a
static reviewer dashboard that stays useful even when the API is down. [1.1]

Every decision surface resolves to exactly one of three bounded outcomes:
below review threshold, human review, or unavailable / fail-closed. There is no
approve-or-block action anywhere in the project. I removed the ambiguous value
`pass` from detector responses specifically because it reads like an
authorization. [1.3]

### The results, stated precisely (~60s)

> **Superseded.** The spoken figures below are Lane B historical. Deliver the
> sealed Lane A result in the banner at the top of this file instead.

On the single locked held-out test at threshold 0.53: precision 69.66 percent,
recall 83.78 percent, PR-AUC 0.8288, ROC-AUC 0.9613. The confusion matrix is
62 true positives, 27 false positives, 12 false negatives, 42,621 true
negatives. [2.1]

Those numbers are locked. They come from one evaluation run, they are stored in
a tamper-evident lock file, and a verifier checks them before use — I have
tests that deliberately mutate the scores and the threshold and confirm the
verifier rejects them. They are never recomputed in the browser. [2.2, 2.4]

I want to be exact about one limitation, because it is the most important
sentence in this pitch: the bundle the API serves is a byte-verified historical
reference bundle, and I have **not** proven it is the same model that produced
those locked metrics. The manifest says so in machine-readable form —
historical taint true, decision-eligible false, historical-metrics-claimed
false — and the API returns those flags on every response. I would rather ship
that flag than imply a link I cannot prove. [3.3]

### Why a reviewer can trust the demo (~60s)

Everything on the dashboard carries one of four evidence labels: historical
evaluation, genuine demo inference, synthetic plumbing test, or illustrative
cost scenario. You always know which one you are looking at before you treat a
number as a claim. [1.4]

The genuine-inference panel really does call a real XGBoost estimator — one
fixed, all-zero example vector, never real transaction data — and it returns a
request ID, model and schema version, the score, the threshold, the bounded
decision, and the provenance block. [3.1, 3.4]

The score is labeled a model score, not a fraud probability, because it is not
calibrated. `calibrated_probability` is literally null in the response. [3.5]

And the failure behavior is the part I am most confident in: a missing or
corrupt bundle never produces a silent approval. Readiness fails and inference
returns an explicit unavailable result. Timeouts return 504, saturation returns
503, and an audit failure returns 503 — none of them ever return a decision.
Those are deterministic tests using synchronization primitives, not sleeps.
[4.1, 4.2]

### Engineering (~45s)

758 Python tests pass on a clean checkout of the release candidate. The
frontend has unit tests plus browser tests covering keyboard reachability, an
accessibility scan, and desktop and 375-pixel mobile views with no overflow and
no console errors. [7.1, 7.3]

Audit evidence is a hash-chained, redacted, append-only NDJSON log with a
verifier that detects mutation, deletion, and reordering. I call it
tamper-evident, not immutable, because the anchor shares the log's trust domain
— that is an honest limit, not a feature. Duplicate requests replay the
original result without rescoring or writing a second event. [4.3, 4.4]

Dependencies are hash-locked with zero known vulnerabilities, full Git history
scans clean for secrets, and the container runs non-root as uid 10001 with no
pip, a read-only root filesystem, and all capabilities dropped. [7.4, 7.5, 7.6]

### Performance and cost, bounded (~30s)

A fixed-input local benchmark recorded 500 out of 500 valid responses at
concurrency 8 with zero errors: p50 44.6 ms, p95 80.4 ms, p99 308.5 ms, about
169 requests per second on one laptop worker. I am reporting the p99 tail
rather than hiding it. That is a single-process loopback measurement — not a
capacity claim, not an SLO, and not a thousand or ten thousand RPS. [5.1]

Core inference consumes zero LLM tokens. It is deterministic tabular XGBoost,
which is also why it is cheap and auditable. [5.2]

The cost panel is explicitly an illustrative what-if over the locked confusion
counts with editable INR assumptions. It is labeled, in those words, as not
Razorpay economics and not a production-optimal threshold. [6.1, 6.2]

### Close (~20s)

SecureSwipe is a small system that is honest about its own boundaries. It tells
you what it knows, what it does not know, and what it refuses to decide. For a
risk system, I think that is the feature that matters most.

---

## 2 — Form answers

**What it does (one line).**
A defense-only card-fraud risk detector and human-review decision aid: it scores
transactions with a provenance-verified XGBoost bundle and returns a bounded
review decision, never an autonomous payment action. [1.2, 1.3]

**Problem addressed.**
Card fraud on extremely imbalanced data, where accuracy is misleading and
reviewers cannot tell a trustworthy number from a decorative one. SecureSwipe
separates locked historical evidence from live demo inference from synthetic
plumbing, and labels every figure accordingly. [1.4]

**Track.** Track 2 — AI Risk Manager. [1.1]

**Tech stack.**
Python 3.12, FastAPI, XGBoost, scikit-learn, pandas; Next.js 16 / React 19 /
TypeScript dashboard; Docker; GitHub Actions with ruff, mypy, pytest, vitest,
Playwright, pip-audit, npm audit, TruffleHog, CodeQL, and Trivy.

**Results.**
*Superseded — Lane B historical. Submit the sealed Lane A figures from the
banner at the top of this file.* Retained for the record:
One locked held-out test at threshold 0.53: precision 69.66%, recall 83.78%,
PR-AUC 0.8288, ROC-AUC 0.9613; TP/FP/FN/TN = 62/27/12/42,621 over 42,722 rows
containing 74 fraud cases. Verified from a tamper-evident lock file. [2.1, 2.2]

**Measured performance.**
500/500 valid responses, 0 errors, concurrency 8: p50 44.63 ms, p95 80.37 ms,
p99 308.48 ms, 169.35 req/s; cold start 5.85 s as an end-to-end upper bound.
Single-process local loopback measurement, not a capacity or SLO claim. Core
inference uses zero LLM tokens. [5.1, 5.2, 5.3]

**AI/LLM usage.**
None in the scoring path. Detection is deterministic tabular XGBoost and
consumes zero LLM tokens. LLM assistance was used for development only. [5.2]

**Is it deployed / live URL.**
No. There is no verified public deployment of this release candidate, and any
prior static URL is not evidence for it. The dashboard builds as a static site
and runs locally; the checked-in workflows perform no deployment. [8.1]

**Razorpay integration.**
None. No Razorpay API, adapter, credential, or payment flow is integrated. The
project is an independent portfolio reference system.

**Known limitations.**
1. The served bundle is not proven to be the model that produced the locked
   metrics; it is flagged historical-tainted and not decision-eligible. [3.3]
2. Scores are uncalibrated — a model score, not a fraud probability. [3.5]
3. Metrics come from one locked held-out run, not repeated trials or a temporal
   backtest.
4. Real-time contextual signals (device, velocity, geography) are a synthetic
   in-browser demonstration, not a trained or evaluated model.
5. Audit evidence is tamper-evident, not immutable; replay state is in-process
   and lost on restart. [4.3]
6. The benchmark is one fixed-input local run; no production capacity claim. [5.1]
7. The original training source inputs could not be re-obtained, so independent
   source-level reproduction is unavailable.

**Why it should win / what is distinctive.**
It is engineered to be *checked* rather than believed: four separated evidence
classes, machine-readable provenance on every response, fail-closed behavior
proven by deterministic tests, a hash-chained audit log with a tamper verifier,
and explicit refusal to link an unproven bundle to locked metrics.

---

## 3 — Final read-only checklist (owner performs submission)

Before submitting, confirm each line. Do not submit while any line is unchecked.

- [x] Quality, Security, and the `linux/amd64` Container workflow are green on
      the submitted commit. Verified on `main` at `374e167` (tree
      `6e112b8b…`, identical to the verified PR head `4c712c7`).
- [ ] No statement implies arm64 container support or a multi-architecture
      release.
- [ ] No claim in the pitch or form lacks a matrix row.
- [ ] No live-URL or deployment claim is made anywhere. [8.1]
- [ ] No claim links the served bundle to the locked metrics. [3.3]
- [ ] No RPS, SLO, capacity, or cost-savings claim beyond the measured
      loopback numbers. [5.1, 6.2]
- [ ] The exact illustrative disclaimer is visible in any cost screenshot. [6.2]
- [ ] No screenshot exposes PAN, CVV, secrets, tokens, or real transaction data.
- [ ] Recording shows only bounded decisions — never an approve/block action.
- [ ] Record the submission receipt/confirmation as an artifact after submitting.

---

## Container architecture scope

The container release target is `linux/amd64`. CI builds it, runs the
liveness/readiness/inference smoke, scans it for HIGH/CRITICAL vulnerabilities,
and publishes an SPDX SBOM on every push and pull request.

The emulated `linux/arm64` leg has been removed from the matrix and is
deferred. Under QEMU user-mode emulation on GitHub-hosted runners the container
reaches `Waiting for application startup.` and never completes startup, so the
smoke step's readiness loop exhausts and the job fails. It reproduced
deterministically three times, did not reproduce locally on native arm64 or
Rosetta-emulated amd64, and was **not** root caused. A speculative thread-pinning
change was written, tested, and then reverted rather than shipped on an unproven
diagnosis.

Accordingly: **do not claim arm64 container support, multi-architecture images,
or a green arm64 CI leg.** State the release target as `linux/amd64` if asked.
