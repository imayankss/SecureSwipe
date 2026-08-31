import Link from "next/link";
import { ExternalLink, ShieldAlert } from "lucide-react";

import { dashboardData } from "@/data/metrics";

const boundaries = [
  "No live merchant use or payment integration is established.",
  "No real merchant economics, savings, or production-scale capacity is established.",
  "The public experience contains aggregate evidence, not transaction rows or model files.",
  "The local reference bundle is separate from the model behind the sealed Lane A evaluation.",
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
          <div className="flex items-center gap-2 text-amber-100">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
            <p className="ss-eyebrow">Trust, limitations, and details</p>
          </div>
          <h2 id="trust-heading" className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-white">
            The boundary travels with the claim.
          </h2>
          <p className="mt-4 text-sm leading-6 text-slate-400">
            Research and portfolio evidence only. Inspect the detailed route for
            source identifiers, methodology, limitations, and local runtime evidence.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/evidence#limitations"
              prefetch={false}
              className="ss-action ss-action-primary focus:outline-none"
            >
              Read evidence limitations
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
          {boundaries.map((boundary) => (
            <li key={boundary} className="rounded-lg bg-[var(--ss-surface-raised)] p-3.5">
              {boundary}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
