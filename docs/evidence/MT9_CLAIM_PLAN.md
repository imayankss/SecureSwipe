# MT9 — reviewer claim hierarchy

Written before any README or dashboard edit. Every number a reviewer sees must
carry exactly one of the six categories below, so nobody has to infer which
model or evidence source produced it.

## The six evidence categories

1. `SEALED FINAL EVALUATION — LANE A / IEEE-CIS`
2. `HISTORICAL SERVING — LOOPBACK / NOT COMPARABLE TO MT3`
3. `ILLUSTRATIVE COST SCENARIO — NOT RAZORPAY ECONOMICS`
4. `LOCAL SQLITE DURABILITY PROTOTYPE — OPTIONAL / NON-DEFAULT`
5. `SYNTHETIC ORDER-INTEGRITY REFERENCE — SEPARATE FROM FRAUD MODEL`
6. `FUTURE OR DEFERRED — NOT IMPLEMENTED`

## The primary scientific result

Category 1. This is the headline number and nothing may be promoted above it.

| Quantity | Value |
| --- | --- |
| Average precision | `0.208660` |
| AP 95 % CI | `[0.195700, 0.222711]` |
| ROC-AUC | `0.814975` |
| At 1,000 reviews/day — recall | `80.18 %` |
| At 1,000 reviews/day — precision | `8.03 %` |
| At 1,000 reviews/day — TP / FP / FN / TN | `2,472` / `28,306` / `611` / `57,192` |

It is **one sealed, programmatically held-out IEEE-CIS evaluation, run exactly
once**. It is not Razorpay or live-merchant performance, and it was not used for
any post-result retuning.

## Lane B separation

The older Lane B historical AP `0.8288` must **never** be promoted above the
Lane A result and the two must **never** be compared: different corpus, base
rate, label definition, and feature space. Where Lane B evidence is retained it
stays visually distinct and labelled as separate historical evidence.

## Assignment of existing surfaces

| Surface | Category |
| --- | --- |
| Lane A sealed final metrics and capacity table | 1 |
| Lane A development capacity workbench (`validation_threshold`) | separate development evidence, labelled as such |
| MT4 loopback RPS / latency | 2 |
| MT5 merchant cost explorer | 3 |
| MT6 SQLite prototype | 4 |
| MT7 order-integrity reference | 5 |
| MT8 Razorpay context adapter | 6 |
| Lane B historical dashboard evidence | separate historical evidence, visually distinct |

## Wording rules

- False positives are **legitimate transactions sent to human review**, never
  automatically declined.
- No tier is optimal, recommended, or a merchant default.
- No illustrative INR figure is a saving, ROI, or real loss.
- MT4 loopback numbers are never presented as production capacity.
- MT6 is always labelled optional / non-default.
- MT7 is always labelled synthetic and separate from ML metrics.
- No real payment action, API integration, or autonomous block is implied.
