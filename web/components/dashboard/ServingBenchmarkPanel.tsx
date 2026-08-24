import { ExternalLink, ServerCog } from "lucide-react";

import { EvidenceLabel } from "@/components/EvidenceLabel";
import { DashboardPanel } from "@/components/dashboard/DashboardPanel";

const benchmarkReportHref =
  "https://github.com/imayankss/SecureSwipe/blob/main/reports/operations/2026-08-24_local_single_node_serving_benchmark.md";

const latencyMetrics = [
  ["p50", "33.60 ms"],
  ["p95", "39.75 ms"],
  ["p99", "70.24 ms"],
  ["Throughput", "246.10 TPS"],
] as const;

export function ServingBenchmarkPanel() {
  return (
    <section aria-label="Preliminary local synthetic serving-path benchmark">
      <DashboardPanel
        eyebrow="Measured local evidence"
        title="Preliminary local synthetic serving-path benchmark"
        description="Fixed loopback baseline from a temporary synthetic-only bundle; this is preliminary and will be rerun against the final release candidate."
        aside={<EvidenceLabel type="synthetic-plumbing-test" />}
        bodyClassName="space-y-4"
      >
        <div className="grid gap-3 lg:grid-cols-[0.9fr_1.35fr]">
          <div className="rounded-md border border-violet-200/20 bg-violet-300/[0.04] p-4">
            <div className="flex items-start gap-3">
              <ServerCog className="mt-0.5 h-4 w-4 shrink-0 text-violet-200" aria-hidden="true" />
              <div>
                <p className="ss-eyebrow text-violet-100">Fixed baseline</p>
                <p className="mt-1 text-sm font-semibold text-white">8 concurrent requests</p>
                <p className="mt-2 text-xs leading-5 text-slate-300">
                  <span className="ss-number font-semibold text-white">500/500</span> successful ·{" "}
                  <span className="ss-number font-semibold text-white">0</span> errors/timeouts
                </p>
              </div>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {latencyMetrics.map(([label, value]) => (
              <div key={label} className="rounded-md border border-white/[0.08] bg-slate-950/35 p-3">
                <dt className="ss-eyebrow text-slate-500">{label}</dt>
                <dd className="ss-number mt-2 text-base font-semibold text-white">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="grid gap-2 rounded-md border border-white/[0.08] bg-slate-950/30 p-3 text-[11.5px] leading-5 text-slate-300 sm:grid-cols-2">
          <p>
            <span className="font-medium text-slate-100">Environment:</span> Apple M2 · 8 GiB RAM · macOS 26.5.2 · Python 3.12.10 · one local Uvicorn worker.
          </p>
          <p>
            <span className="font-medium text-slate-100">Reliability configuration:</span> 16-request admission gate · 5-second server/client timeout.
          </p>
        </div>

        <div role="note" className="rounded-md border border-amber-200/20 bg-amber-300/[0.045] p-3 text-xs leading-5 text-amber-50">
          Local synthetic serving-path measurement only. It does not measure real-model accuracy, public-network performance, Indian/Razorpay traffic, or production capacity. It will be rerun against the final release candidate.
        </div>

        <a
          href={benchmarkReportHref}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-teal-100 underline decoration-teal-200/45 underline-offset-4 transition hover:text-white"
        >
          Read the dated benchmark report in the repository
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      </DashboardPanel>
    </section>
  );
}
