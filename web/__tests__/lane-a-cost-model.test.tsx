import { describe, expect, it } from "vitest";

import { LANE_A_FINAL_TIERS } from "@/data/laneAFinalFrontier";
import {
  ILLUSTRATIVE_STARTING_ASSUMPTIONS,
  MAX_ASSUMPTION_INR,
  type CostAssumptions,
  costForAllTiers,
  costForTier,
  formatCount,
  formatInr,
  formatRate,
  isValidAssumption,
  parseAssumptionInput,
  sensitivityScenarios,
  validateAssumptions,
} from "@/lib/laneACostModel";

/** The authoritative sealed counts, restated independently of the module. */
const FROZEN = [
  { capacityPerDay: 100, reviewBudget: 3077, tp: 838, fp: 2239, fn: 2245, tn: 83259, precision: 0.2723, recall: 0.2718 },
  { capacityPerDay: 250, reviewBudget: 7694, tp: 1409, fp: 6285, fn: 1674, tn: 79213, precision: 0.1831, recall: 0.457 },
  { capacityPerDay: 500, reviewBudget: 15389, tp: 1985, fp: 13404, fn: 1098, tn: 72094, precision: 0.129, recall: 0.6439 },
  { capacityPerDay: 1000, reviewBudget: 30778, tp: 2472, fp: 28306, fn: 611, tn: 57192, precision: 0.0803, recall: 0.8018 },
  { capacityPerDay: 2000, reviewBudget: 61556, tp: 2893, fp: 58663, fn: 190, tn: 26835, precision: 0.047, recall: 0.9384 },
];

const ZERO: CostAssumptions = {
  reviewCostPerQueuedTransaction: 0,
  legitimateCustomerFrictionCostPerFalsePositive: 0,
  missedFraudLossPerFalseNegative: 0,
  chargebackHandlingCostPerFalseNegative: 0,
};

describe("frozen five-tier frontier", () => {
  it("preserves every sealed count exactly", () => {
    expect(LANE_A_FINAL_TIERS).toHaveLength(5);
    LANE_A_FINAL_TIERS.forEach((tier, index) => {
      const expected = FROZEN[index];
      expect(tier.capacityPerDay).toBe(expected.capacityPerDay);
      expect(tier.reviewBudget).toBe(expected.reviewBudget);
      expect(tier.truePositives).toBe(expected.tp);
      expect(tier.falsePositives).toBe(expected.fp);
      expect(tier.falseNegatives).toBe(expected.fn);
      expect(tier.trueNegatives).toBe(expected.tn);
      expect(tier.precision).toBeCloseTo(expected.precision, 4);
      expect(tier.recall).toBeCloseTo(expected.recall, 4);
    });
  });

  it("reconciles against the sealed dataset totals", () => {
    LANE_A_FINAL_TIERS.forEach((tier) => {
      expect(tier.truePositives + tier.falseNegatives).toBe(3083);
      expect(tier.trueNegatives + tier.falsePositives).toBe(85498);
      expect(
        tier.truePositives + tier.falsePositives + tier.falseNegatives + tier.trueNegatives,
      ).toBe(88581);
      expect(tier.truePositives + tier.falsePositives).toBeLessThanOrEqual(tier.reviewBudget);
    });
  });

  it("orders tiers so review workload rises and missed fraud falls", () => {
    for (let i = 1; i < LANE_A_FINAL_TIERS.length; i += 1) {
      expect(LANE_A_FINAL_TIERS[i].falsePositives).toBeGreaterThan(
        LANE_A_FINAL_TIERS[i - 1].falsePositives,
      );
      expect(LANE_A_FINAL_TIERS[i].falseNegatives).toBeLessThan(
        LANE_A_FINAL_TIERS[i - 1].falseNegatives,
      );
    }
  });
});

describe("formula arithmetic", () => {
  it("reconciles component by component for every tier", () => {
    const a = ILLUSTRATIVE_STARTING_ASSUMPTIONS;
    LANE_A_FINAL_TIERS.forEach((tier) => {
      const got = costForTier(tier, a);
      const reviewed = tier.truePositives + tier.falsePositives;
      expect(got.reviewedCount).toBe(reviewed);
      expect(got.reviewWorkloadCost).toBeCloseTo(reviewed * a.reviewCostPerQueuedTransaction, 2);
      expect(got.legitimateFrictionCost).toBeCloseTo(
        tier.falsePositives * a.legitimateCustomerFrictionCostPerFalsePositive, 2);
      expect(got.missedFraudAndChargebackCost).toBeCloseTo(
        tier.falseNegatives *
          (a.missedFraudLossPerFalseNegative + a.chargebackHandlingCostPerFalseNegative), 2);
      expect(got.illustrativeTotalCost).toBeCloseTo(
        got.reviewWorkloadCost + got.legitimateFrictionCost + got.missedFraudAndChargebackCost, 2);
    });
  });

  it("returns a cost for each tier in fixed order", () => {
    const all = costForAllTiers(LANE_A_FINAL_TIERS, ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    expect(all.map((row) => row.capacityPerDay)).toEqual([100, 250, 500, 1000, 2000]);
  });

  it("yields zero total when every assumption is zero", () => {
    costForAllTiers(LANE_A_FINAL_TIERS, ZERO).forEach((row) => {
      expect(row.reviewWorkloadCost).toBe(0);
      expect(row.legitimateFrictionCost).toBe(0);
      expect(row.missedFraudAndChargebackCost).toBe(0);
      expect(row.illustrativeTotalCost).toBe(0);
    });
  });

  it("is deterministic across repeated evaluation", () => {
    const first = costForAllTiers(LANE_A_FINAL_TIERS, ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    const second = costForAllTiers(LANE_A_FINAL_TIERS, ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    expect(second).toEqual(first);
  });

  it("keeps paise precision internally", () => {
    const tier = LANE_A_FINAL_TIERS[0];
    const got = costForTier(tier, { ...ZERO, reviewCostPerQueuedTransaction: 0.01 });
    expect(got.reviewWorkloadCost).toBeCloseTo((tier.truePositives + tier.falsePositives) * 0.01, 2);
  });
});

describe("sensitivity isolation", () => {
  it("higher FP friction changes only the friction term and the total", () => {
    const base = ILLUSTRATIVE_STARTING_ASSUMPTIONS;
    const raised: CostAssumptions = {
      ...base,
      legitimateCustomerFrictionCostPerFalsePositive:
        base.legitimateCustomerFrictionCostPerFalsePositive * 10,
    };
    LANE_A_FINAL_TIERS.forEach((tier) => {
      const before = costForTier(tier, base);
      const after = costForTier(tier, raised);
      expect(after.reviewWorkloadCost).toBe(before.reviewWorkloadCost);
      expect(after.missedFraudAndChargebackCost).toBe(before.missedFraudAndChargebackCost);
      expect(after.legitimateFrictionCost).toBeGreaterThan(before.legitimateFrictionCost);
      expect(after.illustrativeTotalCost).toBeGreaterThan(before.illustrativeTotalCost);
    });
  });

  it("higher FN loss changes only the missed-fraud term and the total", () => {
    const base = ILLUSTRATIVE_STARTING_ASSUMPTIONS;
    const raised: CostAssumptions = {
      ...base,
      missedFraudLossPerFalseNegative: base.missedFraudLossPerFalseNegative * 10,
    };
    LANE_A_FINAL_TIERS.forEach((tier) => {
      const before = costForTier(tier, base);
      const after = costForTier(tier, raised);
      expect(after.reviewWorkloadCost).toBe(before.reviewWorkloadCost);
      expect(after.legitimateFrictionCost).toBe(before.legitimateFrictionCost);
      expect(after.missedFraudAndChargebackCost).toBeGreaterThan(
        before.missedFraudAndChargebackCost);
      expect(after.illustrativeTotalCost).toBeGreaterThan(before.illustrativeTotalCost);
    });
  });

  it("publishes two predeclared scenarios that vary one assumption each", () => {
    const scenarios = sensitivityScenarios(ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    expect(scenarios.map((s) => s.id)).toEqual([
      "higher-review-cost",
      "higher-missed-fraud-loss",
    ]);
    expect(scenarios[0].assumptions.reviewCostPerQueuedTransaction).toBe(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.reviewCostPerQueuedTransaction * 3);
    expect(scenarios[0].assumptions.missedFraudLossPerFalseNegative).toBe(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.missedFraudLossPerFalseNegative);
    expect(scenarios[1].assumptions.missedFraudLossPerFalseNegative).toBe(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.missedFraudLossPerFalseNegative * 3);
  });

  it("never exceeds the guard rail when tripling", () => {
    const near: CostAssumptions = {
      ...ILLUSTRATIVE_STARTING_ASSUMPTIONS,
      missedFraudLossPerFalseNegative: MAX_ASSUMPTION_INR,
    };
    sensitivityScenarios(near).forEach((scenario) => {
      expect(scenario.assumptions.missedFraudLossPerFalseNegative)
        .toBeLessThanOrEqual(MAX_ASSUMPTION_INR);
    });
  });
});

describe("input safety", () => {
  it.each(["", "  ", "abc", "-5", "1e9999", "12.3.4", "٣", "NaN", "Infinity"])(
    "refuses invalid input %j", (raw) => {
      expect(parseAssumptionInput(raw).ok).toBe(false);
    });

  it("refuses amounts above the guard rail", () => {
    const result = parseAssumptionInput(String(MAX_ASSUMPTION_INR + 1));
    expect(result.ok).toBe(false);
  });

  it("accepts valid non-negative amounts including zero", () => {
    ["0", "25", "1234.56", String(MAX_ASSUMPTION_INR)].forEach((raw) => {
      const result = parseAssumptionInput(raw);
      expect(result.ok).toBe(true);
    });
  });

  it.each([NaN, Infinity, -Infinity, -1, "25" as unknown as number, null, undefined])(
    "isValidAssumption rejects %p", (value) => {
      expect(isValidAssumption(value)).toBe(false);
    });

  it("reports every invalid assumption field", () => {
    const issues = validateAssumptions({
      reviewCostPerQueuedTransaction: NaN,
      legitimateCustomerFrictionCostPerFalsePositive: -1,
      missedFraudLossPerFalseNegative: Infinity,
      chargebackHandlingCostPerFalseNegative: MAX_ASSUMPTION_INR + 1,
    });
    expect(issues).toHaveLength(4);
  });

  it("throws rather than returning a misleading number", () => {
    expect(() =>
      costForTier(LANE_A_FINAL_TIERS[0], { ...ZERO, reviewCostPerQueuedTransaction: NaN }),
    ).toThrow(/Invalid illustrative assumptions/);
  });

  it("never produces NaN, Infinity, or a negative cost from valid input", () => {
    const all = costForAllTiers(LANE_A_FINAL_TIERS, {
      reviewCostPerQueuedTransaction: MAX_ASSUMPTION_INR,
      legitimateCustomerFrictionCostPerFalsePositive: MAX_ASSUMPTION_INR,
      missedFraudLossPerFalseNegative: MAX_ASSUMPTION_INR,
      chargebackHandlingCostPerFalseNegative: MAX_ASSUMPTION_INR,
    });
    all.forEach((row) => {
      Object.values(row).forEach((value) => {
        expect(Number.isFinite(value)).toBe(true);
        expect(value).toBeGreaterThanOrEqual(0);
      });
    });
  });
});

describe("deterministic formatting", () => {
  it("formats INR consistently", () => {
    expect(formatInr(0)).toBe("₹0");
    expect(formatInr(1234.4)).toBe(formatInr(1234.4));
    expect(formatInr(1234.6)).toBe(formatInr(1235));
    expect(formatInr(Number.NaN)).toBe("—");
    expect(formatInr(Infinity)).toBe("—");
  });

  it("formats counts and rates deterministically", () => {
    expect(formatCount(88581)).toBe(formatCount(88581));
    expect(formatRate(0.2718)).toBe("27.18%");
    expect(formatRate(0.8018)).toBe("80.18%");
  });
});
