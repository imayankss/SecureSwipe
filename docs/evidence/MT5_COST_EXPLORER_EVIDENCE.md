# MT5 — illustrative merchant cost & review workload explorer

> **Illustrative scenario only — not Razorpay economics, merchant pricing,
> savings, ROI, or a production recommendation.**

This records a **scenario calculator**, not an economic finding. It performs
arithmetic on already-published aggregate counts. It trains nothing, scores
nothing, selects no capacity and no threshold, and makes no network request.

Contract: `docs/evidence/MT5_COST_EXPLORER_CONTRACT.md`, pre-registered and
hashed before any cost-calculation or UI code existed.

## 1 — Provenance of the fixed inputs

Counts come **only** from the sealed one-time final evaluation in
`docs/evidence/LANE_A_FINAL_EVALUATION.md` (result manifest
`65fd02bb26f7e2cec909840f41855fc4af7589028e7a59fda7b5d41cd401d20c`). They are
read-only inputs, never recomputed from scores, and no private artifact is
consulted.

| Capacity/day | Review budget | TP | FP | FN | TN | Precision | Recall |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 3,077 | 838 | 2,239 | 2,245 | 83,259 | 0.2723 | 0.2718 |
| 250 | 7,694 | 1,409 | 6,285 | 1,674 | 79,213 | 0.1831 | 0.4570 |
| 500 | 15,389 | 1,985 | 13,404 | 1,098 | 72,094 | 0.1290 | 0.6439 |
| 1,000 | 30,778 | 2,472 | 28,306 | 611 | 57,192 | 0.0803 | 0.8018 |
| 2,000 | 61,556 | 2,893 | 58,663 | 190 | 26,835 | 0.0470 | 0.9384 |

Every tier reconciles: `TP+FN` = 3,083 positives, `TN+FP` = 85,498 negatives,
all four cells sum to 88,581 rows, and no tier exceeds its review budget. This
was verified against the frozen document before implementation began.

`web/data/laneACapacity.ts` holds the earlier **development** frontier. It is
frozen evidence, was not modified, and is byte-identical before and after MT5.

## 2 — The formula

```
illustrative_total_cost =
      (TP + FP) x review_cost
    + FP        x legitimate_customer_friction_cost
    + FN        x (missed_fraud_loss + chargeback_handling_cost)
```

There is deliberately **no** money-saved, net-benefit, recovery, payback, or
optimal-operating-point term. Amounts are held at paise precision internally and
displayed as whole INR.

## 3 — Illustrative starting assumptions

These are **illustrative starting assumptions**, editable in the panel. They are
not default merchant settings, recommended values, typical values, or
benchmarks, and they are not drawn from Razorpay or any merchant.

| Assumption | Starting value (INR) |
| --- | ---: |
| Review cost per queued transaction | 25 |
| Legitimate-customer friction cost per false-positive review | 40 |
| Missed-fraud loss per false negative | 4,000 |
| Chargeback-handling cost per false negative | 750 |

## 4 — Scenario output under the starting assumptions

| Capacity/day | Reviewed (TP+FP) | Review workload cost | Legitimate-friction cost | Missed-fraud & chargeback | Illustrative total |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 3,077 | ₹76,925 | ₹89,560 | ₹10,663,750 | ₹1,08,30,235 |
| 250 | 7,694 | ₹192,350 | ₹251,400 | ₹7,951,500 | ₹83,95,250 |
| 500 | 15,389 | ₹384,725 | ₹536,160 | ₹5,215,500 | ₹61,36,385 |
| 1,000 | 30,778 | ₹769,450 | ₹1,132,240 | ₹2,902,250 | ₹48,03,940 |
| 2,000 | 61,556 | ₹1,538,900 | ₹2,346,520 | ₹902,500 | ₹47,87,920 |

**Read this as the trade-off, not as a ranking.** Raising capacity from 100 to
2,000 reviews/day raises recall from 27.18 % to 93.84 %, and in the same step
raises legitimate transactions sent to human review from 2,239 to 58,663. Under
these particular assumptions the review and friction terms grow while the
missed-fraud term shrinks. **No tier is recommended, and changing any assumption
changes which term dominates.**

A false positive here is a legitimate transaction **sent to human review — it is
not automatically declined**.

## 5 — Sensitivity scenarios

### Higher review cost

Review cost per queued transaction tripled; other assumptions unchanged.

| Capacity/day | Illustrative total |
| ---: | ---: |
| 100 | ₹1,09,84,085 |
| 250 | ₹87,79,950 |
| 500 | ₹69,05,835 |
| 1,000 | ₹63,42,840 |
| 2,000 | ₹78,65,720 |

### Higher missed-fraud loss

Missed-fraud loss per false negative tripled; other assumptions unchanged.

| Capacity/day | Illustrative total |
| ---: | ---: |
| 100 | ₹2,87,90,235 |
| 250 | ₹2,17,87,250 |
| 500 | ₹1,49,20,385 |
| 1,000 | ₹96,91,940 |
| 2,000 | ₹63,07,920 |

Both scenarios vary a single assumption and are shown side by side without
crowning a winner. They demonstrate that the ordering of tiers by illustrative
cost is an artefact of the assumptions, not a property of the model.

## 6 — Integrity checks and tests

| Check | Result |
| --- | --- |
| Cost-model unit tests | 35 passed |
| Cost-explorer UI tests | 19 passed |
| Full frontend suite (data-check, ESLint, TypeScript, Vitest) | 85 passed |
| Playwright E2E (whole suite) | 10 passed |
| Playwright: desktop, keyboard, 375 px overflow, disclosure visibility, WCAG on panel | passed |
| Static production build | succeeded |
| Python canonical suite | 1,159 passed, 0 failed |
| `git diff --check` | clean |
| Frozen final-evaluation document | byte-identical |
| Frozen `laneACapacity.ts` | byte-identical |

Covered by test: all five tiers preserve their frozen counts; formula arithmetic
reconciles component by component for every tier; zero assumptions give a zero
total; higher FP friction changes only the friction term and the total; higher FN
loss changes only the missed-fraud term and the total; blank, negative,
non-finite, non-numeric and oversized input are refused without ever producing
`NaN`, `Infinity` or a negative cost; formatting is deterministic; edits update
both the selected-tier breakdown and the all-tier table; the selector and inputs
are keyboard operable; required disclosures are present; and no forbidden claim
or private value appears.

**Rendered-output verification.** The built static HTML was scanned directly:
the cost panel contains zero occurrences of `final_test`, `isFraud`,
`TransactionID`, `raw_score`, `decision_score`, or any absolute path, and zero
unnegated forbidden claims.

## 7 — Limitations

- These are **scenario calculations on published aggregate counts, not observed
  merchant costs**. No merchant, payment processor, or real cost was measured.
- Every monetary value is an **illustrative assumption**, not market data.
- The panel selects **no capacity and no threshold**, and nothing in it
  approves, blocks, declines, or steps up a payment.
- Counts come from one dataset partition evaluated once. They are not live
  performance and not a forecast.
- Costs are linear in the counts by construction; real operations have fixed
  costs, queueing, staffing steps and time-varying volume that this does not
  model.
- Lane A and Lane B are **not compared**, here or anywhere in the panel.

## 8 — Prohibited claims

This panel may never be used to claim savings, ROI, cost reduction, fraud
prevented, recovered revenue, real merchant economics, Razorpay pricing or
economics, production readiness, a recommended capacity, or an optimal
threshold.

`final_test` was not accessed by MT5. The role is named only as a provenance
label, exactly as it already appears in the sealed public final-evaluation
document.
