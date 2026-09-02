import { ShieldCheck } from "lucide-react";

import { DashboardPanel } from "@/components/dashboard/DashboardPanel";
import { EvidenceLegend } from "@/components/dashboard/EvidenceLegend";
import { dashboardData } from "@/data/metrics";

const EVIDENCE_SAFEGUARDS = [
  "The public presentation layer keeps trained models and preprocessors inside the verified pipeline boundary.",
  "Only aggregate artifacts reach the dashboard; original and user-submitted transaction data is never served, stored, or logged.",
  "Historical dashboard interactions use tracked, precomputed validation and test artifacts, while genuine inference is isolated and explicitly labelled.",
  "Historical anonymized evidence keeps its original scope and stays separate from current bank traffic and policy.",
  "The XGBoost output is consistently presented as a model score, never as a real-world fraud probability.",
] as const;

export function ScopeEvidencePanel() {
  return (
    <section id="limitations" tabIndex={-1} aria-labelledby="limitations-heading" className="scroll-mt-20 focus:outline-none">
      <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
        <DashboardPanel
          eyebrow="Evidence safeguards"
          title="Clear boundaries make every result stronger"
          description="Scope, provenance and measurement limits travel with every result, so reviewers can use the dashboard with confidence."
          className="h-full"
        >
          <ul className="grid gap-2.5 text-[12px] leading-5 text-slate-300">
            {EVIDENCE_SAFEGUARDS.map((safeguard) => (
              <li key={safeguard} className="flex gap-3 rounded-md border border-emerald-300/15 bg-emerald-300/[0.04] p-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" aria-hidden="true" />
                {safeguard}
              </li>
            ))}
          </ul>
        </DashboardPanel>

        <DashboardPanel
          eyebrow="Evidence taxonomy"
          title="Read every number in context"
          description="Four labels keep measured evidence separate from demos, plumbing tests and illustrative arithmetic."
          className="h-full"
          aside={<ShieldCheck className="h-5 w-5 text-teal-200" aria-hidden="true" />}
        >
          <EvidenceLegend />
          <p id="limitations-heading" className="mt-4 text-[11.5px] leading-5 text-slate-500">
            {dashboardData.project.disclaimer}
          </p>
        </DashboardPanel>
      </div>
    </section>
  );
}
