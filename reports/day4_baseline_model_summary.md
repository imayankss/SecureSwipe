# Day 4 Baseline Model Summary: Credit Card Fraud Detection

## Report Metadata
- Generated: 2026-06-24 11:26:46

## Project Context
This project detects fraudulent credit card transactions in a highly imbalanced dataset. Day 2 confirmed that fraud cases are extremely rare compared to legitimate transactions. Day 3 produced leakage-safe processed training, validation, and test data. Day 4 trains baseline models on the training data and evaluates them on the validation data only.

## Day 4 Scope
Day 4 covers the following baseline models and evaluation steps:
- Dummy baseline (naive majority-class predictor)
- Logistic Regression baseline
- Random Forest baseline
- Validation set metrics for each model
- No threshold tuning was performed
- No final test-set evaluation was performed

## Models Trained
- **dummy_baseline** (DummyClassifier)
- **logistic_regression** (LogisticRegression)
- **random_forest** (RandomForestClassifier)

## Validation Metrics
| model_name | accuracy | precision | recall | f1_score | roc_auc | pr_auc | false_positives | false_negatives | true_positives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dummy_baseline | 0.9982678308092039 | 0.0 | 0.0 | 0.0 | 0.5 | 0.0017321691907960957 | 0 | 74 | 0 |
| logistic_regression | 0.9786053697244914 | 0.06701030927835051 | 0.8783783783783784 | 0.12452107279693486 | 0.9684146535449089 | 0.6275251631550335 | 905 | 9 | 65 |
| random_forest | 0.9994616230893472 | 0.9811320754716981 | 0.7027027027027027 | 0.8188976377952756 | 0.9308812000970886 | 0.8125348843416794 | 1 | 22 | 52 |

## Best Baseline Model
The best baseline model by PR-AUC is **random_forest**. PR-AUC was used to select this model because it focuses on the rare positive (fraud) class rather than overall accuracy.

## Why Accuracy Is Not Enough
Fraud is a rare event in this dataset, so a model can predict almost every transaction as legitimate and still achieve a very high accuracy score while catching no fraud at all. Precision, recall, F1-score, PR-AUC, ROC-AUC, and the confusion matrix give a much more honest picture of how well a model actually detects fraud. PR-AUC is especially important here because it summarizes the precision-recall tradeoff for the rare positive class under heavy imbalance.

## Confusion Matrix Interpretation
- **True negatives**: legitimate transactions correctly classified as legitimate.
- **False positives**: legitimate transactions incorrectly flagged as fraud.
- **False negatives**: fraudulent transactions that were missed by the model.
- **True positives**: fraudulent transactions correctly caught by the model.

False negatives are especially costly in fraud detection because each one represents a fraudulent transaction that went undetected.

## Generated Model Artifacts
- **dummy_baseline**: `artifacts/models/dummy_baseline.joblib`
- **logistic_regression**: `artifacts/models/logistic_regression.joblib`
- **random_forest**: `artifacts/models/random_forest.joblib`

## Generated Metrics Files
- **metrics_json**: `reports/metrics/day4_baseline_metrics.json`
- **metrics_csv**: `reports/metrics/day4_baseline_metrics.csv`

## Day 4 Conclusions
- Baseline models (Dummy, Logistic Regression, Random Forest) were trained on the training data.
- Validation metrics were generated for every baseline model.
- These results establish a benchmark that advanced models must beat.
- The test set remains untouched and reserved for final evaluation.

## Day 5 Next Steps
- Train an XGBoost or LightGBM model.
- Compare the advanced model against the Day 4 baselines.
- Continue prioritizing PR-AUC, recall, precision, and F1-score over accuracy.
- Avoid selecting a final model based on accuracy alone.
