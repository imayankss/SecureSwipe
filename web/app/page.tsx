import { ConfusionMatrix } from "@/components/ConfusionMatrix";
import { CurveAnalysis } from "@/components/CurveAnalysis";
import { DataProvenance } from "@/components/DataProvenance";
import { Footer } from "@/components/Footer";
import { GithubCTA } from "@/components/GithubCTA";
import { Hero } from "@/components/Hero";
import { IllustrativeCostScenario } from "@/components/IllustrativeCostScenario";
import { Methodology } from "@/components/Methodology";
import { ModelPerformance } from "@/components/ModelPerformance";
import { Navigation } from "@/components/Navigation";
import { PipelineTimeline } from "@/components/PipelineTimeline";
import { ProblemSection } from "@/components/ProblemSection";
import { RiskScoreDemo } from "@/components/RiskScoreDemo";
import { ShapSection } from "@/components/ShapSection";
import { ThresholdCards } from "@/components/ThresholdCards";

export default function Home() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <Navigation />
      <main
        id="main-content"
        tabIndex={-1}
        className="min-h-screen overflow-hidden bg-slate-950 text-slate-100"
      >
        <div className="dashboard-grid fixed inset-0 -z-10 bg-[linear-gradient(135deg,#020617_0%,#07111f_48%,#061d1f_100%)]" />
        <Hero />
        <ProblemSection />
        <PipelineTimeline />
        <ModelPerformance />
        <ThresholdCards />
        <IllustrativeCostScenario />
        <ConfusionMatrix />
        <CurveAnalysis />
        <ShapSection />
        <RiskScoreDemo />
        <Methodology />
        <DataProvenance />
        <GithubCTA />
        <Footer />
      </main>
    </>
  );
}
