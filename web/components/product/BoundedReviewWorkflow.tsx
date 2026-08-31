import { ArrowRight, FileCheck2, Gauge, Users } from "lucide-react";

const stages = [
  {
    title: "Input and evidence",
    description: "A versioned input contract and declared evidence boundary.",
    Icon: FileCheck2,
  },
  {
    title: "Bounded score or result",
    description: "A score with schema, threshold, model, and provenance context.",
    Icon: Gauge,
  },
  {
    title: "Review routing",
    description: "Below review threshold or human review; unavailable paths fail closed.",
    Icon: Users,
  },
] as const;

export function BoundedReviewWorkflow() {
  return (
    <section
      id="workflow"
      data-product-section="bounded-review-workflow"
      aria-labelledby="workflow-heading"
      className="ss-section scroll-mt-20"
    >
      <p className="ss-eyebrow">Bounded review workflow</p>
      <h2 id="workflow-heading" className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-white">
        A risk signal ends in a review route, not a payment action.
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
        The workflow keeps the scoring boundary, review threshold, and human role
        explicit from input to result.
      </p>

      <ol className="mt-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:items-stretch">
        {stages.map(({ title, description, Icon }, index) => (
          <li key={title} className="contents">
            <article className="command-panel min-w-0 p-5 sm:p-6">
              <span className="ss-icon-tile">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <p className="ss-number mt-5 text-xs text-slate-500">0{index + 1}</p>
              <h3 className="mt-2 text-base font-semibold text-white">{title}</h3>
              <p className="mt-2 text-xs leading-5 text-slate-400">{description}</p>
            </article>
            {index < stages.length - 1 ? (
              <ArrowRight
                className="mx-auto hidden h-5 w-5 self-center text-slate-600 lg:block"
                aria-hidden="true"
              />
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
