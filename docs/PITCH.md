# 5-Minute Pitch — Shot List & Script

**SecureSwipe** · Razorpay AI Buildathon 2026 · Track 02 — AI Risk Manager

Speech runs **4:45**. The remaining 0:15 is slack and it belongs to the demo
block. Arc: problem 28s → architecture 82s → live demo 90s → metrics 58s.

Every number below is in `docs/evidence/LANE_A_FINAL_EVALUATION.md`. **Re-read
them off that file before recording.** That record is sealed and must not
change — but if anything on screen ever disagrees with this script, **read the
screen**. Quoting a stale figure is the one mistake that would undo what this
project is built on.

Three words are prohibited claims in the sealed record. Never say **blind**,
never say **savings** or **ROI**, never say **optimal threshold**.

---

## Setup before you hit record

```bash
cd web && npm run build && npm run start -- --hostname 127.0.0.1 --port 3000
```

```bash
demo_root=$(mktemp -d)
.venv/bin/python scripts/create_synthetic_bundle.py --output "$demo_root/bundle"
mkdir "$demo_root/audit"
SECURESWIPE_ARTIFACT_ROOT="$demo_root" \
SECURESWIPE_BUNDLE_MANIFEST="$demo_root/bundle/manifest.json" \
SECURESWIPE_AUDIT_LOG="$demo_root/audit/prediction-events.ndjson" \
SECURESWIPE_CORS_ORIGINS="http://127.0.0.1:3000" \
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:3000` at 1440×900. Three tabs, pre-loaded, nothing else:
`/`, `/demo`, `/secureswipe-methodology.html`. Hide bookmarks. Close Slack.

**Do a dry run first, and do it in this order:**

1. Start the API **without** a bundle once and watch `/health/ready` return
   `503`. That is the fail-closed beat. You want to have seen it before the
   camera is on, because it is the beat you will be tempted to rush.
2. Restart with the bundle above, then exercise the full `/demo` walkthrough
   once. The first scoring call after a cold start is slow.
3. Confirm the audit NDJSON is being written to `$demo_root/audit/`. If the
   chain is empty, beat 3 has nothing to show.

**Record the demo against the local API, never the deployed `/demo`.** The
public build carries no external API origin in its CSP, so what ships there is
a clearly labelled recorded transcript. Showing it as live inference would be
the one dishonest frame in an otherwise honest submission.

---

## What is a slide and what is live

| Time | Screen | Rule |
|---|---|---|
| 0:00 – 2:10 | Slides | Architecture and boundaries are arguments. Don't waste a live UI on them. |
| 2:10 – 3:40 | **Live capture** | The judges asked for audit trails and bounded actions. Show them running. |
| 3:40 – 4:20 | Slides | Charts have to survive video compression. A live page at 1080p will not. |
| 4:20 – 4:45 | Slides, then a 3s cut to the live methodology page | Proves the chart is published, not redrawn for the pitch. |

---

## 0:00 – 0:20 · Cover

*Slide 01. Speak over it. Do not read it aloud.*

> "I'm Mayank Suryavanshi. SecureSwipe is a capacity-aware fraud-risk manager
> for Track 02 — and it is defense-only by construction, not by policy. It
> ranks card transactions for a human queue. It never blocks a payment."

---

## 0:20 – 0:48 · The problem

*Slide 02. The top row is the baseline, not SecureSwipe — say "the model to
beat" out loud before you say "zero", so nobody misreads whose number that is.*

> "In my sealed evaluation population, 85,498 of 88,581 transactions are
> legitimate. So here is the model to beat: predict 'legitimate' for every
> single row. It scores **96.52% accuracy** and catches **zero of 3,083** fraud
> cases.
>
> SecureSwipe, ranking under a 1,000-case daily budget, catches **2,472** of
> those 3,083 — on the same held-out population.
>
> So accuracy is not the constraint. The constraint is how many cases a human
> can actually open today — and almost nothing in this space reports that
> number next to the recall it bought."

---

## 0:48 – 1:06 · The decision

*Slide 03. Point at the two outcome chips.*

> "There are exactly two outcomes in this system: `human_review` and
> `below_review_threshold`. You set a daily review budget B; the system ranks by
> score and takes the top B. **The threshold is an output of that budget, never
> an input** — which is how a fraud team is actually staffed."

---

## 1:06 – 1:48 · Architecture

*Slide 04. Walk the flow line left to right, then stop on stages 05 and 06.*

> "Score, rank under capacity, route, explain, audit, replay.
>
> Scoring runs from a checksum-verified local bundle in its own recorded field
> order — deterministic, and **zero LLM tokens on the decision path**. That is
> deliberate: an audit chain is only worth having if the thing it audits is
> reproducible.
>
> Every successful decision gets a hash-chained, allowlisted receipt with no raw
> body, no PAN, no CVV. Each record commits to the hash of the one before it, so
> editing any past decision breaks every hash after it. And an identical request
> replays the original response without re-scoring."

---

## 1:48 – 2:10 · Trust boundary

*Slide 05.*

> "The sealed offline evaluation, the static reviewer site, and the local
> reference API are three separate lanes. They share contracts and provenance —
> **they do not share an evidence claim.** The static site cannot reach a model.
> The local API does not claim to serve the sealed one.
>
> I say that out loud because the alternative is a demo that quietly implies
> both."

---

## 2:10 – 3:40 · Live demo

*Slide 06 on the second monitor; screen share the local app. Narrate the
decision, never the cursor. If a sentence starts with "now I'm…", cut it.*

**Beat 1 — readiness.**

> "Before any decision, the service reports model provenance and the bundle
> checksum. If it cannot verify those, you get no score."

**Beat 2 — a bounded decision.**

> "One fixed fixture, one signal to a human queue. Notice what is *absent*:
> there is no approve, no capture, no decline anywhere in this response body.
> Not disabled — absent. The vocabulary does not contain them."

**Beat 3 — the receipt.**

> "A genuine chained hash, appended before the response returns."

**Beat 4 — replay.**

> "Same request ID, same response, and — the part that matters — **no duplicate
> event** in the chain."

**Beat 5 — invalid input.** *(never cut this one)*

> "A malformed fixture is rejected 422 with no decision. Not a default, not a
> fallback, not a guess."

**Beat 6 — no bundle.** *(never cut this one either)*

> "And with the verified bundle removed, readiness returns 503 and the system
> fails closed — it tells you exactly which precondition failed. **A risk system
> that cannot refuse cleanly is not a risk system.**"

*This block owns the 15 seconds of slack. If you are behind, cut beat 3 and let
the receipt speak for itself inside beat 4.*

---

## 3:40 – 4:05 · The core trade-off

*Slide 07. Trace the blue line up, then the orange line down, with your hand.*

> "This is the finding I would most like to be asked about.
>
> Blue is recall. Orange is alert precision. At 100 reviews a day they are the
> same number — both about **27%**. Everything after that is one being paid for
> with the other.
>
> At 1,000 reviews a day I catch **80.18%** of fraud at **8.03%** alert
> precision — roughly **eleven legitimate customers reviewed for every fraud
> caught**. Doubling to 2,000 recovers **421 more fraud cases** and adds
> **30,357 more legitimate customers** to the queue.
>
> I mark no tier as best, because that depends on costs this evaluation does not
> contain. What I will not do is publish the recall without the queue."

---

## 4:05 – 4:20 · The result

*Slide 08.*

> "Average precision **0.2087**, ROC-AUC **0.8150**, with bootstrap intervals.
> Prevalence is 0.0348, which is what a no-skill ranker scores — so that is
> about six times baseline.
>
> The protocol was written and hashed before a single final-test row was read,
> and the scores were sealed before any label was loaded. It ran **once**, for
> 82 seconds, and there is no second run to choose from."

---

## 4:20 – 4:38 · Evidence boundaries

*Slide 09. Deliver this **confidently, not apologetically**. It is the
differentiator — most submissions will not have it. Lead with what each category
proves; the ceiling is the second half of the sentence, never the whole of it.*

> "Every claim in this project is filed against exactly one evidence category,
> and each one carries a stated ceiling.
>
> The sealed evaluation proves held-out ranking and capacity counts on 88,581
> transactions. The reference demo proves bounded execution, a real audit chain
> and clean refusal. The cost explorer proves how the operating point moves under
> a merchant's own assumptions.
>
> None of them borrows the others' credibility, and none of them is stretched
> past what it measured. **A number with a stated ceiling is a number you can act
> on** — that is the whole point."

---

## 4:38 – 4:45 · Close

*Slide 10, then cut to the live methodology page for three seconds.*

> "Every number you just saw reconciles to a sealed manifest in the repository.
> Open the methodology page and check any one of them while I'm still here."

---

## Likely questions — one-line answers

| Question | Answer |
|---|---|
| Average precision 0.2087 — isn't that low? | Prevalence is 0.034804, which is what a no-skill ranker scores. This is ~6× that, sealed on the first and only run, 95% CI 0.1957–0.2227. |
| Eleven legitimate customers per fraud caught? | Yes — 28,306 false positives for 2,472 true positives at the 1,000/day tier. It's in the headline instead of behind an accuracy figure, because the model that reviews nobody scores 96.52%. |
| Why not just pick a good threshold? | A threshold tells you nothing about tomorrow's staffing. A budget tells you both: at B = 1,000/day the threshold falls out as a minimum selected score of 0.020188. |
| Why does it never block? | The track is defense-only and my evidence is offline ranking. Every outcome is `human_review` or `below_review_threshold`, and a test enforces that — not a sentence in the README. |
| Why is the deployed demo a recorded transcript? | The public CSP carries no external API origin, so there is no verified public scoring backend. Live inference needs the local reference API. Labelling that is cheaper than faking it. |
| Is it calibrated? | ECE 0.003556 over 15 bins, Brier 0.030468 — but bins 7 to 15 are empty: the frozen calibrator never emits ≥ 0.40 on this population. Reported as found, not smoothed. |
| Why evaluate only once? | Because a second run makes the first meaningless. Started 07:06:40Z, finished 07:08:02Z on 27 August, scores hashed into a seal before any label was loaded. |
| What data is this? | Public IEEE-CIS. 88,581 held-out transactions, 3,083 fraud labels, over a 30.78-day window derived from a relative time offset — so no calendar or seasonality claim is available. |
| Would it hold at Razorpay scale? | I don't claim it. The final scale matrix failed closed and I published that instead of quietly dropping it. |
| Where does an LLM fit? | Nowhere on the decision path. Scoring is a deterministic bundle with zero LLM tokens, which is what makes the audit chain worth having. |
| What would you do next? | A cryptographically verified serving chain for the sealed bundle, per-merchant capacity policy, delayed-label handling, and a fairness study with protected attributes and an authorized design. |

If a question presses on a boundary: name what the evidence *does* cover, name
where it is documented, then say what you would measure to extend it. Answer from
strength — the scope is deliberate. Just never defend a number the record does
not support.

---

## If you only land one point

**The capacity frontier.** Recall is not free, the price is a queue of real
customers, and I put that price on the same slide as the win. Everything else
supports it.

---

## Recording notes

- Narrate the **decision**, not the interface.
- The two refusal beats (5 and 6) are the thing most submissions will not have.
  Give them room.
- Never say **blind**, **Razorpay performance**, **savings**, **ROI**, or
  **optimal threshold**. Each is an explicitly prohibited claim in the sealed
  record — and a judge who knows the dataset will hear it.
- If a number on screen differs from this page, read the screen. Always.
