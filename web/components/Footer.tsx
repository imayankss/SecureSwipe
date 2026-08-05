import { ShieldCheck } from "lucide-react";
import { dashboardData } from "@/data/metrics";

export function Footer() {
  return (
    <footer className="border-t border-white/10 px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 text-sm text-slate-400 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="flex items-center gap-2 font-medium text-slate-200">
            <ShieldCheck className="h-4 w-4 text-cyan-200" aria-hidden="true" />
            SecureSwipe
          </p>
          <p className="mt-3 leading-6">{dashboardData.project.disclaimer}</p>
        </div>
        <a
          className="text-slate-300 transition hover:text-cyan-200"
          href={dashboardData.project.repository}
          target="_blank"
          rel="noreferrer"
        >
          Source and methodology ↗
        </a>
      </div>
    </footer>
  );
}
