"use client";

import Image from "next/image";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { shapFeatures } from "@/data/metrics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Section } from "@/components/Section";

export function ShapSection() {
  return (
    <Section
      id="shap"
      eyebrow="Explainability"
      title="Top factors influencing fraud predictions"
      description="SHAP summarizes how the locked XGBoost model used anonymized transformed features on a validation sample."
    >
      <div className="grid gap-6 lg:grid-cols-[1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>SHAP feature importance</CardTitle>
            <CardDescription>Mean absolute SHAP value by feature.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shapFeatures} layout="vertical" margin={{ left: 8, right: 20 }}>
                  <CartesianGrid stroke="rgba(148,163,184,0.16)" horizontal={false} />
                  <XAxis type="number" stroke="#94a3b8" tickLine={false} axisLine={false} />
                  <YAxis dataKey="feature" type="category" stroke="#94a3b8" tickLine={false} axisLine={false} width={70} />
                  <Tooltip
                    contentStyle={{
                      background: "#07111f",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 8,
                      color: "#e2e8f0",
                    }}
                  />
                  <Bar dataKey="importance" fill="#67e8f9" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Generated SHAP plot</CardTitle>
            <CardDescription>
              V1-V28 are anonymized PCA features, so explanations are model-behavior signals.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Image
              src="/images/shap_summary_bar.png"
              alt="SHAP summary bar chart"
              width={900}
              height={520}
              className="rounded-lg border border-white/10"
            />
            <Table>
              <THead>
                <TR>
                  <TH>Feature</TH>
                  <TH>Importance</TH>
                </TR>
              </THead>
              <TBody>
                {shapFeatures.map((feature) => (
                  <TR key={feature.feature}>
                    <TD>{feature.feature}</TD>
                    <TD>{feature.importance.toFixed(4)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </Section>
  );
}
