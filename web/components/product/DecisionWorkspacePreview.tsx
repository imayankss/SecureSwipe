import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { DecisionZoneBand } from "@/components/system/DecisionZoneBand";
import { StateChip } from "@/components/system/StateChip";
import { DEMO_FIXTURE_VERSION, DEMO_REQUEST_ID } from "@/lib/deterministic-demo";

/**
 * A product preview of the decision workspace.
 *
 * It deliberately shows no outcome. The homepage is statically rendered and
 * calls no API, so any decision, score, or receipt printed here would be
 * fabricated. The preview shows the scenario that will be sent and the complete
 * outcome vocabulary, then hands off to `/demo` where a real result is produced.
 */
const OUTCOMES = [
  {
    label: "Human review",
    meaning: "At or above the operating threshold. A person decides.",
    state: "review" as const,
  },
  {
    label: "Below review threshold",
    meaning: "Under the threshold. No review is raised, and nothing is called safe.",
    state: "verified" as const,
  },
  {
    label: "Unavailable — fail closed",
    meaning: "Validation or readiness failed. No outcome is released at all.",
    state: "unavailable" as const,
  },
];

export function DecisionWorkspacePreview() {
  return (
    <section
      id="decision-preview"
      data-product-section="decision-preview"
      aria-labelledby="decision-preview-heading"
      className="ss-section scroll-mt-20"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="ss-eyebrow">Decision workspace</p>
          <h2
            id="decision-preview-heading"
            className="mt-2.5 max-w-2xl text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl"
          >
            Every result carries its own evidence.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            The demo sends one fixed, sanitized scenario and returns a bounded
            outcome with a decision zone, provenance, and an audit receipt.
          </p>
        </div>
        <StateChip state="info" label="Fixed reference scenario · not live traffic" />
      </div>

      <div className="mt-6 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="command-panel p-4 sm:p-5">
          <p className="ss-eyebrow">Scenario that will be sent</p>
          <dl className="mt-3 grid gap-2 text-xs">
            {[
              ["Fixture", DEMO_FIXTURE_VERSION],
              ["Request reference", DEMO_REQUEST_ID],
              ["Input form", "30 anonymized numeric fields"],
              ["Contains", "No PAN, CVV, cardholder, or raw identifier"],
            ].map(([term, value]) => (
              <div key={term} className="rounded-lg bg-[var(--ss-surface-raised)] p-3">
                <dt className="text-slate-500">{term}</dt>
                <dd className="ss-provenance mt-1 break-all text-slate-200">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs leading-5 text-slate-500">
            No outcome is shown here. This page is statically rendered and calls
            no API, so printing a decision would be inventing one.
          </p>
        </div>

        <div className="command-panel p-4 sm:p-5">
          <DecisionZoneBand
            decision="pending"
            // The reference API reports its own operating threshold at run time.
            // Lane B's historical threshold must never stand in for it here.
            operatingThreshold={null}
            idPrefix="preview-"
          />
          <ul className="mt-5 grid gap-2 border-t border-[var(--ss-border)] pt-4">
            {OUTCOMES.map((outcome) => (
              <li key={outcome.label} className="flex flex-wrap items-center gap-2.5">
                <StateChip state={outcome.state} label={outcome.label} />
                <span className="min-w-0 flex-1 text-xs leading-5 text-slate-400">
                  {outcome.meaning}
                </span>
              </li>
            ))}
          </ul>
          <Link
            href="/demo"
            prefetch={false}
            className="ss-action ss-action-primary mt-5 w-full focus:outline-none sm:w-auto"
          >
            Run this scenario in the demo
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  );
}
