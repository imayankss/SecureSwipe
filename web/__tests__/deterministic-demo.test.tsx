import axe from "axe-core";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DemoPage from "@/app/demo/page";
import { DeterministicJudgeDemo } from "@/components/demo/DeterministicJudgeDemo";
import {
  DEMO_FIXTURE,
  DEMO_FIXTURE_VERSION,
  DEMO_REQUEST_ID,
  INVALID_DEMO_REQUEST_ID,
} from "@/lib/deterministic-demo";

const AUDIT_HASH = "a".repeat(64);
const MODEL_HASH = "b".repeat(64);

const prediction = {
  schema_version: "1.0",
  request_id: DEMO_REQUEST_ID,
  raw_score: 0.731,
  calibrated_probability: null,
  decision_score: 0.731,
  score_type: "raw_score",
  operating_threshold: 0.53,
  decision: "human_review",
  model_version: "synthetic-smoke-1",
  bundle_format_version: "3",
  provenance: {
    training_data_fingerprint: "c".repeat(64),
    evidence_category: "synthetic_demo_inference",
    historical_taint: false,
    decision_eligible: false,
    historical_metrics_claimed: false,
    evaluation_performed: false,
  },
} as const;

const modelInfo = {
  schema_version: "1.0",
  model_version: "synthetic-smoke-1",
  bundle_format_version: "3",
  model_artifact_sha256: MODEL_HASH,
  evidence_category: "synthetic_demo_inference",
};

function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** A ready API that records every valid prediction request it receives. */
function readyApi(validRequests: RequestInit[]) {
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/health/ready")) {
      return jsonResponse({
        schema_version: "1.0",
        status: "ready",
        model_version: "synthetic-smoke-1",
      });
    }
    if (url.endsWith("/v1/model-info")) return jsonResponse(modelInfo);

    const requestId = new Headers(init?.headers).get("X-Request-ID");
    if (requestId === INVALID_DEMO_REQUEST_ID) {
      return jsonResponse(
        {
          schema_version: "1.0",
          request_id: INVALID_DEMO_REQUEST_ID,
          error: { code: "validation_error", message: "Request validation failed." },
        },
        422,
      );
    }

    validRequests.push(init ?? {});
    return jsonResponse(prediction, 200, {
      "X-Audit-Event-Hash": AUDIT_HASH,
      ...(validRequests.length > 1 ? { "X-Idempotent-Replay": "true" } : {}),
    });
  });
}

const startButton = () => screen.getByRole("button", { name: "Start guided demo" });
const replayButton = () => screen.getByRole("button", { name: "Replay same request" });
const rejectButton = () => screen.getByRole("button", { name: "Test rejected request" });

describe("guided deterministic demo", () => {
  it("keeps the fixture and request identifiers immutable and deterministic", () => {
    expect(DEMO_FIXTURE_VERSION).toBe("fixed-synthetic-v1");
    expect(DEMO_REQUEST_ID).toBe("secureswipe-reference-demo-v1");
    expect(INVALID_DEMO_REQUEST_ID).toBe("secureswipe-reference-demo-invalid-v1");
    expect(Object.isFrozen(DEMO_FIXTURE)).toBe(true);
    expect(Object.keys(DEMO_FIXTURE)).toHaveLength(30);
  });

  it("runs decision, replay, and fail-closed proofs from real API payloads", async () => {
    const validRequests: RequestInit[] = [];
    vi.stubGlobal("fetch", readyApi(validRequests));
    const user = userEvent.setup();
    const { container } = render(
      <DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />,
    );

    // Keyboard-only start.
    startButton().focus();
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Review");
    });
    expect(validRequests).toHaveLength(1);

    // The suppressed decision score must never reach the document.
    expect(screen.queryByText("0.731")).toBeNull();
    expect(document.body.textContent).not.toContain("0.731");

    await user.click(replayButton());
    // The replay proof must be visible on the persistent audit panel, not only
    // inside the stage the cursor happens to be on.
    await waitFor(() => {
      expect(screen.getByText("Replay · no second event")).toBeInTheDocument();
    });
    expect(screen.getByText(/byte-identical response/i)).toBeInTheDocument();
    expect(validRequests).toHaveLength(2);

    await user.click(rejectButton());
    await waitFor(() => {
      expect(
        screen.getByText(/HTTP 422 · validation_error · no review outcome released/),
      ).toBeInTheDocument();
    });

    // Every valid request carried the identical reference and identical body.
    for (const request of validRequests) {
      expect(new Headers(request.headers).get("X-Request-ID")).toBe(DEMO_REQUEST_ID);
      expect(JSON.parse(String(request.body))).toEqual(DEMO_FIXTURE);
    }

    // Completion recap appears only once the whole journey has run.
    expect(container.querySelector("[data-demo-complete]")).not.toBeNull();
    expect(screen.getByRole("link", { name: /Inspect the evidence/i })).toHaveAttribute(
      "href",
      "/evidence",
    );

    expect(
      (await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations,
    ).toEqual([]);
  });

  it("opens a focus-managed decision trace and returns focus on Escape", async () => {
    const validRequests: RequestInit[] = [];
    vi.stubGlobal("fetch", readyApi(validRequests));
    const user = userEvent.setup();
    render(<DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />);

    await user.click(startButton());

    const trigger = screen.getByRole("button", { name: "Decision trace" });
    await user.click(trigger);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getByRole("heading", { name: "Decision trace" })).toBeInTheDocument();
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it("resets every stage back to its idle state", async () => {
    const validRequests: RequestInit[] = [];
    vi.stubGlobal("fetch", readyApi(validRequests));
    const user = userEvent.setup();
    const { container } = render(
      <DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />,
    );

    await user.click(startButton());
    await waitFor(() => {
      expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Review");
    });

    await user.click(screen.getByRole("button", { name: "Reset demo" }));
    expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Pending");
    expect(container.querySelector("[data-demo-complete]")).toBeNull();
    expect(container.querySelectorAll('[data-step-status="pending"]')).toHaveLength(8);
  });

  it("shows unavailable without issuing a request when no API origin is configured", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(<DeterministicJudgeDemo apiBaseUrl={null} />);

    await user.click(startButton());

    expect(fetchMock).not.toHaveBeenCalled();
    expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Unavailable");
    expect(screen.queryByText(/raw score/i)).toBeNull();
    expect(document.body.textContent).not.toContain("0.731");
  });

  it("keeps an unready API unavailable while malformed input still fails closed", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health/ready")) {
        return jsonResponse(
          { schema_version: "1.0", status: "not_ready", model_version: null },
          503,
        );
      }
      if (url.endsWith("/v1/model-info")) {
        return jsonResponse(
          {
            schema_version: "1.0",
            request_id: "model-unavailable",
            error: { code: "model_unavailable", message: "No verified bundle." },
          },
          503,
        );
      }
      return jsonResponse(
        {
          schema_version: "1.0",
          request_id: INVALID_DEMO_REQUEST_ID,
          error: { code: "validation_error", message: "Request validation failed." },
        },
        422,
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(
      <DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />,
    );

    await user.click(startButton());
    await waitFor(() => {
      expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Unavailable");
    });

    await user.click(rejectButton());
    await waitFor(() => {
      expect(screen.getByText(/HTTP 422 · validation_error/)).toBeInTheDocument();
    });
    expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Unavailable");
  });

  it("renders the required evidence separation without prohibited claims", () => {
    render(<DemoPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Local reference-model demonstration",
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      "This interactive reference demo is separate from the sealed Lane A evaluation and does not claim to serve the headline model.",
    );
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(
      /fraud probability|autonomous block|payment authorization|live merchant|Razorpay-integrated/i,
    );
    expect(text).not.toMatch(/serves? the Lane A model|Lane A model result/i);
    // Never soften "below review threshold" into an approval.
    expect(text).not.toMatch(/\bapproved\b|\bsafe transaction\b|\blegitimate\b/i);
    // Tamper-evident, never tamper-proof.
    expect(text).not.toMatch(/tamper-proof/i);
  });
});
