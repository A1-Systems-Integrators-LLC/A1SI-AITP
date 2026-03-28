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

test.describe("Portfolio management flows", () => {
  test("portfolio page loads with heading and create button", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    await expect(page.locator("#page-heading")).toContainText("Portfolio");
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Create Portfolio button should be visible
    await expect(
      page.locator('button:has-text("Create Portfolio")'),
    ).toBeVisible();
  });

  test("portfolio list renders portfolios or empty state", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Either portfolio cards or the empty state message should be visible
    const hasPortfolios = await page
      .locator("text=No portfolios yet")
      .isVisible()
      .catch(() => false);
    if (hasPortfolios) {
      await expect(
        page.locator("text=No portfolios yet. Create one to get started."),
      ).toBeVisible();
    } else {
      // At least one portfolio card with a name should render
      const portfolioCards = page.locator(
        ".rounded-xl.border h3.text-lg.font-semibold",
      );
      await expect(portfolioCards.first()).toBeVisible({ timeout: 10_000 });
    }
  });

  test("portfolio detail shows holdings table when holdings exist", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // If portfolios exist with holdings, the HoldingsTable renders a table
    const holdingsTable = page.locator("table");
    const hasTable = await holdingsTable
      .first()
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    if (hasTable) {
      // Holdings table should have Symbol header column
      await expect(
        page.locator("th:has-text('Symbol')").first(),
      ).toBeVisible();
    }
    // Page should not crash regardless
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("allocation breakdown toggle renders when holdings present", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Look for the Show Allocation Breakdown button
    const allocationButton = page.locator(
      'button:has-text("Show Allocation Breakdown")',
    );
    const hasButton = await allocationButton
      .first()
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    if (hasButton) {
      await allocationButton.first().click();
      // After clicking, the button text should change to "Hide"
      await expect(
        page.locator('button:has-text("Hide Allocation Breakdown")').first(),
      ).toBeVisible({ timeout: 5_000 });
    }
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("portfolio summary cards show P&L metrics when holdings exist", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Summary stat cards: Total Value, Total Cost, Unrealized P&L, P&L %
    const totalValueLabel = page.locator("text=Total Value");
    const hasStats = await totalValueLabel
      .first()
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    if (hasStats) {
      await expect(
        page.locator("text=Total Cost").first(),
      ).toBeVisible();
      await expect(
        page.locator("text=Unrealized P&L").first(),
      ).toBeVisible();
      await expect(page.locator("text=P&L %").first()).toBeVisible();
    }
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("create portfolio form opens and validates", async ({ page }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // Open create form
    await page.click('button:has-text("Create Portfolio")');
    // Form fields should be visible
    await expect(page.locator("#portfolio-name")).toBeVisible();
    await expect(page.locator("#portfolio-exchange")).toBeVisible();
    await expect(page.locator("#portfolio-desc")).toBeVisible();
    // The Create submit button should be disabled when name is empty
    const createButton = page.locator(
      "button:has-text('Create'):not(:has-text('Portfolio'))",
    );
    await expect(createButton).toBeDisabled();
    // Cancel hides the form
    await page.click('button:has-text("Cancel")');
    await expect(page.locator("#portfolio-name")).not.toBeVisible();
  });

  test("navigate to portfolio from dashboard sidebar", async ({ page }) => {
    await login(page);
    // Start on dashboard
    await expect(page.locator("#page-heading")).toContainText("Dashboard");
    // Click Portfolio link in sidebar
    const nav = page.locator('nav[aria-label="Main navigation"]');
    await nav.locator('a[href="/portfolio"]').click();
    await expect(page).toHaveURL("/portfolio");
    await expect(page.locator("#page-heading")).toContainText("Portfolio");
  });

  test("portfolio page has edit and delete buttons on portfolio cards", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await waitForPageLoad(page);
    // If portfolios exist, each card should have Edit and Delete buttons
    const editButton = page.locator('button:has-text("Edit")');
    const hasEdit = await editButton
      .first()
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    if (hasEdit) {
      await expect(editButton.first()).toBeVisible();
      await expect(
        page.locator('button:has-text("Delete")').first(),
      ).toBeVisible();
    }
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });
});
