import { ShieldCheck } from "lucide-react";
import { dashboardData } from "@/data/metrics";
import { BuildProvenance } from "@/components/system/BuildProvenance";

export function Footer() {
  return (
    <footer className="ss-footer py-10 sm:py-12">
      <div className="ss-page-shell flex flex-col gap-5 text-sm text-slate-400 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="flex items-center gap-2 font-medium text-slate-200">
            <ShieldCheck className="h-4 w-4 text-blue-300" aria-hidden="true" />
            SecureSwipe
          </p>
          <p className="mt-3 leading-6">{dashboardData.project.disclaimer}</p>
        </div>
        <div className="flex flex-col gap-2 sm:items-end">
          <a
            className="ss-text-link"
            href="/secureswipe-methodology.html"
          >
            Methodology ↗
          </a>
          <BuildProvenance repository={dashboardData.project.repository} />
        </div>
      </div>
    </footer>
  );
}
