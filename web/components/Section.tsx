import type { ReactNode } from "react";

export function Section({
  id,
  eyebrow,
  title,
  description,
  children,
}: {
  id?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className="mx-auto w-full max-w-7xl px-4 py-14 sm:px-6 lg:px-8"
    >
      <div className="mb-8 max-w-3xl">
        {eyebrow ? (
          <p className="ss-eyebrow mb-3 text-teal-200">
            {eyebrow}
          </p>
        ) : null}
        <h2 id={headingId} className="max-w-4xl text-3xl font-semibold tracking-[-0.035em] text-white sm:text-4xl">
          {title}
        </h2>
        {description ? (
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-300">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}
