# Data card

## Dataset

The project is designed around the public Kaggle credit-card fraud example
commonly distributed as `creditcard.csv`. Committed historical reports record
284,807 rows and 492 positive `Class` rows. The CSV is intentionally not tracked
and was unavailable during the 2026-08-13 audit, so those source counts are a
historical observation rather than a fresh local verification.

Before any new run, obtain the file through Kaggle's official authentication and
download flow, place it at `data/raw/creditcard.csv`, and verify its terms and
fingerprint. Never commit the CSV or `kaggle.json`.

## Schema and meaning

| Field | Contract | Known interpretation |
|---|---|---|
| `Time` | finite number, >= 0 | elapsed time in the source sample; not a calendar timestamp |
| `V1`–`V28` | finite numbers | anonymized PCA-derived components; original semantics are unavailable |
| `Amount` | finite number, >= 0 | transaction amount in the source dataset's undisclosed operating context |
| `Class` | integer 0 or 1 | source binary label; 1 denotes fraud in this project |

Exact order is required. Missing, extra, non-numeric, NaN, infinite, negative
Time/Amount, and duplicate transaction-feature rows fail closed. The manifest
records an order-sensitive dataset fingerprint without storing raw rows.

## Intended and prohibited use

This dataset supports education and offline imbalanced-classification research.
It is not evidence that the system can authorize payments, operate on current
traffic, or generalize to another geography, merchant mix, fraud taxonomy, or
time period. Do not send real customer/card data to the reference API.

## Bias, privacy, and limitations

- PCA anonymization removes domain meaning needed for actionable root-cause or
  causal explanations.
- No declared protected attributes are present, so protected-group fairness
  cannot be measured. This is missing evidence, not evidence of fairness.
- The historical repository report found 1,081 duplicate rows. Their original
  split overlap cannot be measured until the CSV is restored. New runs reject
  duplicates before splitting.
- `Time` is relative, so blocked evaluation measures ordering within this sample
  rather than contemporary calendar drift.
- Label creation, delay, disputes, recovery, and investigation processes are not
  documented; label noise and selection bias therefore remain unknown.
