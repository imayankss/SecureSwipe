"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Gauge, Info } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/Section";
import { dashboardData } from "@/data/metrics";

const REQUEST_TIMEOUT_MS = 3_000;
const SYNTHETIC_FEATURES = {
  Time: 0,
  V1: 0,
  V2: 0,
  V3: 0,
  V4: 0,
  V5: 0,
  V6: 0,
  V7: 0,
  V8: 0,
  V9: 0,
  V10: 0,
  V11: 0,
  V12: 0,
  V13: 0,
  V14: 0,
  V15: 0,
  V16: 0,
  V17: 0,
  V18: 0,
  V19: 0,
  V20: 0,
  V21: 0,
  V22: 0,
  V23: 0,
  V24: 0,
  V25: 0,
  V26: 0,
  V27: 0,
  V28: 0,
  Amount: 0,
} as const;

type LiveState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; decision: string; score: number }
  | { status: "empty" }
  | { status: "unavailable"; message: string }
  | { status: "error"; message: string };

type LivePrediction = {
  decision?: unknown;
  decision_score?: unknown;
};

function apiUrlFromEnvironment() {
  return process.env.NEXT_PUBLIC_SECURESWIPE_API_URL?.trim().replace(/\/$/, "") || null;
}

function isPrediction(value: unknown): value is LivePrediction {
  return typeof value === "object" && value !== null;
}

export function RiskScoreDemo({ apiBaseUrl = apiUrlFromEnvironment() }: { apiBaseUrl?: string | null } = {}) {
  const thresholdPercent = dashboardData.finalEvaluation.threshold * 100;
  const [score, setScore] = useState(thresholdPercent);
  const [liveState, setLiveState] = useState<LiveState>({ status: "idle" });
  const requiresReview = score >= thresholdPercent;

  async function runSyntheticPrediction() {
    if (!apiBaseUrl) {
      setLiveState({
        status: "unavailable",
        message: "Live demo is not configured; the safe static example remains active.",
      });
      return;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    setLiveState({ status: "loading" });
    try {
      const response = await fetch(`${apiBaseUrl}/v1/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(SYNTHETIC_FEATURES),
        signal: controller.signal,
      });
      if (response.status === 503) {
        setLiveState({ status: "unavailable", message: "The reference API is not ready." });
        return;
      }
      if (!response.ok) {
        throw new Error(`API returned ${response.status}.`);
      }
      const payload: unknown = await response.json();
      if (!isPrediction(payload) || typeof payload.decision !== "string" || typeof payload.decision_score !== "number") {
        setLiveState({ status: "empty" });
        return;
      }
      setLiveState({ status: "success", decision: payload.decision, score: payload.decision_score });
    } catch (error) {
      const message = error instanceof DOMException && error.name === "AbortError"
        ? "The live API timed out; the static example is still available."
        : "The live API could not be reached; the static example is still available.";
      setLiveState({ status: "error", message });
    } finally {
      window.clearTimeout(timeout);
    }
  }

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
              role="status"
              aria-live="polite"
              aria-label="Hypothetical review decision"
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
          <div className="mt-6 rounded-lg border border-white/10 bg-slate-950/30 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-white">Optional synthetic API check</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  Sends an all-zero synthetic feature vector only when you opt in. No customer or transaction data is used.
                </p>
              </div>
              <button
                type="button"
                onClick={runSyntheticPrediction}
                disabled={liveState.status === "loading"}
                className="rounded-lg border border-cyan-200/25 bg-cyan-300/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-wait disabled:opacity-60"
              >
                {liveState.status === "loading" ? "Checking API…" : "Try synthetic API"}
              </button>
            </div>
            <div className="mt-4" aria-live="polite">
              {liveState.status === "idle" ? (
                <p className="text-xs text-slate-400">Static fallback active until the API check is requested.</p>
              ) : null}
              {liveState.status === "loading" ? <p role="status" aria-label="Synthetic API status" className="text-sm text-cyan-100">Contacting the reference API…</p> : null}
              {liveState.status === "success" ? (
                <p role="status" aria-label="Synthetic API status" className="text-sm text-emerald-100">
                  Synthetic API result: {liveState.decision} at score {liveState.score.toFixed(3)}.
                </p>
              ) : null}
              {liveState.status === "empty" ? <p role="status" aria-label="Synthetic API status" className="text-sm text-amber-100">The API returned no usable prediction; static fallback remains active.</p> : null}
              {liveState.status === "unavailable" || liveState.status === "error" ? (
                <p role="status" aria-label="Synthetic API status" className="text-sm text-amber-100">{liveState.message}</p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
