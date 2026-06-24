export const datasetStats = {
  totalTransactions: 284807,
  legitimate: 284315,
  fraud: 492,
  fraudRate: 0.1727,
  imbalanceRatio: 577.88,
};

export const heroMetrics = [
  {
    label: "Transactions",
    value: "284,807",
    description: "Total credit card transactions",
  },
  {
    label: "Fraud Cases",
    value: "492",
    description: "Confirmed fraudulent transactions",
  },
  {
    label: "Fraud Rate",
    value: "0.1727%",
    description: "Highly imbalanced dataset",
  },
  {
    label: "Test PR-AUC",
    value: "0.8288",
    description: "Primary fraud metric",
  },
  {
    label: "Fraud Recall",
    value: "83.78%",
    description: "Locked test-set fraud detection",
  },
];

export const finalMetrics = [
  { label: "Final Test PR-AUC", value: "0.8288" },
  { label: "Final Test ROC-AUC", value: "0.9613" },
  { label: "Precision", value: "69.66%" },
  { label: "Recall", value: "83.78%" },
  { label: "F1 Score", value: "76.07%" },
];

export const pipelineSteps = [
  "Data Validation",
  "EDA",
  "Preprocessing",
  "Baselines",
  "XGBoost",
  "Threshold Tuning",
  "SHAP + Final Evaluation",
];

export const thresholdResults = [
  {
    name: "Default Threshold",
    threshold: "0.50",
    precision: "60.61%",
    recall: "81.08%",
    f1: "69.36%",
  },
  {
    name: "Best F1 Threshold",
    threshold: "0.98",
    precision: "91.38%",
    recall: "71.62%",
    f1: "80.30%",
  },
  {
    name: "Business Threshold",
    threshold: "0.53",
    precision: "62.50%",
    recall: "81.08%",
    f1: "70.59%",
  },
];

export const confusionMatrix = {
  threshold: 0.53,
  truePositive: 62,
  falsePositive: 27,
  falseNegative: 12,
  trueNegative: 42621,
};

export const modelComparison = [
  { model: "Dummy", prAuc: 0.0017, rocAuc: 0.5 },
  { model: "Logistic Regression", prAuc: 0.6275, rocAuc: 0.9684 },
  { model: "Random Forest", prAuc: 0.8125, rocAuc: 0.9309 },
  { model: "XGBoost", prAuc: 0.8288, rocAuc: 0.9613 },
];

export const shapFeatures = [
  { feature: "V4", importance: 1.9142 },
  { feature: "V14", importance: 1.8084 },
  { feature: "V12", importance: 0.8405 },
  { feature: "V10", importance: 0.6036 },
  { feature: "V3", importance: 0.5067 },
  { feature: "V11", importance: 0.3776 },
  { feature: "V26", importance: 0.3205 },
  { feature: "V16", importance: 0.3183 },
  { feature: "Amount", importance: 0.3139 },
  { feature: "V8", importance: 0.3049 },
];
