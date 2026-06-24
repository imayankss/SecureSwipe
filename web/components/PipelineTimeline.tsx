import { CheckCircle2 } from "lucide-react";
import { pipelineSteps } from "@/data/metrics";
import { Card, CardContent } from "@/components/ui/card";
import { Section } from "@/components/Section";

export function PipelineTimeline() {
  return (
    <Section
      id="pipeline"
      eyebrow="Pipeline"
      title="A complete ML workflow, packaged for review"
      description="Each stage is separated into reusable scripts, modules, reports, and tests."
    >
      <Card>
        <CardContent className="p-5">
          <ol className="grid gap-4 md:grid-cols-7">
            {pipelineSteps.map((step, index) => (
              <li key={step} className="relative">
                <div className="flex h-full flex-col gap-3 rounded-lg border border-white/10 bg-slate-950/60 p-4">
                  <CheckCircle2 className="h-5 w-5 text-emerald-300" />
                  <span className="text-xs text-slate-500">0{index + 1}</span>
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
