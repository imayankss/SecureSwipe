import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const PANEL = "#lane-a-cost-explorer";
const DISCLOSURE =
  "Illustrative scenario only — not Razorpay economics, merchant pricing, savings, ROI, or a production recommendation.";

test("desktop cost explorer shows the disclosure and sealed-evidence provenance", async ({
  page,
}) => {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/predict")) apiRequests.push(request.url());
  });

  await page.goto("/#lane-a-cost-explorer");
  const panel = page.locator(PANEL);
  await expect(panel).toBeVisible();

  await expect(
    panel.getByRole("heading", { name: /Illustrative merchant cost & review workload/i }),
  ).toBeVisible();
  await expect(panel.getByTestId("cost-explorer-disclosure")).toHaveText(DISCLOSURE);
  await expect(panel.getByText(/not automatically declined/i)).toBeVisible();
  await expect(panel.getByText(/LANE_A_FINAL_EVALUATION\.md/)).toBeVisible();

  // Static panel: no inference request may be triggered by the explorer.
  expect(apiRequests).toEqual([]);
});

test("disclosure is visible without scrolling inside the panel", async ({ page }) => {
  await page.goto("/#lane-a-cost-explorer");
  const panel = page.locator(PANEL);
  await expect(panel).toBeVisible();

  const geometry = await panel.evaluate((element) => {
    const disclosure = element.querySelector<HTMLElement>(
      '[data-testid="cost-explorer-disclosure"]',
    );
    const panelBox = element.getBoundingClientRect();
    const disclosureBox = disclosure!.getBoundingClientRect();
    return {
      panelTop: panelBox.top,
      panelScrollTop: element.scrollTop,
      disclosureTop: disclosureBox.top,
      disclosureBottom: disclosureBox.bottom,
      panelBottom: panelBox.bottom,
    };
  });
  // The panel is not internally scrolled and the disclosure sits within it.
  expect(geometry.panelScrollTop).toBe(0);
  expect(geometry.disclosureTop).toBeGreaterThanOrEqual(geometry.panelTop);
  expect(geometry.disclosureBottom).toBeLessThanOrEqual(geometry.panelBottom);
});

test("capacity tiers and assumptions are keyboard operable and recompute the total", async ({
  page,
}) => {
  await page.goto("/#lane-a-cost-explorer");
  const panel = page.locator(PANEL);
  const group = panel.getByRole("group", {
    name: /Select a capacity tier for the illustrative cost scenario/i,
  });
  const tiers = group.getByRole("button");
  await expect(tiers).toHaveCount(5);

  await expect(tiers.nth(0)).toHaveAttribute("aria-pressed", "true");
  await tiers.nth(4).focus();
  await page.keyboard.press("Enter");
  await expect(tiers.nth(4)).toHaveAttribute("aria-pressed", "true");
  await expect(tiers.nth(0)).toHaveAttribute("aria-pressed", "false");

  const table = panel.getByTestId("all-tier-cost-table");
  const before = await table.textContent();

  const missedFraud = panel.getByLabel("Missed-fraud loss per false negative (₹)");
  await missedFraud.focus();
  await missedFraud.fill("9000");
  await expect(table).not.toHaveText(before ?? "");

  // Invalid input must never surface a misleading figure.
  await missedFraud.fill("");
  await expect(panel.getByTestId("cost-explorer-invalid")).toBeVisible();
  await expect(panel.getByTestId("selected-tier-breakdown")).toHaveCount(0);
  const invalidText = (await panel.textContent()) ?? "";
  expect(invalidText).not.toMatch(/NaN|Infinity|₹-/);
});

test("mobile 375px cost explorer has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/#lane-a-cost-explorer");
  const panel = page.locator(PANEL);
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("cost-explorer-disclosure")).toBeVisible();

  const widths = await panel.evaluate((element) => ({
    client: element.clientWidth,
    scroll: element.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);

  const pageWidths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(pageWidths.scroll).toBeLessThanOrEqual(pageWidths.client);
});

test("cost explorer has no WCAG violations", async ({ page }) => {
  await page.goto("/#lane-a-cost-explorer");
  await expect(page.locator(PANEL)).toBeVisible();
  const results = await new AxeBuilder({ page }).include(PANEL).analyze();
  expect(results.violations).toEqual([]);
});
