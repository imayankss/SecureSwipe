import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SyntheticPlumbingSimulator } from "@/components/SyntheticPlumbingSimulator";
import { formatSyntheticInr } from "@/data/displayCurrency";
import { createSimulator } from "@/data/syntheticFixture";

const FORBIDDEN_WORDS = [
  "approve",
  "approved",
  "block",
  "blocked",
  "fraud_probability",
  "razorpay risk score",
];

describe("synthetic plumbing-test generator (pure module)", () => {
  it("uses Indian number formatting for synthetic INR display", () => {
    expect(formatSyntheticInr(100_000, "INR")).toBe("₹1,00,000.00");
  });

  it("is deterministic for a fixed seed", () => {
    const first = createSimulator({ seed: 42 });
    const second = createSimulator({ seed: 42 });
    const firstEvents = [
      first.generateEvent(),
      first.generateEvent(),
      first.generateEvent(),
    ];
    const secondEvents = [
      second.generateEvent(),
      second.generateEvent(),
      second.generateEvent(),
    ];
    expect(firstEvents.map((record) => record.input)).toEqual(
      secondEvents.map((record) => record.input),
    );
    expect(firstEvents.map((record) => record.output.decision)).toEqual(
      secondEvents.map((record) => record.output.decision),
    );
    expect(
      firstEvents.map((record) => record.output.context_signal_score),
    ).toEqual(secondEvents.map((record) => record.output.context_signal_score));
  });

  it("tags every decision with the synthetic_plumbing_test evidence type and a legal decision value", () => {
    const simulator = createSimulator({ seed: 7 });
    for (let i = 0; i < 10; i += 1) {
      const record = simulator.generateEvent();
      expect(record.output.evidence_type).toBe("synthetic_plumbing_test");
      expect([
        "below_review_threshold",
        "human_review",
        "unavailable_fail_closed",
      ]).toContain(record.output.decision);
      expect(record.output.context_signal_score).toBeGreaterThanOrEqual(0);
      expect(record.output.context_signal_score).toBeLessThanOrEqual(1);
    }
  });

  it("replays a duplicate event_id deterministically without rewriting the original decision", () => {
    const simulator = createSimulator({ seed: 3 });
    const original = simulator.generateEvent();
    const replayed = simulator.replay(original.input.event_id);
    expect(replayed).not.toBeNull();
    expect(replayed?.output.decision).toBe(original.output.decision);
    expect(replayed?.output.context_signal_score).toBe(
      original.output.context_signal_score,
    );
    expect(replayed?.output.request_id).not.toBe(original.output.request_id);
    expect(replayed?.output.is_duplicate).toBe(true);
    expect(original.output.is_duplicate).toBe(false);
  });

  it("bounds retained state across generated events and repeated replays", () => {
    const simulator = createSimulator({ seed: 13 });
    for (let index = 0; index < 75; index += 1) simulator.generateEvent();
    expect(simulator.getEvents()).toHaveLength(50);

    const newestEventId = simulator.getEvents().at(-1)?.input.event_id;
    expect(newestEventId).toBeDefined();
    for (let index = 0; index < 49; index += 1) {
      expect(simulator.replay(newestEventId!)).not.toBeNull();
      expect(simulator.getEvents().length).toBeLessThanOrEqual(50);
    }
  });

  it("fails closed on an out-of-bounds amount instead of scoring it", () => {
    const simulator = createSimulator({ seed: 11 });
    const record = simulator.generateInvalidEvent();
    expect(record.output.decision).toBe("unavailable_fail_closed");
    expect(record.output.context_signal_score).toBe(0);
  });

  it("resets to an empty, re-seeded state", () => {
    const simulator = createSimulator({ seed: 5 });
    simulator.generateEvent();
    simulator.generateEvent();
    expect(simulator.getEvents()).toHaveLength(2);
    simulator.reset({ seed: 5 });
    expect(simulator.getEvents()).toHaveLength(0);
    const record = simulator.generateEvent();
    const freshSimulator = createSimulator({ seed: 5 });
    const freshRecord = freshSimulator.generateEvent();
    expect(record.input).toEqual(freshRecord.input);
  });

  it("never emits forbidden approve/block/fraud-probability wording", () => {
    const simulator = createSimulator({ seed: 99 });
    for (let i = 0; i < 15; i += 1) {
      const record = simulator.generateEvent();
      const serialized = JSON.stringify(record).toLowerCase();
      for (const word of FORBIDDEN_WORDS) {
        expect(serialized).not.toContain(word);
      }
    }
  });
});

describe("SyntheticPlumbingSimulator UI", () => {
  it("stays empty until the user generates an event, then shows the synthetic evidence label", async () => {
    const user = userEvent.setup();
    render(<SyntheticPlumbingSimulator />);

    expect(screen.getByText(/No synthetic events yet/)).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Generate next synthetic event" }),
    );
    expect(
      screen.getAllByText("Synthetic plumbing test").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByLabelText("Synthetic event timeline"),
    ).toBeInTheDocument();
  });

  it("defaults fabricated example amounts to accessible INR formatting and offers USD display conversion", async () => {
    const user = userEvent.setup();
    render(<SyntheticPlumbingSimulator />);

    const currencySelector = screen.getByLabelText(
      "Synthetic amount display currency",
    );
    expect(currencySelector).toHaveValue("INR");
    expect(
      screen.getByText(/INR is the default for fabricated example amounts/),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Generate next synthetic event" }),
    );
    expect(screen.getByText("₹4,805.00")).toBeInTheDocument();

    await user.selectOptions(currencySelector, "USD");
    expect(screen.getByText("$57.89")).toBeInTheDocument();
    expect(
      screen.getByText(/never changes genuine-model input semantics/),
    ).toBeInTheDocument();
  });

  it("marks a replayed event as a duplicate without changing its decision", async () => {
    const user = userEvent.setup();
    render(<SyntheticPlumbingSimulator />);

    await user.click(
      screen.getByRole("button", { name: "Generate next synthetic event" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Replay last event ID (duplicate)" }),
    );
    expect(
      screen.getByText(/Duplicate submission of an existing event_id/),
    ).toBeInTheDocument();
  });

  it("demonstrates the fail-closed path on an out-of-bounds event", async () => {
    const user = userEvent.setup();
    render(<SyntheticPlumbingSimulator />);

    await user.click(
      screen.getByRole("button", {
        name: "Simulate out-of-bounds event (fail closed)",
      }),
    );
    expect(screen.getAllByText("Unavailable / fail closed")).toHaveLength(2);
  });

  it("resets the demo session back to empty", async () => {
    const user = userEvent.setup();
    render(<SyntheticPlumbingSimulator />);

    await user.click(
      screen.getByRole("button", { name: "Generate next synthetic event" }),
    );
    expect(
      screen.queryByText(/No synthetic events yet/),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Reset demo session" }),
    );
    expect(screen.getByText(/No synthetic events yet/)).toBeInTheDocument();
  });

  it("never renders forbidden approve/block/fraud-probability wording", async () => {
    const user = userEvent.setup();
    const { container } = render(<SyntheticPlumbingSimulator />);
    await user.click(
      screen.getByRole("button", { name: "Generate next synthetic event" }),
    );
    const text = container.textContent?.toLowerCase() ?? "";
    for (const word of FORBIDDEN_WORDS) {
      expect(text).not.toContain(word);
    }
  });
});
