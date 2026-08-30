import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import EvidencePage from "@/app/evidence/page";
import Home from "@/app/page";
import { ProductHero } from "@/components/product/ProductHero";
import { ReviewStrategySurface } from "@/components/product/ReviewStrategySurface";
import { LANE_A_CAPACITY_TIERS } from "@/data/laneACapacity";
import { LANE_A_FINAL_METRICS, LANE_A_FINAL_TIERS } from "@/data/laneAFinalFrontier";
import { dashboardData } from "@/data/metrics";
import {
  ILLUSTRATIVE_STARTING_ASSUMPTIONS,
  costForTier,
  formatInr,
} from "@/lib/laneACostModel";

const HEADLINE_TIER = LANE_A_FINAL_TIERS[3];

/**
 * `/evidence` renders lazily-revealed curve images behind an observer.
 */
class TestIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0];

  constructor(private readonly callback: IntersectionObserverCallback) {}

  observe(target: Element) {
    this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this);
  }

  disconnect() {}
  takeRecords() {
    return [];
  }
  unobserve() {}
}

beforeAll(() => {
  vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);
});

afterAll(() => {
  vi.unstubAllGlobals();
});

/**
 * The homepage is required to NAME the claims it forbids ("not ... savings,
 * ROI, or a production recommendation"), so a bare substring scan would fail on
 * the very disclosure that protects the reader. This mirrors the clause-level
 * check already used by the cost-explorer suite: split the visible reading into
 * clauses and fail only where a clause carrying the term lacks a negation.
 */
const NEGATIONS = /\b(not|no|never|without|neither|nor)\b/i;

function expectNoAffirmativeClaim(body: string, term: RegExp): void {
  const affirmative = body
    .split(/(?<=[.;])\s+/)
    .filter((clause) => term.test(clause))
    .filter((clause) => !NEGATIONS.test(clause));
  expect(affirmative, `unqualified use of ${term}`).toEqual([]);
}

/** Rendered text with element boundaries preserved as spaces. */
function visibleText(container: HTMLElement): string {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  let node = walker.nextNode();
  while (node) {
    const value = node.nodeValue?.trim();
    if (value) parts.push(value);
    node = walker.nextNode();
  }
  return parts.join(" ");
}

function heroSection(container: HTMLElement): HTMLElement {
  const hero = container.querySelector<HTMLElement>(
    '[data-product-section="product-promise"]',
  );
  expect(hero, "the hero section must be present").not.toBeNull();
  return hero!;
}

describe("P0.3 hero", () => {
  it("names the product, the reviewer, and the bounded outcome", () => {
    const { container } = render(<ProductHero />);
    const text = visibleText(heroSection(container));

    expect(text).toMatch(/human-review decision support/i);
    expect(text).toMatch(/risk or operations reviewer/i);
    expect(text).toMatch(/before\s+a human decision/i);
    expect(text).toMatch(/human review/i);
    expect(text).toMatch(/below review threshold/i);
  });

  it("offers one primary action to the review strategy and one to the evidence route", () => {
    render(<ProductHero />);

    expect(screen.getByRole("link", { name: /Explore the review strategy/i })).toHaveAttribute(
      "href",
      "#review-strategy",
    );
    expect(screen.getByRole("link", { name: "Inspect the evidence" })).toHaveAttribute(
      "href",
      "/evidence",
    );
  });

  it("carries exactly one headline metric, read from the sealed Lane A final source", () => {
    const { container } = render(<ProductHero />);
    const headline = screen.getByTestId("hero-headline-evidence");

    // The one number is the frozen sealed-final recall, not a recomputation.
    expect(within(headline).getByText("80.18%")).toBeInTheDocument();
    expect(`${(HEADLINE_TIER.recall * 100).toFixed(2)}%`).toBe("80.18%");
    expect(HEADLINE_TIER.capacityPerDay).toBe(1_000);

    // A single evaluation metric only: no second metric card in the hero.
    expect(container.querySelectorAll('[data-testid="hero-headline-evidence"]')).toHaveLength(1);

    const text = visibleText(heroSection(container));
    expect(text).toMatch(/SEALED FINAL EVALUATION — LANE A \/ IEEE-CIS/);
    expect(text).toMatch(/recall in the sealed Lane A final evaluation/i);
    expect(text).toMatch(/Review-capacity and false-positive trade-offs are available below/i);
    expect(text).toMatch(/evaluated exactly once/i);
    expect(text).toMatch(/Not\s+Razorpay, live-merchant, or production performance/i);
  });

  it("does not combine the capacity tier and its false-positive count in the hero", () => {
    // 1,000/day and 28,306 are two review-strategy-specific facts. Stating them
    // together in the hero reads as "80.18% recall at 1,000/day, 28,306 FPs" —
    // a merged claim the hero must not make. They may still appear separately
    // and accurately labelled inside the review-strategy interaction/evidence.
    const { container } = render(<ProductHero />);
    const text = visibleText(heroSection(container));

    expect(text).not.toMatch(/1,000 reviews\/day/i);
    expect(text).not.toContain(HEADLINE_TIER.falsePositives.toLocaleString("en-US"));
    expect(text).not.toMatch(/reviews\/day[\s\S]*legitimate transactions/i);
  });

  it("keeps the Lane A development frontier out of the headline", () => {
    const { container } = render(<ProductHero />);
    const text = visibleText(heroSection(container));

    for (const tier of LANE_A_CAPACITY_TIERS) {
      expect(text).not.toContain(`${(tier.recall * 100).toFixed(2)}%`);
    }
    expect(text).not.toMatch(/development evidence/i);
    expect(text).not.toMatch(/validation_threshold/i);
  });

  it("renders no evidence legend, taxonomy, or disclaimer wall in the hero", () => {
    const { container } = render(<ProductHero />);
    const hero = heroSection(container);

    expect(within(hero).queryByRole("note")).toBeNull();
    expect(hero.querySelector('[aria-label="Evidence category legend"]')).toBeNull();
    for (const label of [
      "Historical evaluation",
      "Genuine demo inference",
      "Synthetic plumbing test",
    ]) {
      expect(within(hero).queryByText(label)).toBeNull();
    }
  });

  it("keeps the Buildathon reference as small project context, not the brand", () => {
    const { container } = render(<ProductHero />);
    const heading = screen.getByRole("heading", { level: 1 });

    expect(heading.textContent).not.toMatch(/razorpay/i);
    expect(visibleText(heroSection(container))).toMatch(
      /Project context only; no payment integration is represented/i,
    );
  });
});

describe("P0.3 compact review-strategy surface", () => {
  it("keeps the capacity selector over the five frozen sealed tiers", () => {
    render(<ReviewStrategySurface />);
    const group = screen.getByRole("group", {
      name: /Select a capacity tier for the illustrative cost scenario/i,
    });
    const buttons = within(group).getAllByRole("button");

    expect(buttons).toHaveLength(LANE_A_FINAL_TIERS.length);
    expect(buttons.map((b) => b.textContent)).toEqual([
      "100/day", "250/day", "500/day", "1,000/day", "2,000/day",
    ]);
  });

  it("shows the coverage / workload / false-positive trade-off for the selected tier", () => {
    render(<ReviewStrategySurface />);
    const panel = screen.getByTestId("selected-tier-breakdown");
    const tier = LANE_A_FINAL_TIERS[0];

    expect(within(panel).getByText(`${(tier.recall * 100).toFixed(2)}%`)).toBeInTheDocument();
    expect(within(panel).getByText(tier.reviewBudget.toLocaleString("en-IN"))).toBeInTheDocument();
    expect(within(panel).getByText(tier.falsePositives.toLocaleString("en-IN"))).toBeInTheDocument();
  });

  it("recomputes the illustrative total when the tier changes", async () => {
    const user = userEvent.setup();
    render(<ReviewStrategySurface />);
    const group = screen.getByRole("group", {
      name: /Select a capacity tier for the illustrative cost scenario/i,
    });

    await user.click(within(group).getAllByRole("button")[4]);
    const expected = costForTier(LANE_A_FINAL_TIERS[4], ILLUSTRATIVE_STARTING_ASSUMPTIONS);
    const panel = screen.getByTestId("selected-tier-breakdown");
    expect(within(panel).getByText(formatInr(expected.illustrativeTotalCost))).toBeInTheDocument();
  });

  it("keeps the cost assumptions editable and labelled illustrative", async () => {
    const user = userEvent.setup();
    render(<ReviewStrategySurface />);

    expect(screen.getAllByText(/Illustrative starting assumptions/i).length).toBeGreaterThan(0);
    const input = screen.getByLabelText("Missed-fraud loss per false negative (₹)");
    await user.clear(input);
    await user.type(input, "9000");

    const expected = costForTier(LANE_A_FINAL_TIERS[0], {
      ...ILLUSTRATIVE_STARTING_ASSUMPTIONS,
      missedFraudLossPerFalseNegative: 9000,
    });
    const panel = screen.getByTestId("selected-tier-breakdown");
    expect(within(panel).getByText(formatInr(expected.illustrativeTotalCost))).toBeInTheDocument();
  });

  it("still refuses invalid input rather than showing a misleading number", async () => {
    const user = userEvent.setup();
    render(<ReviewStrategySurface />);

    await user.clear(screen.getByLabelText("Review cost per queued transaction (₹)"));
    expect(await screen.findByTestId("cost-explorer-invalid")).toBeInTheDocument();
    expect(screen.queryByTestId("selected-tier-breakdown")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|₹-/);
  });

  it("links to the detailed capacity evidence", () => {
    render(<ReviewStrategySurface />);
    expect(
      screen.getByRole("link", { name: /Inspect detailed evidence/i }),
    ).toHaveAttribute("href", "/evidence#lane-a-capacity");
  });

  it("drops the badge row, comparison table, intervals, and scenarios", () => {
    const { container } = render(<ReviewStrategySurface />);

    expect(screen.queryByTestId("all-tier-cost-table")).toBeNull();
    expect(screen.queryByTestId("sealed-final-metrics")).toBeNull();
    expect(screen.queryByTestId("sensitivity-higher-review-cost")).toBeNull();
    expect(screen.queryByTestId("sensitivity-higher-missed-fraud-loss")).toBeNull();
    expect(screen.queryByText("Sealed Lane A final aggregate evidence")).toBeNull();
    expect(visibleText(container)).not.toMatch(/95% CI/);
  });
});

describe("P0.3 homepage evidence separation", () => {
  it("keeps Lane B historical metrics off the homepage", () => {
    const { container } = render(<Home />);
    const text = visibleText(container);
    const laneB = dashboardData.finalEvaluation;

    expect(text).not.toContain(String(laneB.threshold));
    expect(text).not.toContain((42_621).toLocaleString("en-US"));
    expect(text).not.toContain("42621");
    expect(text).not.toMatch(/PR-AUC/i);
    expect(text).not.toMatch(/confusion matrix/i);
    expect(text).not.toMatch(/Historical evaluation command board/i);
  });

  it("shows no Lane A sealed interval or aggregate-metric detail on the homepage", () => {
    const { container } = render(<Home />);
    const text = visibleText(container);

    expect(text).not.toContain(LANE_A_FINAL_METRICS.averagePrecision.toFixed(6));
    expect(text).not.toContain(LANE_A_FINAL_METRICS.rocAuc.toFixed(6));
    expect(text).not.toMatch(/95% CI/);
  });

  it("introduces no unsupported savings, production, or payment-action claim", () => {
    const { container } = render(<Home />);
    const text = visibleText(container);

    // Absolute prohibitions: these must not appear at all.
    for (const pattern of [
      /money saved/i, /cost savings/i, /fraud prevented/i, /production[- ]ready/i,
      /net (profit|benefit)/i, /payback/i, /live fraud prevention/i,
      /razorpay[- ]scale/i, /deployed model/i, /optimi[sz]ed policy/i,
    ]) {
      expect(text, `homepage must not claim ${pattern}`).not.toMatch(pattern);
    }
    // These may appear only where the homepage explicitly disclaims them.
    for (const pattern of [/\bROI\b/i, /savings/i, /real merchant economics/i]) {
      expectNoAffirmativeClaim(text, pattern);
    }
    // The homepage may only describe payment action in the negative.
    expect(text).toMatch(/Payment action stays outside this system/i);
    expect(text).not.toMatch(/\b(approves|blocks|declines) a payment\b/i);
  });

  it("keeps the detailed table, intervals, and footnotes on the evidence route", () => {
    const { container } = render(<EvidencePage />);
    const text = visibleText(container);

    expect(screen.getByTestId("all-tier-cost-table")).toBeInTheDocument();
    expect(screen.getByTestId("sealed-final-metrics")).toBeInTheDocument();
    expect(screen.getByTestId("sensitivity-higher-review-cost")).toBeInTheDocument();
    expect(screen.getByTestId("sensitivity-higher-missed-fraud-loss")).toBeInTheDocument();
    expect(text).toMatch(/95% CI/);
    expect(text).toMatch(/\(TP \+ FP\) × review cost/);
    expect(text).toMatch(/LANE_A_FINAL_EVALUATION\.md/);
    // The Lane A development frontier stays here too, still labelled.
    expect(screen.getByText("Development evidence")).toBeInTheDocument();
  });
});
