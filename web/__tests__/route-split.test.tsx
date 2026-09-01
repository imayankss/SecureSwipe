import { render, screen } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import EvidencePage from "@/app/evidence/page";
import Home from "@/app/page";

class TestIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0];

  constructor(private readonly callback: IntersectionObserverCallback) {}

  observe(target: Element) {
    this.callback(
      [{ isIntersecting: true, target } as IntersectionObserverEntry],
      this,
    );
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

function expectLocalAnchorsToResolve(container: HTMLElement) {
  const anchors = Array.from(container.querySelectorAll<HTMLAnchorElement>('a[href^="#"]'));
  for (const anchor of anchors) {
    const href = anchor.getAttribute("href");
    if (href && href.length > 1) {
      expect(container.querySelector(href), `${href} should resolve on the current route`).not.toBeNull();
    }
  }
}

describe("product and evidence route split", () => {
  it("renders exactly five lightweight product sections at the root", () => {
    const { container } = render(<Home />);

    expect(
      screen.getByRole("heading", { level: 1, name: /Payment-risk review, made inspectable/i }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("[data-product-section]")).toHaveLength(5);
    expect(screen.getByRole("link", { name: "Inspect the evidence" })).toHaveAttribute(
      "href",
      "/evidence",
    );
    expect(screen.queryByText("Historical evaluation command board")).not.toBeInTheDocument();
    expect(screen.queryByText("Synthetic event, feature, and decision plumbing")).not.toBeInTheDocument();
    expect(container.querySelector('a[href="/review-policy"]')).toBeNull();
    expect(container.querySelector('a[href="/operations"]')).toBeNull();
    expect(container.querySelector('a[href="/methodology"]')).toBeNull();
    expectLocalAnchorsToResolve(container);
  });

  it("renders the preserved command center at the evidence route", () => {
    const { container } = render(<EvidencePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Scientific evidence and system boundaries" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Historical evaluation command board")).toBeInTheDocument();
    expect(screen.getByText("Synthetic event, feature, and decision plumbing")).toBeInTheDocument();
    expect(screen.getAllByText("Illustrative merchant cost & review workload")).toHaveLength(2);
    expect(container.querySelectorAll("[data-evidence-disclosure]")).toHaveLength(4);
    expect(
      screen.getByRole("button", {
        name: "Show details: Threshold, curve, and explainability detail",
      }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", {
        name: "Show details: Architecture, methodology and audit trail",
      }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Back to product overview" })).toHaveAttribute(
      "href",
      "/",
    );
    expectLocalAnchorsToResolve(container);
  });
});
