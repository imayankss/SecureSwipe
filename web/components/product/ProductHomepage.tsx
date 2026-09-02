import { BoundedReviewWorkflow } from "@/components/product/BoundedReviewWorkflow";
import { DecisionWorkspacePreview } from "@/components/product/DecisionWorkspacePreview";
import { EvidenceKpiStrip } from "@/components/product/EvidenceKpiStrip";
import { EvidenceStatus } from "@/components/product/EvidenceStatus";
import { ProductHero } from "@/components/product/ProductHero";
import { ReviewStrategySurface } from "@/components/product/ReviewStrategySurface";
import { TrustAndDetails } from "@/components/product/TrustAndDetails";

/**
 * The reviewer's path: what it is, what was measured, how a decision flows,
 * what a result looks like, the capacity trade-off, where evidence lives, and
 * the boundary the whole thing sits inside.
 */
export function ProductHomepage() {
  return (
    <div className="ss-page-shell">
      <ProductHero />
      <EvidenceKpiStrip />
      <BoundedReviewWorkflow />
      <DecisionWorkspacePreview />
      <ReviewStrategySurface />
      <EvidenceStatus />
      <TrustAndDetails />
    </div>
  );
}
