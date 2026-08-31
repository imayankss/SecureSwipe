"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

type EvidenceDisclosureProps = {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  cue?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
};

/**
 * An explicit disclosure boundary for secondary evidence chapters.
 *
 * The labelled section and its evidence cue remain visible when collapsed.
 * The button owns the expanded state and the controlled region remains one
 * obvious keyboard interaction away without relying on pointer-only behavior.
 */
export function EvidenceDisclosure({
  id,
  eyebrow,
  title,
  description,
  children,
  cue,
  defaultOpen = false,
  className,
}: EvidenceDisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);
  const headingId = `${id}-heading`;
  const regionId = `${id}-content`;

  return (
    <section
      id={id}
      aria-labelledby={headingId}
      data-evidence-disclosure=""
      data-state={open ? "open" : "closed"}
      className={cn("evidence-disclosure scroll-mt-24", className)}
    >
      <header className="grid gap-5 p-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:p-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <p className="ss-eyebrow">{eyebrow}</p>
            {cue}
          </div>
          <h2
            id={headingId}
            className="mt-2.5 max-w-3xl text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl"
          >
            {title}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{description}</p>
        </div>

        <button
          type="button"
          aria-expanded={open}
          aria-controls={regionId}
          aria-label={`${open ? "Hide" : "Show"} details: ${title}`}
          onClick={() => setOpen((current) => !current)}
          className="ss-action ss-action-secondary w-full focus:outline-none sm:w-auto"
        >
          {open ? "Hide details" : "Show details"}
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
            aria-hidden="true"
          />
        </button>
      </header>

      <div id={regionId} hidden={!open} className="border-t border-[var(--ss-border)] p-4 sm:p-6">
        {children}
      </div>
    </section>
  );
}
