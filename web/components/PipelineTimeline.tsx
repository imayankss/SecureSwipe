import { CheckCircle2 } from "lucide-react";
import { pipelineSteps } from "@/data/metrics";
import { Card, CardContent } from "@/components/ui/card";
import { Section } from "@/components/Section";

export function PipelineTimeline() {
  return (
    <Section
      id="pipeline"
      eyebrow="Pipeline"
      title="Expensive ML work stays outside the request path"
      description="Training, threshold search, curve generation, and SHAP analysis run in the Python workflow. The deployable frontend serves only the reviewed export; no provider deployment is verified here."
    >
      <Card className="border-teal-200/15">
        <CardContent className="p-4 sm:p-5">
          <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-7">
            {pipelineSteps.map((step, index) => (
              <li key={step} className="relative min-w-0">
                <div className="flex h-full flex-col gap-3 rounded-lg border border-white/10 bg-slate-950/45 p-4 transition-colors hover:border-teal-200/25 hover:bg-slate-950/60">
                  <CheckCircle2 className="h-5 w-5 text-teal-200" />
                  <span className="ss-number text-xs text-slate-400">{String(index + 1).padStart(2, "0")}</span>
                  <span className="text-sm font-medium leading-5 text-white">{step}</span>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </Section>
  );
}
