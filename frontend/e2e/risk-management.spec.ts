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

/** Wait for lazy-loaded page content to finish rendering (Suspense fallback). */
async function waitForPageLoad(page: Page) {
  await page.waitForFunction(
    () =>
      !document.querySelector("main")?.textContent?.includes("Loading..."),
    { timeout: 10_000 },
  );
}

test.describe("Risk management flows", () => {
  test("risk page loads with heading and status cards", async ({ page }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Risk Management",
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Status cards should render (Equity, Drawdown, Daily PnL, Total PnL, Status)
    await expect(page.locator("text=Equity").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator("text=Drawdown").first()).toBeVisible();
  });

  test("risk status shows active or halted state", async ({ page }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // The Status card should show either "Active" or "HALTED"
    const statusIndicator = page.locator("text=Active, text=HALTED");
    await expect(statusIndicator.first()).toBeVisible({ timeout: 10_000 });
  });

  test("risk limits section displays configurable limits", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Risk Limits heading
    await expect(
      page.locator("h3:has-text('Risk Limits')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // Limit field labels should render
    await expect(
      page.locator("text=Max Drawdown").first(),
    ).toBeVisible();
    await expect(
      page.locator("text=Max Open Positions").first(),
    ).toBeVisible();
  });

  test("risk limits edit button toggles edit mode", async ({ page }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Wait for the Risk Limits section to be visible
    await expect(
      page.locator("h3:has-text('Risk Limits')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // The parent container should have an Edit button
    const limitsSection = page.locator(
      "h3:has-text('Risk Limits')",
    ).locator("..");
    const sectionEditBtn = limitsSection.locator('button:has-text("Edit")');
    const hasEdit = await sectionEditBtn
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    if (hasEdit) {
      await sectionEditBtn.click();
      // Save and Cancel buttons should appear
      await expect(
        limitsSection.locator('button:has-text("Save")'),
      ).toBeVisible();
      await expect(
        limitsSection.locator('button:has-text("Cancel")'),
      ).toBeVisible();
    }
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("VaR section displays value at risk metrics", async ({ page }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Value at Risk heading
    await expect(
      page.locator("h3:has-text('Value at Risk')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // VaR metric labels
    await expect(page.locator("text=VaR 95%").first()).toBeVisible();
    await expect(page.locator("text=VaR 99%").first()).toBeVisible();
    await expect(page.locator("text=CVaR 95%").first()).toBeVisible();
    await expect(page.locator("text=CVaR 99%").first()).toBeVisible();
    // Method selector should be present
    const methodSelector = page.locator(
      'select option[value="parametric"]',
    );
    await expect(methodSelector.first()).toBeAttached();
  });

  test("portfolio health / heat check section renders", async ({ page }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Portfolio Health heading
    await expect(
      page.locator("h3:has-text('Portfolio Health')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // Health badge should show Healthy or Unhealthy
    const healthBadge = page.locator("text=Healthy, text=Unhealthy");
    await expect(healthBadge.first()).toBeVisible();
  });

  test("alert history section renders with severity filter", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Alert History heading
    await expect(
      page.locator("h3:has-text('Alert History')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // Severity filter dropdown with options
    const severitySelect = page.locator(
      'select option:has-text("All Severities")',
    );
    await expect(severitySelect.first()).toBeAttached();
    // Check that severity options exist
    await expect(
      page.locator('select option:has-text("Critical")').first(),
    ).toBeAttached();
    await expect(
      page.locator('select option:has-text("Warning")').first(),
    ).toBeAttached();
    await expect(
      page.locator('select option:has-text("Info")').first(),
    ).toBeAttached();
    // Event type filter input
    await expect(
      page.locator('input[placeholder="Filter by event type"]').first(),
    ).toBeVisible();
  });

  test("halt trading button is visible when not halted", async ({ page }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Either "Halt Trading" button (when active) or "Resume Trading" (when halted)
    const haltButton = page.locator('button:has-text("Halt Trading")');
    const resumeButton = page.locator('button:has-text("Resume Trading")');
    const hasHalt = await haltButton
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    const hasResume = await resumeButton
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    // One of the two should be visible
    expect(hasHalt || hasResume).toBe(true);
  });

  test("position sizer and trade checker sections render", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Position Sizer heading
    await expect(
      page.locator("h3:has-text('Position Sizer')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // Entry price and stop loss inputs
    await expect(page.locator("#risk-entry-price")).toBeVisible();
    await expect(page.locator("#risk-stop-loss")).toBeVisible();
    // Calculate button
    await expect(
      page.locator('button:has-text("Calculate")').first(),
    ).toBeVisible();
    // Trade Checker heading
    await expect(
      page.locator("h3:has-text('Trade Checker')").first(),
    ).toBeVisible();
    // Trade symbol input and Buy/Sell buttons
    await expect(page.locator("#risk-trade-symbol")).toBeVisible();
    await expect(
      page.locator('button:has-text("Buy")').first(),
    ).toBeVisible();
    await expect(
      page.locator('button:has-text("Sell")').first(),
    ).toBeVisible();
    await expect(
      page.locator('button:has-text("Check Trade")').first(),
    ).toBeVisible();
  });

  test("portfolio selector allows switching risk context", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/risk", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Portfolio selector dropdown
    const portfolioSelect = page.locator("#risk-portfolio-id");
    await expect(portfolioSelect).toBeVisible({ timeout: 10_000 });
    // Should have at least one option
    const options = portfolioSelect.locator("option");
    const count = await options.count();
    expect(count).toBeGreaterThan(0);
  });

  test("risk status API returns valid data", async ({ page }) => {
    await login(page);
    const response = await page.request.get("/api/risk/1/status/");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("equity");
    expect(body).toHaveProperty("drawdown");
    expect(body).toHaveProperty("is_halted");
  });
});
