import Link from "next/link";
import { ArrowRight, Scale } from "lucide-react";

import { LaneACostExplorer } from "@/components/dashboard/LaneACostExplorer";

/**
 * The homepage's central interaction: a compact, product-facing review-strategy
 * surface.
 *
 * It renders the compact variant of the same Lane A explorer used on the
 * evidence route, so the selector, the frozen sealed-final counts and the pure
 * cost model are shared rather than copied. The badge row, sealed-metric
 * interval block, all-tier comparison table, sensitivity scenarios and long
 * provenance footnotes stay on `/evidence`.
 */
export function ReviewStrategySurface() {
  return (
    <section
      id="review-strategy"
      data-product-section="review-strategy"
      aria-labelledby="review-strategy-heading"
      className="ss-section scroll-mt-20"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-blue-300">
            <Scale className="h-4 w-4" aria-hidden="true" />
            <p className="ss-eyebrow">Review strategy</p>
          </div>
          <h2
            id="review-strategy-heading"
            className="mt-3 max-w-2xl text-3xl font-semibold tracking-[-0.035em] text-white"
          >
            More coverage also means more review work.
          </h2>
          <p className="ss-prose mt-4 max-w-2xl text-sm leading-6 text-slate-400">
            Pick a review capacity to see what it buys and what it costs. A false
            positive is a legitimate transaction sent to human review — it is not
            automatically declined. No tier is a default or a recommendation.
          </p>
        </div>

        <Link
          href="/evidence#lane-a-capacity"
          prefetch={false}
          className="ss-text-link shrink-0 focus:outline-none"
        >
          Inspect detailed evidence
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>

      <div className="mt-9">
        <LaneACostExplorer variant="compact" idPrefix="home-" />
      </div>
    </section>
  );
}
