import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Backtesting } from "../src/pages/Backtesting";
import { renderWithProviders, mockFetch } from "./helpers";

const mockStrategies = [
  { name: "CryptoInvestorV1", framework: "freqtrade", file_path: "" },
  { name: "BollingerMeanReversion", framework: "freqtrade", file_path: "" },
];

const mockResults = [
  {
    id: 1,
    job_id: "abc-123",
    framework: "freqtrade",
    strategy_name: "CryptoInvestorV1",
    symbol: "BTC/USDT",
    timeframe: "1h",
    timerange: "20250101-20250201",
    metrics: {},
    trades: [],
    config: {},
    created_at: "2026-02-10T12:00:00Z",
  },
];

describe("Backtesting Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResults,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Backtesting />);
    expect(screen.getByText("Backtesting")).toBeInTheDocument();
  });

  it("renders configuration form", () => {
    renderWithProviders(<Backtesting />);
    expect(screen.getByText("Configuration")).toBeInTheDocument();
    expect(screen.getByText("Run Backtest")).toBeInTheDocument();
  });

  it("renders history table after data loads", async () => {
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("History")).toBeInTheDocument();
    const cells = await screen.findAllByText("CryptoInvestorV1");
    expect(cells.length).toBeGreaterThanOrEqual(1);
  });
});

describe("Backtesting - Configuration Form", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResults,
      }),
    );
  });

  it("renders strategy dropdown", () => {
    renderWithProviders(<Backtesting />);
    const strategySelect = document.getElementById("bt-strategy");
    expect(strategySelect).toBeInTheDocument();
  });

  it("renders symbol input", () => {
    renderWithProviders(<Backtesting />);
    const symbolInput = document.getElementById("bt-symbol");
    expect(symbolInput).toBeInTheDocument();
  });

  it("renders timeframe select", () => {
    renderWithProviders(<Backtesting />);
    const timeframeSelect = document.getElementById("bt-timeframe");
    expect(timeframeSelect).toBeInTheDocument();
  });

  it("renders exchange select", () => {
    renderWithProviders(<Backtesting />);
    const exchangeSelect = document.getElementById("bt-exchange");
    expect(exchangeSelect).toBeInTheDocument();
  });

  it("renders Run Backtest button", () => {
    renderWithProviders(<Backtesting />);
    expect(screen.getByText("Run Backtest")).toBeInTheDocument();
  });

  it("renders Export CSV link in history", async () => {
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("Export CSV")).toBeInTheDocument();
  });

  it("shows empty state when no results", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
      }),
    );
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("History")).toBeInTheDocument();
  });

  it("framework buttons have aria-labels", () => {
    renderWithProviders(<Backtesting />);
    const buttons = screen.getAllByRole("button");
    const fwButtons = buttons.filter(btn => btn.getAttribute("aria-label")?.includes("Select"));
    expect(fwButtons.length).toBeGreaterThan(0);
  });

  it("refresh history button has aria-label", async () => {
    renderWithProviders(<Backtesting />);
    const btn = await screen.findByLabelText("Refresh history");
    expect(btn).toBeInTheDocument();
  });
});

const mockResultsWithMetrics = [
  {
    id: 1,
    job_id: "abc-123",
    framework: "freqtrade",
    strategy_name: "CryptoInvestorV1",
    symbol: "BTC/USDT",
    timeframe: "1h",
    timerange: "20250101-20250201",
    metrics: { sharpe_ratio: 1.5, max_drawdown: 0.15, win_rate: 0.65, total_trades: 42 },
    trades: [],
    config: {},
    created_at: "2026-02-10T12:00:00Z",
  },
  {
    id: 2,
    job_id: "def-456",
    framework: "freqtrade",
    strategy_name: "BollingerMeanReversion",
    symbol: "ETH/USDT",
    timeframe: "4h",
    timerange: "20250101-20250201",
    metrics: { sharpe_ratio: 0.8, max_drawdown: 0.25, win_rate: 0.55, total_trades: 28 },
    trades: [],
    config: {},
    created_at: "2026-02-11T12:00:00Z",
  },
];

describe("Backtesting - History Table Metrics", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResultsWithMetrics,
      }),
    );
  });

  it("shows Sharpe ratio in history table", async () => {
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("1.50")).toBeInTheDocument();
  });

  it("shows max drawdown as percentage", async () => {
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("15.0%")).toBeInTheDocument();
  });

  it("shows win rate as percentage", async () => {
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("65.0%")).toBeInTheDocument();
  });

  it("shows trade count", async () => {
    renderWithProviders(<Backtesting />);
    expect(await screen.findByText("42")).toBeInTheDocument();
  });

  it("renders selection checkboxes for comparison", async () => {
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThanOrEqual(2);
  });

  it("shows selection count when 2+ selected", async () => {
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    expect(screen.getByText("2 selected for comparison")).toBeInTheDocument();
  });
});

describe("Backtesting - Empty Results", () => {
  it("shows empty state message when no history and no job", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
      }),
    );
    renderWithProviders(<Backtesting />);
    await waitFor(() => {
      expect(screen.getByText("Configure a backtest and click Run to see results.")).toBeInTheDocument();
    });
  });
});
