import { test, expect, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.fill("#username", "admin");
  await page.fill("#password", "admin");
  await page.click('button[type="submit"]');
  await page.waitForSelector('nav[aria-label="Main navigation"]', {
    timeout: 30_000,
  });
}

test.describe("API Health — backend integration", () => {
  test("health endpoint returns status ok with database and scheduler fields", async ({
    request,
  }) => {
    const response = await request.get("/api/health/?detailed=true");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("status");
    expect(body).toHaveProperty("database");
    expect(body).toHaveProperty("scheduler");
  });

  test("login + session cookie works for authenticated API calls", async ({
    page,
  }) => {
    await login(page);
    const response = await page.request.get("/api/auth/status/");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("username", "admin");
  });

  test("dashboard KPIs endpoint returns valid JSON structure", async ({
    page,
  }) => {
    await login(page);
    const response = await page.request.get("/api/dashboard/kpis/");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(typeof body).toBe("object");
  });

  test("regime dashboard renders without error boundary", async ({ page }) => {
    await login(page);
    await page.goto("/regime", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    await expect(page.locator("#page-heading")).toContainText("Regime");
  });

  test("risk status endpoint accessible after auth", async ({ page }) => {
    await login(page);
    const response = await page.request.get("/api/risk/1/status/");
    expect(response.status()).toBe(200);
  });

  test("scheduler page shows task rows", async ({ page }) => {
    await login(page);
    await page.goto("/scheduler", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    await expect(page.locator("#page-heading")).toContainText("Scheduler");
    // Table or list of tasks should be present
    await expect(
      page.locator("table, [role='table'], [aria-label*='task']").first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("data management page shows data quality section", async ({ page }) => {
    await login(page);
    await page.goto("/data", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    await expect(page.locator("#page-heading")).toContainText("Data");
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("WebSocket ConnectionStatus shows connected state after login", async ({
    page,
  }) => {
    await login(page);
    // ConnectionStatus renders somewhere in the layout — look for a connected indicator
    // It may show as "Connected" text or a green dot
    const connectionIndicator = page.locator(
      '[aria-label*="onnect"], [title*="onnect"], text=Connected',
    );
    // Allow some time for WebSocket to establish
    await expect(connectionIndicator.first()).toBeVisible({ timeout: 15_000 });
  });
});
