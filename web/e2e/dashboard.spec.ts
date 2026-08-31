import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("product homepage is lightweight, keyboard reachable, static, and WCAG-scannable", async ({ page }) => {
  const predictionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/predict")) predictionRequests.push(request.url());
  });

  await page.goto("/");
  await expect(page).toHaveTitle(/SecureSwipe/);
  await expect(
    page.getByRole("heading", { level: 1, name: /Payment-risk review, made inspectable/i }),
  ).toBeVisible();
  await expect(page.locator("[data-product-section]")).toHaveCount(5);
  await expect(page.getByText(/Payment action stays outside this system/)).toBeVisible();
  await expect(page.getByText("Historical evaluation command board")).toHaveCount(0);

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

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
  // P0.3 made the Lane A review-strategy surface the homepage's central
  // interaction, which ships one client-component chunk that the previously
  // all-static homepage did not carry (8 -> 9 scripts). The byte budgets are
  // deliberately left untouched so they still catch payload regressions:
  // measured usage after the change is ~191 KB of a 350 KB script allowance.
  expect(assetBudget.scriptCount).toBeLessThanOrEqual(9);
  expect(assetBudget.scriptEncodedBytes).toBeLessThanOrEqual(350_000);
  expect(assetBudget.totalRequestCount).toBeLessThanOrEqual(12);
  expect(assetBudget.totalEncodedBytes).toBeLessThanOrEqual(450_000);
});

test("homepage review-strategy surface is interactive and keyboard reachable at 375px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");

  // The hero's primary action reaches the review-strategy surface in-page.
  const primary = page.getByRole("link", { name: /Explore the review strategy/i });
  await expect(primary).toHaveAttribute("href", "#review-strategy");
  await primary.focus();
  await expect(primary).toBeFocused();
  await page.keyboard.press("Enter");

  const surface = page.locator("#review-strategy");
  await expect(surface).toBeVisible();

  // Selector, core metrics and the editable illustrative cost all survive.
  const group = surface.getByRole("group", {
    name: /Select a capacity tier for the illustrative cost scenario/i,
  });
  const tiers = group.getByRole("button");
  await expect(tiers).toHaveCount(5);
  await expect(tiers.nth(0)).toHaveAttribute("aria-pressed", "true");

  await tiers.nth(3).focus();
  await page.keyboard.press("Enter");
  await expect(tiers.nth(3)).toHaveAttribute("aria-pressed", "true");
  await expect(tiers.nth(0)).toHaveAttribute("aria-pressed", "false");

  const breakdown = surface.getByTestId("selected-tier-breakdown");
  const before = await breakdown.textContent();
  const missedFraud = surface.getByLabel("Missed-fraud loss per false negative (₹)");
  await missedFraud.focus();
  await missedFraud.fill("9000");
  await expect(breakdown).not.toHaveText(before ?? "");

  // Detail belongs to the evidence route, not the homepage.
  await expect(surface.getByTestId("all-tier-cost-table")).toHaveCount(0);
  await expect(surface.getByTestId("sealed-final-metrics")).toHaveCount(0);
  await expect(page.getByText("95% CI")).toHaveCount(0);
  await expect(
    surface.getByRole("link", { name: /Inspect detailed evidence/i }),
  ).toHaveAttribute("href", "/evidence#lane-a-capacity");

  const widths = await surface.evaluate((element) => ({
    client: element.clientWidth,
    scroll: element.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
});

test("homepage hero leads with one sealed Lane A headline and no legend", async ({ page }) => {
  await page.goto("/");
  const hero = page.locator('[data-product-section="product-promise"]');

  const headline = hero.getByTestId("hero-headline-evidence");
  await expect(headline).toBeVisible();
  await expect(headline).toContainText("80.18%");
  await expect(headline).toContainText("SEALED FINAL EVALUATION — LANE A / IEEE-CIS");
  await expect(headline).toContainText(
    "recall in the sealed Lane A final evaluation. Review-capacity and false-positive trade-offs are available below.",
  );
  await expect(headline).toContainText("Not Razorpay, live-merchant, or production performance");

  // The capacity tier and its false-positive count must not be combined here.
  await expect(headline).not.toContainText("1,000 reviews/day");
  await expect(headline).not.toContainText("28,306");

  // No evidence legend, taxonomy badges, or Lane B metric competes in the hero.
  await expect(hero.getByRole("note")).toHaveCount(0);
  await expect(hero.getByText("Historical evaluation", { exact: true })).toHaveCount(0);
  await expect(page.getByText("0.53")).toHaveCount(0);
});

test("shared midnight and blue visual tokens remain consistent across both routes", async ({
  page,
}) => {
  for (const route of ["/", "/evidence"]) {
    await page.goto(route);
    const visualSystem = await page.locator("#main-content").evaluate((main) => {
      const rootStyle = getComputedStyle(document.documentElement);
      const mainStyle = getComputedStyle(main);
      const gridStyle = getComputedStyle(main, "::before");
      return {
        tokens: {
          background: rootStyle.getPropertyValue("--ss-background").trim(),
          surface: rootStyle.getPropertyValue("--ss-surface").trim(),
          raised: rootStyle.getPropertyValue("--ss-surface-raised").trim(),
          border: rootStyle.getPropertyValue("--ss-border").trim(),
          primary: rootStyle.getPropertyValue("--ss-primary").trim(),
          primaryHover: rootStyle.getPropertyValue("--ss-primary-hover").trim(),
          text: rootStyle.getPropertyValue("--ss-text").trim(),
          muted: rootStyle.getPropertyValue("--ss-muted").trim(),
        },
        backgroundColor: mainStyle.backgroundColor,
        backgroundImage: gridStyle.backgroundImage,
        backgroundPointerEvents: gridStyle.pointerEvents,
        fontFamily: getComputedStyle(document.body).fontFamily,
      };
    });

    expect(visualSystem.tokens).toEqual({
      background: "#070b12",
      surface: "#0d1420",
      raised: "#10223a",
      border: "#243650",
      primary: "#3b82f6",
      primaryHover: "#60a5fa",
      text: "#f8fafc",
      muted: "#a8b3c7",
    });
    expect(visualSystem.backgroundColor).toBe("rgb(7, 11, 18)");
    expect(visualSystem.backgroundImage).toContain("radial-gradient");
    expect(visualSystem.backgroundPointerEvents).toBe("none");
    expect(visualSystem.fontFamily).toContain("ui-sans-serif");
  }

  await page.goto("/");
  const primary = page.getByRole("link", { name: /Explore the review strategy/i });
  const primaryStyles = await primary.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      background: style.backgroundColor,
      color: style.color,
      height: element.getBoundingClientRect().height,
    };
  });
  expect(primaryStyles).toMatchObject({
    background: "rgb(59, 130, 246)",
    color: "rgb(7, 11, 18)",
  });
  expect(primaryStyles.height).toBeGreaterThanOrEqual(44);

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/evidence");
  const touchTargets = await page
    .locator('summary, button, input:not([type="range"])')
    .evaluateAll((elements) =>
      elements
        .filter((element) => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && rect.height > 0;
        })
        .map((element) => ({
          label: element.getAttribute("aria-label") ?? element.textContent?.trim(),
          height: element.getBoundingClientRect().height,
        })),
    );
  expect(touchTargets.every((target) => target.height >= 44)).toBe(true);
});

test("evidence route preserves the detailed scientific command center", async ({ page }) => {
  const predictionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/predict")) predictionRequests.push(request.url());
  });

  await page.goto("/evidence");
  await expect(
    page.getByRole("heading", { level: 1, name: "Scientific evidence and system boundaries" }),
  ).toBeVisible();
  await expect(page.getByText("Historical evaluation command board")).toBeVisible();
  await expect(page.locator("#risk")).toBeVisible();
  await expect(page.locator("#lane-a-capacity")).toBeVisible();
  const syntheticDisclosure = page
    .locator("#synthetic-and-scenarios")
    .locator('button[aria-controls="synthetic-and-scenarios-content"]');
  await expect(syntheticDisclosure).toHaveAccessibleName(
    "Show details: Plumbing test and Lane B cost scenario",
  );
  await expect(syntheticDisclosure).toHaveAttribute("aria-expanded", "false");
  await syntheticDisclosure.focus();
  await page.keyboard.press("Enter");
  await expect(syntheticDisclosure).toHaveAttribute("aria-expanded", "true");
  await expect(syntheticDisclosure).toHaveAccessibleName(
    "Hide details: Plumbing test and Lane B cost scenario",
  );
  await expect(page.locator("#synthetic")).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to product overview" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(predictionRequests).toEqual([]);
});

test("evidence disclosures remain keyboard operable and overflow-safe at 375px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/evidence");

  const control = page
    .locator("#historical-analysis")
    .locator('button[aria-controls="historical-analysis-content"]');
  await expect(control).toHaveAccessibleName(
    "Show details: Threshold, curve, and explainability detail",
  );
  await control.focus();
  await expect(control).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(control).toHaveAttribute("aria-expanded", "true");
  await expect(control).toHaveAccessibleName(
    "Hide details: Threshold, curve, and explainability detail",
  );
  await expect(page.locator("#thresholds")).toBeVisible();

  const widths = await page.locator("#historical-analysis").evaluate((element) => ({
    client: element.clientWidth,
    scroll: element.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
});

test("mobile route navigation is keyboard reachable in both directions", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  const pagesMenu = page.getByText("Pages", { exact: true });
  await pagesMenu.focus();
  await page.keyboard.press("Enter");
  const menu = page.locator("details[open]");
  const evidenceLink = menu.getByRole("link", { name: "Evidence" });
  await expect(evidenceLink).toBeVisible();
  await evidenceLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/evidence$/);
  await expect(page.getByRole("link", { name: "Back to product overview" })).toBeVisible();

  await page.getByRole("link", { name: "Back to product overview" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/$/);
});

test("both routes have no page overflow, broken internal links, or console errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(request.url()));

  for (const route of ["/", "/evidence"]) {
    for (const viewport of [
      { width: 1280, height: 900 },
      { width: 375, height: 812 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto(route);
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
  }

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});

test("mobile illustrative cost panel exposes its bounded INR evidence without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/evidence#illustrative-cost");
  const disclosure = page.locator("#synthetic-and-scenarios");
  const disclosureControl = disclosure.locator(
    'button[aria-controls="synthetic-and-scenarios-content"]',
  );
  await disclosureControl.focus();
  await page.keyboard.press("Enter");
  await expect(disclosureControl).toHaveAttribute("aria-expanded", "true");
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

  const navigation = await page.goto("/evidence");
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
