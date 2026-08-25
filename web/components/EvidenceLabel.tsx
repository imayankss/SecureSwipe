import { Badge } from "@/components/ui/badge";

export type EvidenceType =
  | "historical-evaluation"
  | "genuine-demo-inference"
  | "synthetic-plumbing-test"
  | "illustrative-cost-scenario";

const EVIDENCE_COPY: Record<EvidenceType, { label: string; className: string }> = {
  "historical-evaluation": {
    label: "Historical evaluation",
    className: "border-cyan-300/30 bg-cyan-300/10 text-cyan-100",
  },
  "genuine-demo-inference": {
    label: "Genuine demo inference",
    className: "border-emerald-300/30 bg-emerald-300/10 text-emerald-100",
  },
  "synthetic-plumbing-test": {
    label: "Synthetic plumbing test",
    className: "border-violet-300/30 bg-violet-300/10 text-violet-100",
  },
  "illustrative-cost-scenario": {
    label:
      "Illustrative scenario — not Razorpay economics and not a production-optimal threshold.",
    className: "border-amber-300/30 bg-amber-300/10 text-amber-100",
  },
};

/**
 * A typed, reusable badge naming which of the four evidence categories a
 * panel belongs to (see README.md "What You're Looking At"). Every
 * model-adjacent number or interaction on the dashboard should carry exactly
 * one of these labels so it can never be mistaken for another category.
 */
export function EvidenceLabel({ type }: { type: EvidenceType }) {
  const { label, className } = EVIDENCE_COPY[type];
  return (
    <Badge role="note" aria-label={label} title={label} className={className}>
      {label}
    </Badge>
  );
}
