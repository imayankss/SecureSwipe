# MT5 — illustrative merchant cost explorer contract

**Pre-registered before any cost-calculation or UI code was written.** This
document is hashed and its digest recorded before implementation begins.

This is an **illustrative scenario tool**. It is not model training, threshold
selection, capacity selection, or business economics. It computes arithmetic on
already-published aggregate counts and nothing else.

## 1 — Fixed inputs, from sealed public evidence only

The explorer consumes exactly the five-tier final frontier published in
`docs/evidence/LANE_A_FINAL_EVALUATION.md`. These counts are read-only inputs.
They are never recomputed from scores, and no private artifact is consulted.

| Daily review capacity | Review budget | TP | FP | FN | TN | Precision | Recall |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 3,077 | 838 | 2,239 | 2,245 | 83,259 | 0.2723 | 0.2718 |
| 250 | 7,694 | 1,409 | 6,285 | 1,674 | 79,213 | 0.1831 | 0.4570 |
| 500 | 15,389 | 1,985 | 13,404 | 1,098 | 72,094 | 0.1290 | 0.6439 |
| 1,000 | 30,778 | 2,472 | 28,306 | 611 | 57,192 | 0.0803 | 0.8018 |
| 2,000 | 61,556 | 2,893 | 58,663 | 190 | 26,835 | 0.0470 | 0.9384 |

Every tier reconciles against the sealed totals: 3,083 positives, 85,498
negatives, 88,581 rows.

`web/data/laneACapacity.ts` holds the **development** frontier and is frozen
evidence. MT5 does not modify it and does not read it as the source for these
final counts.

## 2 — What the tool is and is not

- **Static and client-side.** It makes no network request, no API call, and no
  fraud-scoring call. It touches no model, score, or threshold.
- **It does not choose anything.** It selects no capacity, no threshold, and no
  operating point, and it declares no tier better than another.
- It is not Razorpay economics, merchant pricing, savings, ROI, or a production
  recommendation.

## 3 — The exact formula

```
illustrative_total_cost =
      (TP + FP) x review_cost
    + FP        x legitimate_customer_friction_cost
    + FN        x (missed_fraud_loss + chargeback_handling_cost)
```

Reported as three transparent components plus the total:

- **review workload cost** = `(TP + FP) x review_cost`
- **legitimate-friction cost** = `FP x legitimate_customer_friction_cost`
- **missed-fraud-and-chargeback scenario cost** = `FN x (missed_fraud_loss + chargeback_handling_cost)`

Nothing else is computed. There is deliberately **no** "money saved", "net
benefit", "recovery", "payback", or "optimal operating point" term.

## 4 — The four editable assumptions

All four are INR, all four are editable, all four are visible, and all four are
**synthetic and illustrative**:

1. review cost per queued transaction;
2. legitimate-customer friction cost per false-positive review;
3. missed-fraud loss per false negative;
4. chargeback-handling cost per false negative.

The visible starting values are labelled **`Illustrative starting assumptions`**.
They are never called default merchant settings, recommended values, typical
values, or benchmarks.

## 5 — Validation and numeric safety

Each assumption must be a **finite, non-negative** number. Blank, negative,
non-finite, non-numeric, or excessively large input must never produce `NaN`,
`Infinity`, a negative cost, or a silently misleading figure. Invalid input is
rejected and surfaced to the user; the last valid computation is not
misrepresented as applying to the invalid value.

Calculations retain paise-level precision internally and are displayed in INR
consistently, with the same rounding rule everywhere in the panel.

## 6 — Sensitivity scenarios

At least two sensitivity scenarios are displayed, computed across the **same
five fixed capacity tiers** by varying assumptions only:

- **Higher review cost** — review cost raised, other assumptions held.
- **Higher missed-fraud loss** — missed-fraud loss raised, other assumptions held.

Sensitivity output is clearly marked illustrative. No scenario is crowned a
winner, and the words `best`, `recommended`, `optimal`, and `saves` are not used
to describe any tier or scenario.

## 7 — Required disclosure

The panel displays, without scrolling inside the panel:

> `Illustrative scenario only — not Razorpay economics, merchant pricing, savings, ROI, or a production recommendation.`

It also states plainly that **false positives are legitimate transactions sent
to human review, not automatically declined**, and it carries an evidence label
tying the panel to the sealed final Lane A aggregate evaluation.

## 8 — Accessibility

Keyboard operable throughout; every input has a real label and an accessible
description; meaningful changes are announced to screen readers via a polite
live region; usable at 375 px with no page-level horizontal overflow.

## 9 — Predeclared test cases

1. All five tiers preserve their frozen counts exactly.
2. Formula arithmetic reconciles for every tier, component by component.
3. Zero-cost inputs yield a zero total.
4. High FP-friction changes only the friction term and the total.
5. High FN-loss changes only the missed-fraud term and the total.
6. Invalid, negative, non-finite, blank, and excessively large input is refused
   safely.
7. Formatting and INR rounding are deterministic.
8. User edits update both the selected-tier breakdown and the all-tier table.
9. Selector and inputs are keyboard accessible.
10. Required disclosure and limitation text is present.
11. No forbidden claim string is introduced.
12. No model score, private value, raw row, label, or final-test reference
    enters the frontend.

## 10 — Prohibited claims

This panel may never claim savings, ROI, cost reduction, fraud prevented,
recovered revenue, real merchant economics, Razorpay pricing or economics,
production readiness, a recommended capacity, or an optimal threshold. It may
never compare Lane A with Lane B.

These are **scenario calculations on published aggregate counts, not observed
merchant costs**. `final_test` is not accessed by anything this contract
authorises.
