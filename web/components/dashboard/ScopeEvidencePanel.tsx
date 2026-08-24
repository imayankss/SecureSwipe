import { AlertTriangle, ShieldCheck } from "lucide-react";

import { DashboardPanel } from "@/components/dashboard/DashboardPanel";
import { EvidenceLegend } from "@/components/dashboard/EvidenceLegend";
import { dashboardData } from "@/data/metrics";

export function ScopeEvidencePanel() {
  return (
    <section id="limitations" tabIndex={-1} aria-labelledby="limitations-heading" className="scroll-mt-20 focus:outline-none">
      <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
        <DashboardPanel
          eyebrow="Claims boundary"
          title="What this dashboard does not prove"
          description="The safety boundary travels with the evidence, not in a detached disclaimer."
          className="h-full"
        >
          <ul className="grid gap-2.5 text-[12px] leading-5 text-slate-300">
            {dashboardData.limitations.map((limitation) => (
              <li key={limitation} className="flex gap-3 rounded-md border border-white/[0.07] bg-slate-950/30 p-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-200" aria-hidden="true" />
                {limitation}
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

