import Link from "next/link";

import { StateChip } from "@/components/system/StateChip";
import {
  LANE_A_FINAL_EVIDENCE,
  LANE_A_FINAL_METRICS,
  LANE_A_FINAL_TIERS,
} from "@/data/laneAFinalFrontier";

/**
 * Four headline measurements, all read from the one sealed Lane A final source.
 *
 * Every card comes from the same evaluation so the strip cannot silently mix
 * lanes: Lane B historical figures come from a different corpus, base rate and
 * label definition and are never averaged or compared with these.
 */
const tier = LANE_A_FINAL_TIERS[3];

const integer = new Intl.NumberFormat("en-US");
const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

type Kpi = {
  label: string;
  value: string;
  interpretation: string;
};

const KPIS: readonly Kpi[] = [
  {
    label: "Fraud surfaced for review",
    value: percent.format(tier.recall),
    interpretation: `${integer.format(tier.truePositives)} of ${integer.format(
      LANE_A_FINAL_EVIDENCE.positives,
    )} labelled fraud cases were routed to a reviewer at this capacity.`,
  },
  {
    label: "Precision at that capacity",
    value: percent.format(tier.precision),
    interpretation: `Most reviewed items are legitimate: ${integer.format(
      tier.falsePositives,
    )} legitimate transactions were also sent to review.`,
  },
  {
    label: "Average precision",
    value: LANE_A_FINAL_METRICS.averagePrecision.toFixed(4),
    interpretation: `Threshold-independent ranking quality. 95% bootstrap interval ${LANE_A_FINAL_METRICS.averagePrecisionCiLow.toFixed(
      4,
    )}–${LANE_A_FINAL_METRICS.averagePrecisionCiHigh.toFixed(4)}.`,
  },
  {
    label: "Fraud not surfaced",
    value: integer.format(tier.falseNegatives),
    interpretation:
      "Cases that stayed below the operating threshold at this capacity and reached no reviewer.",
  },
] as const;

export function EvidenceKpiStrip() {
  return (
    <section
      id="measured-evidence"
      data-product-section="measured-evidence"
      aria-labelledby="measured-evidence-heading"
      className="ss-section scroll-mt-20"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="ss-eyebrow">Measured evidence</p>
          <h2
            id="measured-evidence-heading"
            className="mt-2.5 max-w-2xl text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl"
          >
            What the sealed evaluation actually measured.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            All four figures come from the same one-time Lane A final evaluation
            at a review capacity of {integer.format(tier.capacityPerDay)} per day,
            over {integer.format(LANE_A_FINAL_EVIDENCE.rows)} held-out rows. They
            are never mixed with Lane B historical metrics.
          </p>
        </div>
        <StateChip state="info" label="Sealed final evaluation · evaluated once" />
      </div>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {KPIS.map((kpi) => (
          <div key={kpi.label} className="command-panel p-4 sm:p-5">
            <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-400">
              {kpi.label}
            </dt>
            <dd>
              <p className="ss-number mt-3 text-3xl font-semibold leading-none text-white">
                {kpi.value}
              </p>
              <p className="mt-3 text-xs leading-5 text-slate-400">
                {kpi.interpretation}
              </p>
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 text-xs leading-5 text-slate-500">
        Source: sealed result manifest{" "}
        <span className="ss-provenance text-slate-400">
          {LANE_A_FINAL_EVIDENCE.resultManifestSha256.slice(0, 12)}…
        </span>{" "}
        ·{" "}
        <Link href="/evidence#lane-a-capacity" prefetch={false} className="ss-text-link min-h-0 text-xs">
          Open the full evaluation record
        </Link>
      </p>
    </section>
  );
}
