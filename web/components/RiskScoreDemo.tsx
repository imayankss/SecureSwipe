"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Gauge, Info } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/Section";
import { dashboardData } from "@/data/metrics";

export function RiskScoreDemo() {
  const thresholdPercent = dashboardData.finalEvaluation.threshold * 100;
  const [score, setScore] = useState(thresholdPercent);
  const requiresReview = score >= thresholdPercent;

  return (
    <Section
      id="risk"
      eyebrow="Decision demonstration"
      title="See how a score crosses the review threshold"
      description="This user-controlled score explains the decision rule only. It is not a transaction, a live prediction, or a claim about a real customer."
    >
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Model score decision rule</CardTitle>
              <CardDescription>Hypothetical, user-controlled XGBoost score.</CardDescription>
            </div>
            <Badge
              className={
                requiresReview
                  ? "border-rose-300/30 bg-rose-300/10 text-rose-100"
                  : "border-emerald-300/30 bg-emerald-300/10 text-emerald-100"
              }
            >
              {requiresReview ? (
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {requiresReview ? "Send to review" : "Below review threshold"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 lg:grid-cols-[0.7fr_1fr] lg:items-center">
            <div>
              <p className="text-6xl font-semibold text-white">{score.toFixed(0)}</p>
              <p className="mt-2 text-sm text-slate-300">Hypothetical model score / 100</p>
              <p className="mt-1 text-sm text-slate-400">Review threshold: {thresholdPercent.toFixed(0)}</p>
            </div>
            <div className="space-y-5">
              <Progress value={score} />
              <label htmlFor="score-control" className="flex items-center gap-2 text-sm font-medium text-white">
                <Gauge className="h-4 w-4 text-cyan-200" aria-hidden="true" />
                Adjust hypothetical score
              </label>
              <input
                id="score-control"
                type="range"
                min={0}
                max={100}
                step={1}
                value={score}
                onChange={(event) => setScore(Number(event.target.value))}
                className="w-full accent-cyan-300"
                aria-valuetext={`${score.toFixed(0)} out of 100`}
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setScore(thresholdPercent - 1)}
                  className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-cyan-200/25 hover:bg-white/[0.08]"
                >
                  Just below · {(thresholdPercent - 1).toFixed(0)}
                </button>
                <button
                  type="button"
                  onClick={() => setScore(thresholdPercent)}
                  className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-cyan-200/25 hover:bg-white/[0.08]"
                >
                  At threshold · {thresholdPercent.toFixed(0)}
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-emerald-200/15 bg-emerald-300/[0.04] p-4">
                  <CheckCircle2 className="h-5 w-5 text-emerald-200" aria-hidden="true" />
                  <p className="mt-3 text-sm font-medium text-white">Below threshold</p>
                  <p className="mt-1 text-xs text-slate-400">Score &lt; {thresholdPercent.toFixed(0)}</p>
                </div>
                <div className="rounded-lg border border-rose-200/15 bg-rose-300/[0.04] p-4">
                  <AlertTriangle className="h-5 w-5 text-rose-200" aria-hidden="true" />
                  <p className="mt-3 text-sm font-medium text-white">Manual review signal</p>
                  <p className="mt-1 text-xs text-slate-400">Score ≥ {thresholdPercent.toFixed(0)}</p>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-6 flex gap-3 rounded-lg border border-cyan-200/15 bg-cyan-300/[0.035] p-4 text-sm leading-6 text-slate-300">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-cyan-200" aria-hidden="true" />
            The project has not calibrated this class-weighted XGBoost score as a real-world fraud probability. Production policy would also need cost, latency, monitoring, and human-review controls.
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
