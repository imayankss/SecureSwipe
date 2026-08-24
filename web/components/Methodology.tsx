import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { dashboardData, formatInteger } from "@/data/metrics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const methodItems = [
  ["Preprocessing", dashboardData.methodology.preprocessing],
  ["Imbalance handling", dashboardData.methodology.imbalanceHandling],
  ["Selection", dashboardData.methodology.selection],
  ["Final evaluation", dashboardData.methodology.finalTest],
];

export function Methodology() {
  return (
    <Section
      id="methodology"
      eyebrow="Methodology"
      title="Designed to separate fitting, selection, and final evaluation"
      description={dashboardData.methodology.splitStrategy}
    >
      <div className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
        <Card className="border-teal-200/15">
          <CardHeader>
            <CardTitle>Stratified data split</CardTitle>
            <CardDescription>Fraud prevalence is preserved across all partitions.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto rounded-b-xl bg-slate-950/20">
            <Table>
              <THead>
                <TR>
                  <TH>Split</TH>
                  <TH>Rows</TH>
                  <TH>Fraud</TH>
                  <TH>Fraud rate</TH>
                </TR>
              </THead>
              <TBody>
                {dashboardData.dataset.splits.map((split) => (
                  <TR key={split.name}>
                    <TD className="capitalize">{split.name}</TD>
                    <TD>{formatInteger(split.rows)}</TD>
                    <TD>{formatInteger(split.fraud)}</TD>
                    <TD>{split.fraudPercent.toFixed(4)}%</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
        <div className="grid gap-3">
          {methodItems.map(([title, description]) => (
            <Card key={title} className="hover:border-teal-200/25">
              <CardContent className="flex gap-4 p-4">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-teal-200" aria-hidden="true" />
                <div>
                  <h3 className="font-medium text-white">{title}</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-300">{description}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
      <Card className="mt-5 border-amber-200/20 bg-amber-300/[0.04]">
        <CardContent className="flex gap-4 p-5">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-200" aria-hidden="true" />
          <div>
            <h3 className="font-semibold text-white">Known limitations</h3>
            <ul className="mt-3 grid gap-2 text-sm leading-6 text-slate-300 md:grid-cols-2">
              {dashboardData.limitations.map((limitation) => (
                <li key={limitation}>• {limitation}</li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
