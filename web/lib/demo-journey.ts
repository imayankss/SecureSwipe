/**
 * The eight stages of the guided demonstration.
 *
 * Stage ids are stable and are used as test hooks. Titles are the user-facing
 * labels; `evidence` states plainly where each stage's result comes from, so a
 * reviewer never has to guess whether something was measured or fixed.
 */
export type DemoStageId =
  | "receive"
  | "validate"
  | "evaluate"
  | "decide"
  | "explain"
  | "audit"
  | "replay"
  | "failure";

export type DemoStage = {
  id: DemoStageId;
  /** 1-based position, kept for the numbered rail and the legacy step hooks. */
  index: number;
  title: string;
  purpose: string;
  idleDetail: string;
};

export const DEMO_STAGES: readonly DemoStage[] = [
  {
    id: "receive",
    index: 1,
    title: "Receive",
    purpose: "Load the fixed sanitized scenario the demo will send.",
    idleDetail: "The reference scenario has not been loaded yet.",
  },
  {
    id: "validate",
    index: 2,
    title: "Validate",
    purpose: "Check request schema and verify the served bundle is ready.",
    idleDetail: "Schema and bundle readiness have not been checked.",
  },
  {
    id: "evaluate",
    index: 3,
    title: "Evaluate",
    purpose: "Score the request with the verified reference bundle.",
    idleDetail: "No evaluation has been requested.",
  },
  {
    id: "decide",
    index: 4,
    title: "Decide",
    purpose: "Apply the bounded review policy to the returned score.",
    idleDetail: "No bounded outcome has been returned.",
  },
  {
    id: "explain",
    index: 5,
    title: "Explain",
    purpose: "Show the evidence the outcome rests on, and its limits.",
    idleDetail: "No decision evidence is available yet.",
  },
  {
    id: "audit",
    index: 6,
    title: "Audit",
    purpose: "Confirm the tamper-evident audit receipt the API committed.",
    idleDetail: "No audit receipt has been returned.",
  },
  {
    id: "replay",
    index: 7,
    title: "Replay",
    purpose: "Send the same request again and prove no second event is written.",
    idleDetail: "The replay proof has not been run.",
  },
  {
    id: "failure",
    index: 8,
    title: "Failure handling",
    purpose: "Send a malformed request and prove it fails closed.",
    idleDetail: "The fail-closed proof has not been run.",
  },
] as const;

export const CORE_STAGE_IDS: readonly DemoStageId[] = [
  "receive",
  "validate",
  "evaluate",
  "decide",
  "explain",
  "audit",
] as const;

export function stageByIndex(index: number) {
  return DEMO_STAGES[index] ?? DEMO_STAGES[DEMO_STAGES.length - 1];
}
