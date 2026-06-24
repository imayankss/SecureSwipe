"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { finalMetrics, modelComparison } from "@/data/metrics";
import { MetricCard } from "@/components/MetricCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";

export function ModelPerformance() {
  return (
    <Section
      id="performance"
      eyebrow="Model Performance"
      title="XGBoost leads on fraud-focused metrics"
      description="The final evaluation reports PR-AUC, ROC-AUC, precision, recall, and F1 at the locked business threshold."
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {finalMetrics.map((metric) => (
          <MetricCard key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Model comparison</CardTitle>
          <CardDescription>PR-AUC is the primary metric for the rare fraud class.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelComparison}>
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
                <Bar dataKey="prAuc" name="PR-AUC" fill="#67e8f9" radius={[5, 5, 0, 0]} />
                <Bar dataKey="rocAuc" name="ROC-AUC" fill="#86efac" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
