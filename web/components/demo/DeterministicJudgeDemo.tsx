"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Play,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";

import {
  DEMO_FIXTURE,
  DEMO_FIXTURE_VERSION,
  DEMO_REQUEST_ID,
  INVALID_DEMO_FIXTURE,
  INVALID_DEMO_REQUEST_ID,
} from "@/lib/deterministic-demo";

const REQUEST_TIMEOUT_MS = 4_000;
const AUDIT_HASH_PATTERN = /^[a-f0-9]{64}$/;

type StepStatus = "pending" | "running" | "success" | "unavailable" | "failure";

type DemoStep = {
  id: number;
  title: string;
  status: StepStatus;
  detail: string;
};

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

type DemoOutcome = "Review" | "Below review threshold" | "Unavailable" | null;

const STEP_DEFINITIONS = [
  [1, "Load fixed sanitized fixture", "Waiting to load the local synthetic fixture."],
  [2, "Request bounded API result", "Waiting for the configured local reference API."],
  [3, "Show returned review outcome", "No outcome has been returned."],
  [4, "Confirm genuine audit event", "No audit confirmation has been returned."],
  [5, "Replay the same fixed ID", "The replay request has not run."],
  [6, "Reject deliberately malformed input", "The fail-closed check has not run."],
] as const;

function initialSteps(): DemoStep[] {
  return STEP_DEFINITIONS.map(([id, title, detail]) => ({
    id,
    title,
    detail,
    status: "pending",
  }));
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
    ) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function isEvidenceCategory(value: unknown): value is EvidenceCategory {
  return value === "synthetic_demo_inference" ||
    value === "new_authorized_development_evidence" ||
    value === "historical_reference_demo_inference";
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
    typeof prediction.raw_score === "number" && Number.isFinite(prediction.raw_score) &&
    (prediction.calibrated_probability === null ||
      (typeof prediction.calibrated_probability === "number" &&
        Number.isFinite(prediction.calibrated_probability))) &&
    typeof prediction.decision_score === "number" &&
    Number.isFinite(prediction.decision_score) &&
    (prediction.score_type === "raw_score" || prediction.score_type === "calibrated_probability") &&
    typeof prediction.operating_threshold === "number" &&
    Number.isFinite(prediction.operating_threshold) &&
    (prediction.decision === "human_review" || prediction.decision === "below_review_threshold") &&
    typeof prediction.model_version === "string" && prediction.model_version.length > 0 &&
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
    typeof info.model_version === "string" && info.model_version.length > 0 &&
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
  return payload.schema_version === "1.0" &&
    typeof payload.request_id === "string" &&
    typeof error.code === "string" &&
    typeof error.message === "string";
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

function statusLabel(status: StepStatus) {
  return {
    pending: "Pending",
    running: "Running",
    success: "Verified",
    unavailable: "Unavailable",
    failure: "Failed",
  }[status];
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "success") return <CheckCircle2 className="h-5 w-5" aria-hidden="true" />;
  if (status === "unavailable") return <ShieldAlert className="h-5 w-5" aria-hidden="true" />;
  if (status === "failure") return <AlertTriangle className="h-5 w-5" aria-hidden="true" />;
  return <Circle className="h-5 w-5" aria-hidden="true" />;
}

export function DeterministicJudgeDemo({
  apiBaseUrl = apiUrlFromEnvironment(),
}: {
  apiBaseUrl?: string | null;
} = {}) {
  const [steps, setSteps] = useState<DemoStep[]>(initialSteps);
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<DemoOutcome>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [auditHash, setAuditHash] = useState<string | null>(null);

  function updateStep(id: number, status: StepStatus, detail: string) {
    setSteps((current) => current.map((step) => (
      step.id === id ? { ...step, status, detail } : step
    )));
  }

  function markUnavailable(from: number, detail: string) {
    setSteps((current) => current.map((step) => (
      step.id >= from && step.id <= 5 ? { ...step, status: "unavailable", detail } : step
    )));
    setOutcome("Unavailable");
  }

  async function demonstrateInvalidInput(baseUrl: string) {
    updateStep(6, "running", "Sending one deliberately malformed synthetic request.");
    try {
      const response = await fetchWithDeadline(`${baseUrl}/v1/predict`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": INVALID_DEMO_REQUEST_ID,
        },
        body: JSON.stringify(INVALID_DEMO_FIXTURE),
      });
      const payload = await jsonOrNull(response);
      const leakedDecision = typeof payload === "object" && payload !== null && "decision" in payload;
      if (response.status === 422 && isErrorEnvelope(payload) &&
        payload.error.code === "validation_error" && !leakedDecision) {
        updateStep(
          6,
          "success",
          `HTTP 422 · ${payload.error.code} · no review outcome released.`,
        );
        return;
      }
      updateStep(6, "failure", `Expected fail-closed HTTP 422; received HTTP ${response.status}.`);
    } catch {
      updateStep(6, "unavailable", "Malformed-input check could not reach the configured API.");
    }
  }

  async function runWalkthrough() {
    if (running) return;
    setRunning(true);
    setSteps(initialSteps());
    setOutcome(null);
    setModelInfo(null);
    setAuditHash(null);
    updateStep(
      1,
      "success",
      `${DEMO_FIXTURE_VERSION} loaded with fixed request ID ${DEMO_REQUEST_ID}.`,
    );

    if (!apiBaseUrl) {
      markUnavailable(2, "No valid local reference API origin was configured at build time.");
      updateStep(6, "unavailable", "Malformed-input check requires the configured local API.");
      setRunning(false);
      return;
    }

    updateStep(2, "running", "Checking readiness before requesting a bounded result.");
    let readyResponse: Response;
    let infoResponse: Response;
    try {
      [readyResponse, infoResponse] = await Promise.all([
        fetchWithDeadline(`${apiBaseUrl}/health/ready`),
        fetchWithDeadline(`${apiBaseUrl}/v1/model-info`),
      ]);
    } catch {
      markUnavailable(2, "Unavailable — fail closed. The configured local API could not be reached.");
      updateStep(6, "unavailable", "Malformed-input check could not reach the configured API.");
      setRunning(false);
      return;
    }

    const readyPayload = await jsonOrNull(readyResponse);
    const infoPayload = await jsonOrNull(infoResponse);
    if (infoResponse.ok && isModelInfo(infoPayload)) setModelInfo(infoPayload);
    if (!readyResponse.ok || typeof readyPayload !== "object" || readyPayload === null ||
      (readyPayload as Record<string, unknown>).status !== "ready") {
      markUnavailable(2, "Unavailable — fail closed. The configured API is not model-ready.");
      await demonstrateInvalidInput(apiBaseUrl);
      setRunning(false);
      return;
    }

    let firstPrediction: Prediction | null = null;
    let confirmedAuditHash: string | null = null;
    try {
      const firstResponse = await fetchWithDeadline(`${apiBaseUrl}/v1/predict`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": DEMO_REQUEST_ID,
        },
        body: JSON.stringify(DEMO_FIXTURE),
      });
      const firstPayload = await jsonOrNull(firstResponse);
      if (!firstResponse.ok || !isPrediction(firstPayload) ||
        firstPayload.request_id !== DEMO_REQUEST_ID) {
        const detail = isErrorEnvelope(firstPayload)
          ? `Unavailable — fail closed. API returned ${firstPayload.error.code}.`
          : `Unavailable — fail closed. API returned HTTP ${firstResponse.status}.`;
        markUnavailable(2, detail);
      } else {
        firstPrediction = firstPayload;
        updateStep(2, "success", "Configured local reference API returned HTTP 200.");
        const label = firstPayload.decision === "human_review" ? "Review" : "Below review threshold";
        setOutcome(label);
        updateStep(3, "success", `${label} · returned by API schema ${firstPayload.schema_version}.`);

        const committedAuditHash = firstResponse.headers.get("x-audit-event-hash");
        if (committedAuditHash && AUDIT_HASH_PATTERN.test(committedAuditHash)) {
          confirmedAuditHash = committedAuditHash;
          setAuditHash(committedAuditHash);
          updateStep(
            4,
            "success",
            `Original committed audit event ${committedAuditHash.slice(0, 12)}… confirmed by API receipt.`,
          );
        } else {
          updateStep(
            4,
            "unavailable",
            "No audit-event confirmation was returned; the demo does not infer one.",
          );
        }
      }
    } catch {
      markUnavailable(2, "Unavailable — fail closed. The prediction request did not complete.");
    }

    if (firstPrediction) {
      updateStep(5, "running", `Replaying ${DEMO_REQUEST_ID} with identical canonical input.`);
      try {
        const replayResponse = await fetchWithDeadline(`${apiBaseUrl}/v1/predict`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": DEMO_REQUEST_ID,
          },
          body: JSON.stringify(DEMO_FIXTURE),
        });
        const replayPayload = await jsonOrNull(replayResponse);
        const replayConfirmed = replayResponse.headers.get("x-idempotent-replay") === "true";
        const replayAuditHash = replayResponse.headers.get("x-audit-event-hash");
        const receiptMatches = confirmedAuditHash !== null &&
          replayAuditHash === confirmedAuditHash && AUDIT_HASH_PATTERN.test(replayAuditHash);
        if (replayResponse.ok && isPrediction(replayPayload) && replayConfirmed &&
          JSON.stringify(replayPayload) === JSON.stringify(firstPrediction)) {
          updateStep(5, "success", "API confirmed a same-process replay; response matched exactly.");
          if (receiptMatches && confirmedAuditHash) {
            updateStep(
              4,
              "success",
              `Original committed audit event ${confirmedAuditHash.slice(0, 12)}… confirmed on both responses; no new event claimed.`,
            );
          } else {
            setAuditHash(null);
            updateStep(
              4,
              "unavailable",
              "The replay did not return the same readable original audit receipt; no confirmation is inferred.",
            );
          }
        } else {
          updateStep(5, "failure", "The API did not independently confirm an identical replay.");
        }
      } catch {
        updateStep(5, "unavailable", "Replay could not reach the configured local API.");
      }
    }

    await demonstrateInvalidInput(apiBaseUrl);
    setRunning(false);
  }

  const successfulSteps = steps.filter((step) => step.status === "success").length;

  return (
    <section aria-labelledby="walkthrough-title" className="ss-card p-5 sm:p-7 lg:p-8">
      <div className="grid gap-6 lg:grid-cols-[0.72fr_1.28fr] lg:gap-10">
        <div>
          <p className="ss-eyebrow">Fixed local sequence</p>
          <h2 id="walkthrough-title" className="mt-3 text-2xl sm:text-3xl">
            One control, six truthful checks
          </h2>
          <p className="mt-4 max-w-xl text-sm leading-6 text-slate-300">
            The page sends only a fixed synthetic fixture. It has no editable transaction form and
            never substitutes a static score when the API is unavailable.
          </p>

          <dl className="mt-6 grid gap-3 text-sm">
            <div className="rounded-lg bg-[var(--ss-surface-raised)] p-4">
              <dt className="ss-eyebrow">Fixture</dt>
              <dd className="mt-2 text-slate-200">{DEMO_FIXTURE_VERSION} · sanitized generated constants</dd>
            </div>
            <div className="rounded-lg bg-[var(--ss-surface-raised)] p-4">
              <dt className="ss-eyebrow">Fixed request ID</dt>
              <dd className="ss-provenance mt-2 break-all text-xs text-slate-200">{DEMO_REQUEST_ID}</dd>
            </div>
          </dl>

          <button
            type="button"
            onClick={runWalkthrough}
            disabled={running}
            className="ss-action ss-action-primary mt-6 w-full focus:outline-none sm:w-auto"
          >
            {running ? <Circle className="h-4 w-4" aria-hidden="true" /> :
              successfulSteps > 0 ? <RotateCcw className="h-4 w-4" aria-hidden="true" /> :
                <Play className="h-4 w-4" aria-hidden="true" />}
            {running ? "Running deterministic walkthrough…" :
              successfulSteps > 0 ? "Run deterministic walkthrough again" :
                "Run deterministic walkthrough"}
          </button>

          <div className="mt-6 rounded-lg border border-[var(--ss-border)] bg-[var(--ss-background)] p-4" aria-live="polite">
            <p className="ss-eyebrow">Current bounded outcome</p>
            <p data-demo-outcome className="mt-2 text-xl font-semibold text-white">
              {outcome ?? "Pending"}
            </p>
            {modelInfo ? (
              <div className="mt-3 space-y-1 text-xs leading-5 text-slate-400">
                <p>Reference bundle: <span className="ss-provenance text-slate-200">{modelInfo.model_version}</span></p>
                <p>Schema: <span className="ss-provenance text-slate-200">{modelInfo.schema_version}</span></p>
                {modelInfo.model_artifact_sha256 ? (
                  <p>Verified artifact: <span className="ss-provenance text-slate-200">{modelInfo.model_artifact_sha256.slice(0, 12)}…</span></p>
                ) : null}
                <p>Evidence category: <span className="ss-provenance break-all text-slate-200">{modelInfo.evidence_category}</span></p>
              </div>
            ) : null}
            {auditHash ? (
              <p className="mt-3 text-xs text-slate-400">
                Audit confirmation: <span className="ss-provenance text-slate-200">{auditHash.slice(0, 12)}…</span>
              </p>
            ) : null}
          </div>
        </div>

        <ol className="grid gap-3" aria-label="Deterministic demonstration steps">
          {steps.map((step) => (
            <li
              key={step.id}
              data-demo-step={step.id}
              className="rounded-xl border border-[var(--ss-border)] bg-[var(--ss-background)] p-4 sm:p-5"
            >
              <div className="flex gap-3">
                <span
                  className={
                    `mt-0.5 shrink-0 ${
                      step.status === "success" ? "text-emerald-300" :
                      step.status === "unavailable" ? "text-amber-300" :
                      step.status === "failure" ? "text-rose-300" :
                      step.status === "running" ? "text-blue-300" : "text-slate-500"
                    }`
                  }
                >
                  <StepIcon status={step.status} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-base font-semibold">{step.id}. {step.title}</h3>
                    <span className="ss-chip min-h-0 px-2 py-1 text-[10px]" data-step-status={step.status}>
                      {statusLabel(step.status)}
                    </span>
                  </div>
                  <p className="mt-2 break-words text-sm leading-6 text-slate-400">{step.detail}</p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
