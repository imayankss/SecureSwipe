import Link from "next/link";
import { ArrowRight, PlayCircle } from "lucide-react";

import {
  LANE_A_FINAL_CATEGORY,
  LANE_A_FINAL_TIERS,
} from "@/data/laneAFinalFrontier";

/**
 * The single homepage headline evaluation.
 *
 * Derived only from the sealed Lane A final frontier module. No Lane B metric,
 * no Lane A development figure, and no recomputation appears here: the tier is
 * read from the frozen array and formatted for display.
 */
const headlineTier = LANE_A_FINAL_TIERS[3];

if (headlineTier.capacityPerDay !== 1_000) {
  throw new Error("The frozen 1,000 reviews/day Lane A final tier is unavailable.");
}

const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function ProductHero() {
  return (
    <section
      id="overview"
      data-product-section="product-promise"
      tabIndex={-1}
      aria-labelledby="product-heading"
      className="scroll-mt-20 py-10 focus:outline-none sm:py-14 lg:py-16"
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)] lg:items-center lg:gap-12">
        <div className="max-w-3xl">
          <p className="ss-eyebrow">SecureSwipe · AI Risk Manager</p>
          <h1
            id="product-heading"
            className="mt-3 max-w-3xl text-3xl leading-[1.06] tracking-[-0.04em] sm:text-5xl"
          >
            Payment-risk review, <span className="text-blue-300">made inspectable.</span>
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-200">
            Human-review decision support for a risk or operations reviewer.
            Inspect bounded review signals and review-capacity trade-offs before
            a human decision.
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            SecureSwipe routes results only to{" "}
            <strong className="font-medium text-white">human review</strong> or marks
            them <strong className="font-medium text-white">below review threshold</strong>.
            Payment action stays outside this system.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link
              href="/demo"
              prefetch={false}
              className="ss-action ss-action-primary focus:outline-none"
            >
              <PlayCircle className="h-4 w-4" aria-hidden="true" />
              Run the 2-minute demo
            </Link>
            <Link
              href="/evidence"
              prefetch={false}
              className="ss-action ss-action-secondary focus:outline-none"
            >
              Inspect the evidence
            </Link>
            <a href="#review-strategy" className="ss-text-link focus:outline-none">
              Explore the review strategy
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        </div>

        <aside
          className="command-panel p-5 sm:p-6"
          aria-label="Headline evaluation result"
          data-testid="hero-headline-evidence"
        >
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-blue-200">
            {LANE_A_FINAL_CATEGORY}
          </p>
          <p className="ss-number mt-3.5 break-words text-5xl font-semibold leading-none text-white">
            {percent.format(headlineTier.recall)}
          </p>
          <p className="mt-3 max-w-sm text-sm leading-6 text-slate-300">
            recall in the sealed Lane A final evaluation. Review-capacity and
            false-positive trade-offs are available below.
          </p>
          <p className="mt-4 border-t border-white/[0.08] pt-3.5 text-[11px] leading-5 text-slate-500">
            Evaluated exactly once on a programmatically held-out role. Not
            Razorpay, live-merchant, or production performance.
          </p>
        </aside>
      </div>

      <p className="mt-8 max-w-2xl border-l border-white/10 pl-3 text-xs leading-5 text-slate-500">
        Built for Razorpay AI Builder Internship · Track 2: AI Risk Manager.
        Project context only; no payment integration is represented.
      </p>
    </section>
  );
}
