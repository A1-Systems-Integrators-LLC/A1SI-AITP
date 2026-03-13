import { test, expect, type Page } from "@playwright/test";

/**
 * Helper: log in via the session-based auth form.
 * Login form uses id="username" and id="password" inputs with a submit button.
 */
async function login(page: Page) {
  await page.goto("/login");
  await page.fill("#username", "admin");
  await page.fill("#password", "admin");
  await page.click('button[type="submit"]');
  // Wait for authenticated layout to render (sidebar nav appears after login)
  await page.waitForSelector('nav[aria-label="Main navigation"]', {
    timeout: 30_000,
  });
}

test.describe("Smoke tests", () => {
  test("login with valid credentials redirects to dashboard", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.fill("#username", "admin");
    await page.fill("#password", "admin");
    await page.click('button[type="submit"]');
    // Sidebar nav should show "Dashboard" link (confirms auth + redirect)
    await expect(page.locator('nav[aria-label="Main navigation"]')).toBeVisible();
    await expect(page.locator("text=Dashboard")).toBeVisible();
  });

  test("login with invalid credentials shows error", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#username", "wrong");
    await page.fill("#password", "wrong");
    await page.click('button[type="submit"]');
    // Should stay on login page and show error message
    await expect(page).toHaveURL("/login");
    await expect(
      page.locator(".text-red-400, .bg-red-500\\/10")
    ).toBeVisible();
  });

  test("dashboard loads with page heading", async ({ page }) => {
    await login(page);
    await expect(page.locator("#page-heading")).toBeVisible();
    await expect(page.locator("#page-heading")).toContainText("Dashboard");
  });

  test("navigate all pages without crash", async ({ page }) => {
    test.slow(); // Triple timeout — 14 routes with potentially slow API calls in CI
    await login(page);
    // Routes from App.tsx router config
    const routes = [
      "/",
      "/portfolio",
      "/market",
      "/trading",
      "/data",
      "/screening",
      "/risk",
      "/regime",
      "/backtest",
      "/paper-trading",
      "/ml",
      "/scheduler",
      "/workflows",
      "/opportunities",
      "/conviction",
      "/settings",
    ];
    for (const route of routes) {
      await page.goto(route, { waitUntil: "domcontentloaded" });
      // Wait briefly for lazy-loaded page to render (Suspense fallback)
      await page.waitForFunction(
        () => !document.querySelector("main")?.textContent?.includes("Loading..."),
        { timeout: 10_000 },
      );
      // No error boundary should be visible
      await expect(
        page.locator("text=Something went wrong")
      ).not.toBeVisible();
    }
  });

  test("sidebar navigation links work", async ({ page }) => {
    await login(page);
    const nav = page.locator('nav[aria-label="Main navigation"]');
    // Click Portfolio link in nav
    await nav.locator('a[href="/portfolio"]').click();
    await expect(page).toHaveURL("/portfolio");
    await expect(page.locator("#page-heading")).toContainText("Portfolio");
    // Click Trading link in nav
    await nav.locator('a[href="/trading"]').click();
    await expect(page).toHaveURL("/trading");
    await expect(page.locator("#page-heading")).toContainText("Trading");
  });

  test("theme toggle switches and persists across reload", async ({
    page,
  }) => {
    await login(page);
    // Default theme is "dark" (from useLocalStorage default)
    const initialTheme = await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme")
    );
    // ThemeToggle aria-label is "Switch to light mode" when dark, "Switch to dark mode" when light
    const themeToggle = page.locator(
      'button[aria-label="Switch to light mode"], button[aria-label="Switch to dark mode"]'
    );
    await expect(themeToggle).toBeVisible();
    await themeToggle.click();
    // Theme should have changed
    const newTheme = await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme")
    );
    expect(newTheme).not.toBe(initialTheme);
    // Reload and verify persistence (localStorage key "ci:theme")
    await page.reload();
    await page.waitForLoadState("networkidle");
    const themeAfterReload = await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme")
    );
    expect(themeAfterReload).toBe(newTheme);
  });

  test("asset class selector updates context", async ({ page }) => {
    test.slow(); // Asset class switches trigger API refetches that may be slow in CI
    await login(page);
    // AssetClassSelector renders buttons with text "Crypto", "Equities", "Forex"
    const equitiesButton = page.locator("button", { hasText: "Equities" });
    await expect(equitiesButton).toBeVisible();
    await equitiesButton.click();
    // After click, the Equities button should have the active style (bg-primary)
    // Verify no crash
    await expect(
      page.locator("text=Something went wrong")
    ).not.toBeVisible();
    // Switch to Forex
    const forexButton = page.locator("button", { hasText: "Forex" });
    await forexButton.click();
    await expect(
      page.locator("text=Something went wrong")
    ).not.toBeVisible();
    // Switch back to Crypto
    const cryptoButton = page.locator("button", { hasText: "Crypto" });
    await cryptoButton.click();
    await expect(
      page.locator("text=Something went wrong")
    ).not.toBeVisible();
  });

  test("create portfolio flow", async ({ page }) => {
    await login(page);
    await page.goto("/portfolio");
    // Click "Create Portfolio" button
    await page.click("button:has-text('Create Portfolio')");
    // Fill the create form (id="portfolio-name")
    await page.fill("#portfolio-name", "E2E Test Portfolio");
    // Submit via "Create" button inside the form
    await page.click("button:has-text('Create'):not(:has-text('Portfolio'))");
    // Should see the new portfolio name rendered
    await expect(page.locator("text=E2E Test Portfolio")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("logout returns to login page", async ({ page }) => {
    await login(page);
    // Sign out button has aria-label="Sign out"
    const signOutButton = page.locator('button[aria-label="Sign out"]');
    await expect(signOutButton).toBeVisible();
    await signOutButton.click();
    await expect(page).toHaveURL(/\/login/);
    // Login form should be visible again
    await expect(page.locator("#username")).toBeVisible();
  });
});
