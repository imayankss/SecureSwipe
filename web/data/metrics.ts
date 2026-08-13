import dashboardJson from "@/public/data/dashboard.json";

export const dashboardData = dashboardJson;

export type ThresholdPoint = (typeof dashboardData.thresholdAnalysis.points)[number];

export const formatInteger = (value: number) =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);

export const formatMetric = (value: number, digits = 4) => value.toFixed(digits);

export const formatPercent = (value: number, digits = 2) =>
  `${(value * 100).toFixed(digits)}%`;

export const heroMetrics = [
  {
    label: "Evaluated transactions",
    value: formatInteger(dashboardData.finalEvaluation.total_samples),
    description: "Locked held-out test split",
  },
  {
    label: "Test fraud cases",
    value: formatInteger(dashboardData.finalEvaluation.total_fraud),
    description: "Rare positive class",
  },
  {
    label: "Test average precision",
    value: formatMetric(dashboardData.finalEvaluation.pr_auc),
    description: "Primary final metric",
  },
  {
    label: "Fraud recall",
    value: formatPercent(dashboardData.finalEvaluation.recall),
    description: `At the recorded ${dashboardData.finalEvaluation.threshold.toFixed(2)} threshold`,
  },
];

export const finalMetrics = [
  { label: "Average precision", value: formatMetric(dashboardData.finalEvaluation.pr_auc) },
  { label: "ROC-AUC", value: formatMetric(dashboardData.finalEvaluation.roc_auc) },
  { label: "Precision", value: formatPercent(dashboardData.finalEvaluation.precision) },
  { label: "Recall", value: formatPercent(dashboardData.finalEvaluation.recall) },
  { label: "F1 score", value: formatPercent(dashboardData.finalEvaluation.f1_score) },
];

export const pipelineSteps = [
  "Validate + profile",
  "Stratified split",
  "Train-only preprocessing",
  "Baseline comparison",
  "XGBoost selection",
  "Validation thresholding",
  "Historical test + SHAP",
];

export const modelComparison = dashboardData.modelComparison.map((item) => ({
  model: item.displayName,
  prAuc: item.pr_auc,
  rocAuc: item.roc_auc,
  precision: item.precision,
  recall: item.recall,
  f1: item.f1,
}));

export const shapFeatures = dashboardData.explainability.features.slice(0, 10).map((item) => ({
  feature: item.feature,
  importance: item.mean_abs_shap_value,
}));
