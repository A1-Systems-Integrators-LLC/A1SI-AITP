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

test.describe("Market and analysis flows", () => {
  test("regime dashboard loads with heading and symbol selector", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/regime", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("h2:has-text('Regime Dashboard')")).toBeVisible();
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Symbol selector dropdown
    await expect(
      page.locator('select[aria-label="Select symbol for regime analysis"]'),
    ).toBeVisible();
  });

  test("regime dashboard shows status cards with regime data", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/regime", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Status cards: Current Regime, Confidence, Primary Strategy, Position Modifier
    await expect(
      page.locator("text=Current Regime").first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator("text=Confidence").first(),
    ).toBeVisible();
    await expect(
      page.locator("text=Primary Strategy").first(),
    ).toBeVisible();
    await expect(
      page.locator("text=Position Modifier").first(),
    ).toBeVisible();
  });

  test("regime dashboard shows sub-indicators section", async ({ page }) => {
    await login(page);
    await page.goto("/regime", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Sub-Indicators heading
    await expect(
      page.locator("h3:has-text('Sub-Indicators')").first(),
    ).toBeVisible({ timeout: 10_000 });
    // ADX gauge label should be visible
    await expect(page.locator("text=ADX").first()).toBeVisible();
  });

  test("market opportunities page loads with heading", async ({ page }) => {
    await login(page);
    await page.goto("/opportunities", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Market Opportunities",
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("market opportunities has asset class filter dropdown", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/opportunities", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Asset class filter should have All Assets, Crypto, Forex, Equities options
    const allAssetsOption = page.locator(
      'select option:has-text("All Assets")',
    );
    await expect(allAssetsOption.first()).toBeAttached({ timeout: 10_000 });
    await expect(
      page.locator('select option:has-text("Crypto")').first(),
    ).toBeAttached();
    await expect(
      page.locator('select option:has-text("Forex")').first(),
    ).toBeAttached();
    await expect(
      page.locator('select option:has-text("Equities")').first(),
    ).toBeAttached();
  });

  test("market opportunities has type filter dropdown", async ({ page }) => {
    await login(page);
    await page.goto("/opportunities", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Type filter should have All Types and specific scanner types
    await expect(
      page.locator('select option:has-text("All Types")').first(),
    ).toBeAttached({ timeout: 10_000 });
    await expect(
      page.locator('select option:has-text("Volume Surge")').first(),
    ).toBeAttached();
    await expect(
      page.locator('select option:has-text("Breakout")').first(),
    ).toBeAttached();
  });

  test("market opportunities summary cards render when data available", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/opportunities", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Summary cards: Active, Avg Score, High Score (75+), Types Active
    const activeLabel = page.locator("text=Active").first();
    const hasCards = await activeLabel
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    if (hasCards) {
      await expect(page.locator("text=Avg Score").first()).toBeVisible();
    }
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("conviction dashboard loads with signal heatmap section", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/conviction", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Conviction Dashboard",
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Signal Heatmap heading
    await expect(
      page.locator("h3:has-text('Signal Heatmap')").first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("conviction dashboard heatmap shows signal buttons or skeleton", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/conviction", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Either signal buttons (with aria-label="View signal for ...") or skeleton loader
    const signalButton = page.locator(
      'button[aria-label^="View signal for"]',
    );
    const skeleton = page.locator('[data-testid="heatmap-skeleton"]');
    const hasSignals = await signalButton
      .first()
      .isVisible({ timeout: 8_000 })
      .catch(() => false);
    const hasSkeleton = await skeleton
      .isVisible({ timeout: 2_000 })
      .catch(() => false);
    // One of signals, skeleton, or error should be present (page should not be blank)
    const hasError = await page
      .locator("text=No signal data available")
      .isVisible({ timeout: 2_000 })
      .catch(() => false);
    expect(hasSignals || hasSkeleton || hasError).toBe(true);
  });

  test("navigate between analysis pages via sidebar", async ({ page }) => {
    await login(page);
    const nav = page.locator('nav[aria-label="Main navigation"]');
    // Navigate to Market Analysis
    await nav.locator('a[href="/market"]').click();
    await expect(page).toHaveURL("/market");
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Market Analysis",
    );
    // Navigate to Regime Dashboard
    await nav.locator('a[href="/regime"]').click();
    await expect(page).toHaveURL("/regime");
    await waitForPageLoad(page);
    await expect(
      page.locator("h2:has-text('Regime Dashboard')"),
    ).toBeVisible();
    // Navigate to Opportunities
    await nav.locator('a[href="/opportunities"]').click();
    await expect(page).toHaveURL("/opportunities");
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Market Opportunities",
    );
    // Navigate to Conviction
    await nav.locator('a[href="/conviction"]').click();
    await expect(page).toHaveURL("/conviction");
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Conviction Dashboard",
    );
  });

  test("market analysis page loads with chart controls", async ({ page }) => {
    await login(page);
    await page.goto("/market", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText(
      "Market Analysis",
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Symbol input, timeframe select, and exchange select should be present
    await expect(
      page.locator('input[placeholder="Symbol"]'),
    ).toBeVisible();
    // Indicator sections: Overlays and Panes
    await expect(page.locator("h3:has-text('Overlays')")).toBeVisible();
    await expect(page.locator("h3:has-text('Panes')")).toBeVisible();
  });

  test("market analysis indicator buttons toggle without crash", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/market", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Click an overlay indicator button (sma_21)
    const smaButton = page.locator(
      'button[aria-label="Toggle sma_21 indicator"]',
    );
    await expect(smaButton).toBeVisible({ timeout: 10_000 });
    await smaButton.click();
    // No crash
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Click a pane indicator (rsi_14)
    const rsiButton = page.locator(
      'button[aria-label="Toggle rsi_14 indicator"]',
    );
    await expect(rsiButton).toBeVisible();
    await rsiButton.click();
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("data management page loads with heading and controls", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/data", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText("Data");
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("regime API returns valid data for authenticated user", async ({
    page,
  }) => {
    await login(page);
    const response = await page.request.get(
      "/api/regime/current/?symbol=BTC/USDT",
    );
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("regime");
    expect(body).toHaveProperty("confidence");
  });
});
