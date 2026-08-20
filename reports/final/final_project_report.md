# Current Project Report: SecureSwipe

Audit status: **INCOMPLETE**

SecureSwipe is a portfolio reference for offline fraud-risk modelling and
a bundle-gated inference API. It is not a bank authorization or compliance
system and no verified trained fraud model is present in this checkout.

## Historical reported test observation

- Model: `xgboost_baseline`
- Recorded validation-selected threshold: `0.53`
- Average precision (historical key `pr_auc`): `0.8287848539773868`
- Precision / recall / F1: `0.6966292134831461` / `0.8378378378378378` / `0.7607361963190185`
- Confusion counts TP/FP/FN/TN: `62` / `27` / `12` / `42621`

The random test result has already been observed, has possible duplicate
contamination, lacks original artifact/runtime provenance, and is excluded
from all new decisions. It is not out-of-time or deployment evidence.

## Current evidence

See `docs/industrialization/STATE.md` and `QUALITY_SCORECARD.md` for
executed commands, external blockers, and the next action. File presence
alone is never reported as a passing quality gate.
