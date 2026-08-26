/**
 * Lane A (IEEE-CIS) capacity-frontier development evidence.
 *
 * AGGREGATE VALUES ONLY. No rows, identifiers, email domains, device strings,
 * amounts, labels, scores, or private paths appear here.
 *
 * These figures come from the `validation_threshold` role of the frozen Lane A
 * chronological partition. They are DEVELOPMENT evidence: the final evaluation
 * has not been run. They must never be compared with Lane B historical metrics,
 * which come from a different corpus, base rate, label definition and feature
 * space.
 *
 * Generated from the Lane A v2 development run; see
 * docs/evidence/LANE_A_V2_FREEZE.md for the full provenance chain.
 */

export const LANE_A_ILLUSTRATIVE_LABEL =
  "Illustrative development scenario \u2014 not Razorpay economics, not a production SLO, and not a universal merchant policy.";

export type LaneACapacityTier = {
  capacityPerDay: number;
  reviewBudget: number;
  alertsSelected: number;
  averageReviewsPerDay: number;
  alertRate: number;
  truePositives: number;
  falsePositives: number;
  falseNegatives: number;
  trueNegatives: number;
  precision: number;
  recall: number;
  precisionCiLow: number;
  precisionCiHigh: number;
  recallCiLow: number;
  recallCiHigh: number;
  capacityUtilisation: number;
  reachesRecall80: boolean;
};

export const LANE_A_EVALUATION = {
  role: "validation_threshold",
  population: 70865,
  positives: 2668,
  evaluationPeriodDays: 22.1988,
  selectedVariant: "E \u2014 full_candidate_snapshot",
  modelInputs: 24,
  scoreTerminology: "calibrated probability",
  calibration: "platt",
} as const;

export const LANE_A_CAPACITY_TIERS: LaneACapacityTier[] = [
  {
    capacityPerDay: 100,
    reviewBudget: 2219,
    alertsSelected: 2219,
    averageReviewsPerDay: 100.0,
    alertRate: 0.031313,
    truePositives: 783,
    falsePositives: 1436,
    falseNegatives: 1885,
    trueNegatives: 66761,
    precision: 0.352862,
    recall: 0.293478,
    precisionCiLow: 0.333249,
    precisionCiHigh: 0.372983,
    recallCiLow: 0.276507,
    recallCiHigh: 0.311044,
    capacityUtilisation: 1.000000,
    reachesRecall80: false,
  },
  {
    capacityPerDay: 250,
    reviewBudget: 5549,
    alertsSelected: 5549,
    averageReviewsPerDay: 250.0,
    alertRate: 0.078304,
    truePositives: 1295,
    falsePositives: 4254,
    falseNegatives: 1373,
    trueNegatives: 63943,
    precision: 0.233375,
    recall: 0.485382,
    precisionCiLow: 0.222433,
    precisionCiHigh: 0.244687,
    recallCiLow: 0.466453,
    recallCiHigh: 0.504354,
    capacityUtilisation: 1.000000,
    reachesRecall80: false,
  },
  {
    capacityPerDay: 500,
    reviewBudget: 11099,
    alertsSelected: 11099,
    averageReviewsPerDay: 500.0,
    alertRate: 0.156622,
    truePositives: 1751,
    falsePositives: 9348,
    falseNegatives: 917,
    trueNegatives: 58849,
    precision: 0.157762,
    recall: 0.656297,
    precisionCiLow: 0.151099,
    precisionCiHigh: 0.164662,
    recallCiLow: 0.638062,
    recallCiHigh: 0.674082,
    capacityUtilisation: 1.000000,
    reachesRecall80: false,
  },
  {
    capacityPerDay: 1000,
    reviewBudget: 22198,
    alertsSelected: 22198,
    averageReviewsPerDay: 1000.0,
    alertRate: 0.313243,
    truePositives: 2165,
    falsePositives: 20033,
    falseNegatives: 503,
    trueNegatives: 48164,
    precision: 0.097531,
    recall: 0.811469,
    precisionCiLow: 0.093698,
    precisionCiHigh: 0.101504,
    recallCiLow: 0.796184,
    recallCiHigh: 0.825859,
    capacityUtilisation: 1.000000,
    reachesRecall80: true,
  },
  {
    capacityPerDay: 2000,
    reviewBudget: 44397,
    alertsSelected: 44397,
    averageReviewsPerDay: 2000.0,
    alertRate: 0.626501,
    truePositives: 2503,
    falsePositives: 41894,
    falseNegatives: 165,
    trueNegatives: 26303,
    precision: 0.056378,
    recall: 0.938156,
    precisionCiLow: 0.054270,
    precisionCiHigh: 0.058562,
    recallCiLow: 0.928371,
    recallCiHigh: 0.946681,
    capacityUtilisation: 1.000000,
    reachesRecall80: true,
  },
];

/**
 * Minimum validation workload reaching recall >= 0.80. This is a DERIVED
 * COVERAGE REFERENCE only. It is not a merchant capacity, not a recommended
 * default, and is deliberately not adopted as a policy setting.
 */
export const LANE_A_RECALL80_REFERENCE = {
  minimumReviews: 21420,
  impliedReviewsPerDay: 965,
  achievedRecall: 0.800225,
  achievedPrecision: 0.099673,
} as const;
