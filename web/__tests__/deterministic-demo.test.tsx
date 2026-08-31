import axe from "axe-core";
import { render, screen, waitFor } from "@testing-library/react";
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

describe("deterministic judge demo", () => {
  it("keeps the fixture and request identifiers immutable and deterministic", () => {
    expect(DEMO_FIXTURE_VERSION).toBe("fixed-synthetic-v1");
    expect(DEMO_REQUEST_ID).toBe("secureswipe-reference-demo-v1");
    expect(INVALID_DEMO_REQUEST_ID).toBe("secureswipe-reference-demo-invalid-v1");
    expect(Object.isFrozen(DEMO_FIXTURE)).toBe(true);
    expect(Object.keys(DEMO_FIXTURE)).toHaveLength(30);
    expect(JSON.stringify(DEMO_FIXTURE)).toBe(JSON.stringify(DEMO_FIXTURE));
  });

  it("uses real API payloads for outcome, audit, replay, and fail-closed validation", async () => {
    const validRequests: RequestInit[] = [];
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health/ready")) {
        return jsonResponse({ schema_version: "1.0", status: "ready", model_version: "synthetic-smoke-1" });
      }
      if (url.endsWith("/v1/model-info")) return jsonResponse(modelInfo);

      const requestId = new Headers(init?.headers).get("X-Request-ID");
      if (requestId === INVALID_DEMO_REQUEST_ID) {
        return jsonResponse({
          schema_version: "1.0",
          request_id: INVALID_DEMO_REQUEST_ID,
          error: { code: "validation_error", message: "Request validation failed." },
        }, 422);
      }

      validRequests.push(init ?? {});
      return jsonResponse(
        prediction,
        200,
        {
          "X-Audit-Event-Hash": AUDIT_HASH,
          ...(validRequests.length > 1 ? { "X-Idempotent-Replay": "true" } : {}),
        },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(
      <DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />,
    );

    const run = screen.getByRole("button", { name: "Run deterministic walkthrough" });
    run.focus();
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(container.querySelectorAll('[data-step-status="success"]')).toHaveLength(6);
    });
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText(/Original committed audit event aaaaaaaaaaaa… confirmed on both responses/)).toBeInTheDocument();
    expect(screen.getByText(/same-process replay; response matched exactly/i)).toBeInTheDocument();
    expect(screen.getByText(/HTTP 422 · validation_error · no review outcome released/)).toBeInTheDocument();
    expect(screen.getByText(/Verified artifact:/)).toHaveTextContent("bbbbbbbbbbbb…");
    expect(screen.queryByText("0.731")).toBeNull();

    expect(validRequests).toHaveLength(2);
    for (const request of validRequests) {
      expect(new Headers(request.headers).get("X-Request-ID")).toBe(DEMO_REQUEST_ID);
      expect(JSON.parse(String(request.body))).toEqual(DEMO_FIXTURE);
    }
    expect(fetchMock).toHaveBeenCalledTimes(5);

    await user.click(screen.getByRole("button", { name: "Run deterministic walkthrough again" }));
    await waitFor(() => {
      expect(container.querySelectorAll('[data-step-status="success"]')).toHaveLength(6);
    });
    expect(screen.getByText(/Original committed audit event aaaaaaaaaaaa… confirmed on both responses/)).toBeInTheDocument();
    expect(validRequests).toHaveLength(4);
    expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  });

  it("keeps audit confirmation unavailable when replay receipt is absent", async () => {
    let validRequestCount = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health/ready")) {
        return jsonResponse({ schema_version: "1.0", status: "ready", model_version: "synthetic-smoke-1" });
      }
      if (url.endsWith("/v1/model-info")) return jsonResponse(modelInfo);
      if (new Headers(init?.headers).get("X-Request-ID") === INVALID_DEMO_REQUEST_ID) {
        return jsonResponse({
          schema_version: "1.0",
          request_id: INVALID_DEMO_REQUEST_ID,
          error: { code: "validation_error", message: "Request validation failed." },
        }, 422);
      }
      validRequestCount += 1;
      return jsonResponse(prediction, 200, {
        ...(validRequestCount === 1 ? { "X-Audit-Event-Hash": AUDIT_HASH } : {}),
        ...(validRequestCount > 1 ? { "X-Idempotent-Replay": "true" } : {}),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(
      <DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />,
    );

    await user.click(screen.getByRole("button", { name: "Run deterministic walkthrough" }));

    await waitFor(() => {
      expect(container.querySelector('[data-demo-step="4"] [data-step-status="unavailable"]')).not.toBeNull();
    });
    expect(screen.getByText(/replay did not return the same readable original audit receipt/i)).toBeInTheDocument();
    expect(screen.queryByText(/no new event claimed/i)).toBeNull();
  });

  it("shows unavailable without issuing a request when no API origin is configured", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(<DeterministicJudgeDemo apiBaseUrl={null} />);

    await user.click(screen.getByRole("button", { name: "Run deterministic walkthrough" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Unavailable");
    expect(container.querySelectorAll('[data-step-status="unavailable"]')).toHaveLength(5);
    expect(screen.queryByText(/raw score/i)).toBeNull();
  });

  it("keeps an unready API unavailable while still proving malformed input fails closed", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health/ready")) {
        return jsonResponse({ schema_version: "1.0", status: "not_ready", model_version: null }, 503);
      }
      if (url.endsWith("/v1/model-info")) {
        return jsonResponse({
          schema_version: "1.0",
          request_id: "model-unavailable",
          error: { code: "model_unavailable", message: "No verified bundle." },
        }, 503);
      }
      return jsonResponse({
        schema_version: "1.0",
        request_id: INVALID_DEMO_REQUEST_ID,
        error: { code: "validation_error", message: "Request validation failed." },
      }, 422);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(
      <DeterministicJudgeDemo apiBaseUrl="http://127.0.0.1:8000" />,
    );

    await user.click(screen.getByRole("button", { name: "Run deterministic walkthrough" }));

    await waitFor(() => {
      expect(container.querySelector('[data-demo-step="6"] [data-step-status="success"]')).not.toBeNull();
    });
    expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Unavailable");
    expect(screen.getAllByText(/configured API is not model-ready/i)).toHaveLength(4);
    expect(screen.getByText(/HTTP 422 · validation_error/)).toBeInTheDocument();
  });

  it("renders the required evidence separation without prohibited outcome claims", () => {
    render(<DemoPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Local reference-model demonstration",
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      "This interactive reference demo is separate from the sealed Lane A evaluation and does not claim to serve the headline model.",
    );
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/fraud probability|autonomous block|payment authorization|live merchant|Razorpay-integrated/i);
    expect(text).not.toMatch(/serves? the Lane A model|Lane A model result/i);
  });
});
