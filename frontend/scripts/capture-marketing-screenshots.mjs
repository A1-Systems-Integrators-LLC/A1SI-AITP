/**
 * Marketing screenshot capture for the AITP web dashboard.
 *
 * Drives the running prod frontend with Playwright/Chromium at HD (1920x1080),
 * logging in and capturing every route. Pages taller than the viewport also get
 * viewport-sized section captures so long pages can be used piecewise on the
 * marketing site.
 *
 * Usage:
 *   cd frontend && node scripts/capture-marketing-screenshots.mjs
 *
 * Chromium's system libs are not installed on the WSL host, so this is normally
 * run inside mcr.microsoft.com/playwright — see marketing/README.md.
 *
 * Env:
 *   BASE_URL   default http://localhost:4101
 *   OUT_DIR    default <repo>/marketing/screenshots
 *   USERNAME   default admin
 *   PASSWORD   default admin
 */
import { chromium } from "@playwright/test";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";

const BASE_URL = process.env.BASE_URL || "http://localhost:4101";
const OUT_DIR =
  process.env.OUT_DIR ||
  path.resolve(import.meta.dirname, "..", "..", "marketing", "screenshots");
const USERNAME = process.env.USERNAME || "admin";
const PASSWORD = process.env.PASSWORD || "admin";

const WIDTH = 1920;
const HEIGHT = 1080;

/** Routes in sidebar order; labels mirror Layout.tsx nav items. */
const ROUTES = [
  { path: "/", slug: "dashboard", label: "Dashboard" },
  { path: "/portfolio", slug: "portfolio", label: "Portfolio" },
  { path: "/market", slug: "market-analysis", label: "Market" },
  { path: "/trading", slug: "trading", label: "Trading" },
  { path: "/data", slug: "data-management", label: "Data" },
  { path: "/screening", slug: "screening", label: "Screening" },
  { path: "/risk", slug: "risk-management", label: "Risk" },
  { path: "/regime", slug: "regime", label: "Regime" },
  { path: "/backtest", slug: "backtesting", label: "Backtest" },
  { path: "/paper-trading", slug: "paper-trading", label: "Paper Trade" },
  { path: "/ml", slug: "ml-models", label: "ML Models" },
  { path: "/scheduler", slug: "scheduler", label: "Scheduler" },
  { path: "/workflows", slug: "workflows", label: "Workflows" },
  { path: "/opportunities", slug: "opportunities", label: "Opportunities" },
  { path: "/conviction", slug: "conviction", label: "Conviction" },
  { path: "/reports", slug: "reports", label: "Reports" },
  { path: "/settings", slug: "settings", label: "Settings" },
];

/**
 * Layout.tsx persists the theme under this key and mirrors it onto
 * <html data-theme>. Login renders outside Layout, so the attribute has to be
 * set by hand there.
 */
const THEME = process.env.THEME || "light";

/** Kill animations/carets and hide scrollbars so captures are deterministic. */
const STABILIZE_CSS = `
  *, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
    caret-color: transparent !important;
  }
  html { scrollbar-width: none !important; }
  ::-webkit-scrollbar { width: 0 !important; height: 0 !important; }
`;

/**
 * Layout renders `<main role="main" class="flex-1 overflow-auto">` inside a
 * `h-screen` flex box, so the document itself never scrolls — the page content
 * scrolls inside <main>. Everything below measures/scrolls that element, not
 * window, and falls back to the document for the login page (no Layout).
 */
const SCROLLER = 'main[role="main"]';

async function scrollerMetrics(page) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) {
      const d = document.documentElement;
      return { inner: false, scrollHeight: d.scrollHeight, clientHeight: d.clientHeight };
    }
    return { inner: true, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
  }, SCROLLER);
}

async function scrollTo(page, top) {
  await page.evaluate(
    ([sel, y]) => {
      const el = document.querySelector(sel);
      if (el) el.scrollTop = y;
      else window.scrollTo(0, y);
    },
    [SCROLLER, top],
  );
}

/**
 * App.tsx renders a bare "Loading…" PageLoader while the auth check is in
 * flight and while a lazy route chunk loads. Capturing that is worthless, so
 * block until the real page (its <main>) is mounted.
 */
async function waitForAppReady(page, timeout = 45000) {
  await page.locator(SCROLLER).waitFor({ state: "attached", timeout });
  await page.locator(`${SCROLLER} h1, ${SCROLLER} h2`).first().waitFor({
    state: "visible",
    timeout,
  });
}

/**
 * A lazily-imported route chunk occasionally fails to resolve, leaving the
 * Suspense fallback up forever. One hard reload clears it.
 */
async function waitForAppReadyOrReload(page, routePath) {
  try {
    await waitForAppReady(page);
  } catch {
    process.stdout.write("   (stuck on loader — reloading)\n");
    await page.goto(`${BASE_URL}${routePath}`, { waitUntil: "domcontentloaded" });
    await page.addStyleTag({ content: STABILIZE_CSS });
    await waitForAppReady(page, 90000);
  }
}

async function settle(page, extraMs = 3000) {
  try {
    await page.waitForLoadState("networkidle", { timeout: 15000 });
  } catch {
    // Polling/websocket traffic can keep the network busy; not fatal.
  }
  // Wait out loading skeletons if any are still mounted.
  try {
    await page
      .locator('[class*="animate-pulse"], [data-testid*="skeleton"]')
      .first()
      .waitFor({ state: "detached", timeout: 20000 });
  } catch {
    // No skeleton, or a slow endpoint never resolves — proceed either way.
  }
  await page.waitForTimeout(extraMs);
}

async function capture(page, slug, index) {
  const prefix = String(index).padStart(2, "0");
  const results = [];

  await scrollTo(page, 0);
  await page.waitForTimeout(300);

  // Above-the-fold hero shot at exactly 1920x1080.
  const heroPath = path.join(OUT_DIR, `${prefix}-${slug}-hero.png`);
  await page.screenshot({ path: heroPath, fullPage: false });
  results.push(path.basename(heroPath));

  const { scrollHeight } = await scrollerMetrics(page);

  // Chromium can't rasterise beyond ~16k px; clamp so tall pages still render.
  const fullHeight = Math.min(Math.max(scrollHeight, HEIGHT), 16000);

  // A whole-page shot: grow the viewport so <main> has nothing left to scroll,
  // which also stretches the sidebar to the full image height.
  const fullPath = path.join(OUT_DIR, `${prefix}-${slug}-full.png`);
  if (fullHeight > HEIGHT) {
    await page.setViewportSize({ width: WIDTH, height: fullHeight });
    await page.waitForTimeout(1200);
    await scrollTo(page, 0);
    await page.waitForTimeout(400);
  }
  await page.screenshot({ path: fullPath, fullPage: false });
  results.push(path.basename(fullPath));

  if (fullHeight > HEIGHT) {
    await page.setViewportSize({ width: WIDTH, height: HEIGHT });
    await page.waitForTimeout(800);
  }

  // Slice pages meaningfully taller than one viewport into HD sections.
  if (scrollHeight > HEIGHT * 1.25) {
    const maxScroll = scrollHeight - HEIGHT;
    const sectionCount = Math.ceil(scrollHeight / HEIGHT);
    for (let i = 0; i < sectionCount; i++) {
      const y = Math.min(i * HEIGHT, maxScroll);
      await scrollTo(page, y);
      await page.waitForTimeout(700);
      const sectionPath = path.join(
        OUT_DIR,
        `${prefix}-${slug}-section-${String(i + 1).padStart(2, "0")}.png`,
      );
      await page.screenshot({ path: sectionPath, fullPage: false });
      results.push(path.basename(sectionPath));
      if (y >= maxScroll) break;
    }
    await scrollTo(page, 0);
  }

  return { slug, docHeight: scrollHeight, files: results };
}

async function main() {
  await rm(OUT_DIR, { recursive: true, force: true });
  await mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: 1,
    colorScheme: THEME,
  });
  await context.addInitScript((theme) => {
    localStorage.setItem("ci:theme", JSON.stringify(theme));
    document.documentElement.setAttribute("data-theme", theme);
  }, THEME);
  const page = await context.newPage();

  const manifest = [];

  // --- Login page (captured unauthenticated) ---
  await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({ content: STABILIZE_CSS });
  await settle(page, 1500);
  manifest.push(await capture(page, "login", 0));

  // --- Authenticate ---
  await page.fill("#username", USERNAME);
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 30000,
  });
  await waitForAppReady(page);
  await settle(page, 3000);

  await page.addStyleTag({ content: STABILIZE_CSS });

  // --- Authenticated routes ---
  // Navigate by clicking the sidebar rather than page.goto(): a hard reload
  // re-bootstraps the SPA and re-fires every dashboard query, which reliably
  // saturates Daphne and leaves the backend wedged part-way through a run.
  for (const [i, route] of ROUTES.entries()) {
    process.stdout.write(`→ ${route.path} (${route.label})\n`);
    if (page.url().replace(BASE_URL, "") !== route.path) {
      await page.click(`a[href="${route.path}"]`);
      await page.waitForURL(`**${route.path}`, { timeout: 30000 });
    }
    await waitForAppReadyOrReload(page, route.path);
    await settle(page);
    // Blur any auto-focused control so no focus ring lands in the shot.
    await page.evaluate(() => document.activeElement?.blur?.());
    const result = await capture(page, route.slug, i + 1);
    result.label = route.label;
    result.route = route.path;
    manifest.push(result);
    process.stdout.write(
      `   height=${result.docHeight}px files=${result.files.length}\n`,
    );
  }

  await browser.close();

  process.stdout.write(`\n=== MANIFEST (${OUT_DIR}) ===\n`);
  let total = 0;
  for (const m of manifest) {
    total += m.files.length;
    process.stdout.write(
      `${(m.label || "Login").padEnd(16)} ${String(m.docHeight).padStart(6)}px  ${m.files.join(", ")}\n`,
    );
  }
  process.stdout.write(`\nTotal files: ${total}\n`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
