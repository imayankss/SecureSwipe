import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { LaneACapacityWorkbench } from "@/components/dashboard/LaneACapacityWorkbench";
import { LANE_A_CAPACITY_TIERS, LANE_A_RECALL80_REFERENCE } from "@/data/laneACapacity";

describe("Lane A capacity workbench", () => {
  it("shows every required evidence label", () => {
    render(<LaneACapacityWorkbench />);
    for (const label of [
      "IEEE-CIS Lane A",
      "Development evidence",
      "Final evaluation sealed",
      "Illustrative capacity",
      "No Razorpay or live-merchant economics",
      "Not comparable with Lane B historical metrics",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("offers exactly the five illustrative capacity tiers", () => {
    render(<LaneACapacityWorkbench />);
    const group = screen.getByRole("group", {
      name: /select an illustrative daily review capacity/i,
    });
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(5);
    expect(buttons.map((b) => b.textContent)).toEqual([
      "100/day",
      "250/day",
      "500/day",
      "1,000/day",
      "2,000/day",
    ]);
  });

  it("activates a capacity tier from the keyboard and announces updated metrics", async () => {
    const user = userEvent.setup();
    render(<LaneACapacityWorkbench />);
    const capacityGroup = screen.getByRole("group", {
      name: /select an illustrative daily review capacity/i,
    });
    const lowest = within(capacityGroup).getByRole("button", { name: "100/day" });
    const highest = within(capacityGroup).getByRole("button", { name: "2,000/day" });
    expect(lowest).toHaveAttribute("aria-pressed", "true");

    highest.focus();
    expect(highest).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(highest).toHaveAttribute("aria-pressed", "true");
    expect(lowest).toHaveAttribute("aria-pressed", "false");

    const top = LANE_A_CAPACITY_TIERS[LANE_A_CAPACITY_TIERS.length - 1];
    expect(
      screen.getAllByText(`${(top.recall * 100).toFixed(2)}%`).length,
    ).toBeGreaterThan(0);
    // The nested cost panel has its own live region; target the workbench's.
    const announcements = screen
      .getAllByRole("status")
      .map((node) => node.textContent ?? "");
    expect(
      announcements.some((text) =>
        /selected capacity 2,000 reviews per day: precision 5\.64%, recall 93\.82%, and 44,397 reviews/i.test(
          text,
        ),
      ),
    ).toBe(true);
  });

  it("keeps the low-capacity reference visible rather than hiding poor recall", () => {
    render(<LaneACapacityWorkbench />);
    const lowest = LANE_A_CAPACITY_TIERS[0];
    expect(lowest.reachesRecall80).toBe(false);
    const capacityGroup = screen.getByRole("group", {
      name: /select an illustrative daily review capacity/i,
    });
    expect(within(capacityGroup).getByRole("button", { name: "100/day" })).toBeInTheDocument();
    expect(
      screen.getAllByText(`${(lowest.recall * 100).toFixed(2)}%`).length,
    ).toBeGreaterThan(0);
  });

  it("labels the 80% recall workload as a reference, not a default", () => {
    render(<LaneACapacityWorkbench />);
    expect(
      screen.getByText(/not a merchant capacity and not a recommended default/i),
    ).toBeInTheDocument();
    expect(LANE_A_RECALL80_REFERENCE.minimumReviews).toBeGreaterThan(0);
  });

  it("states human review only, never approve or block", () => {
    render(<LaneACapacityWorkbench />);
    // Both the capacity workbench and its nested cost panel state this.
    expect(
      screen.getAllByText(/approves, blocks, declines, or steps up a payment/i).length,
    ).toBeGreaterThan(0);
  });

  it("carries the illustrative-scenario disclaimer", () => {
    render(<LaneACapacityWorkbench />);
    expect(screen.getByText(/not Razorpay economics, not a production SLO/i)).toBeInTheDocument();
  });

  it("renders a scrollable table wrapper so 375px has no page overflow", () => {
    const { container } = render(<LaneACapacityWorkbench />);
    expect(container.querySelector(".overflow-x-auto")).not.toBeNull();
  });
});
