import { EvidenceLabel } from "@/components/EvidenceLabel";

const legend = [
  ["historical-evaluation", "Locked measurements from tracked validation or already-observed random-holdout artifacts."],
  ["genuine-demo-inference", "Actual estimator output from an explicit opt-in request to the provenance-verified reference API; the response carries its own evidence category and decision-eligibility flags."],
  ["synthetic-plumbing-test", "Fabricated in-browser events or explicitly local synthetic serving-path measurements; neither is real-world fraud evidence."],
  ["illustrative-cost-scenario", "Visible arithmetic assumptions applied to locked aggregate counts; never a savings claim."],
] as const;

export function EvidenceLegend({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "flex flex-wrap gap-2" : "grid gap-2 sm:grid-cols-2"} aria-label="Evidence category legend">
      {legend.map(([type, description]) => (
        <div
          key={type}
          className={
            compact
              ? "flex items-center"
              : "rounded-md border border-white/[0.08] bg-slate-950/35 p-3"
          }
        >
          <EvidenceLabel type={type} />
          {!compact ? <p className="mt-2 text-[11.5px] leading-5 text-slate-400">{description}</p> : null}
        </div>
      ))}
    </div>
  );
}
