import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { Footer } from "@/components/Footer";
import { Navigation } from "@/components/Navigation";
import { CommandCenterDashboard } from "@/components/dashboard/CommandCenterDashboard";
import { LaneACapacityWorkbench } from "@/components/dashboard/LaneACapacityWorkbench";

export const metadata: Metadata = {
  title: "Evidence | SecureSwipe",
  description:
    "Detailed scientific evidence, local reference behavior, synthetic tests, illustrative scenarios, provenance, and limitations.",
};

const evidenceAnchors = [
  ["Lane A final", "#lane-a-capacity"],
  ["Lane B historical", "#historical"],
  ["Reference inference", "#risk"],
  ["Synthetic & scenarios", "#synthetic-and-scenarios"],
  ["Methodology", "#methodology-details"],
  ["Limitations", "#limitations"],
] as const;

export default function EvidencePage() {
  return (
    <>
      <Navigation activePage="evidence" />
      <main
        id="main-content"
        tabIndex={-1}
        className="ss-app-background min-h-screen overflow-x-clip"
      >
        <header className="ss-page-shell pb-10 pt-10 sm:pb-14 sm:pt-16">
          <Link
            href="/"
            className="ss-text-link"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to product overview
          </Link>
          <p className="ss-eyebrow mt-10">Detailed evidence record</p>
          <h1 className="mt-3 max-w-4xl text-4xl leading-[1.06] tracking-[-0.04em] sm:text-5xl">
            Scientific evidence and system boundaries
          </h1>
          <p className="mt-5 max-w-[46rem] text-base leading-7 text-slate-300">
            Inspect locked historical evaluation, local reference inference,
            synthetic plumbing and reliability evidence, illustrative scenarios,
            methodology, provenance, and limitations without merging their claims.
          </p>

          <nav className="mt-6" aria-label="Evidence sections">
            <ul className="flex flex-wrap gap-2">
              {evidenceAnchors.map(([label, href]) => (
                <li key={href}>
                  <a
                    href={href}
                    className="ss-chip"
                  >
                    {label}
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </header>

        <div className="ss-page-shell pb-14">
          <LaneACapacityWorkbench />
          <CommandCenterDashboard />
        </div>
        <Footer />
      </main>
    </>
  );
}
