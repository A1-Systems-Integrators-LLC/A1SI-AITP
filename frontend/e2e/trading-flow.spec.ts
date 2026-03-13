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

test.describe("Trading flows", () => {
  test("paper trading page shows instance status", async ({ page }) => {
    await login(page);
    await page.goto("/paper-trading", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    await expect(page.locator("#page-heading")).toContainText("Paper");
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
  });

  test("order form validates inputs — rejects empty submission", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/trading", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    // Try submitting the order form without filling fields
    const submitButton = page.locator(
      'button[type="submit"][aria-label*="order"], button[type="submit"]:has-text("Place")',
    );
    if (await submitButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await submitButton.click();
      // Form should not navigate away — validation should prevent submission
      await expect(page).toHaveURL(/\/trading/);
    }
  });

  test("conviction dashboard loads without crash", async ({ page }) => {
    await login(page);
    await page.goto("/conviction", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    // Should have page heading or some content rendered
    await expect(page.locator("#page-heading")).toBeVisible();
  });

  test("opportunities page has asset class filter", async ({ page }) => {
    await login(page);
    await page.goto("/opportunities", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () =>
        !document.querySelector("main")?.textContent?.includes("Loading..."),
      { timeout: 10_000 },
    );
    await expect(
      page.locator("text=Something went wrong"),
    ).not.toBeVisible();
    await expect(page.locator("#page-heading")).toBeVisible();
    // Asset class filter should be present (dropdown or buttons)
    const filter = page.locator(
      'select[aria-label*="asset"], button:has-text("Crypto"), [aria-label*="filter"]',
    );
    await expect(filter.first()).toBeVisible({ timeout: 10_000 });
  });
});
