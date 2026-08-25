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
  await expect(page.getByText("precomputed · static-first", { exact: true })).toBeVisible();

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

test("desktop and 375px static views have no page overflow, broken internal links, or console errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(request.url()));

  for (const viewport of [
    { width: 1280, height: 900 },
    { width: 375, height: 812 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByText("Track 2: AI Risk Manager", { exact: false })).toBeVisible();
    const audit = await page.evaluate(() => {
      const missingTargets = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]'))
        .map((anchor) => anchor.getAttribute("href"))
        .filter((href): href is string => Boolean(href && href.length > 1))
        .filter((href) => document.querySelector(href) === null);
      return {
        pageClientWidth: document.documentElement.clientWidth,
        pageScrollWidth: document.documentElement.scrollWidth,
        missingTargets,
      };
    });
    expect(audit.pageScrollWidth).toBeLessThanOrEqual(audit.pageClientWidth);
    expect(audit.missingTargets).toEqual([]);
  }

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});

test("mobile illustrative cost panel exposes its bounded INR evidence without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/#illustrative-cost");
  const panel = page.locator("#illustrative-cost");

  await expect(panel).toBeVisible();
  await expect(panel.getByLabel("Illustrative review cost")).toHaveValue("83");
  await expect(
    panel.getByLabel("Illustrative legitimate-customer friction"),
  ).toHaveValue("830");
  await expect(panel.getByLabel("Illustrative missed-fraud loss")).toHaveValue(
    "8300",
  );
  await expect(
    panel.getByLabel("Illustrative chargeback handling"),
  ).toHaveValue("4150");
  await expect(panel.getByLabel("Locked historical cost fixture")).toContainText(
    "Threshold0.53",
  );
  await expect(panel.getByTestId("illustrative-total")).toContainText(
    "₹3,86,697.00",
  );
  await expect(
    panel
      .getByText(
        "Illustrative scenario — not Razorpay economics and not a production-optimal threshold.",
        { exact: true },
      )
      .first(),
  ).toBeVisible();

  const widths = await panel.evaluate((element) => ({
    client: element.clientWidth,
    scroll: element.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
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
        decision: "human_review",
        model_version: "browser-test-bundle-1",
        bundle_format_version: "3",
        provenance: {
          training_data_fingerprint: "browser-test-fingerprint",
          evidence_category: "historical_reference_demo_inference",
          historical_taint: true,
          decision_eligible: false,
          historical_metrics_claimed: false,
          evaluation_performed: false,
        },
      }),
    });
  });

  const navigation = await page.goto("/");
  expect(navigation?.headers()["content-security-policy"]).toContain(
    "connect-src 'self' http://127.0.0.1:3200",
  );
  await page.getByRole("button", { name: "Try genuine inference" }).click();
  await expect(page.getByRole("status", { name: "Genuine demo inference status" })).toContainText(
    "Genuine demo inference result: human review at score 0.731. Model bundle: browser-test-bundle-1 (format 3). API provenance: historical_reference_demo_inference; decision eligible: no.",
  );
  await expect(page.getByText(/No customer or transaction data is used/)).toBeVisible();
  expect(predictionRequests).toHaveLength(1);
  expect(predictionRequests[0].url).toBe("http://127.0.0.1:3200/v1/predict");
  expect(predictionRequests[0].body).toEqual(
    Object.fromEntries(["Time", ...Array.from({ length: 28 }, (_, index) => `V${index + 1}`), "Amount"].map((key) => [key, 0])),
  );
});
