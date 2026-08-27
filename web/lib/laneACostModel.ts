/**
 * Pure, deterministic illustrative cost model for the Lane A capacity frontier.
 *
 * Arithmetic on already-published aggregate counts only. There is no model, no
 * score, no threshold, no API call, no browser storage, no randomness, and no
 * dependency on the current time. The same inputs always produce the same
 * output.
 *
 * Deliberately absent: any notion of money saved, net benefit, recovery,
 * payback, or an optimal operating point. This tool computes scenario costs; it
 * does not choose anything.
 *
 * Contract: docs/evidence/MT5_COST_EXPLORER_CONTRACT.md
 */

import type { LaneAFinalTier } from "@/data/laneAFinalFrontier";

/** The four editable illustrative assumptions, all INR, all non-negative. */
export type CostAssumptions = {
  /** Cost of putting one transaction through human review. */
  reviewCostPerQueuedTransaction: number;
  /** Cost of friction imposed on a legitimate customer sent to review. */
  legitimateCustomerFrictionCostPerFalsePositive: number;
  /** Illustrative loss carried by one missed fraudulent transaction. */
  missedFraudLossPerFalseNegative: number;
  /** Illustrative handling cost of one chargeback from a missed fraud. */
  chargebackHandlingCostPerFalseNegative: number;
};

export type CostBreakdown = {
  capacityPerDay: number;
  reviewedCount: number;
  reviewWorkloadCost: number;
  legitimateFrictionCost: number;
  missedFraudAndChargebackCost: number;
  illustrativeTotalCost: number;
};

export type AssumptionKey = keyof CostAssumptions;

export type ValidationIssue = { field: AssumptionKey; message: string };

/**
 * Visible starting point for the explorer.
 *
 * These are illustrative starting assumptions. They are NOT default merchant
 * settings, recommended values, typical values, or benchmarks.
 */
export const ILLUSTRATIVE_STARTING_ASSUMPTIONS: CostAssumptions = {
  reviewCostPerQueuedTransaction: 25,
  legitimateCustomerFrictionCostPerFalsePositive: 40,
  missedFraudLossPerFalseNegative: 4_000,
  chargebackHandlingCostPerFalseNegative: 750,
};

export const ASSUMPTION_LABELS: Record<AssumptionKey, string> = {
  reviewCostPerQueuedTransaction: "Review cost per queued transaction",
  legitimateCustomerFrictionCostPerFalsePositive:
    "Legitimate-customer friction cost per false-positive review",
  missedFraudLossPerFalseNegative: "Missed-fraud loss per false negative",
  chargebackHandlingCostPerFalseNegative:
    "Chargeback-handling cost per false negative",
};

/** Upper guard so a pasted or fat-fingered figure cannot produce nonsense. */
export const MAX_ASSUMPTION_INR = 10_000_000;

/** Round to paise, then to whole INR only at display time. */
const toPaise = (value: number): number => Math.round(value * 100);
const fromPaise = (paise: number): number => paise / 100;

export function isValidAssumption(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= MAX_ASSUMPTION_INR
  );
}

/**
 * Parse raw user text into an assumption value.
 *
 * Blank, non-numeric, negative, non-finite and oversized input are all refused
 * rather than coerced, so no invalid entry can reach the arithmetic.
 */
export function parseAssumptionInput(
  raw: string,
): { ok: true; value: number } | { ok: false; message: string } {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, message: "Enter an amount in INR." };
  }
  if (!/^\d*\.?\d*$/.test(trimmed)) {
    return { ok: false, message: "Enter a non-negative number, digits only." };
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    return { ok: false, message: "Enter a finite amount." };
  }
  if (parsed < 0) {
    return { ok: false, message: "Amount cannot be negative." };
  }
  if (parsed > MAX_ASSUMPTION_INR) {
    return {
      ok: false,
      message: `Amount cannot exceed ${MAX_ASSUMPTION_INR.toLocaleString("en-IN")} INR.`,
    };
  }
  return { ok: true, value: parsed };
}

/** Every assumption that fails validation, in declaration order. */
export function validateAssumptions(
  assumptions: CostAssumptions,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  (Object.keys(ASSUMPTION_LABELS) as AssumptionKey[]).forEach((field) => {
    if (!isValidAssumption(assumptions[field])) {
      issues.push({
        field,
        message: `${ASSUMPTION_LABELS[field]} must be a finite amount between 0 and ${MAX_ASSUMPTION_INR.toLocaleString("en-IN")} INR.`,
      });
    }
  });
  return issues;
}

/**
 * Illustrative cost for one frozen capacity tier.
 *
 * Throws on invalid assumptions rather than returning a misleading number.
 */
export function costForTier(
  tier: LaneAFinalTier,
  assumptions: CostAssumptions,
): CostBreakdown {
  const issues = validateAssumptions(assumptions);
  if (issues.length > 0) {
    throw new Error(`Invalid illustrative assumptions: ${issues[0].message}`);
  }

  const reviewedCount = tier.truePositives + tier.falsePositives;
  const reviewPaise = reviewedCount * toPaise(assumptions.reviewCostPerQueuedTransaction);
  const frictionPaise =
    tier.falsePositives *
    toPaise(assumptions.legitimateCustomerFrictionCostPerFalsePositive);
  const missedPaise =
    tier.falseNegatives *
    (toPaise(assumptions.missedFraudLossPerFalseNegative) +
      toPaise(assumptions.chargebackHandlingCostPerFalseNegative));

  return {
    capacityPerDay: tier.capacityPerDay,
    reviewedCount,
    reviewWorkloadCost: fromPaise(reviewPaise),
    legitimateFrictionCost: fromPaise(frictionPaise),
    missedFraudAndChargebackCost: fromPaise(missedPaise),
    illustrativeTotalCost: fromPaise(reviewPaise + frictionPaise + missedPaise),
  };
}

/** Illustrative cost for every frozen tier, in fixed tier order. */
export function costForAllTiers(
  tiers: readonly LaneAFinalTier[],
  assumptions: CostAssumptions,
): CostBreakdown[] {
  return tiers.map((tier) => costForTier(tier, assumptions));
}

export type SensitivityScenario = {
  id: string;
  name: string;
  description: string;
  assumptions: CostAssumptions;
};

/**
 * Predeclared sensitivity scenarios, computed over the same five fixed tiers.
 *
 * Neither scenario is preferred, and neither crowns a tier.
 */
export function sensitivityScenarios(
  base: CostAssumptions,
): SensitivityScenario[] {
  return [
    {
      id: "higher-review-cost",
      name: "Higher review cost",
      description:
        "Review cost per queued transaction tripled; other assumptions unchanged.",
      assumptions: {
        ...base,
        reviewCostPerQueuedTransaction: Math.min(
          base.reviewCostPerQueuedTransaction * 3,
          MAX_ASSUMPTION_INR,
        ),
      },
    },
    {
      id: "higher-missed-fraud-loss",
      name: "Higher missed-fraud loss",
      description:
        "Missed-fraud loss per false negative tripled; other assumptions unchanged.",
      assumptions: {
        ...base,
        missedFraudLossPerFalseNegative: Math.min(
          base.missedFraudLossPerFalseNegative * 3,
          MAX_ASSUMPTION_INR,
        ),
      },
    },
  ];
}

/** Deterministic INR display. Same value always renders identically. */
export function formatInr(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-IN");
}

export function formatRate(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}
