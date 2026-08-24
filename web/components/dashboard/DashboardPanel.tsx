import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function DashboardPanel({
  eyebrow,
  title,
  description,
  aside,
  children,
  className,
  bodyClassName,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <article className={cn("command-panel", className)}>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-white/[0.07] px-5 py-4 sm:px-6">
        <div className="min-w-0">
          {eyebrow ? <p className="ss-eyebrow text-slate-500">{eyebrow}</p> : null}
          <h3 className="mt-1 text-lg font-semibold leading-tight text-white sm:text-xl">{title}</h3>
          {description ? (
            <p className="mt-1.5 max-w-2xl text-xs leading-5 text-slate-400">{description}</p>
          ) : null}
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </header>
      <div className={cn("p-5 sm:p-6", bodyClassName)}>{children}</div>
    </article>
  );
}

