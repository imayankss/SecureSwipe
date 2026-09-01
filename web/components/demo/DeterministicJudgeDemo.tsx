"use client";

import { useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  FileClock,
  FileSearch,
  Play,
  RotateCcw,
  ShieldX,
  Repeat2,
} from "lucide-react";
import Link from "next/link";

import { CopyButton } from "@/components/system/CopyButton";
import {
  DecisionBadge,
  decisionMeaning,
  type BoundedDecision,
} from "@/components/system/DecisionBadge";
import { DecisionZoneBand } from "@/components/system/DecisionZoneBand";
import { Drawer } from "@/components/system/Drawer";
import { StateChip, StateIcon, type SystemState } from "@/components/system/StateChip";
import {
  CORE_STAGE_IDS,
  DEMO_STAGES,
  type DemoStageId,
} from "@/lib/demo-journey";
import {
  DEMO_FIXTURE,
  DEMO_FIXTURE_VERSION,
  DEMO_REQUEST_ID,
  INVALID_DEMO_FIXTURE,
  INVALID_DEMO_REQUEST_ID,
  RECORDED_REFERENCE_RUN,
  RECORDED_RUN_LABEL,
} from "@/lib/deterministic-demo";

const REQUEST_TIMEOUT_MS = 4_000;
const AUDIT_HASH_PATTERN = /^[a-f0-9]{64}$/;

type StageStatus = "pending" | "running" | "success" | "unavailable" | "failure";

type EvidenceCategory =
  | "synthetic_demo_inference"
  | "new_authorized_development_evidence"
  | "historical_reference_demo_inference";

type Prediction = {
  schema_version: "1.0";
  request_id: string;
  raw_score: number;
  calibrated_probability: number | null;
  decision_score: number;
  score_type: "raw_score" | "calibrated_probability";
  operating_threshold: number;
  decision: "human_review" | "below_review_threshold";
  model_version: string;
  bundle_format_version: string;
  provenance: {
    training_data_fingerprint: string;
    evidence_category: EvidenceCategory;
    historical_taint: boolean;
    decision_eligible: boolean;
    historical_metrics_claimed: boolean;
    evaluation_performed: boolean;
  };
};

type ModelInfo = {
  schema_version: "1.0";
  model_version: string;
  bundle_format_version: string;
  model_artifact_sha256: string | null;
  evidence_category: EvidenceCategory;
};

type ErrorEnvelope = {
  schema_version: "1.0";
  request_id: string;
  error: { code: string; message: string };
};

type StageState = { status: StageStatus; detail: string };

/**
 * The decision evidence the UI renders.
 *
 * Both the live API path and the recorded transcript populate this same shape,
 * so neither path can render a field the other lacks. It deliberately has no
 * score field: the response contract suppresses the decision score.
 */
type DecisionEvidence = {
  scoreType: string;
  operatingThreshold: number;
  modelVersion: string;
  bundleFormatVersion: string;
  evidenceCategory: string;
  decisionEligible: boolean;
};

function initialStages(): Record<DemoStageId, StageState> {
  return Object.fromEntries(
    DEMO_STAGES.map((stage) => [stage.id, { status: "pending", detail: stage.idleDetail }]),
  ) as Record<DemoStageId, StageState>;
}

function apiUrlFromEnvironment() {
  const raw = process.env.NEXT_PUBLIC_SECURESWIPE_API_URL?.trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    )
      return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function isEvidenceCategory(value: unknown): value is EvidenceCategory {
  return (
    value === "synthetic_demo_inference" ||
    value === "new_authorized_development_evidence" ||
    value === "historical_reference_demo_inference"
  );
}

function isPrediction(value: unknown): value is Prediction {
  if (typeof value !== "object" || value === null) return false;
  const prediction = value as Record<string, unknown>;
  const provenance = prediction.provenance;
  if (typeof provenance !== "object" || provenance === null) return false;
  const source = provenance as Record<string, unknown>;
  return (
    prediction.schema_version === "1.0" &&
    typeof prediction.request_id === "string" &&
    typeof prediction.raw_score === "number" &&
    Number.isFinite(prediction.raw_score) &&
    (prediction.calibrated_probability === null ||
      (typeof prediction.calibrated_probability === "number" &&
        Number.isFinite(prediction.calibrated_probability))) &&
    typeof prediction.decision_score === "number" &&
    Number.isFinite(prediction.decision_score) &&
    (prediction.score_type === "raw_score" ||
      prediction.score_type === "calibrated_probability") &&
    typeof prediction.operating_threshold === "number" &&
    Number.isFinite(prediction.operating_threshold) &&
    (prediction.decision === "human_review" ||
      prediction.decision === "below_review_threshold") &&
    typeof prediction.model_version === "string" &&
    prediction.model_version.length > 0 &&
    typeof prediction.bundle_format_version === "string" &&
    typeof source.training_data_fingerprint === "string" &&
    isEvidenceCategory(source.evidence_category) &&
    typeof source.historical_taint === "boolean" &&
    typeof source.decision_eligible === "boolean" &&
    typeof source.historical_metrics_claimed === "boolean" &&
    typeof source.evaluation_performed === "boolean"
  );
}

function isModelInfo(value: unknown): value is ModelInfo {
  if (typeof value !== "object" || value === null) return false;
  const info = value as Record<string, unknown>;
  return (
    info.schema_version === "1.0" &&
    typeof info.model_version === "string" &&
    info.model_version.length > 0 &&
    typeof info.bundle_format_version === "string" &&
    (info.model_artifact_sha256 === null ||
      (typeof info.model_artifact_sha256 === "string" &&
        AUDIT_HASH_PATTERN.test(info.model_artifact_sha256))) &&
    isEvidenceCategory(info.evidence_category)
  );
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const payload = value as Record<string, unknown>;
  if (typeof payload.error !== "object" || payload.error === null) return false;
  const error = payload.error as Record<string, unknown>;
  return (
    payload.schema_version === "1.0" &&
    typeof payload.request_id === "string" &&
    typeof error.code === "string" &&
    typeof error.message === "string"
  );
}

async function jsonOrNull(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchWithDeadline(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  success: "Verified",
  unavailable: "Unavailable",
  failure: "Failed",
};

const STATUS_STATE: Record<StageStatus, SystemState> = {
  pending: "pending",
  running: "running",
  success: "verified",
  unavailable: "unavailable",
  failure: "critical",
};

export function DeterministicJudgeDemo({
  apiBaseUrl = apiUrlFromEnvironment(),
}: {
  apiBaseUrl?: string | null;
} = {}) {
  const [stages, setStages] = useState<Record<DemoStageId, StageState>>(initialStages);
  const [running, setRunning] = useState(false);
  const [started, setStarted] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [decision, setDecision] = useState<BoundedDecision>("pending");
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [evidence, setEvidence] = useState<DecisionEvidence | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [auditHash, setAuditHash] = useState<string | null>(null);
  const [replayProved, setReplayProved] = useState(false);
  const [failureProved, setFailureProved] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  /** Which source produced what is currently on screen. */
  const [source, setSource] = useState<"none" | "live" | "recorded">("none");
  const startRef = useRef<HTMLButtonElement | null>(null);

  const stageList = DEMO_STAGES;
  const current = stageList[Math.min(cursor, stageList.length - 1)];

  function setStage(id: DemoStageId, status: StageStatus, detail: string) {
    setStages((prev) => ({ ...prev, [id]: { status, detail } }));
  }

  function failClosedFrom(from: DemoStageId, detail: string) {
    const start = stageList.findIndex((stage) => stage.id === from);
    setStages((prev) => {
      const next = { ...prev };
      for (const stage of stageList.slice(start)) {
        if (stage.id === "failure") continue;
        next[stage.id] = { status: "unavailable", detail };
      }
      return next;
    });
    setDecision("unavailable");
  }

  function resetDemo() {
    setStages(initialStages());
    setRunning(false);
    setStarted(false);
    setCursor(0);
    setDecision("pending");
    setPrediction(null);
    setEvidence(null);
    setModelInfo(null);
    setAuditHash(null);
    setReplayProved(false);
    setFailureProved(false);
    setTraceOpen(false);
    setSource("none");
    startRef.current?.focus();
  }

  /** Stages 1-6: receive through audit. */
  async function runCore() {
    if (running) return;
    setRunning(true);
    setStarted(true);
    setStages(initialStages());
    setDecision("pending");
    setPrediction(null);
    setEvidence(null);
    setModelInfo(null);
    setAuditHash(null);
    setReplayProved(false);
    setFailureProved(false);
    setCursor(0);
    setSource("live");

    setStage(
      "receive",
      "success",
      `Fixed scenario ${DEMO_FIXTURE_VERSION} loaded with reference ${DEMO_REQUEST_ID}.`,
    );

    if (!apiBaseUrl) {
      failClosedFrom(
        "validate",
        "No reference API origin was configured at build time, so nothing was sent.",
      );
      setStage(
        "failure",
        "unavailable",
        "The fail-closed proof needs the configured reference API.",
      );
      setCursor(3);
      setRunning(false);
      return;
    }

    setStage("validate", "running", "Checking bundle readiness before sending the request.");
    let readyResponse: Response;
    let infoResponse: Response;
    try {
      [readyResponse, infoResponse] = await Promise.all([
        fetchWithDeadline(`${apiBaseUrl}/health/ready`),
        fetchWithDeadline(`${apiBaseUrl}/v1/model-info`),
      ]);
    } catch {
      failClosedFrom("validate", "The reference API could not be reached. No outcome was released.");
      setCursor(3);
      setRunning(false);
      return;
    }

    const readyPayload = await jsonOrNull(readyResponse);
    const infoPayload = await jsonOrNull(infoResponse);
    if (infoResponse.ok && isModelInfo(infoPayload)) setModelInfo(infoPayload);
    if (
      !readyResponse.ok ||
      typeof readyPayload !== "object" ||
      readyPayload === null ||
      (readyPayload as Record<string, unknown>).status !== "ready"
    ) {
      failClosedFrom(
        "validate",
        "The reference API is not model-ready, so no outcome was released.",
      );
      setCursor(3);
      setRunning(false);
      return;
    }

    setStage("validate", "success", "Request schema accepted and the served bundle reported ready.");
    setStage("evaluate", "running", "Requesting one bounded result from the reference bundle.");

    try {
      const response = await fetchWithDeadline(`${apiBaseUrl}/v1/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Request-ID": DEMO_REQUEST_ID },
        body: JSON.stringify(DEMO_FIXTURE),
      });
      const payload = await jsonOrNull(response);
      if (!response.ok || !isPrediction(payload) || payload.request_id !== DEMO_REQUEST_ID) {
        const detail = isErrorEnvelope(payload)
          ? `The API failed closed with ${payload.error.code}. No outcome was released.`
          : `The API failed closed with HTTP ${response.status}. No outcome was released.`;
        failClosedFrom("evaluate", detail);
        setCursor(3);
        setRunning(false);
        return;
      }

      setPrediction(payload);
      setEvidence({
        scoreType: payload.score_type,
        operatingThreshold: payload.operating_threshold,
        modelVersion: payload.model_version,
        bundleFormatVersion: payload.bundle_format_version,
        evidenceCategory: payload.provenance.evidence_category,
        decisionEligible: payload.provenance.decision_eligible,
      });
      setStage("evaluate", "success", `Reference bundle returned HTTP 200 under schema ${payload.schema_version}.`);

      const bounded: BoundedDecision =
        payload.decision === "human_review" ? "review" : "below_threshold";
      setDecision(bounded);
      setStage(
        "decide",
        "success",
        payload.decision === "human_review"
          ? "Bounded policy routed this to human review. No payment action was taken."
          : "Bounded policy recorded this below the review threshold. No review was raised.",
      );
      setStage(
        "explain",
        "success",
        `Decided by comparing the ${payload.score_type.replace("_", " ")} against operating threshold ${payload.operating_threshold.toFixed(2)}.`,
      );

      const committed = response.headers.get("x-audit-event-hash");
      if (committed && AUDIT_HASH_PATTERN.test(committed)) {
        setAuditHash(committed);
        setStage(
          "audit",
          "success",
          `Audit receipt ${committed.slice(0, 12)}… was committed and returned by the API.`,
        );
      } else {
        setStage(
          "audit",
          "unavailable",
          "The API returned no audit receipt. The demo does not infer one.",
        );
      }
      setCursor(3);
    } catch {
      failClosedFrom("evaluate", "The evaluation request did not complete. No outcome was released.");
      setCursor(3);
    }
    setRunning(false);
  }

  /**
   * Replay the recorded reference transcript.
   *
   * Runs the whole journey with no network at all, so a reviewer can see every
   * proof immediately. It is labelled as a recorded transcript everywhere it is
   * shown and never claims to be a live inference.
   */
  function runRecorded() {
    if (running) return;
    setStarted(true);
    setStages(initialStages());
    setPrediction(null);
    setReplayProved(false);
    setFailureProved(false);
    setSource("recorded");

    const run = RECORDED_REFERENCE_RUN;
    setEvidence({
      scoreType: run.score_type,
      operatingThreshold: run.operating_threshold,
      modelVersion: run.model_version,
      bundleFormatVersion: run.bundle_format_version,
      evidenceCategory: "historical_reference_demo_inference",
      decisionEligible: false,
    });
    setModelInfo({
      schema_version: "1.0",
      model_version: run.model_version,
      bundle_format_version: run.bundle_format_version,
      model_artifact_sha256: run.model_artifact_sha256,
      evidence_category: "historical_reference_demo_inference",
    });
    setDecision("review");
    setAuditHash(run.audit_event_hash);
    setReplayProved(true);
    setFailureProved(true);

    const recorded: Record<DemoStageId, string> = {
      receive: `Recorded transcript for ${DEMO_FIXTURE_VERSION} loaded from the repository.`,
      validate: "Recorded: request schema accepted and the served bundle reported ready.",
      evaluate: "Recorded: the reference bundle returned HTTP 200 under schema 1.0.",
      decide: "Recorded: bounded policy routed this to human review. No payment action was taken.",
      explain: `Recorded: decided by comparing the ${run.score_type.replace(/_/g, " ")} against operating threshold ${run.operating_threshold.toFixed(2)}.`,
      audit: `Recorded audit receipt ${run.audit_event_hash.slice(0, 12)}… returned on both responses; no second event was claimed.`,
      replay: "Recorded: the API confirmed a replay and returned a byte-identical response.",
      failure: "Recorded: HTTP 422 · validation_error · no review outcome released.",
    };
    setStages(
      Object.fromEntries(
        DEMO_STAGES.map((stage) => [
          stage.id,
          { status: "success" as StageStatus, detail: recorded[stage.id] },
        ]),
      ) as Record<DemoStageId, StageState>,
    );
    setCursor(3);
  }

  /** Stage 7: prove the same reference does not create a second audit event. */
  async function runReplay() {
    if (running || !apiBaseUrl || !prediction) return;
    setRunning(true);
    setStage("replay", "running", `Re-sending reference ${DEMO_REQUEST_ID} with identical input.`);
    try {
      const response = await fetchWithDeadline(`${apiBaseUrl}/v1/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Request-ID": DEMO_REQUEST_ID },
        body: JSON.stringify(DEMO_FIXTURE),
      });
      const payload = await jsonOrNull(response);
      const replayConfirmed = response.headers.get("x-idempotent-replay") === "true";
      const replayHash = response.headers.get("x-audit-event-hash");
      const receiptMatches =
        auditHash !== null && replayHash === auditHash && AUDIT_HASH_PATTERN.test(replayHash);

      if (
        response.ok &&
        isPrediction(payload) &&
        replayConfirmed &&
        JSON.stringify(payload) === JSON.stringify(prediction)
      ) {
        setReplayProved(true);
        setStage(
          "replay",
          "success",
          "The API confirmed a replay and returned a byte-identical response.",
        );
        if (receiptMatches && auditHash) {
          setStage(
            "audit",
            "success",
            `Audit receipt ${auditHash.slice(0, 12)}… returned on both responses; no second event was claimed.`,
          );
        } else {
          setAuditHash(null);
          setStage(
            "audit",
            "unavailable",
            "The replay did not return the same readable receipt, so no confirmation is inferred.",
          );
        }
      } else {
        setStage("replay", "failure", "The API did not independently confirm an identical replay.");
      }
    } catch {
      setStage("replay", "unavailable", "The replay request could not reach the reference API.");
    }
    setCursor(6);
    setRunning(false);
  }

  /** Stage 8: prove a malformed request is rejected without releasing an outcome. */
  async function runFailure() {
    if (running || !apiBaseUrl) {
      setStage("failure", "unavailable", "The fail-closed proof needs the configured reference API.");
      setCursor(7);
      return;
    }
    setRunning(true);
    setStage("failure", "running", "Sending one deliberately malformed request.");
    try {
      const response = await fetchWithDeadline(`${apiBaseUrl}/v1/predict`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": INVALID_DEMO_REQUEST_ID,
        },
        body: JSON.stringify(INVALID_DEMO_FIXTURE),
      });
      const payload = await jsonOrNull(response);
      const leaked =
        typeof payload === "object" && payload !== null && "decision" in payload;
      if (
        response.status === 422 &&
        isErrorEnvelope(payload) &&
        payload.error.code === "validation_error" &&
        !leaked
      ) {
        setFailureProved(true);
        setStage(
          "failure",
          "success",
          `HTTP 422 · ${payload.error.code} · no review outcome released.`,
        );
      } else {
        setStage(
          "failure",
          "failure",
          `Expected a fail-closed HTTP 422; received HTTP ${response.status}.`,
        );
      }
    } catch {
      setStage("failure", "unavailable", "The fail-closed check could not reach the reference API.");
    }
    setCursor(7);
    setRunning(false);
  }

  const verifiedCount = useMemo(
    () => Object.values(stages).filter((stage) => stage.status === "success").length,
    [stages],
  );

  const coreComplete = CORE_STAGE_IDS.every(
    (id) => stages[id].status === "success" || stages[id].status === "unavailable",
  );
  const journeyComplete =
    coreComplete && stages.replay.status !== "pending" && stages.failure.status !== "pending";

  const traceRows = stageList.map((stage) => ({
    stage,
    ...stages[stage.id],
  }));

  return (
    <section aria-labelledby="guided-demo-title" data-demo-root className="grid gap-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(15rem,0.34fr)_minmax(0,1fr)] lg:items-start">
        {/* ---------------------------------------------------------------
            Journey rail
            --------------------------------------------------------------- */}
        <div className="command-panel p-4 sm:p-5">
          <div className="flex items-baseline justify-between gap-2">
            <h2 id="guided-demo-title" className="text-sm font-semibold text-white">
              Guided journey
            </h2>
            <span className="ss-provenance text-[11px] text-slate-500">
              {verifiedCount}/{stageList.length}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
            About two minutes end to end.
          </p>

          <ol className="ss-step-rail mt-3.5" aria-label="Demonstration stages">
            {stageList.map((stage, index) => {
              const state = stages[stage.id];
              return (
                <li key={stage.id}>
                  <button
                    type="button"
                    onClick={() => setCursor(index)}
                    aria-current={current.id === stage.id ? "step" : undefined}
                    data-demo-step={stage.index}
                    data-stage-id={stage.id}
                    className="ss-step-row w-full focus:outline-none"
                    data-current={current.id === stage.id}
                  >
                    <span
                      className={
                        state.status === "success"
                          ? "text-emerald-300"
                          : state.status === "unavailable"
                            ? "text-amber-300"
                            : state.status === "failure"
                              ? "text-rose-300"
                              : state.status === "running"
                                ? "text-blue-300"
                                : "text-slate-500"
                      }
                    >
                      <StateIcon
                        state={STATUS_STATE[state.status]}
                        className={`mt-0.5 h-4 w-4${
                          state.status === "running" ? " motion-safe:animate-spin" : ""
                        }`}
                      />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold text-white">
                        {stage.index}. {stage.title}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">
                        {stage.purpose}
                      </span>
                    </span>
                    <span className="sr-only" data-step-status={state.status}>
                      {STATUS_LABEL[state.status]}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        {/* ---------------------------------------------------------------
            Workspace
            --------------------------------------------------------------- */}
        <div className="grid min-w-0 gap-4">
          <div className="command-panel p-4 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="ss-eyebrow">
                  Stage {current.index} of {stageList.length}
                </p>
                <h3 className="mt-2 text-xl font-semibold text-white sm:text-2xl">
                  {current.title}
                </h3>
                <p className="mt-1.5 max-w-xl text-sm leading-6 text-slate-400">
                  {current.purpose}
                </p>
              </div>
              <StateChip
                state={STATUS_STATE[stages[current.id].status]}
                label={STATUS_LABEL[stages[current.id].status]}
              />
            </div>

            <p
              className="mt-4 rounded-lg border border-[var(--ss-border)] bg-[var(--ss-background)] p-3.5 text-sm leading-6 text-slate-300"
              aria-live="polite"
              data-stage-detail={current.id}
            >
              {stages[current.id].detail}
            </p>

            {!started ? (
              <div className="mt-4 grid gap-3 rounded-lg border border-[var(--ss-border)] bg-[var(--ss-surface-raised)] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-blue-200">
                  Before you start
                </p>
                <dl className="grid gap-2.5 text-xs leading-5 sm:grid-cols-2">
                  <div>
                    <dt className="text-slate-500">Scenario</dt>
                    <dd className="ss-provenance mt-0.5 break-all text-slate-200">
                      {DEMO_FIXTURE_VERSION}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Reference</dt>
                    <dd className="ss-provenance mt-0.5 break-all text-slate-200">
                      {DEMO_REQUEST_ID}
                    </dd>
                  </div>
                </dl>
                <p className="text-xs leading-5 text-slate-400">
                  This sends one fixed, sanitized synthetic scenario. There is no
                  editable transaction form, and no score is substituted when the
                  API is unavailable.
                </p>
              </div>
            ) : null}

            {source !== "none" ? (
              <p
                className="mt-4 flex items-start gap-2 rounded-lg border p-3 text-xs leading-5"
                data-demo-source={source}
                style={
                  source === "recorded"
                    ? {
                        borderColor: "var(--ss-warning-border)",
                        background: "var(--ss-warning-surface)",
                        color: "var(--ss-warning)",
                      }
                    : {
                        borderColor: "var(--ss-info-border)",
                        background: "var(--ss-info-surface)",
                        color: "var(--ss-info)",
                      }
                }
              >
                {source === "recorded"
                  ? RECORDED_RUN_LABEL
                  : "Live run against the configured reference API."}
              </p>
            ) : null}

            {/* Controls */}
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                ref={startRef}
                type="button"
                onClick={runCore}
                disabled={running}
                className="ss-action ss-action-primary focus:outline-none"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {started ? "Run decision again" : "Start guided demo"}
              </button>
              <button
                type="button"
                onClick={runRecorded}
                disabled={running}
                className="ss-action ss-action-secondary focus:outline-none"
              >
                <FileClock className="h-4 w-4" aria-hidden="true" />
                Run recorded reference
              </button>
              <button
                type="button"
                onClick={runReplay}
                disabled={running || !prediction}
                className="ss-action ss-action-secondary focus:outline-none disabled:opacity-45"
              >
                <Repeat2 className="h-4 w-4" aria-hidden="true" />
                Replay same request
              </button>
              <button
                type="button"
                onClick={runFailure}
                disabled={running}
                className="ss-action ss-action-secondary focus:outline-none disabled:opacity-45"
              >
                <ShieldX className="h-4 w-4" aria-hidden="true" />
                Test rejected request
              </button>
              <button
                type="button"
                onClick={() => setTraceOpen(true)}
                disabled={!started}
                className="ss-action ss-action-secondary focus:outline-none disabled:opacity-45"
              >
                <FileSearch className="h-4 w-4" aria-hidden="true" />
                Decision trace
              </button>
              <button
                type="button"
                onClick={resetDemo}
                className="ss-action ss-action-secondary focus:outline-none"
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Reset demo
              </button>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setCursor((value) => Math.max(0, value - 1))}
                disabled={cursor === 0}
                className="ss-chip focus:outline-none disabled:opacity-40"
              >
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                Back
              </button>
              <button
                type="button"
                onClick={() =>
                  setCursor((value) => Math.min(stageList.length - 1, value + 1))
                }
                disabled={cursor >= stageList.length - 1}
                className="ss-chip focus:outline-none disabled:opacity-40"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
          </div>

          {/* Result card */}
          <div className="command-panel p-4 sm:p-6" data-demo-result>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="ss-eyebrow">Bounded outcome</p>
                <p
                  data-demo-outcome
                  className="mt-2 text-2xl font-semibold text-white"
                >
                  {decision === "pending"
                    ? "Pending"
                    : decision === "review"
                      ? "Review"
                      : decision === "below_threshold"
                        ? "Below review threshold"
                        : "Unavailable"}
                </p>
              </div>
              <DecisionBadge decision={decision} />
            </div>
            <p className="mt-2.5 max-w-2xl text-sm leading-6 text-slate-400">
              {decisionMeaning(decision)}
            </p>

            <div className="mt-5 border-t border-[var(--ss-border)] pt-5">
              <DecisionZoneBand
                decision={decision}
                operatingThreshold={evidence?.operatingThreshold ?? null}
                idPrefix="demo-"
              />
            </div>

            {/* Explanation: only what the contract actually returns. */}
            <div className="mt-5 border-t border-[var(--ss-border)] pt-5">
              <p className="ss-eyebrow">Decision evidence</p>
              {evidence ? (
                <>
                  <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                    {[
                      ["Score type compared", evidence.scoreType.replace(/_/g, " ")],
                      ["Operating threshold", evidence.operatingThreshold.toFixed(2)],
                      ["Reference bundle", evidence.modelVersion],
                      ["Bundle format", evidence.bundleFormatVersion],
                      ["Evidence category", evidence.evidenceCategory],
                      [
                        "Decision eligible",
                        evidence.decisionEligible ? "Yes" : "No — demonstration only",
                      ],
                    ].map(([term, value]) => (
                      <div
                        key={term}
                        className="rounded-lg bg-[var(--ss-surface-raised)] p-3"
                      >
                        <dt className="text-slate-500">{term}</dt>
                        <dd className="ss-provenance mt-1 break-words text-slate-200">
                          {value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <p className="mt-3 rounded-lg border border-[var(--ss-border)] bg-[var(--ss-background)] p-3 text-xs leading-5 text-slate-400">
                    This contract publishes the comparison that produced the
                    outcome, not per-feature attribution, and it withholds the
                    decision score itself. Historical global feature ranking is
                    kept on{" "}
                    <Link href="/evidence#historical-analysis" className="ss-text-link min-h-0 text-xs">
                      the evidence route
                    </Link>{" "}
                    where its non-causal limits stay attached. Inputs are
                    anonymized PCA components with no merchant-readable meaning.
                  </p>
                </>
              ) : (
                <p className="mt-3 rounded-lg border border-dashed border-[var(--ss-border)] p-4 text-xs leading-5 text-slate-500">
                  No decision evidence yet. Start the guided demo to request one
                  bounded result.
                </p>
              )}
            </div>

            {/* Audit receipt */}
            <div className="mt-5 border-t border-[var(--ss-border)] pt-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="ss-eyebrow">Audit receipt</p>
                {auditHash ? (
                  <CopyButton value={auditHash} label="Copy audit reference" />
                ) : null}
              </div>
              {auditHash ? (
                <div className="mt-3 grid gap-2 text-xs">
                  <div className="rounded-lg bg-[var(--ss-surface-raised)] p-3">
                    <p className="text-slate-500">Committed receipt (truncated)</p>
                    <p className="ss-provenance mt-1 break-all text-slate-200">
                      {auditHash.slice(0, 16)}…
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StateChip state="verified" label="Receipt returned by API" />
                    {replayProved ? (
                      <StateChip state="verified" label="Replay · no second event" />
                    ) : null}
                  </div>
                  <p className="leading-5 text-slate-400">
                    The audit chain is append-only and{" "}
                    <strong className="font-semibold text-slate-200">tamper-evident</strong>:
                    altering a committed event breaks the chain, which
                    verification detects. It is not tamper-proof.
                  </p>
                </div>
              ) : (
                <p className="mt-3 rounded-lg border border-dashed border-[var(--ss-border)] p-4 text-xs leading-5 text-slate-500">
                  No audit receipt has been returned. The demo never invents one.
                </p>
              )}
            </div>

            {modelInfo?.model_artifact_sha256 ? (
              <p className="mt-4 text-[11px] leading-5 text-slate-500">
                Verified artifact:{" "}
                <span className="ss-provenance text-slate-300">
                  {modelInfo.model_artifact_sha256.slice(0, 12)}…
                </span>
              </p>
            ) : null}
          </div>

          {/* Completion recap */}
          {journeyComplete ? (
            <div
              className="command-panel p-4 sm:p-6"
              data-demo-complete
              aria-live="polite"
            >
              <p className="ss-eyebrow">Demonstration complete</p>
              <h3 className="mt-2 text-lg font-semibold text-white">
                What this run actually proved
              </h3>
              <ul className="mt-3 grid gap-2 text-xs leading-5 text-slate-300 sm:grid-cols-2">
                {[
                  ["Bounded outcome", "Review or below threshold only — never a payment action."],
                  ["Fail-closed", failureProved ? "Malformed input rejected with HTTP 422." : "Fail-closed path was not confirmed in this run."],
                  ["Idempotent replay", replayProved ? "Identical response, no second audit event." : "Replay was not confirmed in this run."],
                  ["Audit", auditHash ? "Tamper-evident receipt returned by the API." : "No receipt was returned; none was inferred."],
                ].map(([term, detail]) => (
                  <li key={term} className="rounded-lg bg-[var(--ss-surface-raised)] p-3">
                    <p className="font-semibold text-white">{term}</p>
                    <p className="mt-1 text-slate-400">{detail}</p>
                  </li>
                ))}
              </ul>
              <Link
                href="/evidence"
                prefetch={false}
                className="ss-action ss-action-primary mt-4 focus:outline-none"
              >
                Inspect the evidence
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          ) : null}
        </div>
      </div>

      <Drawer
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        labelledBy="decision-trace-title"
        title="Decision trace"
        description="Every stage of this run, with the status actually observed. Nothing is inferred."
      >
        <ol className="grid gap-2">
          {traceRows.map(({ stage, status, detail }) => (
            <li
              key={stage.id}
              className="rounded-lg border border-[var(--ss-border)] bg-[var(--ss-background)] p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-xs font-semibold text-white">
                  {stage.index}. {stage.title}
                </h3>
                <StateChip state={STATUS_STATE[status]} label={STATUS_LABEL[status]} />
              </div>
              <p className="mt-1.5 break-words text-[11px] leading-5 text-slate-400">
                {detail}
              </p>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-[11px] leading-5 text-slate-500">
          Stage durations are not shown because this contract does not return
          measured per-stage timings. Animation is never presented as timing
          evidence.
        </p>
      </Drawer>
    </section>
  );
}
