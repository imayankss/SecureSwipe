import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ShieldCheck } from "lucide-react";

import { Footer } from "@/components/Footer";
import { Navigation } from "@/components/Navigation";
import { DeterministicJudgeDemo } from "@/components/demo/DeterministicJudgeDemo";

export const metadata: Metadata = {
  title: "Local reference-model demonstration | SecureSwipe",
  description: "A deterministic local walkthrough of the configured SecureSwipe reference API.",
};

export default function DemoPage() {
  return (
    <>
      <Navigation activePage="demo" />
      <main id="main-content" tabIndex={-1} className="ss-app-background min-h-screen overflow-x-clip">
        <header className="ss-page-shell pb-10 pt-10 sm:pb-14 sm:pt-16">
          <Link href="/" className="ss-text-link">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to product overview
          </Link>
          <p className="ss-eyebrow mt-10">Deterministic judge walkthrough</p>
          <h1 className="mt-3 max-w-4xl text-4xl leading-[1.06] tracking-[-0.04em] sm:text-5xl">
            Local reference-model demonstration
          </h1>
          <p className="mt-5 max-w-[46rem] text-base leading-7 text-slate-300">
            Run one fixed, sanitized synthetic request through the configured local API and inspect
            its bounded outcome, audit confirmation, replay behavior, and fail-closed validation.
          </p>
          <div className="mt-6 flex max-w-[52rem] gap-3 rounded-xl border border-blue-300/25 bg-blue-400/[0.08] p-4 text-sm leading-6 text-slate-200" role="note">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-blue-300" aria-hidden="true" />
            <p>
              This interactive reference demo is separate from the sealed Lane A evaluation and
              does not claim to serve the headline model.
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

