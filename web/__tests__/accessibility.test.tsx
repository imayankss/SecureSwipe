import axe from "axe-core";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Navigation } from "@/components/Navigation";
import { ConfusionMatrix } from "@/components/ConfusionMatrix";
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
  it("exposes responsive navigation and safe external-link semantics", async () => {
    const user = userEvent.setup();
    const { container } = render(<Navigation />);

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    const menu = screen.getByText("Sections");
    await user.click(menu);
    expect(menu.closest("details")).toHaveAttribute("open");
    expect(screen.getAllByRole("link", { name: "Thresholds" })).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Open SecureSwipe GitHub repository" })).toHaveAttribute(
      "rel",
      expect.stringContaining("noopener"),
    );
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
