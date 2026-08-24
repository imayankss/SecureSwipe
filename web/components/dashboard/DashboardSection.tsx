import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function DashboardSection({
  id,
  eyebrow,
  title,
  description,
  aside,
  children,
  className,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const headingId = `${id}-command-heading`;
  return (
    <section
      id={id}
      tabIndex={-1}
      aria-labelledby={headingId}
      className={cn("scroll-mt-20 focus:outline-none", className)}
    >
      <header className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="ss-eyebrow text-teal-200">{eyebrow}</p>
          <h2 id={headingId} className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white sm:text-3xl">
            {title}
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function DashboardSlot({
  children,
  className,
  density = "comfortable",
}: {
  children: ReactNode;
  className?: string;
  density?: "compact" | "comfortable";
}) {
  return (
    <div className={cn("command-slot min-w-0", className)} data-density={density}>
      {children}
    </div>
  );
}

