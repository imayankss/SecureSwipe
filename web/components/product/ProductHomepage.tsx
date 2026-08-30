import { BoundedReviewWorkflow } from "@/components/product/BoundedReviewWorkflow";
import { EvidenceStatus } from "@/components/product/EvidenceStatus";
import { ProductHero } from "@/components/product/ProductHero";
import { ReviewStrategySurface } from "@/components/product/ReviewStrategySurface";
import { TrustAndDetails } from "@/components/product/TrustAndDetails";

export function ProductHomepage() {
  return (
    <div className="ss-page-shell">
      <ProductHero />
      <BoundedReviewWorkflow />
      <ReviewStrategySurface />
      <EvidenceStatus />
      <TrustAndDetails />
    </div>
  );
}
