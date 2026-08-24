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

test("configured production live demo sends one genuine inference request and validates the full response", async ({ page }) => {
  const predictionRequests: { url: string; body: unknown }[] = [];
  await page.route("http://127.0.0.1:3200/v1/predict", async (route) => {
    const request = route.request();
    predictionRequests.push({ url: request.url(), body: request.postDataJSON() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3100" },
      body: JSON.stringify({
        schema_version: "1.0",
        request_id: "browser-live-1",
        raw_score: 0.731,
        calibrated_probability: null,
        decision_score: 0.731,
        score_type: "raw_score",
        operating_threshold: 0.53,
        decision: "review",
        model_version: "browser-test-bundle-1",
      }),
    });
  });

  const navigation = await page.goto("/");
  expect(navigation?.headers()["content-security-policy"]).toContain(
    "connect-src 'self' http://127.0.0.1:3200",
  );
  await page.getByRole("button", { name: "Try genuine inference" }).click();
  await expect(page.getByRole("status", { name: "Genuine demo inference status" })).toContainText(
    "Genuine demo inference result: review at score 0.731. Model bundle: browser-test-bundle-1.",
  );
  await expect(page.getByText(/No customer or transaction data is used/)).toBeVisible();
  expect(predictionRequests).toHaveLength(1);
  expect(predictionRequests[0].url).toBe("http://127.0.0.1:3200/v1/predict");
  expect(predictionRequests[0].body).toEqual(
    Object.fromEntries(["Time", ...Array.from({ length: 28 }, (_, index) => `V${index + 1}`), "Amount"].map((key) => [key, 0])),
  );
});
