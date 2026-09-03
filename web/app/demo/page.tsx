import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Clock3, ShieldCheck } from "lucide-react";

import { Footer } from "@/components/Footer";
import { Navigation } from "@/components/Navigation";
import { DeterministicJudgeDemo } from "@/components/demo/DeterministicJudgeDemo";
import { StateChip } from "@/components/system/StateChip";

export const metadata: Metadata = {
  title: "Local reference-model demonstration | SecureSwipe",
  description: "A deterministic local walkthrough of the configured SecureSwipe reference API.",
};

export default function DemoPage() {
  return (
    <>
      <Navigation activePage="demo" />
      <main
        id="main-content"
        tabIndex={-1}
        className="ss-app-background min-h-screen overflow-x-clip"
      >
        <header className="ss-page-shell pb-7 pt-8 sm:pb-9 sm:pt-12">
          <Link href="/" className="ss-text-link">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to product overview
          </Link>

          <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
              <p className="ss-eyebrow">Guided demonstration</p>
              <h1 className="mt-2.5 max-w-3xl text-3xl leading-[1.08] tracking-[-0.04em] sm:text-4xl">
                Local reference-model demonstration
              </h1>
              <p className="ss-prose mt-3.5 max-w-[46rem] text-sm leading-6 text-slate-300">
                Run one fixed, sanitized synthetic request through the configured
                reference API and inspect its bounded outcome, decision evidence,
                audit receipt, replay behavior, and fail-closed validation.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <StateChip state="info" label="Fixed reference scenario" />
              <span className="ss-state" data-state="neutral">
                <Clock3 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                About 2 minutes
              </span>
            </div>
          </div>

          <div
            className="mt-5 flex max-w-[52rem] gap-3 rounded-xl border border-blue-300/25 bg-blue-400/[0.08] p-3.5 text-sm leading-6 text-slate-200"
            role="note"
          >
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-blue-300" aria-hidden="true" />
            <p>
              This interactive reference demo is separate from the sealed Lane A
              evaluation and does not claim to serve the headline model.
            </p>
          </div>
        </header>

        <div className="ss-page-shell pb-16 sm:pb-20">
          <DeterministicJudgeDemo />
        </div>
        <Footer />
      </main>
    </>
  );
}
