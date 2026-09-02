import {
  FileCheck2,
  Gauge,
  Inbox,
  ReceiptText,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

type Stage = {
  title: string;
  summary: string;
  detail: string;
  Icon: LucideIcon;
  tone: "info" | "verified" | "warning";
};

/**
 * The end-to-end path a request takes, from sanitized input to a bounded route.
 *
 * Each stage exposes its own explanation through a native `<details>` so the
 * flow stays readable at a glance and progressive disclosure needs no script.
 */
const STAGES: readonly Stage[] = [
  {
    title: "Sanitized transaction",
    summary: "A versioned input contract with no cardholder data.",
    detail:
      "Inputs are anonymized PCA components and an amount. No PAN, CVV, cardholder identity, or raw identifier enters the system.",
    Icon: Inbox,
    tone: "info",
  },
  {
    title: "Schema and provenance validation",
    summary: "Malformed or unverified input fails closed.",
    detail:
      "Strict schema validation rejects malformed requests with a structured error and releases no outcome. The served bundle must report ready before any request is scored.",
    Icon: FileCheck2,
    tone: "info",
  },
  {
    title: "Verified model scoring",
    summary: "Scored by a bundle whose artifact digest is checked.",
    detail:
      "The reference bundle reports its version, format, and artifact digest so a reviewer can tell exactly what produced a result.",
    Icon: Gauge,
    tone: "info",
  },
  {
    title: "Bounded review policy",
    summary: "Compared against the recorded operating threshold.",
    detail:
      "The score is compared with the operating threshold. The only outcomes are human review or below review threshold — there is no autonomous allow or block.",
    Icon: ShieldCheck,
    tone: "warning",
  },
  {
    title: "Audit receipt",
    summary: "An append-only, tamper-evident event is committed.",
    detail:
      "Each committed decision produces a chained audit event. Altering a committed event breaks the chain, which verification detects.",
    Icon: ReceiptText,
    tone: "verified",
  },
  {
    title: "Human review or below threshold",
    summary: "A person decides. Payment action stays outside.",
    detail:
      "Items above the threshold reach a human reviewer. Items below it raise no review. Neither outcome authorizes, declines, or settles a payment.",
    Icon: Users,
    tone: "verified",
  },
] as const;

const TONE_CLASS: Record<Stage["tone"], string> = {
  info: "text-blue-300",
  verified: "text-emerald-300",
  warning: "text-amber-300",
};

export function BoundedReviewWorkflow() {
  return (
    <section
      id="workflow"
      data-product-section="bounded-review-workflow"
      aria-labelledby="workflow-heading"
      className="ss-section scroll-mt-20"
    >
      <p className="ss-eyebrow">Decision flow</p>
      <h2
        id="workflow-heading"
        className="mt-2.5 max-w-2xl text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl"
      >
        A risk signal ends in a review route, not a payment action.
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
        Six stages from sanitized input to a bounded outcome. Open any stage for
        what it guarantees.
      </p>

      <ol className="mt-6 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {STAGES.map((stage, index) => (
          <li key={stage.title}>
            <details className="evidence-disclosure group h-full p-4" name="workflow-stage">
              <summary className="cursor-pointer list-none marker:content-none focus:outline-none">
                <span className="flex items-start gap-3">
                  <span className={`ss-icon-tile h-9 w-9 shrink-0 ${TONE_CLASS[stage.tone]}`}>
                    <stage.Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="ss-number block text-[11px] text-slate-500">
                      Step {index + 1} of {STAGES.length}
                    </span>
                    <span className="mt-1 block text-sm font-semibold text-white">
                      {stage.title}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-slate-400">
                      {stage.summary}
                    </span>
                  </span>
                </span>
              </summary>
              <p className="mt-3 border-t border-[var(--ss-border)] pt-3 text-xs leading-5 text-slate-300">
                {stage.detail}
              </p>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
