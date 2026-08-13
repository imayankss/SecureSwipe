import { dashboardData, formatInteger } from "@/data/metrics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";

export function ConfusionMatrix() {
  const confusionMatrix = dashboardData.finalEvaluation;
  const cells = [
    { label: "True negative", short: "TN", value: confusionMatrix.true_negatives, tone: "text-emerald-200", detail: "Legitimate → legitimate" },
    { label: "False positive", short: "FP", value: confusionMatrix.false_positives, tone: "text-amber-200", detail: "Legitimate → review" },
    { label: "False negative", short: "FN", value: confusionMatrix.false_negatives, tone: "text-rose-200", detail: "Fraud → legitimate" },
    { label: "True positive", short: "TP", value: confusionMatrix.true_positives, tone: "text-cyan-200", detail: "Fraud → review" },
  ];

  return (
    <Section
      id="confusion"
      eyebrow="Historical reported random holdout"
      title={`Recorded threshold: ${confusionMatrix.threshold.toFixed(2)}`}
      description="This already-observed random-holdout confusion matrix is locked historical evidence, not a current production or out-of-time estimate."
    >
      <Card>
        <CardHeader>
          <CardTitle>Historical reported confusion matrix</CardTitle>
          <CardDescription>
            {formatInteger(confusionMatrix.total_samples)} test rows · rows are actual classes · columns are decisions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {cells.map((cell) => (
              <div key={cell.label} className="rounded-lg border border-white/10 bg-slate-950/70 p-5">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-slate-400">{cell.label}</p>
                  <span className="font-mono text-xs text-slate-400">{cell.short}</span>
                </div>
                <p className={`mt-2 text-4xl font-semibold ${cell.tone}`}>{formatInteger(cell.value)}</p>
                <p className="mt-2 text-xs text-slate-400">{cell.detail}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
