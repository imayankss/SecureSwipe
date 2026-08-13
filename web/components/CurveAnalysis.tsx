import Image from "next/image";
import { dashboardData, formatMetric } from "@/data/metrics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";

const curves = [
  {
    title: "Precision–recall curve",
    description:
      "The primary curve for the rare fraud class. The dashed baseline is validation prevalence.",
    image: dashboardData.curves.precisionRecall.image,
    value: `Average precision ${formatMetric(dashboardData.curves.precisionRecall.averagePrecision)}`,
    alt: "Validation precision-recall curve for the selected XGBoost model",
  },
  {
    title: "ROC curve",
    description:
      "True-positive rate against false-positive rate across validation thresholds.",
    image: dashboardData.curves.roc.image,
    value: `ROC-AUC ${formatMetric(dashboardData.curves.roc.auc)}`,
    alt: "Validation ROC curve for the selected XGBoost model",
  },
];

export function CurveAnalysis() {
  return (
    <Section
      id="curves"
      eyebrow="Validation curves"
      title="Performance across the full decision range"
      description="These precomputed plots come from the validation split used for model selection and threshold analysis—not from the final test set."
    >
      <div className="grid gap-6 lg:grid-cols-2">
        {curves.map((curve) => (
          <Card key={curve.title}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>{curve.title}</CardTitle>
                  <CardDescription className="mt-2">{curve.description}</CardDescription>
                </div>
                <span className="rounded-full border border-cyan-200/20 bg-cyan-300/10 px-3 py-1 text-xs font-semibold text-cyan-100">
                  {curve.value}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <Image
                src={curve.image}
                alt={curve.alt}
                width={1200}
                height={900}
                unoptimized
                sizes="(max-width: 1024px) 100vw, 50vw"
                className="w-full rounded-lg border border-white/10 bg-white"
              />
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  );
}
