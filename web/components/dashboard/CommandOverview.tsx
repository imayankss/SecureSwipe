import { ArrowDown, DatabaseZap, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EvidenceLabel } from "@/components/EvidenceLabel";
import { EvidenceLegend } from "@/components/dashboard/EvidenceLegend";
import { dashboardData, heroMetrics } from "@/data/metrics";

const posture = [
  "Human-review aid",
  "Historical result locked",
  "Privacy-safe dashboard",
  "No autonomous payment blocking",
];

const decisionPath = [
  "Offline evidence",
  "Validated export",
  "Static dashboard",
  "Optional local API",
  "Bounded result",
  "Human review",
];

export function CommandOverview() {
  return (
    <section id="overview" tabIndex={-1} aria-labelledby="overview-heading" className="scroll-mt-20 focus:outline-none">
      <div className="command-overview-grid">
        <div className="min-w-0 py-2">
          <p className="ss-eyebrow text-teal-200">Razorpay AI Builder Internship · Track 2: AI Risk Manager</p>
          <h1 id="overview-heading" className="mt-2 max-w-4xl text-[2.15rem] font-semibold leading-[1.02] tracking-[-0.05em] text-white sm:text-[3.2rem]">
            Fraud decisions, <span className="text-teal-200">made inspectable.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-[15px] font-medium leading-6 text-slate-200">
            Defense-only fraud-risk evidence and human-review decision aid
          </p>
          <p className="mt-3 max-w-2xl text-[13px] leading-6 text-slate-400">
            Explore tracked validation and already-observed random-holdout summaries:
            model comparison, threshold trade-offs, PR-focused evaluation, and
            non-causal SHAP artifacts whose original output units remain unverified.
          </p>

          <ul className="mt-4 flex flex-wrap gap-2" aria-label="Dashboard posture">
            {posture.map((item) => (
              <li key={item} className="rounded-full border border-white/10 bg-white/[0.035] px-2.5 py-1 text-[11px] text-slate-300">
                {item}
              </li>
            ))}
          </ul>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button href="#historical" className="h-9 rounded-md px-3.5 text-xs">
              Explore the evidence <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
            <EvidenceLegend compact />
          </div>

          <div className="mt-5 flex max-w-2xl items-start gap-3 rounded-md border border-teal-200/15 bg-teal-300/[0.035] p-3 text-[11.5px] leading-5 text-slate-400">
            <DatabaseZap className="mt-0.5 h-4 w-4 shrink-0 text-teal-200" aria-hidden="true" />
            <p>
              <span className="font-medium text-teal-100">precomputed · static-first</span> — historical evidence
              remains useful with the local API down. Genuine inference is a separate, explicit opt-in request.
            </p>
          </div>
        </div>

        <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
          {heroMetrics.map((metric) => (
            <article className="command-kpi" key={metric.label}>
              <div className="flex items-start justify-between gap-2">
                <p className="ss-eyebrow text-slate-500">{metric.label}</p>
                <EvidenceLabel type="historical-evaluation" />
              </div>
              <p className="ss-number mt-3 text-[1.75rem] font-semibold leading-none text-white">{metric.value}</p>
              <p className="mt-2 text-[11.5px] leading-5 text-slate-400">{metric.description}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="command-panel mt-3 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3">
          <p className="ss-eyebrow text-slate-500">Decision path</p>
          <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
            <ShieldCheck className="h-3.5 w-3.5 text-teal-200" aria-hidden="true" /> human review remains explicit
          </span>
        </div>
        <ol className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-2">
          {decisionPath.map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              <span className="rounded-md border border-white/10 bg-slate-950/45 px-2.5 py-1.5 text-xs text-slate-100">
                <span className="ss-number mr-1.5 text-[10px] text-slate-500">{String(index + 1).padStart(2, "0")}</span>
                {step}
              </span>
              {index < decisionPath.length - 1 ? <span className="text-slate-600" aria-hidden="true">→</span> : null}
            </li>
          ))}
        </ol>
        <p className="mt-3 text-[11.5px] leading-5 text-slate-500">{dashboardData.project.disclaimer}</p>
      </div>
    </section>
  );
}
