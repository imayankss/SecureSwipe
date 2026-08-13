import { ArrowRight, DatabaseZap, GitBranch, ShieldCheck } from "lucide-react";
import { dashboardData, heroMetrics } from "@/data/metrics";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/MetricCard";

export function Hero() {
  return (
    <section id="overview" className="relative overflow-hidden px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <div>
          <Badge>
            <ShieldCheck className="h-3.5 w-3.5" />
            Verified artifacts · Safe demonstration mode
          </Badge>
          <h1 className="mt-6 max-w-4xl text-5xl font-semibold tracking-tight text-white sm:text-7xl">
            Fraud decisions,
            <span className="block bg-gradient-to-r from-cyan-200 to-emerald-200 bg-clip-text text-transparent">
              made inspectable.
            </span>
          </h1>
          <p className="mt-4 max-w-3xl text-xl font-medium text-cyan-100">
            SecureSwipe fraud detection and transaction risk analytics
          </p>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
            Explore an end-to-end XGBoost workflow through real validation and test
            outputs: model comparison, threshold trade-offs, PR-focused evaluation,
            and SHAP explainability.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button href="#performance">
              View Results <ArrowRight className="h-4 w-4" />
            </Button>
            <Button
              href={dashboardData.project.repository}
              target="_blank"
              rel="noopener noreferrer"
              variant="secondary"
            >
              <GitBranch className="h-4 w-4" />
              GitHub Repository
            </Button>
          </div>
          <div className="signal-strip mt-8 max-w-xl rounded-lg border border-white/10 bg-slate-950/45 p-4">
            <div className="flex items-center justify-between gap-4 text-xs text-slate-400">
              <span>deployment architecture</span>
              <span className="font-medium text-cyan-100">precomputed · static</span>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div className="h-full w-full rounded-full bg-gradient-to-r from-cyan-200 via-emerald-200 to-cyan-200" />
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 [animation:softPulse_1.8s_ease-in-out_infinite]" />
              <DatabaseZap className="h-3.5 w-3.5 text-cyan-200" aria-hidden="true" />
              no transaction data, retraining, or model loading in web requests
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {heroMetrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>
      </div>
    </section>
  );
}
