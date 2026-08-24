
import { GitBranch, ShieldCheck } from "lucide-react";
import { dashboardData } from "@/data/metrics";

const navItems = [
  ["Overview", "#overview"],
  ["Performance", "#performance"],
  ["Thresholds", "#thresholds"],
  ["Explainability", "#shap"],
  ["Synthetic demo", "#synthetic"],
  ["Methodology", "#methodology"],
];

export function Navigation() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/85 backdrop-blur-xl">
      <nav
        className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-4 sm:px-6 lg:px-8"
        aria-label="Primary navigation"
      >
        <a href="#overview" className="flex items-center gap-2 font-semibold text-white">
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-cyan-200/25 bg-cyan-300/10">
            <ShieldCheck className="h-4 w-4 text-cyan-200" aria-hidden="true" />
          </span>
          SecureSwipe
        </a>
        <div className="hidden items-center gap-5 text-sm text-slate-300 lg:flex">
          {navItems.map(([label, href]) => (
            <a key={href} className="transition hover:text-cyan-200" href={href}>
              {label}
            </a>
          ))}
        </div>
        <details className="relative ml-auto lg:hidden">
          <summary className="cursor-pointer list-none rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-white marker:content-none">
            Sections
          </summary>
          <div className="absolute right-0 mt-2 grid min-w-48 gap-1 rounded-lg border border-white/15 bg-slate-950 p-2 shadow-xl">
            {navItems.map(([label, href]) => (
              <a
                key={href}
                className="rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-white/[0.08] hover:text-cyan-100"
                href={href}
              >
                {label}
              </a>
            ))}
          </div>
        </details>
        <a
          href={dashboardData.project.repository}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-white transition hover:border-cyan-200/30 hover:bg-white/[0.06]"
          aria-label="Open SecureSwipe GitHub repository"
        >
          <GitBranch className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">GitHub</span>
        </a>
      </nav>
    </header>
  );
}
