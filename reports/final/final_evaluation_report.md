# Final Model Evaluation Report: Credit Card Fraud Detection

## Report Metadata

| Field | Value |
|---|---|
| Generated | 2026-06-24T11:47:35.859632+00:00 |
| Champion model | `xgboost_baseline` |
| Evaluated split | `test` |
| Locked threshold | `0.53` |
| Threshold source | development_validation — highest_precision_meeting_recall_target (minimum_recall=0.8) |

---

## Integrity Note — Threshold Selection

Historical observation: repository history records model and threshold selection on validation before this random held-out split was evaluated. The result has now been observed and must not be reused for tuning. Exact duplicate rows were reported in the source dataset, but cross-split overlap was not recorded, so this is not out-of-time or real-world evidence.

This preserves the recorded result as historical evidence; it is not a claim about deployment or future performance.

---

## Dataset Summary

| Field | Value |
|---|---|
| Split evaluated | `test` |
| Total samples | 42,722 |
| Fraud cases | 74 |
| Legitimate cases | 42,648 |

---

## Final Evaluation Metrics

| Metric | Value |
|---|---|
| **Average precision** | **0.8288** |
| ROC-AUC | 0.9613 |
| Precision | 0.6966 |
| Recall | 0.8378 |
| F1-score | 0.7607 |
| Specificity | 0.9994 |
| False Positive Rate | 0.0006 |
| False Negative Rate | 0.1622 |

---

## Confusion Matrix

| | Predicted Legitimate | Predicted Fraud |
|---|---|---|
| **Actual Legitimate** | TN = 42,621 | FP = 27 |
| **Actual Fraud**      | FN = 12 | TP = 62 |

### Interpretation

- **True positives:** 62 — labelled fraud rows flagged at this threshold.
- **False negatives:** 12 — labelled fraud rows not flagged.
- **False positives:** 27 — labelled legitimate rows flagged.
- **True negatives:** 42,621 — labelled legitimate rows not flagged.

> **Decision context:** The historical threshold was selected on validation for the point estimate recall constraint recorded in its source artifact. No fraud-loss, review-cost, recovery, or authorization policy was evaluated.

---

## Why Average Precision Is the Primary Metric

This evaluation split contains **0.1732 % fraud** when the recorded counts are available — an extreme class imbalance.
Under these conditions:

- **Accuracy** is misleading.  A model that always predicts 'legitimate' achieves ~99.8 % accuracy while catching zero fraud.
- **ROC-AUC** is influenced heavily by the large number of true negatives and can appear strong even when fraud detection is poor.
- **Average precision** measures the quality of the precision–recall trade-off for the fraud class only.  It is the most meaningful single-number summary for this problem.

---

## Project Result Summary

| Stage | Result |
|---|---|
| Recorded model | `xgboost_baseline` |
| Recorded threshold | 0.53 |
| **Final test average precision** | **0.8288** |
| Final test Recall | 0.8378 |
| Final test Precision | 0.6966 |
| Final test F1-score | 0.7607 |

---

*Report generated automatically by `src/evaluation/final_evaluation.py`.*
