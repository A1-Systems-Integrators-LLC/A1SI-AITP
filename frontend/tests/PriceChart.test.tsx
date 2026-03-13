import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { PriceChart } from "../src/components/PriceChart";

const mockSetData = vi.fn();
const mockAddSeries = vi.fn().mockReturnValue({ setData: mockSetData });
const mockCreateChart = vi.fn().mockReturnValue({
  addSeries: mockAddSeries,
  timeScale: () => ({ fitContent: vi.fn() }),
  remove: vi.fn(),
  applyOptions: vi.fn(),
});

// Mock lightweight-charts to avoid canvas/DOM issues in tests
vi.mock("lightweight-charts", () => ({
  createChart: (...args: unknown[]) => mockCreateChart(...args),
  CandlestickSeries: "CandlestickSeries",
  LineSeries: "LineSeries",
  HistogramSeries: "HistogramSeries",
}));

const mockData = [
  { timestamp: 1706745600000, open: 42000, high: 42500, low: 41800, close: 42300, volume: 1234 },
  { timestamp: 1706749200000, open: 42300, high: 42700, low: 42100, close: 42600, volume: 987 },
];

const mockIndicatorData = [
  { timestamp: 1706745600000, sma_21: 42100, rsi_14: 55, macd: 50, macd_signal: 48, macd_hist: 2 },
  { timestamp: 1706749200000, sma_21: 42200, rsi_14: 60, macd: 52, macd_signal: 50, macd_hist: -1 },
];

describe("PriceChart", () => {
  beforeEach(() => {
    mockCreateChart.mockClear();
    mockAddSeries.mockClear();
    mockSetData.mockClear();
  });

  it("renders chart container", () => {
    const { container } = render(<PriceChart data={mockData} />);
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("renders with empty data", () => {
    const { container } = render(<PriceChart data={[]} />);
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("renders with custom height", () => {
    const { container } = render(<PriceChart data={mockData} height={600} />);
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("renders pane container when paneIndicators are provided", () => {
    const { container } = render(
      <PriceChart
        data={mockData}
        indicatorData={[{ timestamp: 1706745600000, rsi_14: 55 }]}
        paneIndicators={["rsi_14"]}
      />,
    );
    // Two child divs: main chart + pane chart
    const wrapperDiv = container.firstChild as HTMLElement;
    expect(wrapperDiv.children.length).toBe(2);
  });

  it("does not render pane container when no paneIndicators", () => {
    const { container } = render(<PriceChart data={mockData} />);
    const wrapperDiv = container.firstChild as HTMLElement;
    expect(wrapperDiv.children.length).toBe(1);
  });

  it("uses 5-decimal priceFormatter for forex", () => {
    render(<PriceChart data={mockData} assetClass="forex" />);
    // createChart is called with localization.priceFormatter
    const opts = mockCreateChart.mock.calls[0][1];
    expect(opts.localization.priceFormatter(1.23456)).toBe("1.23456");
  });

  it("uses 2-decimal priceFormatter for crypto", () => {
    render(<PriceChart data={mockData} assetClass="crypto" />);
    const opts = mockCreateChart.mock.calls[0][1];
    expect(opts.localization.priceFormatter(42000.123)).toBe("42000.12");
  });

  it("adds overlay indicator series for each overlay indicator", () => {
    render(
      <PriceChart
        data={mockData}
        indicatorData={mockIndicatorData}
        overlayIndicators={["sma_21"]}
      />,
    );
    // addSeries called for: candlestick + sma_21 = at least 2 calls
    expect(mockAddSeries).toHaveBeenCalledWith("LineSeries", expect.objectContaining({ color: "#f59e0b" }));
    expect(mockSetData).toHaveBeenCalled();
  });

  it("adds MACD histogram series in pane chart", () => {
    render(
      <PriceChart
        data={mockData}
        indicatorData={mockIndicatorData}
        paneIndicators={["macd_hist"]}
      />,
    );
    // HistogramSeries should be used for macd_hist
    expect(mockAddSeries).toHaveBeenCalledWith("HistogramSeries", expect.objectContaining({ color: "#22c55e" }));
  });

  it("adds line series for non-histogram pane indicators", () => {
    render(
      <PriceChart
        data={mockData}
        indicatorData={mockIndicatorData}
        paneIndicators={["rsi_14"]}
      />,
    );
    expect(mockAddSeries).toHaveBeenCalledWith("LineSeries", expect.objectContaining({ color: "#f59e0b" }));
  });

  it("handles mixed pane indicators (macd_hist + macd)", () => {
    render(
      <PriceChart
        data={mockData}
        indicatorData={mockIndicatorData}
        paneIndicators={["macd_hist", "macd"]}
      />,
    );
    expect(mockAddSeries).toHaveBeenCalledWith("HistogramSeries", expect.anything());
    expect(mockAddSeries).toHaveBeenCalledWith("LineSeries", expect.objectContaining({ color: "#3b82f6" }));
  });
});
