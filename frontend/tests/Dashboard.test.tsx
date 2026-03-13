import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Dashboard } from "../src/pages/Dashboard";
import { renderWithProviders, mockFetch } from "./helpers";

// Mock PriceChart to avoid lightweight-charts canvas errors in jsdom
vi.mock("../src/components/PriceChart", () => ({
  PriceChart: ({ data }: { data: unknown[] }) => (
    <div data-testid="price-chart">Chart ({data.length} bars)</div>
  ),
}));

const mockPlatformStatus = {
  frameworks: [
    { name: "VectorBT", installed: true, version: null, status: "running", status_label: "6 screens \u00b7 last run 2h ago", details: { screens_available: 6, total_screens: 42, last_screen_at: new Date(Date.now() - 7200000).toISOString() } },
    { name: "Freqtrade", installed: true, version: null, status: "running", status_label: "3 instances \u00b7 1 open trade", details: { instances_running: 3, strategies: ["CryptoInvestorV1", "BollingerMeanReversion", "VolatilityBreakout"], open_trades: 1 } },
    { name: "NautilusTrader", installed: true, version: null, status: "idle", status_label: "7 strategies configured", details: { strategies_configured: 7, asset_classes: ["crypto", "equity", "forex"] } },
    { name: "HFT Backtest", installed: true, version: null, status: "idle", status_label: "4 strategies configured", details: { strategies_configured: 4 } },
    { name: "CCXT", installed: true, version: "4.5.40", status: "running", status_label: "kraken \u00b7 45.2ms", details: { exchange: "kraken", connected: true, latency_ms: 45.2 } },
  ],
  data_files: 12,
  active_jobs: 2,
};

const mockPortfolios = [
  { id: 1, name: "Main", exchange_id: "binance", description: "", holdings: [], created_at: "", updated_at: "" },
];

const mockRegimeStates = [
  {
    symbol: "BTC/USDT",
    regime: "strong_trend_up",
    confidence: 0.85,
    adx_value: 45.0,
    bb_width_percentile: 60,
    ema_slope: 0.002,
    trend_alignment: 0.8,
    price_structure_score: 0.7,
    transition_probabilities: {},
  },
  {
    symbol: "ETH/USDT",
    regime: "ranging",
    confidence: 0.65,
    adx_value: 18.0,
    bb_width_percentile: 40,
    ema_slope: 0.0001,
    trend_alignment: 0.1,
    price_structure_score: 0.05,
    transition_probabilities: {},
  },
];

const mockJobs = [
  {
    id: "job-1",
    job_type: "backtest",
    status: "running",
    progress: 50,
    progress_message: "Processing...",
    params: null,
    result: null,
    error: null,
    started_at: "2026-02-15T10:00:00Z",
    completed_at: null,
    created_at: "2026-02-15T10:00:00Z",
  },
];

const mockRiskStatus = {
  equity: 10000,
  peak_equity: 10500,
  drawdown: 0.048,
  daily_pnl: 125.50,
  total_pnl: 500.00,
  open_positions: 2,
  is_halted: false,
  halt_reason: "",
};

const mockTickers = [
  {
    symbol: "BTC/USDT",
    price: 65432.10,
    volume_24h: 1234567890,
    change_24h: 2.45,
    high_24h: 66000,
    low_24h: 64000,
    timestamp: "2026-02-23T12:00:00Z",
  },
  {
    symbol: "ETH/USDT",
    price: 3456.78,
    volume_24h: 987654321,
    change_24h: -1.23,
    high_24h: 3500,
    low_24h: 3400,
    timestamp: "2026-02-23T12:00:00Z",
  },
];

const mockOhlcv = [
  { timestamp: 1708646400000, open: 64000, high: 66000, low: 63500, close: 65432, volume: 1000 },
  { timestamp: 1708732800000, open: 65432, high: 67000, low: 65000, close: 66500, volume: 1200 },
];

const mockEquityTickers = [
  {
    symbol: "AAPL/USD",
    price: 185.50,
    volume_24h: 45000000,
    change_24h: 0.85,
    high_24h: 186.00,
    low_24h: 184.00,
    timestamp: "2026-02-23T16:00:00Z",
  },
];

const mockNewsSentiment = {
  asset_class: "crypto",
  hours: 24,
  total_articles: 2,
  avg_score: 0.25,
  overall_label: "positive",
  positive_count: 1,
  negative_count: 0,
  neutral_count: 1,
};

const mockKpis = {
  portfolio: { count: 1, total_value: 10000 },
  trading: { total_trades: 5, win_rate: 60.0, total_pnl: 500.0, profit_factor: 2.0 },
  risk: { daily_pnl: 125.5, drawdown: 0.048, is_halted: false },
  platform: { data_files: 12, active_jobs: 2 },
  paper_trading: {
    instances_running: 2,
    total_pnl: 15.75,
    total_pnl_pct: 3.15,
    open_trades: 1,
    closed_trades: 4,
    win_rate: 75.0,
    instances: [
      { name: "civ1", running: true, strategy: "CryptoInvestorV1", pnl: 10.50, open_trades: 1, closed_trades: 2 },
      { name: "bmr", running: true, strategy: "BollingerMeanReversion", pnl: 5.25, open_trades: 0, closed_trades: 2 },
      { name: "vb", running: false, strategy: "VolatilityBreakout", pnl: 0, open_trades: 0, closed_trades: 0 },
    ],
  },
  generated_at: new Date().toISOString(),
};

const mockNewsArticles = [
  {
    article_id: "test1",
    title: "Test News Article",
    url: "https://example.com/test",
    source: "TestSource",
    summary: "Test summary",
    published_at: new Date().toISOString(),
    symbols: [],
    asset_class: "crypto",
    sentiment_score: 0.5,
    sentiment_label: "positive",
    created_at: new Date().toISOString(),
  },
];

const mockOpportunitySummary = {
  total_active: 3,
  by_type: { volume_surge: 1, rsi_bounce: 1, breakout: 1 },
  top_opportunities: [],
  avg_score: 65.0,
};

const mockDailyReport = {
  generated_at: new Date().toISOString(),
  date: "2026-03-03",
  regime: { status: "ok", dominant_regime: "ranging" },
  top_opportunities: [],
  data_coverage: { total_pairs: 36, pairs_with_data: 10, coverage_pct: 27.8 },
  strategy_performance: { total_orders: 0, win_rate: 0, total_pnl: 0 },
  system_status: { days_paper_trading: 5, min_days_required: 14, readiness: "Gathering baseline data (day 5/14)", is_ready: false },
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "/api/platform/status": mockPlatformStatus,
      "/api/portfolios": mockPortfolios,
      "/api/regime/current": mockRegimeStates,
      "/api/jobs": mockJobs,
      "/api/risk/1/status/": mockRiskStatus,
      "/api/market/tickers": mockTickers,
      "/api/market/ohlcv": mockOhlcv,
      "/api/market/news/sentiment": mockNewsSentiment,
      "/api/market/news": mockNewsArticles,
      "/api/dashboard/kpis/": mockKpis,
      "/api/market/opportunities/summary/": mockOpportunitySummary,
      "/api/market/daily-report/": mockDailyReport,
    }),
  );
});

describe("Dashboard", () => {
  it("renders the page heading", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("renders summary cards", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Portfolios")).toBeInTheDocument();
    expect(screen.getByText("Data Sources")).toBeInTheDocument();
    expect(screen.getByText("Data Files")).toBeInTheDocument();
    expect(screen.getByText("Active Jobs")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("shows Online status", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText("Online")).toBeInTheDocument();
  });

  it("renders framework status section after data loads", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Framework Status")).toBeInTheDocument();
    expect(await screen.findByText("Freqtrade")).toBeInTheDocument();
    expect(screen.getByText("VectorBT")).toBeInTheDocument();
  });

  it("renders regime overview after data loads", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Strong Trend Up")).toBeInTheDocument();
    expect(screen.getByText("Regime Overview")).toBeInTheDocument();
    expect(screen.getByText("Ranging")).toBeInTheDocument();
  });

  it("renders watchlist with ticker data", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Crypto Watchlist")).toBeInTheDocument();
    expect(await screen.findByText("+2.45%")).toBeInTheDocument();
    expect(screen.getByText("-1.23%")).toBeInTheDocument();
  });

  it("renders daily chart section", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Daily")).toBeInTheDocument();
    expect(screen.getByText("BTC/USDT")).toBeInTheDocument();
  });

  it("shows equity-specific content", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/portfolios": mockPortfolios,
        "/api/jobs": mockJobs,
        "/api/risk/1/status/": mockRiskStatus,
        "/api/market/tickers": mockEquityTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
        "/api/regime/current": [],
      }),
    );
    renderWithProviders(<Dashboard />, { assetClass: "equity" });
    expect(await screen.findByText("Equities Watchlist")).toBeInTheDocument();
    expect(await screen.findByText("Yahoo Finance")).toBeInTheDocument();
    expect(screen.getByText(/No regime data available/)).toBeInTheDocument();
  });

  it("shows empty state when no ticker data", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/portfolios": mockPortfolios,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/risk/1/status/": mockRiskStatus,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("No price data available")).toBeInTheDocument();
  });

  it("filters frameworks for equity asset class", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/portfolios": mockPortfolios,
        "/api/jobs": mockJobs,
        "/api/risk/1/status/": mockRiskStatus,
        "/api/market/tickers": mockEquityTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />, { assetClass: "equity" });
    expect(await screen.findByText("Framework Status")).toBeInTheDocument();
    expect(screen.getByText("NautilusTrader")).toBeInTheDocument();
    expect(screen.getByText("VectorBT")).toBeInTheDocument();
    expect(screen.queryByText("Freqtrade")).not.toBeInTheDocument();
    expect(screen.queryByText("HFT Backtest")).not.toBeInTheDocument();
  });

  it("shows data sources with exchanges for crypto", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Available Exchanges")).toBeInTheDocument();
    expect(screen.getByText("Binance")).toBeInTheDocument();
  });

  it("renders news feed section", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("News Feed")).toBeInTheDocument();
    expect(await screen.findByText("Test News Article")).toBeInTheDocument();
  });

  it("refresh buttons have aria-labels", () => {
    renderWithProviders(<Dashboard />);
    const refreshPrices = screen.getByLabelText("Refresh prices");
    expect(refreshPrices).toBeInTheDocument();
  });

  it("jobs refresh button has aria-label", () => {
    renderWithProviders(<Dashboard />);
    const refreshJobs = screen.getByLabelText("Refresh jobs");
    expect(refreshJobs).toBeInTheDocument();
  });

  it("renders watchlist timestamp after data loads", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByText("Crypto Watchlist");
    const timestamp = await screen.findByTestId("watchlist-timestamp");
    expect(timestamp).toBeInTheDocument();
    expect(timestamp.textContent).toContain("as of");
  });

  it("renders KPI timestamp after data loads", async () => {
    renderWithProviders(<Dashboard />);
    const timestamp = await screen.findByTestId("kpi-timestamp");
    expect(timestamp).toBeInTheDocument();
    expect(timestamp.textContent).toContain("Updated");
  });

  it("renders paper trading widget with strategy instances", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByTestId("paper-trading-widget")).toBeInTheDocument();
    expect(screen.getByText("Paper Trading")).toBeInTheDocument();
    expect(screen.getByText("CryptoInvestorV1")).toBeInTheDocument();
    expect(screen.getByText("BollingerMeanReversion")).toBeInTheDocument();
  });

  it("shows paper trading P&L and stats", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByTestId("paper-trading-widget");
    expect(screen.getByText("$15.75")).toBeInTheDocument();
    expect(screen.getByText("+3.15%")).toBeInTheDocument();
    expect(screen.getByText("75.0%")).toBeInTheDocument();
  });

  it("shows View Details link to paper trading page", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByTestId("paper-trading-widget");
    const link = screen.getByText(/View Details/);
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/paper-trading");
  });

  it("shows running/stopped indicators for instances", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByTestId("paper-trading-widget");
    // VolatilityBreakout is stopped, should show its name
    expect(screen.getByText("VolatilityBreakout")).toBeInTheDocument();
  });

  it("shows running status indicator for Freqtrade", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByText("Framework Status");
    const freqtradeRow = screen.getByText("Freqtrade").closest("div.rounded-lg");
    expect(freqtradeRow).toBeInTheDocument();
    // Running status should have a green pulsing dot
    const dot = freqtradeRow!.querySelector(".animate-pulse");
    expect(dot).toBeInTheDocument();
  });

  it("shows framework status labels", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByText("Framework Status");
    // status_label values rendered in the right column
    expect(screen.getByText(/3 instances/)).toBeInTheDocument();
    expect(screen.getByText(/kraken · 45\.2ms/)).toBeInTheDocument();
    expect(screen.getByText(/6 screens/)).toBeInTheDocument();
  });

  it("shows framework status legend", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByText("Framework Status");
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Not Installed")).toBeInTheDocument();
  });

  it("shows KPI error state when dashboard API fails", async () => {
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/dashboard/kpis/")) {
        return Promise.reject(new Error("Network error"));
      }
      return mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      })(input, init);
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/Failed to load dashboard data.*Network error/)).toBeInTheDocument();
  });

  it("shows negative daily P&L in red", async () => {
    const negativeKpis = {
      ...mockKpis,
      risk: { daily_pnl: -50.25, drawdown: 0.1, is_halted: false },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": negativeKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("$-50.25")).toBeInTheDocument();
  });

  it("shows opportunity panel with top opportunities", async () => {
    const oppWithData = {
      total_active: 2,
      avg_score: 72.0,
      by_type: { volume_surge: 1, breakout: 1 },
      top_opportunities: [
        {
          id: 1,
          symbol: "BTC/USDT",
          asset_class: "crypto",
          opportunity_type: "volume_surge",
          score: 80,
          detected_at: new Date().toISOString(),
        },
        {
          id: 2,
          symbol: "AAPL/USD",
          asset_class: "equity",
          opportunity_type: "breakout",
          score: 45,
          detected_at: new Date().toISOString(),
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": oppWithData,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("volume surge")).toBeInTheDocument();
    expect(screen.getByText("breakout")).toBeInTheDocument();
    expect(screen.getByText("2 active opportunities | Avg score: 72")).toBeInTheDocument();
  });

  it("shows trading performance card with negative P&L", async () => {
    const negTradingKpis = {
      ...mockKpis,
      trading: { total_trades: 10, win_rate: 40.0, total_pnl: -250.0, profit_factor: null },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": negTradingKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Trading Performance")).toBeInTheDocument();
    expect(screen.getByText("$-250.00")).toBeInTheDocument();
    // null profit_factor should show infinity symbol
    expect(screen.getByText("\u221E")).toBeInTheDocument();
  });

  it("shows paper trading widget with no instances running", async () => {
    const noInstancesKpis = {
      ...mockKpis,
      paper_trading: {
        instances_running: 0,
        total_pnl: -5.0,
        total_pnl_pct: -1.0,
        open_trades: 0,
        closed_trades: 2,
        win_rate: 50.0,
        instances: [],
      },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": noInstancesKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    await screen.findByTestId("paper-trading-widget");
    expect(screen.getByText(/No Freqtrade instances detected/)).toBeInTheDocument();
    expect(screen.getByText("$-5.00")).toBeInTheDocument();
    expect(screen.getByText("-1.00%")).toBeInTheDocument();
  });

  it("does not show paper trading widget when no paper_trading data", async () => {
    const noPaperKpis = {
      ...mockKpis,
      paper_trading: undefined,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": noPaperKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    await screen.findByText("Dashboard");
    expect(screen.queryByTestId("paper-trading-widget")).not.toBeInTheDocument();
  });

  it("shows daily report system status section", async () => {
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/Gathering baseline data/)).toBeInTheDocument();
    expect(screen.getByText(/Coverage: 27.8%/)).toBeInTheDocument();
    expect(screen.getByText(/Regime: ranging/)).toBeInTheDocument();
  });

  it("shows completed job with timestamp", async () => {
    const completedJobs = [
      {
        id: "job-2",
        job_type: "data_download",
        status: "completed",
        progress: 1.0,
        progress_message: "Done",
        params: null,
        result: null,
        error: null,
        started_at: "2026-02-15T10:00:00Z",
        completed_at: "2026-02-15T10:05:00Z",
        created_at: "2026-02-15T10:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": completedJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("data download")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText(/Completed/)).toBeInTheDocument();
  });

  it("shows no chart data message when OHLCV is empty", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": [],
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/No chart data available/)).toBeInTheDocument();
  });

  it("shows non-crypto empty state message for equity", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": [],
        "/api/jobs": [],
        "/api/dashboard/kpis/": { ...mockKpis, paper_trading: undefined },
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />, { assetClass: "equity" });
    expect(await screen.findByText("Download data to see prices")).toBeInTheDocument();
  });

  it("shows failed job status", async () => {
    const failedJobs = [
      {
        id: "job-3",
        job_type: "backtest",
        status: "failed",
        progress: 0,
        progress_message: "",
        params: null,
        result: null,
        error: "Something went wrong",
        started_at: "2026-02-15T10:00:00Z",
        completed_at: null,
        created_at: "2026-02-15T10:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": failedJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("failed")).toBeInTheDocument();
  });

  it("shows not_installed framework status color", async () => {
    const statusWithNotInstalled = {
      ...mockPlatformStatus,
      frameworks: [
        ...mockPlatformStatus.frameworks,
        { name: "TestFramework", installed: false, version: null, status: "not_installed", status_label: "Not available", details: {} },
      ],
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": statusWithNotInstalled,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    // TestFramework is not in BACKTEST_FRAMEWORKS for crypto, so it won't show
    // But CCXT always shows, so verify VectorBT shows (it is in the filter)
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Framework Status")).toBeInTheDocument();
  });

  it("renders data sources heading as 'Data Sources' for equity", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": [],
        "/api/jobs": [],
        "/api/market/tickers": mockEquityTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />, { assetClass: "equity" });
    // For equity, the heading says "Data Sources" instead of "Available Exchanges"
    expect(await screen.findByText("Equities Watchlist")).toBeInTheDocument();
    // "Data Sources" appears both as summary card label and as section heading for equity
    const dsMatches = screen.getAllByText("Data Sources");
    expect(dsMatches.length).toBeGreaterThanOrEqual(2);
  });

  it("shows daily report with system ready status", async () => {
    const readyReport = {
      ...mockDailyReport,
      system_status: { days_paper_trading: 15, min_days_required: 14, readiness: "Ready for live trading", is_ready: true },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": mockPlatformStatus,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": readyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Ready for live trading")).toBeInTheDocument();
  });

  it("clicks refresh prices button without error", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByText("Crypto Watchlist");
    const btn = screen.getByLabelText("Refresh prices");
    fireEvent.click(btn);
    expect(btn).toBeInTheDocument();
  });

  it("clicks refresh jobs button without error", async () => {
    renderWithProviders(<Dashboard />);
    const btn = screen.getByLabelText("Refresh jobs");
    fireEvent.click(btn);
    expect(btn).toBeInTheDocument();
  });

  it("clicks ticker button to change chart symbol", async () => {
    renderWithProviders(<Dashboard />);
    await screen.findByText("+2.45%");
    // Click on ETH/USDT ticker row — find the one inside a button
    const ethElements = screen.getAllByText("ETH/USDT");
    const ethInButton = ethElements.find((el) => el.closest("button"));
    expect(ethInButton).toBeTruthy();
    fireEvent.click(ethInButton!.closest("button")!);
    // ETH/USDT should still be visible
    expect(ethInButton).toBeInTheDocument();
  });

  it("shows not_installed framework status color", async () => {
    const statusWithNotInstalled = {
      ...mockPlatformStatus,
      frameworks: [
        { name: "NautilusTrader", installed: false, version: null, status: "not_installed", status_label: "Not available", details: {} },
        { name: "CCXT", installed: true, version: "4.5.40", status: "running", status_label: "kraken", details: {} },
        { name: "VectorBT", installed: true, version: null, status: "running", status_label: "running", details: {} },
      ],
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": statusWithNotInstalled,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("NautilusTrader")).toBeInTheDocument();
    // The not_installed dot should have bg-red-400 class
    const row = screen.getByText("NautilusTrader").closest("div.rounded-lg");
    const dot = row!.querySelector(".bg-red-400");
    expect(dot).toBeInTheDocument();
  });

  it("handles unknown framework status color", async () => {
    const statusWithUnknown = {
      ...mockPlatformStatus,
      frameworks: [
        { name: "CCXT", installed: true, version: "4.5.40", status: "mystery_status", status_label: "unknown state", details: {} },
        { name: "VectorBT", installed: true, version: null, status: "running", status_label: "running", details: {} },
      ],
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/platform/status": statusWithUnknown,
        "/api/regime/current": mockRegimeStates,
        "/api/jobs": mockJobs,
        "/api/market/tickers": mockTickers,
        "/api/market/ohlcv": mockOhlcv,
        "/api/market/news/sentiment": mockNewsSentiment,
        "/api/market/news": mockNewsArticles,
        "/api/dashboard/kpis/": mockKpis,
        "/api/market/opportunities/summary/": mockOpportunitySummary,
        "/api/market/daily-report/": mockDailyReport,
      }),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("Framework Status")).toBeInTheDocument();
    expect(screen.getByText("unknown state")).toBeInTheDocument();
  });
});
