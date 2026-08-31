"use client";

import { useMemo, useState } from "react";

import {
  FALSE_POSITIVE_MEANING,
  LANE_A_FINAL_CATEGORY,
  LANE_A_FINAL_EVIDENCE,
  LANE_A_FINAL_ILLUSTRATIVE_LABEL,
  LANE_A_FINAL_METRICS,
  LANE_A_FINAL_TIERS,
} from "@/data/laneAFinalFrontier";
import {
  ASSUMPTION_LABELS,
  ILLUSTRATIVE_STARTING_ASSUMPTIONS,
  MAX_ASSUMPTION_INR,
  type AssumptionKey,
  type CostAssumptions,
  costForAllTiers,
  costForTier,
  formatCount,
  formatInr,
  formatRate,
  parseAssumptionInput,
  sensitivityScenarios,
} from "@/lib/laneACostModel";

const ASSUMPTION_ORDER: AssumptionKey[] = [
  "reviewCostPerQueuedTransaction",
  "legitimateCustomerFrictionCostPerFalsePositive",
  "missedFraudLossPerFalseNegative",
  "chargebackHandlingCostPerFalseNegative",
];

const ASSUMPTION_HELP: Record<AssumptionKey, string> = {
  reviewCostPerQueuedTransaction:
    "Illustrative cost of putting one transaction in front of a human reviewer.",
  legitimateCustomerFrictionCostPerFalsePositive:
    "Illustrative cost of the friction a legitimate customer experiences when their transaction is sent to review.",
  missedFraudLossPerFalseNegative:
    "Illustrative loss carried when one fraudulent transaction is not reviewed.",
  chargebackHandlingCostPerFalseNegative:
    "Illustrative operational cost of handling the chargeback from one missed fraud.",
};

export type LaneACostExplorerVariant = "detailed" | "compact";

export type LaneACostExplorerProps = {
  /**
   * `detailed` (default) is the complete evidence-route panel. `compact` is the
   * product-facing homepage surface: the same data, selector, assumptions and
   * arithmetic, without the badge row, sealed-metric interval block, all-tier
   * comparison table, sensitivity scenarios, or long provenance footnotes.
   *
   * Both variants read the same frozen module and the same pure cost model, so
   * no calculation, selector, or source datum is duplicated between routes.
   */
  variant?: LaneACostExplorerVariant;
  /**
   * Namespace for element ids so the compact and detailed panels can coexist
   * without colliding label/`aria-describedby` targets.
   */
  idPrefix?: string;
};

/**
 * Illustrative merchant cost and review-workload explorer for Lane A.
 *
 * Static and client-side: no network request, no API call, no fraud scoring, no
 * browser storage, no randomness, no dependency on the current time. It reads
 * the sealed five-tier aggregate frontier and does arithmetic on it.
 *
 * It selects no capacity and no threshold, and it declares no tier better than
 * another. Every monetary figure is an editable illustrative assumption.
 */
export function LaneACostExplorer({
  variant = "detailed",
  idPrefix = "",
}: LaneACostExplorerProps = {}) {
  const detailed = variant === "detailed";
  const fieldId = (key: AssumptionKey) => `${idPrefix}${key}`;
  const [selectedCapacity, setSelectedCapacity] = useState<number>(
    LANE_A_FINAL_TIERS[0].capacityPerDay,
  );
  const [rawInputs, setRawInputs] = useState<Record<AssumptionKey, string>>(() => ({
    reviewCostPerQueuedTransaction: String(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.reviewCostPerQueuedTransaction,
    ),
    legitimateCustomerFrictionCostPerFalsePositive: String(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.legitimateCustomerFrictionCostPerFalsePositive,
    ),
    missedFraudLossPerFalseNegative: String(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.missedFraudLossPerFalseNegative,
    ),
    chargebackHandlingCostPerFalseNegative: String(
      ILLUSTRATIVE_STARTING_ASSUMPTIONS.chargebackHandlingCostPerFalseNegative,
    ),
  }));

  const parsed = useMemo(() => {
    const values: Partial<CostAssumptions> = {};
    const errors: Partial<Record<AssumptionKey, string>> = {};
    ASSUMPTION_ORDER.forEach((key) => {
      const result = parseAssumptionInput(rawInputs[key]);
      if (result.ok) {
        values[key] = result.value;
      } else {
        errors[key] = result.message;
      }
    });
    return { values, errors, valid: Object.keys(errors).length === 0 };
  }, [rawInputs]);

  const assumptions = parsed.valid ? (parsed.values as CostAssumptions) : null;

  const tier =
    LANE_A_FINAL_TIERS.find((row) => row.capacityPerDay === selectedCapacity) ??
    LANE_A_FINAL_TIERS[0];

  const breakdown = useMemo(
    () => (assumptions ? costForTier(tier, assumptions) : null),
    [tier, assumptions],
  );
  const allTiers = useMemo(
    () => (assumptions ? costForAllTiers(LANE_A_FINAL_TIERS, assumptions) : null),
    [assumptions],
  );
  const scenarios = useMemo(
    () =>
      assumptions
        ? sensitivityScenarios(assumptions).map((scenario) => ({
            ...scenario,
            costs: costForAllTiers(LANE_A_FINAL_TIERS, scenario.assumptions),
          }))
        : null,
    [assumptions],
  );

  return (
    <section
      id={detailed ? "lane-a-cost-explorer" : `${idPrefix}lane-a-cost-explorer`}
      aria-labelledby={`${idPrefix}lane-a-cost-heading`}
      className={
        detailed
          ? "mt-9 rounded-xl border border-slate-700/60 bg-slate-950/40 p-5 sm:p-6"
          : "rounded-xl border border-white/[0.08] bg-slate-950/40 p-4 sm:p-6"
      }
    >
      <header className="flex flex-col gap-3">
        <h3
          id={`${idPrefix}lane-a-cost-heading`}
          className="text-lg font-semibold text-slate-100"
        >
          Illustrative merchant cost &amp; review workload
        </h3>
        <p
          data-testid="cost-explorer-disclosure"
          className="rounded-lg border border-amber-300/30 bg-amber-300/10 p-3 text-sm font-medium text-amber-100"
        >
          {LANE_A_FINAL_ILLUSTRATIVE_LABEL}
        </p>
        <p className="text-sm leading-relaxed text-slate-300">
          More review capacity catches more fraud, and it also sends more legitimate
          transactions to human review. {FALSE_POSITIVE_MEANING}
        </p>
      </header>

      {detailed ? (
      <section
        aria-labelledby="lane-a-sealed-heading"
        data-testid="sealed-final-metrics"
        className="mt-5 rounded-lg border border-emerald-300/30 bg-emerald-300/5 p-3 sm:p-4"
      >
        <h4
          id="lane-a-sealed-heading"
          className="text-xs font-semibold uppercase tracking-wide text-emerald-100"
        >
          {LANE_A_FINAL_CATEGORY}
        </h4>
        <p className="mt-1 text-xs text-slate-400">
          Evaluated exactly once on a programmatically held-out role. Not Razorpay or
          live-merchant performance, and not comparable with Lane B.
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            {
              term: "Average precision",
              value: LANE_A_FINAL_METRICS.averagePrecision.toFixed(6),
              detail: `95% CI ${LANE_A_FINAL_METRICS.averagePrecisionCiLow.toFixed(6)}–${LANE_A_FINAL_METRICS.averagePrecisionCiHigh.toFixed(6)}`,
            },
            {
              term: "ROC-AUC",
              value: LANE_A_FINAL_METRICS.rocAuc.toFixed(6),
              detail: `95% CI ${LANE_A_FINAL_METRICS.rocAucCiLow.toFixed(6)}–${LANE_A_FINAL_METRICS.rocAucCiHigh.toFixed(6)}`,
            },
            {
              term: "Brier score",
              value: LANE_A_FINAL_METRICS.brierScore.toFixed(6),
              detail: `log loss ${LANE_A_FINAL_METRICS.logLoss.toFixed(6)}`,
            },
            {
              term: "Prevalence",
              value: formatRate(LANE_A_FINAL_EVIDENCE.prevalence, 3),
              detail: `${formatCount(LANE_A_FINAL_EVIDENCE.positives)} of ${formatCount(LANE_A_FINAL_EVIDENCE.rows)} rows`,
            },
          ].map((item) => (
            <div key={item.term} className="min-w-0">
              <dt className="break-words text-xs uppercase tracking-wide text-slate-400">{item.term}</dt>
              <dd className="mt-1 break-words text-base font-semibold text-slate-50">
                {item.value}
              </dd>
              <dd className="mt-0.5 break-words text-xs text-slate-400">{item.detail}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-xs text-slate-400">
          At 1,000 reviews/day this model reaches{" "}
          <span className="font-medium text-slate-200">80.18% recall</span> at{" "}
          <span className="font-medium text-slate-200">8.03% alert precision</span> —
          catching about four fraudulent transactions in five, while sending 28,306
          legitimate transactions to human review. That trade-off is the point of the
          explorer below.
        </p>
      </section>
      ) : (
        <p
          data-testid="sealed-final-provenance"
          className="mt-4 rounded-lg border border-emerald-300/25 bg-emerald-300/[0.06] p-3 text-xs leading-5 text-emerald-50"
        >
          {LANE_A_FINAL_CATEGORY} — evaluated exactly once on a programmatically
          held-out role. Not Razorpay or live-merchant performance, and not
          comparable with Lane B historical metrics.
        </p>
      )}

      <fieldset
        className={
          detailed
            ? "mt-5 rounded-lg border border-slate-700/60 p-3 sm:p-4"
            : "mt-4 rounded-lg border border-slate-700/60 p-3 sm:p-4"
        }
      >
        <legend className="px-1 text-sm font-medium text-slate-200">
          Illustrative starting assumptions (INR, editable)
        </legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {ASSUMPTION_ORDER.map((key) => {
            const error = parsed.errors[key];
            const id = fieldId(key);
            const describedBy = `${id}-help${error ? ` ${id}-error` : ""}`;
            return (
              <div key={key} className="flex flex-col gap-1">
                <label htmlFor={id} className="text-xs font-medium text-slate-200">
                  {ASSUMPTION_LABELS[key]} (₹)
                </label>
                <input
                  id={id}
                  name={key}
                  type="text"
                  inputMode="decimal"
                  value={rawInputs[key]}
                  aria-describedby={describedBy}
                  aria-invalid={error ? true : undefined}
                  onChange={(event) =>
                    setRawInputs((current) => ({ ...current, [key]: event.target.value }))
                  }
                  className="w-full rounded-lg border border-[var(--ss-border)] bg-[#0a111c] px-3 py-2 text-sm text-slate-100 focus:border-blue-400 focus:outline-none"
                />
                <p id={`${id}-help`} className={detailed ? "text-xs text-slate-400" : "sr-only"}>
                  {ASSUMPTION_HELP[key]}
                </p>
                {error ? (
                  <p id={`${id}-error`} role="alert" className="text-xs font-medium text-rose-300">
                    {error}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-slate-400">
          These are illustrative starting assumptions, not default merchant settings,
          recommended values, or benchmarks. Accepted range: 0 to{" "}
          {formatCount(MAX_ASSUMPTION_INR)} INR.
        </p>
      </fieldset>

      <div
        className="mt-5 flex flex-wrap gap-2"
        role="group"
        aria-label="Select a capacity tier for the illustrative cost scenario"
      >
        {LANE_A_FINAL_TIERS.map((row) => {
          const active = row.capacityPerDay === selectedCapacity;
          return (
            <button
              key={row.capacityPerDay}
              type="button"
              aria-pressed={active}
              onClick={() => setSelectedCapacity(row.capacityPerDay)}
              className={`rounded-lg border px-3 py-2 text-sm font-semibold transition focus:outline-none ${
                active
                  ? "border-[var(--ss-primary)] bg-[var(--ss-primary)] text-[#070b12]"
                  : "border-[var(--ss-border)] bg-[var(--ss-surface-raised)] text-slate-300 hover:border-blue-400"
              }`}
            >
              {formatCount(row.capacityPerDay)}/day
            </button>
          );
        })}
      </div>

      <p
        role="status"
        aria-live="polite"
        aria-atomic="true"
        aria-label="Illustrative cost scenario summary"
        className="sr-only"
      >
        {breakdown
          ? `Illustrative scenario at ${formatCount(tier.capacityPerDay)} reviews per day: ` +
            `${formatCount(tier.falsePositives)} legitimate transactions sent to review, ` +
            `${formatCount(tier.falseNegatives)} fraudulent transactions not reviewed, ` +
            `illustrative total ${formatInr(breakdown.illustrativeTotalCost)}.`
          : "Illustrative cost is unavailable until every assumption is a valid amount."}
      </p>

      {breakdown && allTiers && scenarios ? (
        <>
          <dl
            data-testid="selected-tier-breakdown"
            className={
              detailed
                ? "mt-5 grid grid-cols-1 gap-3 min-[430px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4"
                : "mt-4 grid grid-cols-1 gap-3 min-[430px]:grid-cols-2 sm:grid-cols-3"
            }
          >
            {(detailed
              ? [
              { term: "Review budget", value: formatCount(tier.reviewBudget), detail: "over the evaluation period" },
              { term: "Reviewed", value: formatCount(breakdown.reviewedCount), detail: "TP + FP queued" },
              { term: "True positives", value: formatCount(tier.truePositives), detail: "fraud sent to review" },
              { term: "False positives", value: formatCount(tier.falsePositives), detail: "legitimate, sent to review" },
              { term: "False negatives", value: formatCount(tier.falseNegatives), detail: "fraud not reviewed" },
              { term: "True negatives", value: formatCount(tier.trueNegatives), detail: "legitimate, not reviewed" },
              { term: "Precision", value: formatRate(tier.precision), detail: "of reviewed items" },
              { term: "Recall", value: formatRate(tier.recall), detail: "of all fraud" },
              { term: "Review workload cost", value: formatInr(breakdown.reviewWorkloadCost), detail: "(TP + FP) × review cost" },
              { term: "Legitimate-friction cost", value: formatInr(breakdown.legitimateFrictionCost), detail: "FP × friction cost" },
              { term: "Missed-fraud & chargeback", value: formatInr(breakdown.missedFraudAndChargebackCost), detail: "FN × (loss + chargeback)" },
              { term: "Illustrative total", value: formatInr(breakdown.illustrativeTotalCost), detail: "sum of the three components" },
                ]
              : [
              // Compact keeps the coverage / workload / false-positive trade-off
              // and one illustrative total. The full twelve-cell breakdown,
              // comparison table and scenarios stay on the evidence route.
              { term: "Recall", value: formatRate(tier.recall), detail: "of all fraud, sent to review" },
              { term: "Review budget", value: formatCount(tier.reviewBudget), detail: "queued over the period" },
              { term: "False positives", value: formatCount(tier.falsePositives), detail: "legitimate, sent to review" },
              { term: "Precision", value: formatRate(tier.precision), detail: "of reviewed items" },
              { term: "Missed fraud", value: formatCount(tier.falseNegatives), detail: "fraud not reviewed" },
              { term: "Illustrative total", value: formatInr(breakdown.illustrativeTotalCost), detail: "editable assumptions above" },
                ]
            ).map((item) => (
              <div
                key={item.term}
                className="min-w-0 rounded-lg border border-slate-700/60 bg-slate-900/50 p-3"
              >
                <dt className="break-words text-xs uppercase tracking-wide text-slate-400">{item.term}</dt>
                <dd className="mt-1 break-words text-base font-semibold text-slate-50">
                  {item.value}
                </dd>
                <dd className="mt-0.5 break-words text-xs text-slate-400">{item.detail}</dd>
              </div>
            ))}
          </dl>

          {detailed ? (
          <div className="mt-6 overflow-x-auto">
            <table
              data-testid="all-tier-cost-table"
              className="w-full min-w-[44rem] border-collapse text-left text-sm"
            >
              <caption className="pb-2 text-left text-xs text-slate-400">
                Illustrative cost across every capacity tier, under the assumptions above.
                No tier is recommended.
              </caption>
              <thead>
                <tr className="border-b border-slate-700 text-xs uppercase tracking-wide text-slate-400">
                  <th scope="col" className="py-2 pr-3">Capacity/day</th>
                  <th scope="col" className="py-2 pr-3">Review budget</th>
                  <th scope="col" className="py-2 pr-3">False positives</th>
                  <th scope="col" className="py-2 pr-3">False negatives</th>
                  <th scope="col" className="py-2 pr-3">Precision</th>
                  <th scope="col" className="py-2 pr-3">Recall</th>
                  <th scope="col" className="py-2">Illustrative total</th>
                </tr>
              </thead>
              <tbody>
                {LANE_A_FINAL_TIERS.map((row, index) => (
                  <tr
                    key={row.capacityPerDay}
                    data-testid={`cost-row-${row.capacityPerDay}`}
                    className={`border-b border-slate-800 ${
                      row.capacityPerDay === selectedCapacity ? "bg-blue-500/10" : ""
                    }`}
                  >
                    <th scope="row" className="py-2 pr-3 font-medium text-slate-200">
                      {formatCount(row.capacityPerDay)}
                    </th>
                    <td className="py-2 pr-3 text-slate-300">{formatCount(row.reviewBudget)}</td>
                    <td className="py-2 pr-3 text-slate-300">{formatCount(row.falsePositives)}</td>
                    <td className="py-2 pr-3 text-slate-300">{formatCount(row.falseNegatives)}</td>
                    <td className="py-2 pr-3 text-slate-300">{formatRate(row.precision)}</td>
                    <td className="py-2 pr-3 text-slate-300">{formatRate(row.recall)}</td>
                    <td className="py-2 text-slate-300">
                      {formatInr(allTiers[index].illustrativeTotalCost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          ) : null}

          {detailed ? (
          <div className="mt-6 space-y-4">
            <h4 className="text-sm font-semibold text-slate-200">
              Sensitivity scenarios (illustrative)
            </h4>
            {scenarios.map((scenario) => (
              <div
                key={scenario.id}
                data-testid={`sensitivity-${scenario.id}`}
                className="overflow-x-auto rounded-lg border border-slate-700/60 p-3"
              >
                <p className="text-sm font-medium text-slate-200">{scenario.name}</p>
                <p className="mb-2 text-xs text-slate-400">{scenario.description}</p>
                <table className="w-full min-w-[26rem] border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-700 uppercase tracking-wide text-slate-400">
                      <th scope="col" className="py-1.5 pr-3">Capacity/day</th>
                      <th scope="col" className="py-1.5">Illustrative total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {LANE_A_FINAL_TIERS.map((row, index) => (
                      <tr key={row.capacityPerDay} className="border-b border-slate-800">
                        <th scope="row" className="py-1.5 pr-3 font-medium text-slate-300">
                          {formatCount(row.capacityPerDay)}
                        </th>
                        <td className="py-1.5 text-slate-300">
                          {formatInr(scenario.costs[index].illustrativeTotalCost)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          ) : null}
        </>
      ) : (
        <p
          data-testid="cost-explorer-invalid"
          role="alert"
          className="mt-5 rounded-lg border border-rose-400/40 bg-rose-500/10 p-3 text-sm text-rose-100"
        >
          Illustrative cost is not shown while any assumption is invalid. Correct the
          highlighted amounts to see the scenario.
        </p>
      )}

      {!detailed ? (
        <footer className="mt-4 break-words text-xs leading-5 text-slate-400">
          Scenario arithmetic over sealed aggregate counts, not observed merchant
          costs. Every monetary input is illustrative and editable. This panel
          selects no capacity and no threshold, and nothing here approves, blocks,
          declines, or steps up a payment.
        </footer>
      ) : (
      <footer className="mt-6 space-y-2 break-words text-xs leading-relaxed text-slate-400">
        <p>
          <span className="font-medium text-slate-300">Formula:</span> illustrative total
          = (TP + FP) × review cost + FP × legitimate-customer friction cost + FN ×
          (missed-fraud loss + chargeback-handling cost). Amounts are held at paise
          precision internally and displayed as whole INR.
        </p>
        <p>
          <span className="font-medium text-slate-300">Evidence:</span> counts come from
          the sealed Lane A final evaluation ({LANE_A_FINAL_EVIDENCE.source}),{" "}
          {formatCount(LANE_A_FINAL_EVIDENCE.rows)} transactions with{" "}
          {formatCount(LANE_A_FINAL_EVIDENCE.positives)} fraudulent, evaluated exactly
          once on a programmatically held-out role. Result manifest{" "}
          <code className="text-slate-300">{LANE_A_FINAL_EVIDENCE.resultManifestSha256.slice(0, 16)}…</code>.
        </p>
        <p>
          These are scenario calculations on published aggregate counts, not observed
          merchant costs. Every monetary input is illustrative and editable. This panel
          selects no capacity and no threshold, and nothing here approves, blocks,
          declines, or steps up a payment.
        </p>
      </footer>
      )}
    </section>
  );
}
