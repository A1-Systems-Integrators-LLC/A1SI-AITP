import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
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
    { name: "VectorBT", installed: true, version: "0.28.4" },
    { name: "Freqtrade", installed: true, version: "2026.1" },
    { name: "NautilusTrader", installed: true, version: "configured" },
    { name: "HFT Backtest", installed: true, version: "configured" },
    { name: "CCXT", installed: true, version: "4.5.40" },
    { name: "Pandas", installed: true, version: "2.3.3" },
    { name: "TA-Lib", installed: true, version: "0.6.4" },
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
    expect(await screen.findByText("Regime Overview")).toBeInTheDocument();
    expect(screen.getByText("Strong Trend Up")).toBeInTheDocument();
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
      }),
    );
    renderWithProviders(<Dashboard />, { assetClass: "equity" });
    expect(await screen.findByText("Equities Watchlist")).toBeInTheDocument();
    expect(await screen.findByText("Yahoo Finance")).toBeInTheDocument();
    expect(screen.getByText(/not yet available/)).toBeInTheDocument();
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
});
