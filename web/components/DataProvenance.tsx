import { CheckCircle2, Database, FileJson2, LockKeyhole } from "lucide-react";
import { dashboardData } from "@/data/metrics";
import { formatDate } from "@/lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Section } from "@/components/Section";

const safeguards = [
  {
    title: "No private dataset",
    description: "The original transaction CSV is ignored and is not bundled or served.",
    Icon: Database,
  },
  {
    title: "No request-time ML",
    description: "The site never trains or deserializes Python model artifacts during visits.",
    Icon: LockKeyhole,
  },
  {
    title: "Deterministic export",
    description: "The public JSON is rebuilt from tracked reports with cross-file checks.",
    Icon: FileJson2,
  },
];

export function DataProvenance() {
  return (
    <Section
      id="provenance"
      eyebrow="Data provenance"
      title="Every displayed result traces to a tracked artifact"
      description="The web layer is intentionally smaller than the ML pipeline: it receives only aggregate evaluation outputs and explanatory figures."
    >
      <div className="grid gap-5 lg:grid-cols-3">
        {safeguards.map(({ title, description, Icon }) => (
          <Card key={title}>
            <CardContent className="p-5">
              <Icon className="h-5 w-5 text-cyan-200" aria-hidden="true" />
              <h3 className="mt-4 font-semibold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-300">{description}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Export manifest</CardTitle>
          <CardDescription>
            Artifact timestamp {formatDate(dashboardData.project.artifactGeneratedAt)} · schema v
            {dashboardData.schemaVersion}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2">
            {dashboardData.sources.map((source) => (
              <div
                key={source}
                className="flex items-start gap-3 rounded-lg border border-white/10 bg-slate-950/55 p-3 font-mono text-xs text-slate-300"
              >
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" aria-hidden="true" />
                <span className="break-all">{source}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 break-all text-xs text-slate-500">
            Source digest: {dashboardData.project.sourceDigestSha256}
          </p>
        </CardContent>
      </Card>
    </Section>
  );
}
