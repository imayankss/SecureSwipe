import { SlidersHorizontal } from "lucide-react";
import { thresholdResults } from "@/data/metrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/Section";

export function ThresholdCards() {
  return (
    <Section
      id="thresholds"
      eyebrow="Threshold Tuning"
      title="The operating point is a business decision"
      description="The recommended threshold keeps validation recall above 80% while improving precision compared with lower eligible thresholds."
    >
      <div className="grid gap-5 md:grid-cols-3">
        {thresholdResults.map((item) => (
          <Card key={item.name}>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>{item.name}</CardTitle>
                {item.name === "Business Threshold" ? <Badge>Recommended</Badge> : null}
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <SlidersHorizontal className="h-5 w-5 text-cyan-200" />
                <p className="text-3xl font-semibold text-white">{item.threshold}</p>
              </div>
              <dl className="mt-5 grid grid-cols-3 gap-3 text-sm">
                <div>
                  <dt className="text-slate-400">Precision</dt>
                  <dd className="mt-1 font-semibold text-white">{item.precision}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">Recall</dt>
                  <dd className="mt-1 font-semibold text-white">{item.recall}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">F1</dt>
                  <dd className="mt-1 font-semibold text-white">{item.f1}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  );
}
