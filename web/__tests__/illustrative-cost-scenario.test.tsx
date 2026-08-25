import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { IllustrativeCostScenario } from "@/components/IllustrativeCostScenario";

describe("IllustrativeCostScenario", () => {
  it("uses only the locked aggregate confusion counts and visible illustrative assumptions", () => {
    render(<IllustrativeCostScenario />);

    expect(
      screen.getByText("Illustrative merchant cost & review workload"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Illustrative scenario — not Razorpay economics and not a production-optimal threshold.",
      ),
    ).toHaveLength(3);
    expect(screen.getByLabelText("Illustrative display currency")).toHaveValue(
      "INR",
    );
    expect(
      screen.getByLabelText("Illustrative legitimate-customer friction"),
    ).toHaveValue(830);
    expect(
      screen.getByLabelText("Illustrative missed-fraud loss"),
    ).toHaveValue(8300);
    expect(screen.getByLabelText("Illustrative review cost")).toHaveValue(83);
    expect(
      screen.getByLabelText("Illustrative chargeback handling"),
    ).toHaveValue(4150);
    expect(screen.getByTestId("illustrative-total")).toHaveTextContent(
      "₹3,86,697.00",
    );
    const lockedFixture = screen.getByLabelText(
      "Locked historical cost fixture",
    );
    expect(lockedFixture).toHaveTextContent("Threshold0.53");
    expect(lockedFixture).toHaveTextContent("Precision69.66%");
    expect(lockedFixture).toHaveTextContent("Recall83.78%");
    expect(lockedFixture).toHaveTextContent("Review volume89");
    expect(lockedFixture).toHaveTextContent("True positives62");
    expect(lockedFixture).toHaveTextContent("False positives27");
    expect(lockedFixture).toHaveTextContent("False negatives12");
    expect(lockedFixture).toHaveTextContent("True negatives42,621");
    expect(
      screen.getByText(/Fixed display-only conversion: ₹83.00 =\s*\$1.00/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /no currency is assigned to the historical model or dataset amounts/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("62 TP + 27 FP = 89")).toBeInTheDocument();
    expect(
      screen.getByText(/62 TP \+ 27 FP \+ 12 FN \+ 42,621 TN = 42,722/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not a monthly or annual forecast/),
    ).toBeInTheDocument();
  });

  it("recalculates every visible assumption and reconciles every component", async () => {
    const user = userEvent.setup();
    render(<IllustrativeCostScenario />);

    await user.selectOptions(
      screen.getByLabelText("Illustrative display currency"),
      "USD",
    );
    expect(screen.getByTestId("illustrative-total")).toHaveTextContent(
      "$4,659.00",
    );

    const falsePositiveCost = screen.getByLabelText(
      "Illustrative legitimate-customer friction",
    );
    const falseNegativeCost = screen.getByLabelText(
      "Illustrative missed-fraud loss",
    );
    const reviewCost = screen.getByLabelText("Illustrative review cost");
    const chargebackHandling = screen.getByLabelText(
      "Illustrative chargeback handling",
    );
    await user.clear(falsePositiveCost);
    await user.type(falsePositiveCost, "20");
    await user.clear(falseNegativeCost);
    await user.type(falseNegativeCost, "200");
    await user.clear(reviewCost);
    await user.type(reviewCost, "2");
    await user.clear(chargebackHandling);
    await user.type(chargebackHandling, "150");

    expect(screen.getByText("$178.00")).toBeInTheDocument();
    expect(screen.getByText("$540.00")).toBeInTheDocument();
    expect(screen.getByText("$2,400.00")).toBeInTheDocument();
    expect(screen.getByText("$9,300.00")).toBeInTheDocument();
    expect(screen.getByTestId("illustrative-total")).toHaveTextContent(
      "$12,418.00",
    );
    await user.selectOptions(
      screen.getByLabelText("Illustrative display currency"),
      "INR",
    );
    expect(screen.getByTestId("illustrative-total")).toHaveTextContent(
      "₹10,30,694.00",
    );
    expect(
      screen.getByText(/not a savings claim or a threshold recommendation/),
    ).toBeInTheDocument();
  });
});
