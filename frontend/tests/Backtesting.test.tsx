import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
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
    const cells = screen.getAllByText("CryptoInvestorV1");
    expect(cells.length).toBeGreaterThanOrEqual(1);
  });
});
