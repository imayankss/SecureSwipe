"use client";

import { useMemo, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EvidenceLabel } from "@/components/EvidenceLabel";
import {
  DEFAULT_DISPLAY_CURRENCY,
  DISPLAY_CURRENCIES,
  formatIllustrativeUsd,
  fromIllustrativeUsd,
  toIllustrativeUsd,
  type DisplayCurrency,
} from "@/data/displayCurrency";
import { Section } from "@/components/Section";
import { dashboardData, formatInteger } from "@/data/metrics";

const scenario = dashboardData.illustrativeCostScenario;

type Assumptions = typeof scenario.assumptions;

function nonNegative(value: number) {
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

export function IllustrativeCostScenario() {
  const [assumptions, setAssumptions] = useState<Assumptions>(
    scenario.assumptions,
  );
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>(
    DEFAULT_DISPLAY_CURRENCY,
  );
  const confusion = scenario.confusion;
  const recoveryRate = Math.min(1, nonNegative(assumptions.recoveryRate));
  const costs = useMemo(() => {
    const review =
      confusion.reviewWorkload * nonNegative(assumptions.reviewCost);
    const falsePositive =
      confusion.falsePositives * nonNegative(assumptions.falsePositiveCost);
    const missedFraud =
      confusion.falseNegatives * nonNegative(assumptions.falseNegativeCost);
    const residualCaughtFraud =
      confusion.truePositives *
      nonNegative(assumptions.falseNegativeCost) *
      (1 - recoveryRate);
    return {
      review,
      falsePositive,
      missedFraud,
      residualCaughtFraud,
      total: review + falsePositive + missedFraud + residualCaughtFraud,
    };
  }, [assumptions, confusion, recoveryRate]);

  const updateAssumption = (key: keyof Assumptions, displayValue: number) => {
    setAssumptions((current) => ({
      ...current,
      [key]: toIllustrativeUsd(nonNegative(displayValue), displayCurrency),
    }));
  };

  return (
    <Section
      id="illustrative-cost"
      eyebrow="Scenario sandbox"
      title="Illustrative merchant cost & review workload"
      description={scenario.label}
    >
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>Observed-split cost arithmetic</CardTitle>
            <EvidenceLabel type="illustrative-cost-scenario" />
          </div>
          <CardDescription>
            Adjusting these visible inputs changes arithmetic only. It does not
            change the model, threshold, review policy, or any business
            decision.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col gap-3 rounded-lg border border-amber-200/20 bg-amber-300/[0.04] p-4 text-sm text-slate-300 sm:flex-row sm:items-end sm:justify-between">
            <label
              className="grid gap-2 font-medium text-slate-200"
              htmlFor="illustrative-display-currency"
            >
              Illustrative display currency
              <select
                id="illustrative-display-currency"
                aria-describedby="illustrative-currency-note"
                className="rounded-lg border border-white/15 bg-slate-950 px-3 py-2 text-white"
                value={displayCurrency}
                onChange={(event) =>
                  setDisplayCurrency(
                    event.currentTarget.value as DisplayCurrency,
                  )
                }
              >
                {DISPLAY_CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
            <p
              className="max-w-2xl text-xs leading-5 text-slate-400"
              id="illustrative-currency-note"
            >
              INR is the default. Fixed illustrative display conversion: 1 USD ={" "}
              {formatIllustrativeUsd(1, "INR")}. No live FX is fetched; this is
              not Razorpay economics and does not assign a currency to
              historical model or dataset amounts.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="fp-cost"
            >
              False-positive cost ({displayCurrency}; display only)
              <input
                id="fp-cost"
                aria-label="Illustrative false-positive cost"
                className="rounded-lg border border-white/15 bg-slate-950 px-3 py-2 text-white"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "falsePositiveCost",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeUsd(
                  assumptions.falsePositiveCost,
                  displayCurrency,
                )}
              />
            </label>
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="fn-cost"
            >
              False-negative cost ({displayCurrency}; display only)
              <input
                id="fn-cost"
                aria-label="Illustrative false-negative cost"
                className="rounded-lg border border-white/15 bg-slate-950 px-3 py-2 text-white"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "falseNegativeCost",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeUsd(
                  assumptions.falseNegativeCost,
                  displayCurrency,
                )}
              />
            </label>
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="review-cost"
            >
              Review cost per flagged row ({displayCurrency}; display only)
              <input
                id="review-cost"
                aria-label="Illustrative review cost"
                className="rounded-lg border border-white/15 bg-slate-950 px-3 py-2 text-white"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "reviewCost",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeUsd(
                  assumptions.reviewCost,
                  displayCurrency,
                )}
              />
            </label>
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="recovery-rate"
            >
              Fraud recovery rate (%)
              <input
                id="recovery-rate"
                aria-label="Illustrative fraud recovery rate"
                className="rounded-lg border border-white/15 bg-slate-950 px-3 py-2 text-white"
                max="100"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "recoveryRate",
                    nonNegative(event.currentTarget.valueAsNumber) / 100,
                  )
                }
                step="1"
                type="number"
                value={recoveryRate * 100}
              />
            </label>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4 text-sm leading-6 text-slate-300">
              <p className="font-semibold text-slate-100">Formula</p>
              <p className="mt-2 font-mono text-xs text-cyan-100">
                {scenario.formula}
              </p>
              <p className="mt-3">
                Display currency: {displayCurrency}. Arithmetic stays in its
                fixed illustrative USD reference basis; the selector changes
                display only and does not alter historical counts, thresholds,
                or model inputs.
              </p>
              <p>Time horizon: {scenario.timeHorizon}</p>
            </div>
            <div className="rounded-lg border border-amber-200/20 bg-amber-300/[0.06] p-4">
              <p className="text-sm font-semibold text-amber-100">
                {scenario.label}
              </p>
              <p
                className="mt-2 text-3xl font-semibold text-white"
                data-testid="illustrative-total"
              >
                {formatIllustrativeUsd(costs.total, displayCurrency)}
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Illustrative total for this observed split; not a savings claim
                or a threshold recommendation.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [
                "Review workload",
                `${formatInteger(confusion.truePositives)} TP + ${formatInteger(confusion.falsePositives)} FP = ${formatInteger(confusion.reviewWorkload)}`,
                costs.review,
              ],
              [
                "False-positive component",
                `${formatInteger(confusion.falsePositives)} FP`,
                costs.falsePositive,
              ],
              [
                "Missed-fraud component",
                `${formatInteger(confusion.falseNegatives)} FN`,
                costs.missedFraud,
              ],
              [
                "Residual caught-fraud component",
                `${formatInteger(confusion.truePositives)} TP × (1 − recovery)`,
                costs.residualCaughtFraud,
              ],
            ].map(([label, count, amount]) => (
              <div
                className="rounded-lg border border-white/10 bg-white/[0.03] p-4"
                key={label}
              >
                <p className="text-sm text-slate-300">{label}</p>
                <p className="mt-2 text-xs text-slate-400">{count}</p>
                <p className="mt-2 font-semibold text-slate-100">
                  {formatIllustrativeUsd(amount as number, displayCurrency)}
                </p>
              </div>
            ))}
          </div>
          <p className="text-xs leading-5 text-slate-400">
            Reconciliation: {formatInteger(confusion.truePositives)} TP +{" "}
            {formatInteger(confusion.falsePositives)} FP +{" "}
            {formatInteger(confusion.falseNegatives)} FN +{" "}
            {formatInteger(confusion.trueNegatives)} TN ={" "}
            {formatInteger(confusion.totalTransactions)} recorded transactions.
          </p>
        </CardContent>
      </Card>
    </Section>
  );
}
