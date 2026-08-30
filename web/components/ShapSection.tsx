import { EvidenceLabel } from "@/components/EvidenceLabel";
import { Section } from "@/components/Section";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dashboardData, shapFeatures } from "@/data/metrics";

export function ShapSection() {
  const maximumImportance = Math.max(...shapFeatures.map((feature) => feature.importance));

  return (
    <Section
      id="shap"
      eyebrow="Explainability"
      title="Historical SHAP attribution ranking"
      description={`The tracked ${dashboardData.explainability.split} ranking is output-unit and cohort unverified. It describes historical model behavior only—not causality or probability impact.`}
    >
      <Card className="overflow-hidden">
        <CardHeader className="gap-4 border-b border-white/[0.07] sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1.5">
            <CardTitle id="historical-feature-ranking-title">Historical diagnostic feature ranking</CardTitle>
            <CardDescription>
              Top 10 checked-in {dashboardData.explainability.method} values from the {dashboardData.explainability.split}.
            </CardDescription>
          </div>
          <EvidenceLabel type="historical-evaluation" />
        </CardHeader>

        <CardContent className="grid gap-5 p-4 sm:p-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(270px,0.65fr)]">
          <figure
            className="rounded-md border border-white/[0.07] bg-[#07101d] p-3 sm:p-4"
            aria-labelledby="historical-feature-ranking-title"
          >
            <div className="mb-3 grid grid-cols-[2rem_3.5rem_minmax(0,1fr)_4.25rem] items-center gap-2 border-b border-white/[0.06] px-1 pb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500 sm:grid-cols-[2.25rem_4.5rem_minmax(0,1fr)_5rem]">
              <span>Rank</span>
              <span>Feature</span>
              <span>Relative magnitude</span>
              <span className="text-right">Value</span>
            </div>
            <ol className="space-y-2.5">
              {shapFeatures.map((feature, index) => {
                const relativeWidth = `${(feature.importance / maximumImportance) * 100}%`;
                return (
                  <li
                    key={feature.feature}
                    className="grid grid-cols-[2rem_3.5rem_minmax(0,1fr)_4.25rem] items-center gap-2 rounded border border-white/[0.055] bg-slate-950/35 px-1.5 py-2 sm:grid-cols-[2.25rem_4.5rem_minmax(0,1fr)_5rem] sm:px-2.5"
                    aria-label={`Rank ${index + 1}, ${feature.feature}, ${feature.importance.toFixed(4)}`}
                  >
                    <span className="ss-number text-[10px] text-slate-600">{String(index + 1).padStart(2, "0")}</span>
                    <span className="font-mono text-xs font-semibold text-slate-200">{feature.feature}</span>
                    <span className="relative h-2 overflow-hidden rounded-full bg-slate-800/80">
                      <span
                        className="absolute inset-y-0 left-0 rounded-full bg-blue-500"
                        style={{ width: relativeWidth }}
                      />
                    </span>
                    <span className="ss-number text-right text-[11px] text-teal-100">{feature.importance.toFixed(4)}</span>
                  </li>
                );
              })}
            </ol>
          </figure>

          <aside className="flex flex-col justify-between gap-5 rounded-md border border-amber-200/15 bg-amber-300/[0.035] p-4 sm:p-5">
            <div>
              <p className="ss-eyebrow text-amber-200/75">Diagnostic boundary</p>
              <p className="mt-3 text-sm leading-6 text-slate-300">{dashboardData.explainability.caveat}</p>
              <p className="mt-4 border-l-2 border-amber-200/30 pl-3 text-xs leading-5 text-slate-400">
                Anonymized PCA components are not merchant-readable reasons or causal explanations.
              </p>
            </div>

            <dl className="grid gap-3 border-t border-white/[0.07] pt-4 text-xs">
              <div className="flex items-start justify-between gap-4">
                <dt className="text-slate-500">Method</dt>
                <dd className="max-w-[12rem] text-right text-slate-300">{dashboardData.explainability.method}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-slate-500">Scope</dt>
                <dd className="text-right text-slate-300">{dashboardData.explainability.split}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-slate-500">Interpretation</dt>
                <dd className="text-right text-slate-300">Historical, noncausal ranking</dd>
              </div>
            </dl>
          </aside>
        </CardContent>
      </Card>
    </Section>
  );
}
