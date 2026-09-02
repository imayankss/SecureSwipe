import { expect, test, type Page } from "@playwright/test";

/**
 * Visual QA sweep.
 *
 * Captures every route and every demo state at the reviewed viewports and
 * fails on horizontal page overflow. Screenshots land in `.visual-review/`,
 * which is git-ignored, so this produces review material without adding
 * binaries to the diff.
 */
const OUT = ".visual-review";

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "390x844", width: 390, height: 844 },
  { name: "360x800", width: 360, height: 800 },
] as const;

const ROUTES = [
  { name: "home", path: "/" },
  { name: "demo", path: "/demo" },
  { name: "evidence", path: "/evidence" },
] as const;

const corsHeaders = {
  "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Request-ID",
  "Access-Control-Expose-Headers": "X-Request-ID, X-Idempotent-Replay, X-Audit-Event-Hash",
};

async function mockApi(page: Page) {
  const valid: number[] = [];
  await page.route("http://127.0.0.1:3200/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (request.url().endsWith("/health/ready")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders,
        body: JSON.stringify({
          schema_version: "1.0",
          status: "ready",
          model_version: "synthetic-smoke-1",
        }),
      });
      return;
    }
    if (request.url().endsWith("/v1/model-info")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders,
        body: JSON.stringify({
          schema_version: "1.0",
          model_version: "synthetic-smoke-1",
          bundle_format_version: "3",
          model_artifact_sha256: "b".repeat(64),
          evidence_category: "synthetic_demo_inference",
        }),
      });
      return;
    }
    if (request.headers()["x-request-id"] === "secureswipe-reference-demo-invalid-v1") {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        headers: corsHeaders,
        body: JSON.stringify({
          schema_version: "1.0",
          request_id: "secureswipe-reference-demo-invalid-v1",
          error: { code: "validation_error", message: "Request validation failed." },
        }),
      });
      return;
    }
    valid.push(1);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        ...corsHeaders,
        "X-Audit-Event-Hash": "a".repeat(64),
        ...(valid.length > 1 ? { "X-Idempotent-Replay": "true" } : {}),
      },
      body: JSON.stringify({
        schema_version: "1.0",
        request_id: "secureswipe-reference-demo-v1",
        raw_score: 0.731,
        calibrated_probability: null,
        decision_score: 0.731,
        score_type: "raw_score",
        operating_threshold: 0.53,
        decision: "human_review",
        model_version: "synthetic-smoke-1",
        bundle_format_version: "3",
        provenance: {
          training_data_fingerprint: "c".repeat(64),
          evidence_category: "synthetic_demo_inference",
          historical_taint: false,
          decision_eligible: false,
          historical_metrics_claimed: false,
          evaluation_performed: false,
        },
      }),
    });
  });
}

async function expectNoHorizontalOverflow(page: Page, label: string) {
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(
    widths.scroll,
    `${label}: page scrollWidth ${widths.scroll} exceeded clientWidth ${widths.client}`,
  ).toBeLessThanOrEqual(widths.client + 1);
}

for (const viewport of VIEWPORTS) {
  test(`routes render without horizontal overflow at ${viewport.name}`, async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    for (const route of ROUTES) {
      await page.goto(route.path);
      await page.waitForLoadState("networkidle");
      await expectNoHorizontalOverflow(page, `${route.name} @ ${viewport.name}`);
      await page.screenshot({
        path: `${OUT}/${viewport.name}-${route.name}.png`,
        fullPage: true,
      });
    }
  });
}

test("captures every guided demo state at desktop width", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/demo");

  await page.screenshot({ path: `${OUT}/demo-01-initial.png`, fullPage: true });

  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Review");
  await page.screenshot({ path: `${OUT}/demo-02-decision.png`, fullPage: true });

  await page.getByRole("button", { name: "Replay same request" }).click();
  await expect(page.getByText("Replay · no second event")).toBeVisible();
  await page.screenshot({ path: `${OUT}/demo-03-replay-audit.png`, fullPage: true });

  await page.getByRole("button", { name: "Test rejected request" }).click();
  await expect(
    page.getByText(/HTTP 422 · validation_error · no review outcome released/),
  ).toBeVisible();
  await page.screenshot({ path: `${OUT}/demo-04-fail-closed.png`, fullPage: true });

  await page.getByRole("button", { name: "Decision trace" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({ path: `${OUT}/demo-05-decision-trace.png` });
  await expectNoHorizontalOverflow(page, "demo trace drawer");
  await page.keyboard.press("Escape");
});

test("captures the unavailable demo state", async ({ page }) => {
  await page.route("http://127.0.0.1:3200/**", (route) => route.abort("failed"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/demo");
  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Unavailable");
  await page.screenshot({ path: `${OUT}/demo-06-unavailable.png`, fullPage: true });
});

test("the drawer fits a small viewport", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/demo");
  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Review");
  await page.getByRole("button", { name: "Decision trace" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box?.width ?? 0).toBeLessThanOrEqual(360);
  await page.screenshot({ path: `${OUT}/demo-07-drawer-mobile.png` });
  await expectNoHorizontalOverflow(page, "mobile drawer");
});

test("the demo completes with keyboard only", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/demo");

  await page.getByRole("button", { name: "Start guided demo" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Review");

  await page.getByRole("button", { name: "Replay same request" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Replay · no second event")).toBeVisible();

  await page.getByRole("button", { name: "Test rejected request" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-demo-complete]")).toBeVisible();
});

test("reduced motion removes the spinner animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockApi(page);
  await page.goto("/demo");
  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Review");

  // `motion-safe:` utilities must not resolve under a reduced-motion preference.
  const animated = await page.evaluate(() =>
    Array.from(document.querySelectorAll("*")).filter(
      (node) => getComputedStyle(node).animationName !== "none",
    ).length,
  );
  expect(animated).toBe(0);
});
