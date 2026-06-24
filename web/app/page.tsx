import { ConfusionMatrix } from "@/components/ConfusionMatrix";
import { GithubCTA } from "@/components/GithubCTA";
import { Hero } from "@/components/Hero";
import { ModelPerformance } from "@/components/ModelPerformance";
import { PipelineTimeline } from "@/components/PipelineTimeline";
import { ProblemSection } from "@/components/ProblemSection";
import { RiskScoreDemo } from "@/components/RiskScoreDemo";
import { ShapSection } from "@/components/ShapSection";
import { ThresholdCards } from "@/components/ThresholdCards";

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      <div className="dashboard-grid fixed inset-0 -z-10 bg-[linear-gradient(135deg,#020617_0%,#07111f_48%,#061d1f_100%)]" />
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-4 py-5 sm:px-6 lg:px-8">
        <a href="#" className="text-lg font-semibold text-white" aria-label="SecureSwipe home">
          SecureSwipe
        </a>
        <div className="hidden items-center gap-5 text-sm text-slate-300 md:flex">
          <a className="transition hover:text-cyan-200" href="#problem">
            Problem
          </a>
          <a className="transition hover:text-cyan-200" href="#performance">
            Results
          </a>
          <a className="transition hover:text-cyan-200" href="#thresholds">
            Thresholds
          </a>
          <a className="transition hover:text-cyan-200" href="#shap">
            SHAP
          </a>
        </div>
      </nav>
      <Hero />
      <ProblemSection />
      <PipelineTimeline />
      <ModelPerformance />
      <ThresholdCards />
      <ConfusionMatrix />
      <ShapSection />
      <RiskScoreDemo />
      <GithubCTA />
    </main>
  );
}
