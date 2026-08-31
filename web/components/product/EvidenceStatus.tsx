import Link from "next/link";
import { ArrowRight, LockKeyhole } from "lucide-react";

/**
 * A short link-oriented evidence cue.
 *
 * The complete four-category legend, its descriptions, and every detailed
 * measurement live on `/evidence`. The homepage names the categories only so a
 * reviewer knows the separation exists before following the link.
 */
const categories = [
  "Locked historical evaluation",
  "Genuine local/reference inference",
  "Synthetic plumbing and reliability tests",
  "Illustrative cost arithmetic",
];

export function EvidenceStatus() {
  return (
    <section
      id="evidence-status"
      data-product-section="evidence-status"
      aria-labelledby="evidence-status-heading"
      className="ss-section scroll-mt-20"
    >
      <div className="grid gap-8 lg:grid-cols-[0.7fr_1.3fr] lg:items-start">
        <div>
          <div className="flex items-center gap-2 text-blue-300">
            <LockKeyhole className="h-4 w-4" aria-hidden="true" />
            <p className="ss-eyebrow">Evidence status</p>
          </div>
          <h2 id="evidence-status-heading" className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-white">
            Know what each result can support.
          </h2>
          <p className="mt-4 max-w-xl text-sm leading-6 text-slate-400">
            Each result keeps its own source, scope, and limitation so a reviewer
            can tell what was measured from what was only demonstrated.
          </p>
          <Link
            href="/evidence"
            prefetch={false}
            className="ss-text-link mt-6 focus:outline-none"
          >
            Open the complete evidence record
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>

        <div className="command-panel p-5 sm:p-6">
          <ul className="grid gap-2 sm:grid-cols-2">
            {categories.map((category) => (
              <li
                key={category}
                className="rounded-lg bg-[var(--ss-surface-raised)] p-3.5 text-xs leading-5 text-slate-300"
              >
                {category}
              </li>
            ))}
          </ul>
          <p className="mt-4 rounded-lg border border-blue-400/25 bg-blue-500/[0.08] p-3.5 text-xs leading-5 text-slate-300">
            Lane A sealed final evidence is evaluated exactly once and remains
            separate from Lane B historical metrics and the locally served
            reference bundle.
          </p>
        </div>
      </div>
    </section>
  );
}
