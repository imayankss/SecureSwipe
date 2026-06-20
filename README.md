# Credit Card Fraud Detection & Risk Scoring System

## Overview

This project is a modular, production-style machine learning system for detecting
fraudulent credit card transactions and converting model predictions into
business-friendly fraud risk scores. It is built to look and behave like a small
real-world fraud detection pipeline rather than a single exploratory notebook —
with clean architecture, reusable code, saved artifacts, and evaluation reports.

> **Status:** Day 1 — project scaffolding only. No data loading, preprocessing,
> model training, or inference logic has been implemented yet.

## Problem Statement

Credit card fraud detection is a **highly imbalanced binary classification problem**.
Fraudulent transactions represent a tiny fraction of all transactions, which means
naive models and naive metrics can be dangerously misleading.

The goal of this project is to:

- Detect fraudulent transactions in a way that is sensitive to class imbalance.
- Go beyond a binary "fraud / not fraud" label by producing a fraud probability,
  a risk level, and a recommended business action.
- Make explicit, business-aware tradeoffs between catching more fraud (recall)
  and minimizing false alarms (precision).

## Dataset

This project uses the **Credit Card Fraud Detection** dataset from Kaggle:
https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud

The dataset contains anonymized credit card transactions made by European
cardholders.

**Columns:**

| Column      | Description                                                        |
|-------------|---------------------------------------------------------------------|
| `Time`      | Seconds elapsed between this transaction and the first transaction |
| `V1`–`V28`  | Anonymized, PCA-transformed numerical features                     |
| `Amount`    | Transaction amount                                                  |
| `Class`     | Target label — `1` = fraud, `0` = legitimate                       |

**Important limitation:** Because `V1`–`V28` are anonymized PCA components, any
explainability work later in this project (e.g. feature importance, SHAP) can
only describe *model behavior*. It cannot be mapped back to real-world fields
such as merchant, location, card type, or device.

The raw dataset file (`creditcard.csv`) is **not committed to this repository**.
It must be downloaded manually and placed in `data/raw/`.

## Why Accuracy Is Misleading

Fraud is rare. If, for example, 99.8% of transactions in the dataset are
legitimate, a model that predicts "legitimate" for every single transaction
would still score about 99.8% accuracy — while catching zero fraud.

For this reason, this project does **not** optimize for accuracy. Instead it
prioritizes metrics that are meaningful for the rare, positive (fraud) class:

1. **PR-AUC** (primary)
2. **Recall**
3. **Precision**
4. **F1-score**
5. **ROC-AUC** (secondary)
6. **Accuracy** (reported only, for contrast)

## Planned Architecture

The system is organized into independent layers so that each stage of the ML
workflow can be developed, tested, and reused on its own:

```text
Data Layer        → load and validate raw transaction data
Preprocessing      → leakage-safe scaling, splitting, imbalance handling
Modeling           → baseline, intermediate, and advanced classifiers
Evaluation         → fraud-focused metrics, plots, threshold tuning, cost analysis
Risk Scoring       → probability → Low / Medium / High risk + recommended action
Explainability     → feature importance / SHAP (with honest limitations)
Inference          → reusable end-to-end prediction pipeline
Interfaces (later) → optional Streamlit dashboard and FastAPI endpoint
```

## Folder Structure

```text
credit-card-fraud-risk-scoring/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── notebooks/
├── src/
│   ├── data/
│   ├── preprocessing/
│   ├── models/
│   ├── evaluation/
│   ├── explainability/
│   ├── inference/
│   └── utils/
│       ├── paths.py
│       ├── config.py
│       └── logger.py
├── models/
├── reports/
│   ├── figures/
│   └── metrics/
├── app/
├── api/
├── tests/
│   └── test_project_setup.py
├── configs/
│   └── config.yaml
├── scripts/
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml
└── main.py
```

## Planned ML Workflow

1. Load and validate the raw dataset.
2. Perform EDA on class imbalance, `Amount`, `Time`, and selected PCA features.
3. Build a leakage-safe preprocessing pipeline (split first, then fit scaling
   and other transformations only on the training data).
4. Split data into train / validation / test sets using stratified sampling.
5. Train a Logistic Regression baseline.
6. Train a Random Forest model.
7. Train an XGBoost or LightGBM model.
8. Compare models using fraud-focused metrics.
9. Tune the classification threshold on the validation set (never on test).
10. Run cost-sensitive threshold analysis using business costs for false
    positives and false negatives.
11. Convert fraud probability into a Low / Medium / High risk score and
    recommended action.
12. Generate feature importance / SHAP explanations for the final model.
13. Wrap everything in a reusable inference pipeline.

## Planned Models

| Stage        | Model                     |
|--------------|----------------------------|
| Baseline     | Logistic Regression        |
| Intermediate | Random Forest               |
| Advanced     | XGBoost or LightGBM         |

Class imbalance will be handled via class weighting, `scale_pos_weight`, and/or
SMOTE applied **only** to the training split.

## Evaluation Metrics

The following will be reported for every model:

- Precision, Recall, F1-score
- PR-AUC (primary metric) and ROC-AUC (secondary metric)
- Confusion matrix, specificity, false positive rate, false negative rate
- Accuracy (for contrast only — not optimized)

## Threshold Tuning Plan

Rather than using the default `0.5` probability cutoff, this project will sweep
thresholds on the **validation set** and report precision, recall, F1, F2, and
confusion matrix counts at each threshold. Thresholds will be selected to:

- Maximize F1 or F2 score, and/or
- Hit a target recall or target precision, and/or
- Minimize total business cost (see below).

## Risk Scoring Plan

Each transaction's fraud probability will be converted into a risk band and a
recommended action:

| Fraud Probability       | Risk Level | Recommended Action                          |
|--------------------------|------------|-----------------------------------------------|
| `0.00` – `0.20`          | Low        | Approve transaction                            |
| `0.20` – `0.60`          | Medium     | Step-up authentication or manual review        |
| `0.60` – `1.00`          | High       | Block transaction or urgent manual review      |

Risk thresholds are configurable in `configs/config.yaml`.

### Business Cost Analysis (planned)

False positives and false negatives carry different business costs:

- **False Positive** — legitimate transaction flagged as fraud → customer
  friction and manual review cost.
- **False Negative** — fraudulent transaction missed → direct financial loss
  and trust damage.

A configurable cost model (`false_positive_cost`, `false_negative_cost`) will
be used to select a threshold that minimizes total expected cost, rather than
relying on a one-size-fits-all default cutoff.

## Setup Instructions

1. Clone the repository and `cd` into it.
2. Create and activate a virtual environment:

```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
   pip install -r requirements.txt
```

4. (Later step) Download `creditcard.csv` from Kaggle and place it at
   `data/raw/creditcard.csv`. This step is not required for Day 1 setup.

## How to Run the Project Initialization Check

Day 1 only includes a setup/sanity check — no data loading or training yet.

```bash
python main.py
```

This will:

- Load `configs/config.yaml`
- Initialize the project logger
- Print the project name and version
- Print `Project initialized successfully.`

You can also run the setup tests:

```bash
pytest tests/test_project_setup.py
```

## Future Work

- Dataset loading and schema validation
- Exploratory data analysis notebook
- Leakage-safe preprocessing and train/validation/test split
- Logistic Regression, Random Forest, and XGBoost/LightGBM training
- Fraud-focused evaluation, threshold tuning, and cost-sensitive analysis
- Risk scoring and a reusable inference pipeline
- SHAP / feature importance explainability
- Optional Streamlit dashboard and FastAPI prediction endpoint
- Automated tests across all modules

No model results are reported in this README until models have actually been
trained and evaluated.
