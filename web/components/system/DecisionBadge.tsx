import { StateChip, type SystemState } from "@/components/system/StateChip";

/**
 * The complete set of bounded outcomes this product can produce.
 *
 * The API contract returns exactly `human_review` or `below_review_threshold`,
 * and the client adds `unavailable` when it fails closed. There is deliberately
 * no autonomous allow or block outcome: payment action is outside this system.
 */
export type BoundedDecision = "review" | "below_threshold" | "unavailable" | "pending";

const DECISIONS: Record<
  BoundedDecision,
  { label: string; state: SystemState; meaning: string }
> = {
  review: {
    label: "Human review",
    state: "review",
    meaning: "Routed to a human reviewer. No payment action is taken here.",
  },
  below_threshold: {
    // Never "approved", "safe", or "legitimate": the model only reports that
    // this scored under the operating threshold, not that it is not fraud.
    label: "Below review threshold",
    state: "verified",
    meaning: "Scored under the operating threshold, so no review was raised.",
  },
  unavailable: {
    label: "Unavailable — fail closed",
    state: "unavailable",
    meaning: "No outcome was released. The system refuses to guess.",
  },
  pending: {
    label: "Not yet run",
    state: "pending",
    meaning: "No request has been evaluated in this session.",
  },
};

export function decisionLabel(decision: BoundedDecision) {
  return DECISIONS[decision].label;
}

export function decisionMeaning(decision: BoundedDecision) {
  return DECISIONS[decision].meaning;
}

export function DecisionBadge({
  decision,
  className,
}: {
  decision: BoundedDecision;
  className?: string;
}) {
  const { label, state } = DECISIONS[decision];
  return (
    <StateChip
      state={state}
      label={label}
      className={`px-2.5 py-1 text-xs${className ? ` ${className}` : ""}`}
    />
  );
}
