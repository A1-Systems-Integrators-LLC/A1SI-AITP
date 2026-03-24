import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Dashboard } from "../src/pages/Dashboard";
import { renderWithProviders, mockFetch } from "./helpers";

vi.mock("../src/components/PriceChart", () => ({
  PriceChart: ({ data }: { data: unknown[] }) => (
    <div data-testid="price-chart">Chart ({data.length} bars)</div>
  ),
}));

const mockKPIs = {
  portfolio: { count: 3, total_value: 50000, total_cost: 40000, unrealized_pnl: 10000, pnl_pct: 25 },
  trading: { total_trades: 15, win_rate: 60, total_pnl: 1500, profit_factor: 2.5, open_orders: 2, total_orders: 200, rejected_orders: 20, filled_orders: 170, rejection_rate: 10.0 },
  risk: { equity: 10000, drawdown: 0.05, daily_pnl: 125.50, is_halted: false, open_positions: 2 },
  platform: { data_files: 12, active_jobs: 1, framework_count: 7 },
  system_health: { scheduler_running: true, last_data_refresh: "2026-02-24T12:00:00Z", freqtrade_instances: [], active_tasks: 35, total_jobs_completed: 10000, total_jobs_failed: 5 },
  activity_feed: [],
  learning_status: { ml_accuracy: 55.0, ml_predictions_total: 100, ml_models_count: 1, ml_last_trained: null, signal_attributions: 0, orchestrator_states: [] },
  generated_at: "2026-02-24T12:00:00Z",
};

const mockPlatformStatus = {
  frameworks: [
    { name: "VectorBT", installed: true, version: "0.28.4" },
    { name: "CCXT", installed: true, version: "4.5.40" },
    { name: "Pandas", installed: true, version: "2.3.3" },
    { name: "TA-Lib", installed: true, version: "0.6.4" },
  ],
  data_files: 12,
  active_jobs: 1,
};

const defaultHandlers = {
  "/api/dashboard/kpis": mockKPIs,
  "/api/platform/status": mockPlatformStatus,
  "/api/regime/current": [],
  "/api/jobs": [],
  "/api/market/tickers": [],
  "/api/market/ohlcv": [],
  "/api/market/news/sentiment": { asset_class: "crypto", hours: 24, total_articles: 0, avg_score: 0, overall_label: "neutral", positive_count: 0, negative_count: 0, neutral_count: 0 },
  "/api/market/news": [],
  "/api/market/opportunities/summary": { total_active: 0, by_type: {}, top_opportunities: [], avg_score: 0 },
  "/api/market/daily-report": { generated_at: "", date: "", regime: {}, top_opportunities: [], data_coverage: {}, strategy_performance: {}, system_status: { days_paper_trading: 0, min_days_required: 14, readiness: "unknown", is_ready: false } },
};

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch(defaultHandlers));
});

describe("DashboardKPI", () => {
  it("renders portfolio count from KPI", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Portfolios")).toBeInTheDocument();
    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("renders daily P&L from KPI", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("$125.50")).toBeInTheDocument();
  });

  it("renders data files from KPI", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("12")).toBeInTheDocument();
  });

  it("passes asset_class to KPI endpoint", async () => {
    const fetchSpy = vi.fn(mockFetch(defaultHandlers));
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Dashboard />, { assetClass: "equity" });
    await screen.findByText("Dashboard");
    // Wait for KPI call
    await vi.waitFor(() => {
      const calls = fetchSpy.mock.calls.map(([url]: [string]) => url);
      expect(calls.some((u: string) => u.includes("dashboard/kpis") && u.includes("asset_class=equity"))).toBe(true);
    });
  });

  it("shows error on KPI failure", async () => {
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("dashboard/kpis")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch(defaultHandlers)(input, init);
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/Failed to load dashboard data/)).toBeInTheDocument();
  });

  it("KPI API calls correct URL", async () => {
    const fetchSpy = vi.fn(mockFetch(defaultHandlers));
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Dashboard />);
    await screen.findByText("Dashboard");
    await vi.waitFor(() => {
      const calls = fetchSpy.mock.calls.map(([url]: [string]) => url);
      expect(calls.some((u: string) => u.includes("/api/dashboard/kpis/"))).toBe(true);
    });
  });
});
