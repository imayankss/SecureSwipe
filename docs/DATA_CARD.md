# Data card

## Dataset

The project is designed around the public Kaggle credit-card fraud example
commonly distributed as `creditcard.csv`. Committed historical reports record
284,807 rows and 492 positive `Class` rows. The CSV is intentionally not tracked
and was unavailable during the 2026-08-13 audit, so those source counts are a
historical observation rather than a fresh local verification.

To reproduce reference stages, obtain the file through Kaggle's official
authentication/download flow, place it at `data/raw/creditcard.csv`, and verify
its terms and fingerprint. Never commit the CSV or `kaggle.json`. This exact
corpus is already test-observed and cannot support new decisions; those require
a separate authorized dataset whose provenance is recorded locally.

## Schema and meaning

| Field | Contract | Known interpretation |
|---|---|---|
| `Time` | finite number, >= 0 | elapsed time in the source sample; not a calendar timestamp |
| `V1`–`V28` | finite numbers | anonymized PCA-derived components; original semantics are unavailable |
| `Amount` | finite number, >= 0 | transaction amount in the source dataset's undisclosed operating context |
| `Class` | integer 0 or 1 | source binary label; 1 denotes fraud in this project |

Exact order is required. Missing, extra, non-numeric, NaN, infinite, and
negative Time/Amount values fail closed. The curation command fails on
conflicting-label feature duplicates, keeps the first otherwise identical vector
in stable source order, and records raw/curated hashes and removed class counts.
Downstream commands reject any unresolved duplicate.

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
  split overlap cannot be recovered because holdout row identities were never
  retained. Curation can make reference reruns leakage-safe but cannot upgrade or
  recreate the already-observed result.
- `Time` is relative, so blocked evaluation measures ordering within this sample
  rather than contemporary calendar drift.
- Label creation, delay, disputes, recovery, and investigation processes are not
  documented; label noise and selection bias therefore remain unknown.
