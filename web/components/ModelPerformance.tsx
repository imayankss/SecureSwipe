"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dashboardData, finalMetrics, formatPercent, modelComparison } from "@/data/metrics";
import { MetricCard } from "@/components/MetricCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";
import { EvidenceLabel } from "@/components/EvidenceLabel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export function ModelPerformance() {
  return (
    <Section
      id="performance"
      eyebrow="Model Performance"
      title="Validation selected the model; the test split records the historical result"
      description="All four models below were compared on one validation split. Final cards preserve the separately held-out random test observation; they are not out-of-time or deployment evidence."
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-slate-300">Locked test evaluation</p>
          <EvidenceLabel type="historical-evaluation" />
        </div>
        <span className="rounded-full border border-emerald-200/20 bg-emerald-300/10 px-3 py-1 text-xs font-semibold text-emerald-100">
          {dashboardData.finalEvaluation.displayName} · threshold {dashboardData.finalEvaluation.threshold.toFixed(2)}
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {finalMetrics.map((metric) => (
          <MetricCard key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Validation-only model comparison</CardTitle>
          <CardDescription>
            Average precision is the recorded selection metric because the positive class is only {dashboardData.dataset.fraudPrevalencePercent.toFixed(4)}% of the full dataset.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelComparison} margin={{ left: 4, right: 12 }}>
                <CartesianGrid stroke="rgba(148,163,184,0.16)" vertical={false} />
                <XAxis dataKey="model" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} domain={[0, 1]} />
                <Tooltip
                  contentStyle={{
                    background: "#07111f",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 8,
                    color: "#e2e8f0",
                  }}
                />
                <Legend />
                <Bar dataKey="prAuc" name="Average precision" fill="#67e8f9" radius={[5, 5, 0, 0]} />
                <Bar dataKey="rocAuc" name="ROC-AUC" fill="#86efac" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-6 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Model</TH>
                  <TH>Average precision</TH>
                  <TH>ROC-AUC</TH>
                  <TH>Precision</TH>
                  <TH>Recall</TH>
                  <TH>F1</TH>
                </TR>
              </THead>
              <TBody>
                {modelComparison.map((item) => (
                  <TR key={item.model}>
                    <TD className="font-medium text-white">{item.model}</TD>
                    <TD>{item.prAuc.toFixed(4)}</TD>
                    <TD>{item.rocAuc.toFixed(4)}</TD>
                    <TD>{formatPercent(item.precision)}</TD>
                    <TD>{formatPercent(item.recall)}</TD>
                    <TD>{formatPercent(item.f1)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
