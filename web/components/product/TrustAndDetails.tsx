import Link from "next/link";
import { ExternalLink, ShieldCheck } from "lucide-react";

import { dashboardData } from "@/data/metrics";

/**
 * The closing trust section.
 *
 * Each line states what the system *does* guarantee. The guarantees are the
 * same boundaries as before, written as commitments rather than as a list of
 * absences — a reviewer should finish this page knowing what holds, not only
 * what is missing.
 */
const guarantees = [
  "Every result ends at a human reviewer — payment authority stays with your existing systems.",
  "Cost and capacity figures are transparent, editable scenarios, so the arithmetic is auditable line by line.",
  "The public surface ships aggregate evidence only; transaction rows and model artifacts stay inside the pipeline.",
  "The reference demo runs its own bundle, keeping the sealed Lane A evaluation provably untouched.",
];

export function TrustAndDetails() {
  return (
    <section
      id="trust"
      data-product-section="trust-limitations-details"
      aria-labelledby="trust-heading"
      className="ss-section scroll-mt-20"
    >
      <div className="command-panel grid gap-8 p-6 lg:grid-cols-[0.85fr_1.15fr] sm:p-8">
        <div>
          <div className="flex items-center gap-2 text-emerald-200">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            <p className="ss-eyebrow">Trust and guarantees</p>
          </div>
          <h2 id="trust-heading" className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-white">
            Built to be checked, not just believed.
          </h2>
          <p className="mt-4 text-sm leading-6 text-slate-400">
            Every figure on this site traces to a tracked artifact with its scope
            attached. Open the evidence route for source identifiers,
            methodology, and the measurement limits behind each result.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/evidence#limitations"
              prefetch={false}
              className="ss-action ss-action-primary focus:outline-none"
            >
              Read the evidence limits
            </Link>
            <a
              href={dashboardData.project.repository}
              target="_blank"
              rel="noopener noreferrer"
              className="ss-action ss-action-secondary focus:outline-none"
            >
              Inspect the repository
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        </div>

        <ul className="grid gap-2 text-xs leading-5 text-slate-300">
          {guarantees.map((guarantee) => (
            <li
              key={guarantee}
              className="flex gap-2.5 rounded-lg bg-[var(--ss-surface-raised)] p-3.5"
            >
              <ShieldCheck
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300"
                aria-hidden="true"
              />
              <span>{guarantee}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
