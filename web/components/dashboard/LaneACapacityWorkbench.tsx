"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { LaneACostExplorer } from "@/components/dashboard/LaneACostExplorer";
import {
  LANE_A_CAPACITY_TIERS,
  LANE_A_EVALUATION,
  LANE_A_ILLUSTRATIVE_LABEL,
  LANE_A_RECALL80_REFERENCE,
} from "@/data/laneACapacity";

const percent = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`;
const integer = (value: number) => value.toLocaleString("en-US");

/**
 * Lane A (IEEE-CIS) capacity-aware review workbench.
 *
 * Renders only aggregate development evidence. It publishes no rows, no
 * identifiers, no email domains, no device strings, no amounts, no labels and
 * no scores. Lane A and Lane B are deliberately kept in separate sections and
 * their metrics are never charted together: different corpora, base rates,
 * label definitions and feature spaces make any comparison meaningless.
 */
export function LaneACapacityWorkbench() {
  const [selectedCapacity, setSelectedCapacity] = useState<number>(
    LANE_A_CAPACITY_TIERS[0].capacityPerDay,
  );
  const tier =
    LANE_A_CAPACITY_TIERS.find((row) => row.capacityPerDay === selectedCapacity) ??
    LANE_A_CAPACITY_TIERS[0];

  return (
    <section
      id="lane-a-capacity"
      aria-labelledby="lane-a-capacity-heading"
      className="command-panel scroll-mt-24 p-5 sm:p-7"
    >
      <header className="flex flex-col gap-3">
        <div
          aria-label="Lane A evidence provenance"
          className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-5 text-slate-400"
        >
          <Badge className="border-amber-300/30 bg-amber-300/10 text-amber-100">
            Development evidence
          </Badge>
          <span className="font-medium text-slate-200">IEEE-CIS Lane A</span>
          <span aria-hidden="true">·</span>
          <span>Final evaluation sealed</span>
          <span aria-hidden="true">·</span>
          <span>Illustrative capacity</span>
          <span aria-hidden="true">·</span>
          <span>No Razorpay or live-merchant economics</span>
          <span aria-hidden="true">·</span>
          <span>Not comparable with Lane B historical metrics</span>
        </div>
        <h2 id="lane-a-capacity-heading" className="text-2xl font-semibold tracking-[-0.03em] text-white sm:text-3xl">
          Review-capacity workbench
        </h2>
        <p className="max-w-[48rem] text-sm leading-6 text-slate-300">
          A merchant&apos;s review capacity decides what fraud coverage is reachable. This
          panel shows measured trade-offs on the Lane A{" "}
          <code className="text-slate-200">{LANE_A_EVALUATION.role}</code> partition
          ({integer(LANE_A_EVALUATION.population)} transactions,{" "}
          {integer(LANE_A_EVALUATION.positives)} fraudulent, over{" "}
          {LANE_A_EVALUATION.evaluationPeriodDays} days). There is no universal
          capacity: pick a tier to see what it buys.
        </p>
        <p className="max-w-3xl text-xs leading-relaxed text-amber-200/90">
          {LANE_A_ILLUSTRATIVE_LABEL}
        </p>
      </header>

      <div
        role="group"
        aria-label="Select an illustrative daily review capacity"
        className="mt-5 flex flex-wrap gap-2"
      >
        {LANE_A_CAPACITY_TIERS.map((row) => {
          const active = row.capacityPerDay === selectedCapacity;
          return (
            <button
              key={row.capacityPerDay}
              type="button"
              onClick={() => setSelectedCapacity(row.capacityPerDay)}
              aria-pressed={active}
              className={`rounded-lg border px-3 py-2 text-sm font-semibold transition focus:outline-none ${
                active
                  ? "border-[var(--ss-primary)] bg-[var(--ss-primary)] text-[#070b12]"
                  : "border-[var(--ss-border)] bg-[var(--ss-surface-raised)] text-slate-200 hover:border-blue-400"
              }`}
            >
              {integer(row.capacityPerDay)}/day
            </button>
          );
        })}
      </div>

      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        Selected capacity {integer(tier.capacityPerDay)} reviews per day: precision{" "}
        {percent(tier.precision, 2)}, recall {percent(tier.recall, 2)}, and{" "}
        {integer(tier.alertsSelected)} reviews over the development evaluation period.
      </p>

      <dl className="mt-6 grid grid-cols-1 gap-3 min-[430px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
        {[
          { term: "Precision", value: percent(tier.precision, 2),
            detail: `95% CI ${percent(tier.precisionCiLow, 1)}–${percent(tier.precisionCiHigh, 1)}` },
          { term: "Recall", value: percent(tier.recall, 2),
            detail: `95% CI ${percent(tier.recallCiLow, 1)}–${percent(tier.recallCiHigh, 1)}` },
          { term: "Review workload", value: integer(tier.alertsSelected),
            detail: `${integer(Math.round(tier.averageReviewsPerDay))} reviews/day` },
          { term: "False positives", value: integer(tier.falsePositives),
            detail: `${percent(tier.alertRate, 2)} of transactions alerted` },
          { term: "Missed fraud", value: integer(tier.falseNegatives),
            detail: `${integer(tier.truePositives)} caught` },
          { term: "Capacity utilisation", value: percent(tier.capacityUtilisation, 0),
            detail: `budget ${integer(tier.reviewBudget)}` },
          { term: "Reaches 80% recall", value: tier.reachesRecall80 ? "Yes" : "No",
            detail: tier.reachesRecall80 ? "at this capacity" : "not at this capacity" },
          { term: "Model inputs", value: String(LANE_A_EVALUATION.modelInputs),
            detail: LANE_A_EVALUATION.selectedVariant },
        ].map((item) => (
          <div key={item.term} className="min-w-0 rounded-lg border border-slate-700/60 bg-slate-950/40 p-3.5">
            <dt className="text-xs uppercase tracking-wide text-slate-400">{item.term}</dt>
            <dd className="mt-1 text-lg font-semibold text-slate-50">{item.value}</dd>
            <dd className="mt-0.5 text-xs text-slate-400">{item.detail}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[46rem] border-collapse text-left text-sm">
          <caption className="pb-2 text-left text-xs text-slate-400">
            Recall versus workload across every illustrative capacity tier.
          </caption>
          <thead>
            <tr className="border-b border-slate-700 text-xs uppercase tracking-wide text-slate-400">
              <th scope="col" className="py-2 pr-3">Capacity/day</th>
              <th scope="col" className="py-2 pr-3">Reviews</th>
              <th scope="col" className="py-2 pr-3">Precision</th>
              <th scope="col" className="py-2 pr-3">Recall</th>
              <th scope="col" className="py-2 pr-3">False positives</th>
              <th scope="col" className="py-2 pr-3">Missed fraud</th>
              <th scope="col" className="py-2">80% recall</th>
            </tr>
          </thead>
          <tbody>
            {LANE_A_CAPACITY_TIERS.map((row) => (
              <tr
                key={row.capacityPerDay}
                className={`border-b border-slate-800 ${
                  row.capacityPerDay === selectedCapacity ? "bg-blue-500/10" : ""
                }`}
              >
                <th scope="row" className="py-2 pr-3 font-medium text-slate-200">
                  {integer(row.capacityPerDay)}
                </th>
                <td className="py-2 pr-3 text-slate-300">{integer(row.alertsSelected)}</td>
                <td className="py-2 pr-3 text-slate-300">{percent(row.precision, 2)}</td>
                <td className="py-2 pr-3 text-slate-300">{percent(row.recall, 2)}</td>
                <td className="py-2 pr-3 text-slate-300">{integer(row.falsePositives)}</td>
                <td className="py-2 pr-3 text-slate-300">{integer(row.falseNegatives)}</td>
                <td className="py-2 text-slate-300">{row.reachesRecall80 ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="mt-5 space-y-2 text-xs leading-relaxed text-slate-400">
        <p>
          <span className="font-medium text-slate-300">Derived coverage reference:</span>{" "}
          reaching 80% recall on this partition needs{" "}
          {integer(LANE_A_RECALL80_REFERENCE.minimumReviews)} reviews
          (~{integer(LANE_A_RECALL80_REFERENCE.impliedReviewsPerDay)}/day) at{" "}
          {percent(LANE_A_RECALL80_REFERENCE.achievedPrecision, 2)} precision. This is a
          reference figure only — not a merchant capacity and not a recommended default.
        </p>
        <p>
          Output is a {LANE_A_EVALUATION.scoreTerminology} ({LANE_A_EVALUATION.calibration}{" "}
          calibration). Every tier prioritises the highest-risk transactions for
          <span className="font-medium text-slate-300"> human review</span>. Nothing here
          approves, blocks, declines, or steps up a payment.
        </p>
        <p>
          Development evidence from a chronologically held-back validation partition.
          These figures are development-optimistic and are not comparable with Lane B
          historical metrics. The separate sealed final evaluation, run exactly once, is
          reported in the illustrative cost panel below.
        </p>
      </footer>

      <LaneACostExplorer />
    </section>
  );
}
