import { confusionMatrix } from "@/data/metrics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";

export function ConfusionMatrix() {
  const cells = [
    { label: "True Negative", value: confusionMatrix.trueNegative.toLocaleString(), tone: "text-emerald-200" },
    { label: "False Positive", value: confusionMatrix.falsePositive.toLocaleString(), tone: "text-amber-200" },
    { label: "False Negative", value: confusionMatrix.falseNegative.toLocaleString(), tone: "text-rose-200" },
    { label: "True Positive", value: confusionMatrix.truePositive.toLocaleString(), tone: "text-cyan-200" },
  ];

  return (
    <Section
      id="confusion"
      eyebrow="Final Evaluation"
      title="Locked test threshold: 0.53"
      description="The test split was evaluated once after the model and threshold were already locked."
    >
      <Card>
        <CardHeader>
          <CardTitle>Final confusion matrix</CardTitle>
          <CardDescription>Rows are actual classes; columns are predicted classes.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {cells.map((cell) => (
              <div key={cell.label} className="rounded-lg border border-white/10 bg-slate-950/70 p-5">
                <p className="text-sm text-slate-400">{cell.label}</p>
                <p className={`mt-2 text-4xl font-semibold ${cell.tone}`}>{cell.value}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}
