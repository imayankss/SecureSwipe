/**
 * Lane A (IEEE-CIS) FINAL capacity frontier — sealed aggregate evidence.
 *
 * AGGREGATE COUNTS ONLY. No rows, identifiers, email domains, device strings,
 * amounts, labels, scores, or private paths appear here.
 *
 * Source: docs/evidence/LANE_A_FINAL_EVALUATION.md, the one-time final
 * evaluation of the programmatically held-out `final_test` role, evaluated
 * exactly once. These counts are read-only inputs and are never recomputed.
 *
 * This is distinct from `laneACapacity.ts`, which holds the earlier
 * DEVELOPMENT (validation_threshold) frontier and remains frozen evidence.
 *
 * These figures must never be compared with Lane B historical metrics, which
 * come from a different corpus, base rate, label definition and feature space.
 */

export const LANE_A_FINAL_EVIDENCE = {
  source: "docs/evidence/LANE_A_FINAL_EVALUATION.md",
  role: "final_test (programmatically held out, evaluated exactly once)",
  rows: 88_581,
  positives: 3_083,
  negatives: 85_498,
  prevalence: 0.034804,
  evaluationPeriodDays: 30.7784,
  resultManifestSha256:
    "65fd02bb26f7e2cec909840f41855fc4af7589028e7a59fda7b5d41cd401d20c",
} as const;

/**
 * Headline metrics from the sealed one-time final evaluation.
 *
 * Category: SEALED FINAL EVALUATION — LANE A / IEEE-CIS. Evaluated exactly once
 * on a programmatically held-out role. Not Razorpay or live-merchant
 * performance, and never comparable with Lane B historical metrics.
 */
export const LANE_A_FINAL_METRICS = {
  averagePrecision: 0.20866,
  averagePrecisionCiLow: 0.1957,
  averagePrecisionCiHigh: 0.222711,
  rocAuc: 0.814975,
  rocAucCiLow: 0.806402,
  rocAucCiHigh: 0.822899,
  brierScore: 0.030468,
  logLoss: 0.124252,
  expectedCalibrationError: 0.003556,
  bootstrapResamples: 2000,
  bootstrapSeed: 42,
  confidenceLevel: 0.95,
} as const;

export const LANE_A_FINAL_CATEGORY = "SEALED FINAL EVALUATION — LANE A / IEEE-CIS";

export const LANE_A_FINAL_ILLUSTRATIVE_LABEL =
  "Illustrative scenario only — not Razorpay economics, merchant pricing, savings, ROI, or a production recommendation.";

export const FALSE_POSITIVE_MEANING =
  "A false positive is a legitimate transaction sent to human review — it is not automatically declined.";

export type LaneAFinalTier = {
  capacityPerDay: number;
  reviewBudget: number;
  truePositives: number;
  falsePositives: number;
  falseNegatives: number;
  trueNegatives: number;
  precision: number;
  recall: number;
};

/** The five frozen capacity tiers. Order is fixed and must not change. */
export const LANE_A_FINAL_TIERS: readonly LaneAFinalTier[] = [
  {
    capacityPerDay: 100,
    reviewBudget: 3_077,
    truePositives: 838,
    falsePositives: 2_239,
    falseNegatives: 2_245,
    trueNegatives: 83_259,
    precision: 0.2723,
    recall: 0.2718,
  },
  {
    capacityPerDay: 250,
    reviewBudget: 7_694,
    truePositives: 1_409,
    falsePositives: 6_285,
    falseNegatives: 1_674,
    trueNegatives: 79_213,
    precision: 0.1831,
    recall: 0.457,
  },
  {
    capacityPerDay: 500,
    reviewBudget: 15_389,
    truePositives: 1_985,
    falsePositives: 13_404,
    falseNegatives: 1_098,
    trueNegatives: 72_094,
    precision: 0.129,
    recall: 0.6439,
  },
  {
    capacityPerDay: 1_000,
    reviewBudget: 30_778,
    truePositives: 2_472,
    falsePositives: 28_306,
    falseNegatives: 611,
    trueNegatives: 57_192,
    precision: 0.0803,
    recall: 0.8018,
  },
  {
    capacityPerDay: 2_000,
    reviewBudget: 61_556,
    truePositives: 2_893,
    falsePositives: 58_663,
    falseNegatives: 190,
    trueNegatives: 26_835,
    precision: 0.047,
    recall: 0.9384,
  },
] as const;
