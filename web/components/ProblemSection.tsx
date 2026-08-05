"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dashboardData, formatInteger } from "@/data/metrics";
import { formatCompact } from "@/lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";

const chartData = [
  { label: "Legitimate", count: dashboardData.dataset.legitimateTransactions },
  { label: "Fraud", count: dashboardData.dataset.fraudTransactions },
];

export function ProblemSection() {
  return (
    <Section
      id="problem"
      eyebrow="Problem"
      title="Fraud detection breaks accuracy-first thinking"
      description={`With fraud at ${dashboardData.dataset.fraudPrevalencePercent.toFixed(4)}% of transactions, a naive majority classifier reaches ${dashboardData.dataset.majorityClassAccuracyPercent.toFixed(4)}% accuracy while detecting none of the fraud class.`}
    >
      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle>Class imbalance</CardTitle>
              <span className="text-xs font-medium text-slate-400">Logarithmic count scale</span>
            </div>
            <CardDescription>
              The minority class is the business-critical class.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ left: 10, right: 10 }}>
                  <CartesianGrid stroke="rgba(148,163,184,0.16)" vertical={false} />
                  <XAxis dataKey="label" stroke="#94a3b8" tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="#94a3b8"
                    tickLine={false}
                    axisLine={false}
                    scale="log"
                    domain={[100, 1_000_000]}
                    tickFormatter={(value) => formatCompact(Number(value))}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    contentStyle={{
                      background: "#07111f",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 8,
                      color: "#e2e8f0",
                    }}
                  />
                  <Bar dataKey="count" fill="#67e8f9" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
          {[
            ["Legitimate", formatInteger(dashboardData.dataset.legitimateTransactions)],
            ["Fraud", formatInteger(dashboardData.dataset.fraudTransactions)],
            ["Imbalance ratio", `${dashboardData.dataset.imbalanceRatio.toFixed(2)} : 1`],
          ].map(([label, value]) => (
            <Card key={label}>
              <CardContent className="p-5">
                <p className="text-sm text-slate-400">{label}</p>
                <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </Section>
  );
}
