import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { LaneACostExplorer } from "@/components/dashboard/LaneACostExplorer";
import { LANE_A_FINAL_TIERS } from "@/data/laneAFinalFrontier";
import {
  ILLUSTRATIVE_STARTING_ASSUMPTIONS,
  costForTier,
  formatInr,
} from "@/lib/laneACostModel";

const REVIEW_COST = "Review cost per queued transaction (₹)";
const FRICTION = "Legitimate-customer friction cost per false-positive review (₹)";
const MISSED = "Missed-fraud loss per false negative (₹)";

/**
 * Assert a term never appears as an affirmative claim.
 *
 * The panel is required to NAME the claims it forbids ("not Razorpay
 * economics... savings, ROI, or a production recommendation"), so a bare
 * substring scan is wrong. This splits the rendered text into clauses and only
 * fails when a clause containing the term carries no negation.
 */
const NEGATIONS = /\b(not|no|never|without|neither|nor)\b/i;

/**
 * Rendered text with element boundaries preserved as spaces.
 *
 * `document.body.textContent` concatenates adjacent elements without
 * separation ("evidenceNot"), which destroys the word boundaries a reader
 * actually sees. Joining text nodes reflects the perceived reading.
 */
function visibleText(): string {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  let node = walker.nextNode();
  while (node) {
    const value = node.nodeValue?.trim();
    if (value) {
      parts.push(value);
    }
    node = walker.nextNode();
  }
  return parts.join(" ");
}

function expectNoAffirmativeClaim(body: string, term: RegExp): void {
  const clauses = body
    .replace(/([.;—])/g, "$1\u0000")
    .split("\u0000")
    .filter((clause) => term.test(clause));
  const affirmative = clauses.filter((clause) => !NEGATIONS.test(clause));
  expect(affirmative).toEqual([]);
}

describe("Lane A illustrative cost explorer", () => {
  it("shows the required heading and prominent disclosure", () => {
    render(<LaneACostExplorer />);
    expect(
      screen.getByRole("heading", { name: /Illustrative merchant cost & review workload/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("cost-explorer-disclosure")).toHaveTextContent(
      "Illustrative scenario only — not Razorpay economics, merchant pricing, savings, ROI, or a production recommendation.",
    );
  });

  it("explains that false positives are reviewed, not declined", () => {
    render(<LaneACostExplorer />);
    expect(
      screen.getByText(/legitimate transaction sent to human review/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/not automatically declined/i)).toBeInTheDocument();
  });

  it("labels the starting values as illustrative, never as defaults or recommendations", () => {
    render(<LaneACostExplorer />);
    expect(screen.getAllByText(/Illustrative starting assumptions/i).length).toBeGreaterThan(0);
    const body = visibleText();
    expectNoAffirmativeClaim(body, /default merchant settings/i);
    expectNoAffirmativeClaim(body, /recommended values/i);
  });

  it("exposes exactly four labelled, described INR inputs", () => {
    render(<LaneACostExplorer />);
    [REVIEW_COST, FRICTION, MISSED, "Chargeback-handling cost per false negative (₹)"].forEach(
      (label) => {
        const input = screen.getByLabelText(label);
        expect(input).toBeInTheDocument();
        expect(input).toHaveAccessibleDescription();
      },
    );
  });

  it("offers only the five frozen capacity tiers", () => {
    render(<LaneACostExplorer />);
    const group = screen.getByRole("group", {
      name: /Select a capacity tier for the illustrative cost scenario/i,
    });
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(5);
    expect(buttons.map((b) => b.textContent)).toEqual([
      "100/day", "250/day", "500/day", "1,000/day", "2,000/day",
    ]);
  });

  it("renders every frozen count for the selected tier", () => {
    render(<LaneACostExplorer />);
    const panel = screen.getByTestId("selected-tier-breakdown");
    const tier = LANE_A_FINAL_TIERS[0];
    expect(within(panel).getByText(tier.falsePositives.toLocaleString("en-IN"))).toBeInTheDocument();
    expect(within(panel).getByText(tier.falseNegatives.toLocaleString("en-IN"))).toBeInTheDocument();
    expect(within(panel).getByText("27.18%")).toBeInTheDocument();
  });

  it("shows the illustrative total matching the pure model", () => {
    render(<LaneACostExplorer />);
    const expected = costForTier(LANE_A_FINAL_TIERS[0], ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    const panel = screen.getByTestId("selected-tier-breakdown");
    expect(
      within(panel).getByText(formatInr(expected.illustrativeTotalCost)),
    ).toBeInTheDocument();
  });

  it("lists all five tiers with a cost in the comparison table", () => {
    render(<LaneACostExplorer />);
    LANE_A_FINAL_TIERS.forEach((tier) => {
      const row = screen.getByTestId(`cost-row-${tier.capacityPerDay}`);
      const expected = costForTier(tier, ILLUSTRATIVE_STARTING_ASSUMPTIONS);
      expect(within(row).getByText(formatInr(expected.illustrativeTotalCost))).toBeInTheDocument();
    });
  });

  it("is keyboard operable for tier selection", async () => {
    const user = userEvent.setup();
    render(<LaneACostExplorer />);
    const group = screen.getByRole("group", {
      name: /Select a capacity tier for the illustrative cost scenario/i,
    });
    const buttons = within(group).getAllByRole("button");
    expect(buttons[0]).toHaveAttribute("aria-pressed", "true");
    buttons[3].focus();
    await user.keyboard("{Enter}");
    expect(buttons[3]).toHaveAttribute("aria-pressed", "true");
    expect(buttons[0]).toHaveAttribute("aria-pressed", "false");
  });

  it("updates the selected tier breakdown when the tier changes", async () => {
    const user = userEvent.setup();
    render(<LaneACostExplorer />);
    const group = screen.getByRole("group", {
      name: /Select a capacity tier for the illustrative cost scenario/i,
    });
    await user.click(within(group).getAllByRole("button")[4]);
    const panel = screen.getByTestId("selected-tier-breakdown");
    expect(within(panel).getByText((190).toLocaleString("en-IN"))).toBeInTheDocument();
    expect(within(panel).getByText("93.84%")).toBeInTheDocument();
  });

  it("recomputes the breakdown and the all-tier table when an assumption is edited", async () => {
    const user = userEvent.setup();
    render(<LaneACostExplorer />);
    const before = costForTier(LANE_A_FINAL_TIERS[0], ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    const input = screen.getByLabelText(MISSED);
    await user.clear(input);
    await user.type(input, "9000");
    const after = costForTier(LANE_A_FINAL_TIERS[0], {
      ...ILLUSTRATIVE_STARTING_ASSUMPTIONS,
      missedFraudLossPerFalseNegative: 9000,
    });
    expect(after.illustrativeTotalCost).not.toBe(before.illustrativeTotalCost);
    const panel = screen.getByTestId("selected-tier-breakdown");
    expect(within(panel).getByText(formatInr(after.illustrativeTotalCost))).toBeInTheDocument();
    const row = screen.getByTestId("cost-row-2000");
    const rowExpected = costForTier(LANE_A_FINAL_TIERS[4], {
      ...ILLUSTRATIVE_STARTING_ASSUMPTIONS,
      missedFraudLossPerFalseNegative: 9000,
    });
    expect(within(row).getByText(formatInr(rowExpected.illustrativeTotalCost))).toBeInTheDocument();
  });

  it("refuses invalid input without showing a misleading number", async () => {
    const user = userEvent.setup();
    render(<LaneACostExplorer />);
    const input = screen.getByLabelText(REVIEW_COST);
    await user.clear(input);
    expect(await screen.findByTestId("cost-explorer-invalid")).toBeInTheDocument();
    expect(screen.queryByTestId("selected-tier-breakdown")).not.toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|₹-/);
  });

  it("refuses a negative amount", async () => {
    const user = userEvent.setup();
    render(<LaneACostExplorer />);
    const input = screen.getByLabelText(FRICTION);
    await user.clear(input);
    await user.type(input, "-40");
    expect(await screen.findByTestId("cost-explorer-invalid")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
  });

  it("zero assumptions produce a zero illustrative total", async () => {
    const user = userEvent.setup();
    render(<LaneACostExplorer />);
    for (const label of [REVIEW_COST, FRICTION, MISSED, "Chargeback-handling cost per false negative (₹)"]) {
      const input = screen.getByLabelText(label);
      await user.clear(input);
      await user.type(input, "0");
    }
    const panel = screen.getByTestId("selected-tier-breakdown");
    expect(within(panel).getAllByText("₹0").length).toBeGreaterThanOrEqual(4);
  });

  it("shows two sensitivity scenarios without crowning a winner", () => {
    render(<LaneACostExplorer />);
    expect(screen.getByTestId("sensitivity-higher-review-cost")).toBeInTheDocument();
    expect(screen.getByTestId("sensitivity-higher-missed-fraud-loss")).toBeInTheDocument();
    const body = visibleText();
    expect(body).not.toMatch(/\bbest\b/i);
    expect(body).not.toMatch(/\boptimal\b/i);
    expect(body).not.toMatch(/\bsaves\b/i);
    // "recommended" may appear only inside an explicit negation.
    expectNoAffirmativeClaim(body, /\brecommended\b/i);
  });

  it("discloses the formula and links the sealed final evidence", () => {
    render(<LaneACostExplorer />);
    const body = visibleText();
    expect(body).toMatch(/\(TP \+ FP\) × review cost/);
    expect(body).toMatch(/FP × legitimate-customer friction cost/);
    expect(body).toMatch(/FN × \(missed-fraud loss \+ chargeback-handling cost\)/);
    expect(body).toMatch(/LANE_A_FINAL_EVALUATION\.md/);
    expect(body).toMatch(/evaluated exactly\s+once/);
  });

  it("makes no forbidden economic claim", () => {
    render(<LaneACostExplorer />);
    const body = visibleText();
    // Absolute prohibitions: these must not appear at all.
    [/money saved/i, /cost savings/i, /fraud prevented/i, /production[- ]ready/i,
     /net (profit|benefit)/i, /payback/i].forEach((pattern) => {
      expect(body).not.toMatch(pattern);
    });
    // These may appear only where the panel disclaims them.
    [/\bROI\b/i, /razorpay (pricing|economics)/i, /savings/i].forEach((pattern) => {
      expectNoAffirmativeClaim(body, pattern);
    });
  });

  it("exposes no score, label, identifier, or private value", () => {
    render(<LaneACostExplorer />);
    const body = visibleText();
    [/isFraud/i, /TransactionID/i, /final_test/i, /raw_score/i,
     /decision_score/i, /\/Users\//].forEach((pattern) => {
      expect(body).not.toMatch(pattern);
    });
  });

  it("announces the selected scenario in a polite live region", () => {
    render(<LaneACostExplorer />);
    const status = screen.getByRole("status", { name: "Illustrative cost scenario summary" });
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status.textContent).toMatch(/Illustrative scenario at 100 reviews per day/);
  });
});
