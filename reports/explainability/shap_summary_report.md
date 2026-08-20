# SHAP Feature Importance Summary

## Purpose

This historical report records a feature ranking produced from a validation sample. The original run did not retain its row identities, labels, scores, SHAP expected value, output unit, or additivity residuals. The ranking therefore cannot be described as probability impact or independently reproduced from this checkout.

## Important Limitation

Because `V1` to `V28` are anonymized PCA-transformed features, SHAP values explain model behavior in terms of these transformed components. They do not map directly to real-world transaction attributes such as merchant, location, or card type.

## Historical Evidence Status

- **Output unit:** not retained or independently verified. Based on the reviewed code path, TreeExplainer likely used its default raw model output, but the absent model artifact prevents verification.
- **Additivity:** not retained or independently verified.
- **Cohort composition:** unavailable; the original sample did not retain aligned labels, score distribution, or row identities.
- **Model artifact:** intentionally absent from the repository.

New runs use the tested raw-margin/log-odds additivity protocol and emit aggregate cohort evidence. These safeguards do not retroactively validate the values below.

## Top 20 Historical Features by SHAP Importance

| Rank | Feature | Historical Mean Absolute SHAP Value (Unit Unverified) |
|---:|---|---:|
| 1 | V4 | 1.914230 |
| 2 | V14 | 1.808449 |
| 3 | V12 | 0.840523 |
| 4 | V10 | 0.603617 |
| 5 | V3 | 0.506720 |
| 6 | V11 | 0.377626 |
| 7 | V26 | 0.320547 |
| 8 | V16 | 0.318310 |
| 9 | Amount | 0.313929 |
| 10 | V8 | 0.304865 |
| 11 | Time | 0.291748 |
| 12 | V15 | 0.291153 |
| 13 | V7 | 0.287668 |
| 14 | V28 | 0.279879 |
| 15 | V21 | 0.279400 |
| 16 | V24 | 0.267114 |
| 17 | V25 | 0.258173 |
| 18 | V18 | 0.254940 |
| 19 | V19 | 0.249909 |
| 20 | V20 | 0.210927 |

## How to Read This Report

- A higher historical mean absolute value records a larger attribution magnitude in the original run's unspecified model-output unit. It is not evidence of a calibrated fraud-probability change.
- This ranking reflects model behavior only. It does not imply causation or a verified real-world explanation.

## Scope Notes

- The tracked script says the historical values came from a validation sample; the absent artifact and unretained row identities prevent independent reproduction.
- SHAP was used strictly for explanation. It was not used to tune the model, select features, or change preprocessing.
