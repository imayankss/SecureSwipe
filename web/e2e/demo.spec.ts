import { expect, test, type Page } from "@playwright/test";

const requestId = "secureswipe-reference-demo-v1";
const invalidRequestId = "secureswipe-reference-demo-invalid-v1";
const auditHash = "a".repeat(64);
const modelHash = "b".repeat(64);

const corsHeaders = {
  "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Request-ID",
  "Access-Control-Expose-Headers": "X-Request-ID, X-Idempotent-Replay, X-Audit-Event-Hash",
};

/** Routes the demo API to a ready bundle and records valid prediction calls. */
async function mockReadyApi(
  page: Page,
  validRequests: { requestId: string | undefined; body: unknown }[],
) {
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
          model_artifact_sha256: modelHash,
          evidence_category: "synthetic_demo_inference",
        }),
      });
      return;
    }

    const id = request.headers()["x-request-id"];
    if (id === invalidRequestId) {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        headers: corsHeaders,
        body: JSON.stringify({
          schema_version: "1.0",
          request_id: invalidRequestId,
          error: { code: "validation_error", message: "Request validation failed." },
        }),
      });
      return;
    }

    validRequests.push({ requestId: id, body: request.postDataJSON() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        ...corsHeaders,
        "X-Audit-Event-Hash": auditHash,
        ...(validRequests.length > 1 ? { "X-Idempotent-Replay": "true" } : {}),
      },
      body: JSON.stringify({
        schema_version: "1.0",
        request_id: requestId,
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

test("guided demo proves decision, audit, replay, and fail-closed validation", async ({
  page,
}) => {
  const validRequests: { requestId: string | undefined; body: unknown }[] = [];
  await mockReadyApi(page, validRequests);

  const navigation = await page.goto("/demo");
  expect(navigation?.headers()["content-security-policy"]).toContain(
    "connect-src 'self' http://127.0.0.1:3200",
  );
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Local reference-model demonstration",
  );
  await expect(page.getByRole("note")).toContainText(
    "This interactive reference demo is separate from the sealed Lane A evaluation",
  );

  // Keyboard-only start.
  const start = page.getByRole("button", { name: "Start guided demo" });
  await start.focus();
  await page.keyboard.press("Enter");

  await expect(page.locator("[data-demo-outcome]")).toHaveText("Review");
  expect(validRequests).toHaveLength(1);

  // The suppressed decision score must never be rendered.
  await expect(page.getByText("0.731", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Replay same request" }).click();
  await expect(page.getByText("Replay · no second event")).toBeVisible();
  expect(validRequests).toHaveLength(2);
  expect(validRequests.map((r) => r.requestId)).toEqual([requestId, requestId]);
  expect(validRequests[0].body).toEqual(validRequests[1].body);

  await page.getByRole("button", { name: "Test rejected request" }).click();
  await expect(
    page.getByText(/HTTP 422 · validation_error · no review outcome released/),
  ).toBeVisible();

  await expect(page.locator("[data-demo-complete]")).toBeVisible();

  // The decision trace is a real modal dialog with working escape semantics.
  await page.getByRole("button", { name: "Decision trace" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Decision trace" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  // Reset returns the journey to its idle state.
  await page.getByRole("button", { name: "Reset demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Pending");
  await expect(page.locator("[data-demo-complete]")).toHaveCount(0);
});

test("unavailable API never produces a demo outcome", async ({ page }) => {
  await page.route("http://127.0.0.1:3200/**", async (route) => {
    await route.abort("failed");
  });
  await page.goto("/demo");
  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Unavailable");
  await expect(page.getByText("Review", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Below review threshold", { exact: true })).toHaveCount(0);
});

test("the whole demo is reachable on a small viewport without overflow", async ({
  page,
}) => {
  const validRequests: { requestId: string | undefined; body: unknown }[] = [];
  await mockReadyApi(page, validRequests);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/demo");

  await page.getByRole("button", { name: "Start guided demo" }).click();
  await expect(page.locator("[data-demo-outcome]")).toHaveText("Review");

  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
});
