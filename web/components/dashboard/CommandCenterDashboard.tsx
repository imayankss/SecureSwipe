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
import { CurrencyContextBar } from "@/components/dashboard/CurrencyContextBar";
import { DashboardSection, DashboardSlot } from "@/components/dashboard/DashboardSection";
import { DisplayCurrencyProvider } from "@/components/dashboard/DisplayCurrencyContext";
import { HistoricalDatasetPanel } from "@/components/dashboard/HistoricalDatasetPanel";
import { ServingBenchmarkPanel } from "@/components/dashboard/ServingBenchmarkPanel";
import { ScopeEvidencePanel } from "@/components/dashboard/ScopeEvidencePanel";
import { EvidenceLabel } from "@/components/EvidenceLabel";
import { EvidenceDisclosure } from "@/components/evidence/EvidenceDisclosure";

export function CommandCenterDashboard() {
  return (
    <div className="space-y-8 py-10 sm:space-y-10 sm:py-14">
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
        </div>
      </DashboardSection>

      <EvidenceDisclosure
        id="historical-analysis"
        eyebrow="Historical analysis"
        title="Threshold, curve, and explainability detail"
        description="Open the validation-only threshold sweep, full-range curves, and historical noncausal SHAP ranking. Their limitations remain attached to each artifact."
        cue={<EvidenceLabel type="historical-evaluation" />}
      >
        <div className="grid gap-4">
          <DashboardSlot density="compact">
            <ThresholdCards />
          </DashboardSlot>
          <DashboardSlot density="compact">
            <CurveAnalysis />
          </DashboardSlot>
          <DashboardSlot density="compact">
            <ShapSection />
          </DashboardSlot>
        </div>
      </EvidenceDisclosure>

      <DashboardSlot density="compact">
        <RiskScoreDemo />
      </DashboardSlot>

      <EvidenceDisclosure
        id="benchmark-details"
        eyebrow="Local serving evidence"
        title="Benchmark environment and operating limits"
        description="Inspect the measured local serving-path result with its source identity, loopback environment, and non-production capacity boundary."
        cue={<EvidenceLabel type="synthetic-plumbing-test" />}
      >
        <DashboardSlot density="compact">
          <ServingBenchmarkPanel />
        </DashboardSlot>
      </EvidenceDisclosure>

      <EvidenceDisclosure
        id="synthetic-and-scenarios"
        eyebrow="Synthetic and illustrative"
        title="Plumbing test and Lane B cost scenario"
        description="Open the fabricated in-browser workflow and the separate historical-count cost arithmetic. Neither is fraud-performance or merchant-economics evidence."
        cue={<EvidenceLabel type="synthetic-plumbing-test" />}
      >
        <DisplayCurrencyProvider>
          <div className="space-y-4">
            <CurrencyContextBar />
            <DashboardSlot density="compact">
              <SyntheticPlumbingSimulator />
            </DashboardSlot>
            <DashboardSlot density="compact">
              <IllustrativeCostScenario />
            </DashboardSlot>
          </div>
        </DisplayCurrencyProvider>
      </EvidenceDisclosure>

      <EvidenceDisclosure
        id="methodology-details"
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
      </EvidenceDisclosure>

      <ScopeEvidencePanel />

      <DashboardSlot density="compact">
        <GithubCTA />
      </DashboardSlot>
    </div>
  );
}
