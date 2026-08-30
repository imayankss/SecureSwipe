import axe from "axe-core";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Navigation } from "@/components/Navigation";
import { ConfusionMatrix } from "@/components/ConfusionMatrix";
import { EvidenceDisclosure } from "@/components/evidence/EvidenceDisclosure";
import { Hero } from "@/components/Hero";
import { RiskScoreDemo } from "@/components/RiskScoreDemo";
import { Progress } from "@/components/ui/progress";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { dashboardData } from "@/data/metrics";

async function expectNoAxeViolations(container: HTMLElement) {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations).toEqual([]);
}

describe("keyboard and accessibility contracts", () => {
  it("keeps the live demo opt-in and shows the safe unavailable fallback", async () => {
    const user = userEvent.setup();
    render(<RiskScoreDemo apiBaseUrl={null} />);

    expect(screen.getByText("Static fallback active until the genuine inference check is requested.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try genuine inference" }));
    expect(screen.getByRole("status", { name: "Genuine demo inference status" })).toHaveTextContent("Live demo is not configured");
    expect(screen.getByText(/No customer or transaction data is used/)).toBeInTheDocument();
  });

  it("renders loading, success, empty, and API error states without replacing the static demo", async () => {
    const user = userEvent.setup();
    let resolveRequest: ((response: Response) => void) | undefined;
    const request = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });
    vi.stubGlobal("fetch", vi.fn(() => request));
    const { rerender } = render(<RiskScoreDemo apiBaseUrl="https://synthetic.example" />);

    await user.click(screen.getByRole("button", { name: "Try genuine inference" }));
    expect(screen.getByRole("button", { name: "Checking API…" })).toBeDisabled();
    resolveRequest?.(new Response(JSON.stringify({
      schema_version: "1.0",
      request_id: "unit-live-1",
      raw_score: 0.91,
      calibrated_probability: null,
      decision_score: 0.91,
      score_type: "raw_score",
      operating_threshold: 0.53,
      decision: "human_review",
      model_version: "unit-test-bundle-1",
      bundle_format_version: "3",
      provenance: {
        training_data_fingerprint: "unit-test-fingerprint",
        evidence_category: "historical_reference_demo_inference",
        historical_taint: true,
        decision_eligible: false,
        historical_metrics_claimed: false,
        evaluation_performed: false,
      },
    }), { status: 200 }));
    expect(
      await screen.findByText(/Genuine demo inference result: human review at score 0\.910.*historical_reference_demo_inference; decision eligible: no\./),
    ).toBeInTheDocument();

    vi.stubGlobal("fetch", vi.fn(async () => new Response("null", { status: 200 })));
    rerender(<RiskScoreDemo apiBaseUrl="https://synthetic.example" />);
    await user.click(screen.getByRole("button", { name: "Try genuine inference" }));
    expect(await screen.findByRole("status", { name: "Genuine demo inference status" })).toHaveTextContent("no usable prediction");

    vi.stubGlobal("fetch", vi.fn(async () => new Response("null", { status: 504 })));
    rerender(<RiskScoreDemo apiBaseUrl="https://synthetic.example" />);
    await user.click(screen.getByRole("button", { name: "Try genuine inference" }));
    expect(await screen.findByRole("status", { name: "Genuine demo inference status" })).toHaveTextContent(
      "timed out; inference remains unavailable / fail closed",
    );

    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    rerender(<RiskScoreDemo apiBaseUrl="https://synthetic.example" />);
    await user.click(screen.getByRole("button", { name: "Try genuine inference" }));
    expect(await screen.findByRole("status", { name: "Genuine demo inference status" })).toHaveTextContent("could not be reached");
  });

  it("exposes responsive navigation and safe external-link semantics", async () => {
    const user = userEvent.setup();
    const { container } = render(<Navigation activePage="product" />);

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    const menu = screen.getByText("Pages");
    await user.click(menu);
    expect(menu.closest("details")).toHaveAttribute("open");
    expect(screen.getAllByRole("link", { name: "Evidence" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Overview" })[0]).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Open SecureSwipe GitHub repository" })).toHaveAttribute(
      "rel",
      expect.stringContaining("noopener"),
    );
    await expectNoAxeViolations(container);
  });

  it("exposes secondary evidence through an explicit keyboard disclosure", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <EvidenceDisclosure
        id="test-evidence"
        eyebrow="Secondary evidence"
        title="Inspect supporting analysis"
        description="Supporting detail remains one clear interaction away."
      >
        <p>Preserved supporting evidence</p>
      </EvidenceDisclosure>,
    );

    const control = screen.getByRole("button", {
      name: "Show details: Inspect supporting analysis",
    });
    const region = container.querySelector<HTMLElement>("#test-evidence-content");
    expect(control).toHaveAttribute("aria-expanded", "false");
    expect(control).toHaveAttribute("aria-controls", "test-evidence-content");
    expect(region).toHaveAttribute("hidden");

    control.focus();
    await user.keyboard("{Enter}");
    expect(control).toHaveAttribute("aria-expanded", "true");
    expect(control).toHaveAccessibleName("Hide details: Inspect supporting analysis");
    expect(region).not.toHaveAttribute("hidden");
    expect(screen.getByText("Preserved supporting evidence")).toBeVisible();
    await expectNoAxeViolations(container);
  });

  it("announces risk-state changes and supports keyboard range input", async () => {
    const { container } = render(<RiskScoreDemo />);

    const status = screen.getByRole("status", { name: "Hypothetical review decision" });
    expect(status).toHaveTextContent("Send to review");
    const slider = screen.getByRole("slider", { name: "Adjust hypothetical score" });
    fireEvent.change(slider, { target: { value: "52" } });
    expect(status).toHaveTextContent("Below review threshold");
    expect(screen.getByRole("progressbar", { name: "Hypothetical model score" })).toHaveAttribute(
      "aria-valuenow",
      "52",
    );
    await expectNoAxeViolations(container);
  });

  it("gives progress and table primitives machine-readable semantics", async () => {
    const { container } = render(
      <>
        <Progress value={125} />
        <Table>
          <THead>
            <TR>
              <TH>Metric</TH>
            </TR>
          </THead>
          <TBody>
            <TR>
              <TD>Average precision</TD>
            </TR>
          </TBody>
        </Table>
      </>,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByRole("columnheader", { name: "Metric" })).toHaveAttribute("scope", "col");
    await expectNoAxeViolations(container);
  });
});

describe("static deployment boundary", () => {
  it("keeps the reviewed dashboard in precomputed demonstration mode", () => {
    expect(dashboardData.project.deploymentMode).toBe("precomputed-demonstration");
    expect(dashboardData.limitations).toContain(
      "Dashboard interactions use precomputed validation and test artifacts, not live inference.",
    );
  });

  it("qualifies historical and explainability claims in the visible UI", () => {
    const { container } = render(
      <>
        <Hero />
        <ConfusionMatrix />
      </>,
    );
    expect(screen.getByText(/Locked historical artifacts/)).toBeInTheDocument();
    expect(screen.getAllByText(/already-observed random-holdout/)).toHaveLength(2);
    expect(screen.getByText(/Historical reported confusion matrix/)).toBeInTheDocument();
    expect(container).not.toHaveTextContent("Verified artifacts");
    expect(container).not.toHaveTextContent("Final confusion matrix");
  });
});
