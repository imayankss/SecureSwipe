# Credit Card Fraud Detection & Risk Scoring System

An end-to-end machine learning project for detecting fraudulent credit card
transactions in an extremely imbalanced dataset. The project is structured like
a small production-style ML system: data validation, leakage-safe preprocessing,
baseline models, XGBoost, validation-focused model comparison, threshold tuning,
SHAP explainability, and one locked final evaluation.

## Why This Problem Is Hard

Fraud is rare. In this dataset, only 492 out of 284,807 transactions are fraud:

| Item | Value |
|---|---:|
| Total transactions | 284,807 |
| Fraud cases | 492 |
| Legitimate transactions | 284,315 |
| Fraud rate | 0.1727% |
| Imbalance ratio | 577.88:1 |

Accuracy is misleading here. A model can predict every transaction as legitimate
and still score above 99% accuracy while catching zero fraud. This project
therefore prioritizes PR-AUC, recall, precision, F1-score, ROC-AUC, and
confusion matrix analysis.

## Dataset

The project uses the Kaggle Credit Card Fraud Detection dataset. The `V1` to
`V28` fields are anonymized PCA-transformed features, with `Time`, `Amount`,
and `Class` as additional columns. The raw `creditcard.csv` file is not meant
to be committed; place it in `data/raw/creditcard.csv`.

## Tech Stack

- Python, pandas, NumPy
- scikit-learn
- XGBoost
- SHAP
- matplotlib
- pytest
- joblib, pyarrow

## Project Structure

```text
src/data/              data loading, validation, and split helpers
src/preprocessing/     leakage-safe preprocessing pipeline
src/models/            baseline and XGBoost model utilities
src/evaluation/        metrics, comparison, threshold tuning, final evaluation
src/explainability/    SHAP explainability helpers
scripts/               reproducible day-by-day pipeline runners
tests/                 lightweight synthetic unit tests
reports/               generated Markdown reports and metrics
artifacts/models/      trained model artifacts
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Then download the Kaggle dataset and place it at:

```text
data/raw/creditcard.csv
```

## Reproduce The Pipeline

```bash
python3 scripts/run_day2_eda.py
python3 scripts/run_day3_preprocessing.py
python3 scripts/run_day4_baseline_models.py
python3 -m scripts.run_day5_advanced_models
python3 -m scripts.run_day6_threshold_tuning
python3 -m scripts.run_day7_explainability
python3 -m scripts.run_final_evaluation
python3 -m scripts.run_project_audit
```

Run tests:

```bash
python3 -m compileall src scripts tests
pytest
```

## SecureSwipe Dashboard

A modern Next.js dashboard is included in `web/` to present the project results:
class imbalance, ML pipeline, model comparison, threshold tuning, final
confusion matrix, SHAP explainability, and a risk score demo.

Run locally:

```bash
cd web
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

For Vercel, import the GitHub repository and set the root directory to `web`.

## Modeling Summary

Day 4 trained Dummy, Logistic Regression, and Random Forest baselines. Day 5
added XGBoost and selected the champion model by validation PR-AUC.

| Model | Validation PR-AUC | Validation ROC-AUC |
|---|---:|---:|
| XGBoost | 0.8129 | 0.9851 |
| Random Forest | 0.8125 | 0.9309 |
| Logistic Regression | 0.6275 | 0.9684 |
| Dummy baseline | 0.0017 | 0.5000 |

Champion model: `xgboost_baseline`.

## Threshold Tuning

The champion model was tuned on validation data only. The test set was not used
for threshold selection.

| Threshold | Precision | Recall | F1 | Use |
|---:|---:|---:|---:|---|
| 0.50 | 0.6061 | 0.8108 | 0.6936 | Default |
| 0.98 | 0.9138 | 0.7162 | 0.8030 | Best validation F1 |
| 0.53 | 0.6250 | 0.8108 | 0.7059 | Recommended business threshold |

Recommended operating threshold: `0.53`, selected as the highest-precision
threshold with validation recall at least 0.80.

## Explainability

Day 7 uses SHAP on a small validation sample to explain the already-trained
XGBoost model. SHAP is used only for explanation, not tuning, feature selection,
or model changes. Because most features are PCA-anonymized, the explanations
describe model behavior over transformed components rather than real-world
merchant or customer attributes.

Generated outputs:

- `reports/explainability/shap_feature_importance.csv`
- `reports/explainability/shap_top_features.json`
- `reports/explainability/shap_summary_report.md`
- `reports/figures/shap_summary_bar.png`
- `reports/figures/shap_top_features.png`

## Final Evaluation

The final evaluation uses the locked XGBoost model and locked threshold `0.53`
on the held-out test split once. No threshold tuning, model selection,
preprocessing changes, or feature changes are performed using test results.

Final evaluation outputs:

- `reports/final/final_model_evaluation.json`
- `reports/final/final_evaluation_report.md`
- `reports/final/final_project_report.md`
- `reports/final/project_audit_checklist.md`

## Limitations

- The dataset is anonymized and historical, so feature interpretation is limited.
- SHAP explains transformed PCA features, not original business fields.
- No production deployment, monitoring, or live feedback loop is included.
- Threshold costs are discussed qualitatively; a real deployment would require
  fraud-loss and review-cost estimates.

## Future Work

- Add cost-sensitive threshold optimization with real business costs.
- Add monitoring for class drift and calibration drift.
- Add model calibration analysis.
- Package inference behind an API or dashboard only after validation with
  production requirements.

## Author

Mayank Suryavanshi
