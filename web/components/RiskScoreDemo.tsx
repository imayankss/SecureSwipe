"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Gauge, Info } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/Section";
import { EvidenceLabel } from "@/components/EvidenceLabel";
import { dashboardData } from "@/data/metrics";

const REQUEST_TIMEOUT_MS = 3_000;
const EXAMPLE_FEATURES = {
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
  | { status: "success"; decision: string; score: number; modelVersion: string }
  | { status: "empty" }
  | { status: "unavailable"; message: string }
  | { status: "error"; message: string };

type LivePrediction = {
  schema_version: "1.0";
  request_id: string;
  raw_score: number;
  calibrated_probability: number | null;
  decision_score: number;
  score_type: "raw_score" | "calibrated_probability";
  operating_threshold: number;
  decision: "review" | "pass";
  model_version: string;
};

function apiUrlFromEnvironment() {
  const raw = process.env.NEXT_PUBLIC_SECURESWIPE_API_URL?.trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function isPrediction(value: unknown): value is LivePrediction {
  if (typeof value !== "object" || value === null) return false;
  const prediction = value as Record<string, unknown>;
  return (
    prediction.schema_version === "1.0" &&
    typeof prediction.request_id === "string" && prediction.request_id.length > 0 &&
    typeof prediction.raw_score === "number" && Number.isFinite(prediction.raw_score) &&
    (prediction.calibrated_probability === null ||
      (typeof prediction.calibrated_probability === "number" &&
        Number.isFinite(prediction.calibrated_probability))) &&
    typeof prediction.decision_score === "number" && Number.isFinite(prediction.decision_score) &&
    (prediction.score_type === "raw_score" || prediction.score_type === "calibrated_probability") &&
    typeof prediction.operating_threshold === "number" &&
    Number.isFinite(prediction.operating_threshold) &&
    (prediction.decision === "review" || prediction.decision === "pass") &&
    typeof prediction.model_version === "string" && prediction.model_version.length > 0
  );
}

export function RiskScoreDemo({ apiBaseUrl = apiUrlFromEnvironment() }: { apiBaseUrl?: string | null } = {}) {
  const thresholdPercent = dashboardData.finalEvaluation.threshold * 100;
  const [score, setScore] = useState(thresholdPercent);
  const [liveState, setLiveState] = useState<LiveState>({ status: "idle" });
  const requiresReview = score >= thresholdPercent;

  async function runGenuineDemoInference() {
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
        body: JSON.stringify(EXAMPLE_FEATURES),
        signal: controller.signal,
      });
      if (response.status === 503) {
        setLiveState({
          status: "unavailable",
          message: "The reference API is unavailable or at capacity; the static example remains active.",
        });
        return;
      }
      if (response.status === 504) {
        setLiveState({
          status: "unavailable",
          message: "The reference API timed out; inference remains unavailable / fail closed.",
        });
        return;
      }
      if (!response.ok) {
        throw new Error(`API returned ${response.status}.`);
      }
      const payload: unknown = await response.json();
      if (!isPrediction(payload)) {
        setLiveState({ status: "empty" });
        return;
      }
      setLiveState({
        status: "success",
        decision: payload.decision,
        score: payload.decision_score,
        modelVersion: payload.model_version,
      });
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
                  <p className="mt-1 text-xs text-slate-400">Score &ge; {thresholdPercent.toFixed(0)}</p>
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
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-white">Optional genuine demo inference check</p>
                  <EvidenceLabel type="genuine-demo-inference" />
                </div>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  Sends one fixed all-zero example feature vector to the verified model bundle, only when you opt in. No customer or transaction data is used.
                </p>
              </div>
              <button
                type="button"
                onClick={runGenuineDemoInference}
                disabled={liveState.status === "loading"}
                className="rounded-lg border border-cyan-200/25 bg-cyan-300/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-wait disabled:opacity-60"
              >
                {liveState.status === "loading" ? "Checking API…" : "Try genuine inference"}
              </button>
            </div>
            <div className="mt-4" aria-live="polite">
              {liveState.status === "idle" ? (
                <p className="text-xs text-slate-400">Static fallback active until the genuine inference check is requested.</p>
              ) : null}
              {liveState.status === "loading" ? <p role="status" aria-label="Genuine demo inference status" className="text-sm text-cyan-100">Contacting the reference API…</p> : null}
              {liveState.status === "success" ? (
                <p role="status" aria-label="Genuine demo inference status" className="text-sm text-emerald-100">
                  Genuine demo inference result: {liveState.decision} at score {liveState.score.toFixed(3)}. Model bundle: {liveState.modelVersion}.
                </p>
              ) : null}
              {liveState.status === "empty" ? <p role="status" aria-label="Genuine demo inference status" className="text-sm text-amber-100">The API returned no usable prediction; static fallback remains active.</p> : null}
              {liveState.status === "unavailable" || liveState.status === "error" ? (
                <p role="status" aria-label="Genuine demo inference status" className="text-sm text-amber-100">{liveState.message}</p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
