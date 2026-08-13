"use client";

import { useMemo, useState } from "react";
import { Activity, BellRing, CheckCircle2, CircleOff, SlidersHorizontal } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { dashboardData, formatInteger, formatPercent } from "@/data/metrics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/Section";

export function ThresholdCards() {
  const points = dashboardData.thresholdAnalysis.points;
  const operatingThreshold = dashboardData.finalEvaluation.threshold;
  const operatingIndex = points.findIndex((point) => point.threshold === operatingThreshold);
  const [selectedIndex, setSelectedIndex] = useState(operatingIndex >= 0 ? operatingIndex : 0);
  const selected = points[selectedIndex];
  const chartData = useMemo(
    () =>
      points.map((point) => ({
        threshold: point.threshold,
        Precision: point.precision,
        Recall: point.recall,
        F1: point.f1,
      })),
    [points],
  );
  const reviewRate = selected.reviewWorkload / dashboardData.thresholdAnalysis.validationRows;

  return (
    <Section
      id="thresholds"
      eyebrow="Threshold Tuning"
      title="Explore the recorded validation trade-off"
      description="Move through the tracked 0.01–0.99 threshold sweep. Every outcome below is a precomputed validation result; the control does not rerun the model."
    >
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <SlidersHorizontal className="h-5 w-5 text-cyan-200" aria-hidden="true" />
                <CardTitle>Validation threshold explorer</CardTitle>
              </div>
              <CardDescription className="mt-2">
                XGBoost · {formatInteger(dashboardData.thresholdAnalysis.validationRows)} rows · {dashboardData.thresholdAnalysis.validationFrauds} fraud cases
              </CardDescription>
            </div>
            {selected.threshold === operatingThreshold ? <Badge>Selected operating point</Badge> : null}
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-white/10 bg-slate-950/55 p-4 sm:p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Threshold</p>
                <output htmlFor="threshold-control" className="mt-1 block text-4xl font-semibold text-white">
                  {selected.threshold.toFixed(2)}
                </output>
              </div>
              <div className="flex flex-wrap gap-2">
                {dashboardData.thresholdAnalysis.selected.map((item) => {
                  const index = points.findIndex((point) => point.threshold === item.threshold);
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setSelectedIndex(index)}
                      className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-cyan-200/25 hover:bg-white/[0.08]"
                    >
                      {item.label} · {item.threshold.toFixed(2)}
                    </button>
                  );
                })}
              </div>
            </div>
            <label htmlFor="threshold-control" className="sr-only">
              Select a precomputed validation threshold
            </label>
            <input
              id="threshold-control"
              type="range"
              min={0}
              max={points.length - 1}
              step={1}
              value={selectedIndex}
              onChange={(event) => setSelectedIndex(Number(event.target.value))}
              className="mt-6 w-full accent-cyan-300"
              aria-valuetext={`Threshold ${selected.threshold.toFixed(2)}`}
            />
            <div className="mt-2 flex justify-between text-xs text-slate-400">
              <span>{points[0].threshold.toFixed(2)}</span>
              <span>{points.at(-1)?.threshold.toFixed(2)}</span>
            </div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              { label: "Precision", value: formatPercent(selected.precision), Icon: Activity },
              { label: "Recall", value: formatPercent(selected.recall), Icon: CheckCircle2 },
              { label: "F1 score", value: formatPercent(selected.f1), Icon: SlidersHorizontal },
              { label: "Review workload", value: formatInteger(selected.reviewWorkload), Icon: BellRing },
              { label: "Review rate", value: formatPercent(reviewRate, 3), Icon: CircleOff },
            ].map(({ label, value, Icon }) => {
              const IconComponent = Icon;
              return (
                <div key={label} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                  <IconComponent className="h-4 w-4 text-cyan-200" aria-hidden="true" />
                  <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">{label}</p>
                  <p className="mt-1 text-xl font-semibold text-white">{value}</p>
                </div>
              );
            })}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="h-80 rounded-xl border border-white/10 bg-slate-950/40 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 12, right: 16, left: -12, bottom: 4 }}>
                  <CartesianGrid stroke="rgba(148,163,184,0.14)" vertical={false} />
                  <XAxis dataKey="threshold" stroke="#94a3b8" tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 1]} stroke="#94a3b8" tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: "#07111f",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 8,
                      color: "#e2e8f0",
                    }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="Precision" stroke="#67e8f9" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="Recall" stroke="#86efac" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="F1" stroke="#fbbf24" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="grid grid-cols-2 gap-3" aria-label="Validation confusion matrix at selected threshold">
              {[
                ["True negative", selected.trueNegatives, "text-emerald-200"],
                ["False positive", selected.falsePositives, "text-amber-200"],
                ["False negative", selected.falseNegatives, "text-rose-200"],
                ["True positive", selected.truePositives, "text-cyan-200"],
              ].map(([label, value, tone]) => (
                <div key={String(label)} className="rounded-lg border border-white/10 bg-slate-950/55 p-4">
                  <p className="text-xs text-slate-400">{label}</p>
                  <p className={`mt-2 text-3xl font-semibold ${tone}`}>{formatInteger(Number(value))}</p>
                </div>
              ))}
            </div>
          </div>
          <p className="mt-5 rounded-lg border border-amber-200/15 bg-amber-300/[0.04] p-4 text-sm leading-6 text-slate-300">
            {dashboardData.thresholdAnalysis.costAnalysisNote}
          </p>
        </CardContent>
      </Card>
    </Section>
  );
}
