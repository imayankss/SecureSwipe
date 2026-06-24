import { AlertTriangle, CheckCircle2, CircleDot } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/Section";

const riskBands = [
  { range: "0-30%", label: "Low Risk", Icon: CheckCircle2, color: "text-emerald-200" },
  { range: "30-53%", label: "Medium Risk", Icon: CircleDot, color: "text-amber-200" },
  { range: "53-100%", label: "High Risk", Icon: AlertTriangle, color: "text-rose-200" },
];

export function RiskScoreDemo() {
  return (
    <Section
      id="risk"
      eyebrow="Risk Score Demo"
      title="A model score becomes an operational decision"
      description="The dashboard demonstrates how a fraud probability can map to a review decision using the locked threshold."
    >
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Transaction Risk Score</CardTitle>
              <CardDescription>Fake transaction example for product presentation.</CardDescription>
            </div>
            <Badge className="border-rose-300/30 bg-rose-300/10 text-rose-100">
              <AlertTriangle className="h-3.5 w-3.5" />
              Flag for Review
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 lg:grid-cols-[0.7fr_1fr] lg:items-center">
            <div>
              <p className="text-6xl font-semibold text-white">87%</p>
              <p className="mt-2 text-sm text-slate-300">Risk Level: High</p>
              <p className="mt-1 text-sm text-slate-400">Threshold Used: 0.53</p>
            </div>
            <div className="space-y-5">
              <Progress value={87} />
              <div className="grid gap-3 sm:grid-cols-3">
                {riskBands.map(({ range, label, Icon, color }) => (
                  <div key={label} className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
                    <Icon className={`h-5 w-5 ${color}`} />
                    <p className="mt-3 text-sm font-medium text-white">{label}</p>
                    <p className="mt-1 text-xs text-slate-400">{range}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
