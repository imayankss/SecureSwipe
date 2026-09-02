import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import DemoPage from "@/app/demo/page";
import EvidencePage from "@/app/evidence/page";
import Home from "@/app/page";
import { ScopeEvidencePanel } from "@/components/dashboard/ScopeEvidencePanel";
import { DeterministicJudgeDemo } from "@/components/demo/DeterministicJudgeDemo";
import { Navigation } from "@/components/Navigation";
import { DEMO_STAGES } from "@/lib/demo-journey";
import { RECORDED_REFERENCE_RUN } from "@/lib/deterministic-demo";

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

beforeAll(() => vi.stubGlobal("IntersectionObserver", TestIntersectionObserver));
afterAll(() => vi.unstubAllGlobals());

function visibleText(container: HTMLElement): string {
  return (container.textContent ?? "").replace(/\s+/g, " ");
}

describe("route shell and navigation", () => {
  it("renders all three routes with a single level-1 heading each", () => {
    for (const [name, Page] of [
      ["home", Home],
      ["evidence", EvidencePage],
      ["demo", DemoPage],
    ] as const) {
      const { container, unmount } = render(<Page />);
      expect(
        within(container).getAllByRole("heading", { level: 1 }),
        `${name} must have exactly one h1`,
      ).toHaveLength(1);
      unmount();
    }
  });

  it("marks only the active route with aria-current on both navigations", () => {
    const { container } = render(<Navigation activePage="demo" />);
    const current = container.querySelectorAll('a[aria-current="page"]');

    // One in the desktop group and one in the mobile disclosure.
    expect(current).toHaveLength(2);
    for (const link of current) {
      expect(link).toHaveAttribute("href", "/demo");
    }
  });

  it("keeps the complete route set inside the mobile disclosure", () => {
    const { container } = render(<Navigation activePage="product" />);
    const mobile = container.querySelector("details");

    expect(mobile).not.toBeNull();
    const links = within(mobile as HTMLElement).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/",
      "/evidence",
      "/demo",
    ]);
  });

  it("exposes a skip link before the main landmark", () => {
    render(<Navigation activePage="product" />);
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
  });

  it("links the shared footer to the standalone methodology page", () => {
    render(<Home />);
    expect(screen.getByRole("link", { name: /Methodology/i })).toHaveAttribute(
      "href",
      "/secureswipe-methodology.html",
    );
  });
});

describe("homepage reviewer path", () => {
  it("offers the two-minute demo as the primary action", () => {
    render(<Home />);
    const cta = screen.getByRole("link", { name: /Run the 2-minute demo/i });

    expect(cta).toHaveAttribute("href", "/demo");
    expect(cta.className).toContain("ss-action-primary");
  });

  it("routes the reviewer to the demo and the evidence record", () => {
    const { container } = render(<Home />);
    const hrefs = Array.from(container.querySelectorAll("a[href]")).map((a) =>
      a.getAttribute("href"),
    );

    expect(hrefs).toContain("/demo");
    expect(hrefs).toContain("/evidence");
  });

  it("shows four measured KPIs sourced from one sealed evaluation", () => {
    const { container } = render(<Home />);
    const strip = container.querySelector('[data-product-section="measured-evidence"]');

    expect(strip).not.toBeNull();
    expect((strip as HTMLElement).querySelectorAll("dt")).toHaveLength(4);
    expect(visibleText(strip as HTMLElement)).toMatch(/never mixed with Lane B/i);
  });

  it("previews the decision workspace without inventing an outcome", () => {
    const { container } = render(<Home />);
    const preview = container.querySelector('[data-product-section="decision-preview"]');
    const text = visibleText(preview as HTMLElement);

    expect(text).toMatch(/No outcome is shown here/i);
    expect(text).toMatch(/Fixed reference scenario/i);
    expect(preview?.querySelector('[data-decision-zone="pending"]')).not.toBeNull();
  });
});

describe("decision terminology and claim safety", () => {
  const routes = [
    ["home", Home],
    ["evidence", EvidencePage],
    ["demo", DemoPage],
  ] as const;

  it("never softens 'below review threshold' into an approval", () => {
    // Only outcome-shaped approval language is forbidden. Unrelated compounds
    // such as "no domain-approved cost model" are legitimate and must pass.
    const outcomeApproval =
      /(transaction|outcome|decision|result|request)\s+(is\s+)?(approved|safe|legitimate)\b|\b(approved|safe|legitimate)\s+(transaction|outcome|decision)\b/i;
    const negation = /\b(not|no|never|without|neither|nor)\b/i;

    for (const [name, Page] of routes) {
      const { container, unmount } = render(<Page />);
      const affirmative = visibleText(container)
        .split(/(?<=[.;])\s+/)
        .filter((clause) => outcomeApproval.test(clause))
        .filter((clause) => !negation.test(clause));

      expect(affirmative, `${name} must not call an outcome approved/safe`).toEqual([]);
      unmount();
    }
  });

  it("never claims autonomous payment behaviour or tamper-proof audit", () => {
    for (const [name, Page] of routes) {
      const { container, unmount } = render(<Page />);
      const text = visibleText(container);
      expect(text, `${name}`).not.toMatch(/AUTO_BLOCK|AUTO_ALLOW|tamper-proof/i);
      expect(text, `${name}`).not.toMatch(/autonomous (payment )?authorization/i);
      unmount();
    }
  });

  it("never presents unproven scale, capacity, or savings as fact", () => {
    const negation = /\b(not|no|never|without|neither|nor|did not)\b/i;
    for (const [name, Page] of routes) {
      const { container, unmount } = render(<Page />);
      const clauses = visibleText(container).split(/(?<=[.;])\s+/);
      const risky = clauses.filter(
        (clause) =>
          /production capacity|horizontal scaling|money saved|amount protected|fraud prevented|real-time|production SLO/i.test(
            clause,
          ) && !negation.test(clause),
      );
      expect(risky, `${name} carries an unqualified claim`).toEqual([]);
      unmount();
    }
  });

  it("keeps the reliability claim paired with its measurement boundary", () => {
    const { container } = render(<EvidencePage />);
    const panel = container.querySelector('[data-evidence-section="reliability-and-audit"]');
    const text = visibleText(panel as HTMLElement);

    expect(text).toMatch(/checkout-exhaustion defect/i);
    expect(text).toMatch(/three consecutive four-worker, concurrency-64 proofs/i);
    expect(text).toMatch(/production-capacity and horizontal-scaling claims stay reserved/i);
    expect(text).toMatch(/design capability kept separate from benchmark-proven capacity/i);
  });

  it("states the evidence boundary as positive, inspectable safeguards", () => {
    const { container } = render(<ScopeEvidencePanel />);
    const panel = container.querySelector("#limitations");
    const text = visibleText(panel as HTMLElement);

    expect(text).toMatch(/Clear boundaries make every result stronger/i);
    expect(text).toMatch(/Only aggregate artifacts reach the dashboard/i);
    expect(text).toMatch(/model score, never as a real-world fraud probability/i);
    expect(text).not.toMatch(/What this dashboard does not prove/i);
  });
});

describe("guided demo navigation", () => {
  it("moves forward and back through every stage without running the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<DeterministicJudgeDemo apiBaseUrl={null} />);

    const next = screen.getByRole("button", { name: "Next" });
    const back = screen.getByRole("button", { name: "Back" });

    expect(back).toBeDisabled();
    expect(screen.getByText(`Stage 1 of ${DEMO_STAGES.length}`)).toBeInTheDocument();

    await user.click(next);
    expect(screen.getByText(`Stage 2 of ${DEMO_STAGES.length}`)).toBeInTheDocument();

    await user.click(back);
    expect(screen.getByText(`Stage 1 of ${DEMO_STAGES.length}`)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists all eight stages with an accessible status for each", () => {
    const { container } = render(<DeterministicJudgeDemo apiBaseUrl={null} />);

    expect(container.querySelectorAll("[data-stage-id]")).toHaveLength(8);
    expect(container.querySelectorAll("[data-step-status]")).toHaveLength(8);
    for (const stage of DEMO_STAGES) {
      expect(
        container.querySelector(`[data-stage-id="${stage.id}"]`),
        `${stage.id} must be present`,
      ).not.toBeNull();
    }
  });
});

describe("evidence route sections", () => {
  it("anchors every section link to a target that exists on the route", () => {
    const { container } = render(<EvidencePage />);
    const anchors = Array.from(
      container.querySelectorAll<HTMLAnchorElement>('a[href^="#"]'),
    );

    expect(anchors.length).toBeGreaterThan(0);
    for (const anchor of anchors) {
      const href = anchor.getAttribute("href");
      if (href && href.length > 1) {
        expect(container.querySelector(href), `${href} must resolve`).not.toBeNull();
      }
    }
  });

  it("separates measured evidence from illustrative arithmetic", () => {
    const { container } = render(<EvidencePage />);
    const text = visibleText(container);

    expect(text).toMatch(/Illustrative scenario only/i);
    expect(text).toMatch(/not Razorpay economics/i);
  });
});

describe("recorded reference run", () => {
  it("completes the whole journey with no network and labels itself as recorded", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(<DeterministicJudgeDemo apiBaseUrl={null} />);

    await user.click(screen.getByRole("button", { name: "Run recorded reference" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(container.querySelectorAll('[data-step-status="success"]')).toHaveLength(8);
    expect(container.querySelector("[data-demo-outcome]")).toHaveTextContent("Review");
    expect(container.querySelector('[data-demo-source="recorded"]')).not.toBeNull();
    expect(screen.getByText(/replayed, not measured now/i)).toBeInTheDocument();
    expect(container.querySelector("[data-demo-complete]")).not.toBeNull();
  });

  it("never presents the recorded transcript as a live inference", () => {
    // The suppressed decision score must not be stored in the transcript.
    // `score_type` names which score was compared and is published by the
    // contract, so it is a key name, not a score value.
    const keys = Object.keys(RECORDED_REFERENCE_RUN);
    expect(keys).not.toContain("raw_score");
    expect(keys).not.toContain("decision_score");
    expect(keys).not.toContain("calibrated_probability");
    expect(RECORDED_REFERENCE_RUN.audit_event_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(RECORDED_REFERENCE_RUN.model_artifact_sha256).toMatch(/^[a-f0-9]{64}$/);
  });
});
