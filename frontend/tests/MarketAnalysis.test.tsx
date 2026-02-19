import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { MarketAnalysis } from "../src/pages/MarketAnalysis";
import { renderWithProviders, mockFetch } from "./helpers";

// Mock lightweight-charts to avoid canvas/DOM issues in tests
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: vi.fn() }),
    timeScale: () => ({ fitContent: vi.fn() }),
    remove: vi.fn(),
  }),
  CandlestickSeries: "CandlestickSeries",
  LineSeries: "LineSeries",
  HistogramSeries: "HistogramSeries",
}));

const mockOhlcv = [
  { timestamp: 1706745600000, open: 42000, high: 42500, low: 41800, close: 42300, volume: 1234 },
  { timestamp: 1706749200000, open: 42300, high: 42700, low: 42100, close: 42600, volume: 987 },
];

describe("MarketAnalysis Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/ohlcv": mockOhlcv,
        "/api/indicators": { data: [] },
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<MarketAnalysis />);
    expect(screen.getByText("Market Analysis")).toBeInTheDocument();
  });

  it("renders symbol input with default value", () => {
    renderWithProviders(<MarketAnalysis />);
    expect(screen.getByDisplayValue("BTC/USDT")).toBeInTheDocument();
  });

  it("renders timeframe selector", () => {
    renderWithProviders(<MarketAnalysis />);
    expect(screen.getByDisplayValue("1h")).toBeInTheDocument();
  });

  it("renders exchange selector", () => {
    renderWithProviders(<MarketAnalysis />);
    expect(screen.getByDisplayValue("Sample")).toBeInTheDocument();
  });

  it("renders overlay indicator buttons", () => {
    renderWithProviders(<MarketAnalysis />);
    expect(screen.getByText("Overlays")).toBeInTheDocument();
    expect(screen.getByText("sma_21")).toBeInTheDocument();
    expect(screen.getByText("sma_50")).toBeInTheDocument();
    expect(screen.getByText("bb_upper")).toBeInTheDocument();
  });

  it("renders pane indicator buttons", () => {
    renderWithProviders(<MarketAnalysis />);
    expect(screen.getByText("Panes")).toBeInTheDocument();
    expect(screen.getByText("rsi_14")).toBeInTheDocument();
    expect(screen.getByText("macd")).toBeInTheDocument();
  });
});
