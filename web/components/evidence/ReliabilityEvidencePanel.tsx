import { StateChip } from "@/components/system/StateChip";

/**
 * Reliability and audit evidence.
 *
 * Two strictly separated groups. Verified behaviour is what deterministic
 * tests, PostgreSQL integration tests, and the three repair proofs established.
 * The measurement boundary records what the load evidence did NOT establish, so
 * a reader never has to infer capacity from a repair result.
 */
const VERIFIED: readonly { title: string; detail: string }[] = [
  {
    title: "Model-bundle verification",
    detail:
      "The served bundle reports its version, format, and artifact digest, and the API refuses to score until it reports ready.",
  },
  {
    title: "Strict request validation",
    detail:
      "Malformed requests are rejected with a structured validation error and no outcome is released.",
  },
  {
    title: "Durable idempotency",
    detail:
      "Re-sending the same request reference returns the committed response and writes no second audit event.",
  },
  {
    title: "Append-only, tamper-evident audit",
    detail:
      "Decisions are committed to a chained audit log. Altering a committed event breaks the chain, which full verification detects.",
  },
  {
    title: "State-store defect reproduced and repaired",
    detail:
      "A PostgreSQL state-store connection checkout-exhaustion defect was reproduced under a pre-registered protocol and repaired by queueing completions before pool checkout.",
  },
  {
    title: "Repair validated three consecutive times",
    detail:
      "Three consecutive four-worker, concurrency-64 proofs each reconciled exactly, with no state-store failure, no client timeout, and full audit-chain verification.",
  },
];

const MEASURED_SCOPE: readonly string[] = [
  "The completed proof establishes state-store correctness under the frozen repair protocol; production-capacity and horizontal-scaling claims stay reserved for a completed matrix.",
  "The architecture supports a multi-worker deployment model, with that design capability kept separate from benchmark-proven capacity.",
  "Published load observations are reproducible local-loopback results from one laptop and a synthetic fixture; production SLOs remain environment-specific.",
  "Every partial matrix cell is retained transparently as negative evidence instead of being promoted to a capacity result.",
];

export function ReliabilityEvidencePanel() {
  return (
    <section
      id="reliability-and-audit"
      aria-labelledby="reliability-heading"
      className="command-panel scroll-mt-36 p-5 sm:p-6"
      data-evidence-section="reliability-and-audit"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="ss-eyebrow">Reliability and audit</p>
          <h2
            id="reliability-heading"
            className="mt-2 text-xl font-semibold tracking-[-0.03em] text-white sm:text-2xl"
          >
            Reliability repairs proven under concurrency, with scope attached.
          </h2>
        </div>
        <StateChip state="verified" label="Operational tests" />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.09em] text-emerald-300">
            Proven behaviour
          </h3>
          <ul className="mt-3 grid gap-2">
            {VERIFIED.map((item) => (
              <li
                key={item.title}
                className="rounded-lg bg-[var(--ss-surface-raised)] p-3"
              >
                <p className="text-xs font-semibold text-white">{item.title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">{item.detail}</p>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.09em] text-amber-300">
            Measured scope
          </h3>
          <ul className="mt-3 grid gap-2">
            {MEASURED_SCOPE.map((item) => (
              <li
                key={item}
                className="rounded-lg border border-[var(--ss-warning-border)] bg-[var(--ss-warning-surface)] p-3 text-xs leading-5 text-slate-300"
              >
                {item}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] leading-5 text-slate-500">
            Verified reliability behaviour, local-environment performance
            observations, and the production reference architecture are three
            different things and are never merged into one claim.
          </p>
        </div>
      </div>
    </section>
  );
}
