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
      eyebrow="Final Evaluation"
      title={`Locked test threshold: ${confusionMatrix.threshold.toFixed(2)}`}
      description="The model and operating point were selected on validation data before this held-out test confusion matrix was produced."
    >
      <Card>
        <CardHeader>
          <CardTitle>Final confusion matrix</CardTitle>
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
                  <span className="font-mono text-xs text-slate-500">{cell.short}</span>
                </div>
                <p className={`mt-2 text-4xl font-semibold ${cell.tone}`}>{formatInteger(cell.value)}</p>
                <p className="mt-2 text-xs text-slate-500">{cell.detail}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
