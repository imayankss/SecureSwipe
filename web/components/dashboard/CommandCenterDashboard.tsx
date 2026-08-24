import { ConfusionMatrix } from "@/components/ConfusionMatrix";
import { CurveAnalysis } from "@/components/CurveAnalysis";
import { DataProvenance } from "@/components/DataProvenance";
import { GithubCTA } from "@/components/GithubCTA";
import { IllustrativeCostScenario } from "@/components/IllustrativeCostScenario";
import { Methodology } from "@/components/Methodology";
import { ModelPerformance } from "@/components/ModelPerformance";
import { PipelineTimeline } from "@/components/PipelineTimeline";
import { RiskScoreDemo } from "@/components/RiskScoreDemo";
import { ShapSection } from "@/components/ShapSection";
import { SyntheticPlumbingSimulator } from "@/components/SyntheticPlumbingSimulator";
import { ThresholdCards } from "@/components/ThresholdCards";
import { CommandOverview } from "@/components/dashboard/CommandOverview";
import { CurrencyContextBar } from "@/components/dashboard/CurrencyContextBar";
import { DashboardSection, DashboardSlot } from "@/components/dashboard/DashboardSection";
import { DisplayCurrencyProvider } from "@/components/dashboard/DisplayCurrencyContext";
import { HistoricalDatasetPanel } from "@/components/dashboard/HistoricalDatasetPanel";
import { ServingBenchmarkPanel } from "@/components/dashboard/ServingBenchmarkPanel";
import { ScopeEvidencePanel } from "@/components/dashboard/ScopeEvidencePanel";
import { EvidenceLabel } from "@/components/EvidenceLabel";

export function CommandCenterDashboard() {
  return (
    <div className="mx-auto max-w-[1280px] space-y-10 px-4 py-8 sm:px-6 sm:py-10">
      <CommandOverview />

      <DashboardSection
        id="historical"
        eyebrow="Locked historical evidence"
        title="Historical evaluation command board"
        description="A compact view of the tracked benchmark, validation decisions and already-observed random-holdout result. Nothing in this section is live or out-of-time evidence."
        aside={<EvidenceLabel type="historical-evaluation" />}
      >
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
          <div className="xl:col-span-5">
            <HistoricalDatasetPanel />
          </div>
          <DashboardSlot className="xl:col-span-7" density="compact">
            <ConfusionMatrix />
          </DashboardSlot>
          <DashboardSlot className="xl:col-span-12" density="compact">
            <ModelPerformance />
          </DashboardSlot>
          <DashboardSlot className="xl:col-span-12" density="compact">
            <ThresholdCards />
          </DashboardSlot>
          <DashboardSlot className="xl:col-span-12" density="compact">
            <CurveAnalysis />
          </DashboardSlot>
          <DashboardSlot className="xl:col-span-12" density="compact">
            <ShapSection />
          </DashboardSlot>
        </div>
      </DashboardSection>

      <DashboardSlot density="compact">
        <RiskScoreDemo />
      </DashboardSlot>

      <DashboardSlot density="compact">
        <ServingBenchmarkPanel />
      </DashboardSlot>

      <DisplayCurrencyProvider>
        <div className="space-y-3">
          <CurrencyContextBar />
          <DashboardSlot density="compact">
            <SyntheticPlumbingSimulator />
          </DashboardSlot>
          <DashboardSlot density="compact">
            <IllustrativeCostScenario />
          </DashboardSlot>
        </div>
      </DisplayCurrencyProvider>

      <DashboardSection
        id="architecture"
        eyebrow="Scalable reference"
        title="Architecture, methodology and audit trail"
        description="Compact reference panels describe the tracked offline workflow and static presentation boundary without asserting provider deployment or production scale."
      >
        <div className="grid gap-3 xl:grid-cols-12">
          <DashboardSlot className="xl:col-span-12" density="compact">
            <PipelineTimeline />
          </DashboardSlot>
          <DashboardSlot className="xl:col-span-7" density="compact">
            <Methodology />
          </DashboardSlot>
          <DashboardSlot className="xl:col-span-5" density="compact">
            <DataProvenance />
          </DashboardSlot>
        </div>
      </DashboardSection>

      <ScopeEvidencePanel />

      <DashboardSlot density="compact">
        <GithubCTA />
      </DashboardSlot>
    </div>
  );
}
