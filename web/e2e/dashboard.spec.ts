import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("production dashboard is keyboard reachable, static, and WCAG-scannable", async ({ page }) => {
  const predictionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/predict")) predictionRequests.push(request.url());
  });

  await page.goto("/");
  await expect(page).toHaveTitle(/SecureSwipe/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("precomputed · static", { exact: true })).toBeVisible();

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const scoreSlider = page.getByRole("slider", { name: "Adjust hypothetical score" });
  await scoreSlider.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(
    page.getByRole("status", { name: "Hypothetical review decision" }),
  ).toContainText("Below review threshold");

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  expect(predictionRequests).toEqual([]);

  const assetBudget = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    const scripts = resources.filter((entry) => entry.initiatorType === "script");
    return {
      scriptCount: scripts.length,
      scriptEncodedBytes: scripts.reduce((total, entry) => total + entry.encodedBodySize, 0),
      totalRequestCount: resources.length + 1,
      totalEncodedBytes:
        navigation.encodedBodySize +
        resources.reduce((total, entry) => total + entry.encodedBodySize, 0),
    };
  });
  expect(assetBudget.scriptCount).toBeLessThanOrEqual(8);
  expect(assetBudget.scriptEncodedBytes).toBeLessThanOrEqual(350_000);
  expect(assetBudget.totalRequestCount).toBeLessThanOrEqual(12);
  expect(assetBudget.totalEncodedBytes).toBeLessThanOrEqual(450_000);
});

test("mobile navigation exposes every dashboard section", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.getByText("Sections", { exact: true }).click();
  const menu = page.locator("details[open]");
  await expect(menu.getByRole("link", { name: "Thresholds" })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Explainability" })).toBeVisible();
  await menu.getByRole("link", { name: "Thresholds" }).click();
  await expect(page).toHaveURL(/#thresholds$/);
  await expect(page.locator("#thresholds")).toBeVisible();
});

test("live demo stays opt-in and preserves the static fallback when no API is configured", async ({ page }) => {
  const predictionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/predict")) predictionRequests.push(request.url());
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Try synthetic API" }).click();
  await expect(page.getByRole("status", { name: "Synthetic API status" })).toContainText("Live demo is not configured");
  await expect(page.getByText("Static fallback active until the API check is requested.")).not.toBeVisible();
  await expect(page.getByText(/No customer or transaction data is used/)).toBeVisible();
  expect(predictionRequests).toEqual([]);
});
