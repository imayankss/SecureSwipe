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
  ILLUSTRATIVE_INR_PER_USD,
  formatIllustrativeInr,
  fromIllustrativeInr,
  toIllustrativeInr,
  type DisplayCurrency,
} from "@/data/displayCurrency";
import { Section } from "@/components/Section";
import { useCommandDisplayCurrency } from "@/components/dashboard/DisplayCurrencyContext";
import { CostBreakdownChart } from "@/components/dashboard/CostBreakdownChart";
import { dashboardData, formatInteger, formatPercent } from "@/data/metrics";

const scenario = dashboardData.illustrativeCostScenario;

type Assumptions = typeof scenario.assumptions;

function nonNegative(value: number) {
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

export function IllustrativeCostScenario() {
  const commandCurrency = useCommandDisplayCurrency();
  const [assumptions, setAssumptions] = useState<Assumptions>(
    scenario.assumptions,
  );
  const [localDisplayCurrency, setLocalDisplayCurrency] = useState<DisplayCurrency>(
    DEFAULT_DISPLAY_CURRENCY,
  );
  const displayCurrency = commandCurrency?.displayCurrency ?? localDisplayCurrency;
  const setDisplayCurrency = commandCurrency?.setDisplayCurrency ?? setLocalDisplayCurrency;
  const confusion = scenario.confusion;
  const locked = dashboardData.finalEvaluation;
  const costs = useMemo(() => {
    const review =
      confusion.reviewWorkload * nonNegative(assumptions.reviewCost);
    const legitimateCustomerFriction =
      confusion.falsePositives *
      nonNegative(assumptions.legitimateCustomerFriction);
    const missedFraud =
      confusion.falseNegatives * nonNegative(assumptions.missedFraudLoss);
    const chargebackHandling =
      confusion.truePositives *
      nonNegative(assumptions.chargebackHandling);
    return {
      review,
      legitimateCustomerFriction,
      missedFraud,
      chargebackHandling,
      total:
        review +
        legitimateCustomerFriction +
        missedFraud +
        chargebackHandling,
    };
  }, [assumptions, confusion]);

  const updateAssumption = (key: keyof Assumptions, displayValue: number) => {
    setAssumptions((current) => ({
      ...current,
      [key]: toIllustrativeInr(nonNegative(displayValue), displayCurrency),
    }));
  };

  return (
    <Section
      id="illustrative-cost"
      eyebrow="Scenario sandbox"
      title="Illustrative merchant cost & review workload"
      description={scenario.label}
    >
      <Card className="border-amber-200/20">
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
          {!commandCurrency ? <div className="flex flex-col gap-3 rounded-xl border border-amber-200/20 bg-amber-300/[0.04] p-4 text-sm text-slate-300 sm:flex-row sm:items-end sm:justify-between">
            <label
              className="grid gap-2 font-medium text-slate-200"
              htmlFor="illustrative-display-currency"
            >
              Illustrative display currency
              <select
                id="illustrative-display-currency"
                aria-describedby="illustrative-currency-note"
                className="rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-white shadow-inner shadow-black/20"
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
              All four editable assumptions use an illustrative INR basis. Fixed
              display-only conversion: ₹{ILLUSTRATIVE_INR_PER_USD.toFixed(2)} =
              $1.00. No live FX is fetched, and no currency is assigned to the
              historical model or dataset amounts.
            </p>
          </div> : null}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="review-cost"
            >
              Review cost per flagged row ({displayCurrency}; illustrative INR basis)
              <input
                id="review-cost"
                aria-label="Illustrative review cost"
                className="rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-white shadow-inner shadow-black/20"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "reviewCost",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeInr(
                  assumptions.reviewCost,
                  displayCurrency,
                )}
              />
            </label>
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="legitimate-customer-friction"
            >
              Legitimate-customer friction per false positive ({displayCurrency}; illustrative INR basis)
              <input
                id="legitimate-customer-friction"
                aria-label="Illustrative legitimate-customer friction"
                className="rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-white shadow-inner shadow-black/20"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "legitimateCustomerFriction",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeInr(
                  assumptions.legitimateCustomerFriction,
                  displayCurrency,
                )}
              />
            </label>
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="missed-fraud-loss"
            >
              Missed-fraud loss per false negative ({displayCurrency}; illustrative INR basis)
              <input
                id="missed-fraud-loss"
                aria-label="Illustrative missed-fraud loss"
                className="rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-white shadow-inner shadow-black/20"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "missedFraudLoss",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeInr(
                  assumptions.missedFraudLoss,
                  displayCurrency,
                )}
              />
            </label>
            <label
              className="grid gap-2 text-sm font-medium text-slate-200"
              htmlFor="chargeback-handling"
            >
              Chargeback handling per caught fraud ({displayCurrency}; illustrative INR basis)
              <input
                id="chargeback-handling"
                aria-label="Illustrative chargeback handling"
                className="rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-white shadow-inner shadow-black/20"
                min="0"
                onChange={(event) =>
                  updateAssumption(
                    "chargebackHandling",
                    nonNegative(event.currentTarget.valueAsNumber),
                  )
                }
                step="0.01"
                type="number"
                value={fromIllustrativeInr(
                  assumptions.chargebackHandling,
                  displayCurrency,
                )}
              />
            </label>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-xl border border-white/10 bg-slate-950/55 p-4 text-sm leading-6 text-slate-300">
              <p className="font-semibold text-slate-100">Formula</p>
              <p className="mt-2 font-mono text-xs text-teal-100">
                {scenario.formula}
              </p>
              <p className="mt-3">
                Display currency: {displayCurrency}. Arithmetic stays in its
                canonical illustrative INR basis; the selector changes
                display only and does not alter historical counts, thresholds,
                or model inputs.
              </p>
              <p>Time horizon: {scenario.timeHorizon}</p>
            </div>
            <div className="rounded-xl border border-amber-200/20 bg-amber-300/[0.06] p-4">
              <p className="text-sm font-semibold text-amber-100">
                {scenario.label}
              </p>
              <p
                className="ss-number mt-2 text-3xl font-semibold text-white"
                data-testid="illustrative-total"
              >
                {formatIllustrativeInr(costs.total, displayCurrency)}
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Illustrative total for this observed split; not a savings claim
                or a threshold recommendation.
              </p>
            </div>
          </div>

          <div
            aria-label="Locked historical cost fixture"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            {[
              ["Threshold", locked.threshold.toFixed(2)],
              ["Precision", formatPercent(locked.precision)],
              ["Recall", formatPercent(locked.recall)],
              ["Review volume", formatInteger(confusion.reviewWorkload)],
              ["True positives", formatInteger(confusion.truePositives)],
              ["False positives", formatInteger(confusion.falsePositives)],
              ["False negatives", formatInteger(confusion.falseNegatives)],
              ["True negatives", formatInteger(confusion.trueNegatives)],
            ].map(([label, value]) => (
              <div
                className="rounded-xl border border-white/10 bg-white/[0.03] p-4"
                key={label}
              >
                <p className="text-xs text-slate-400">{label}</p>
                <p className="ss-number mt-2 text-lg font-semibold text-white">
                  {value}
                </p>
              </div>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [
                "Review workload",
                `${formatInteger(confusion.truePositives)} TP + ${formatInteger(confusion.falsePositives)} FP = ${formatInteger(confusion.reviewWorkload)}`,
                costs.review,
              ],
              [
                "Legitimate-customer friction",
                `${formatInteger(confusion.falsePositives)} FP`,
                costs.legitimateCustomerFriction,
              ],
              [
                "Missed-fraud component",
                `${formatInteger(confusion.falseNegatives)} FN`,
                costs.missedFraud,
              ],
              [
                "Chargeback handling",
                `${formatInteger(confusion.truePositives)} TP`,
                costs.chargebackHandling,
              ],
            ].map(([label, count, amount]) => (
              <div
                className="rounded-xl border border-white/10 bg-white/[0.03] p-4"
                key={label}
              >
                <p className="text-sm text-slate-300">{label}</p>
                <p className="mt-2 text-xs text-slate-400">{count}</p>
                <p className="ss-number mt-2 font-semibold text-slate-100">
                  {formatIllustrativeInr(amount as number, displayCurrency)}
                </p>
              </div>
            ))}
          </div>
          <CostBreakdownChart
            total={costs.total}
            items={[
              { label: "Review workload", value: costs.review, tone: "bg-teal-300" },
              { label: "Legitimate-customer friction", value: costs.legitimateCustomerFriction, tone: "bg-amber-200" },
              { label: "Missed-fraud component", value: costs.missedFraud, tone: "bg-rose-300" },
              { label: "Chargeback handling", value: costs.chargebackHandling, tone: "bg-violet-300" },
            ]}
          />
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
