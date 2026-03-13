import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { EquityCurve } from "../src/components/EquityCurve";

// Mock lightweight-charts to avoid canvas/DOM issues in tests
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: vi.fn() }),
    timeScale: () => ({ fitContent: vi.fn() }),
    priceScale: () => ({ applyOptions: vi.fn() }),
    remove: vi.fn(),
    applyOptions: vi.fn(),
  }),
  LineSeries: "LineSeries",
  AreaSeries: "AreaSeries",
}));

// Mock ResizeObserver as a class
class MockResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}
vi.stubGlobal("ResizeObserver", MockResizeObserver);

const mockTrades = [
  { close_date: "2024-01-15T10:00:00Z", profit_abs: 150 },
  { close_date: "2024-01-16T14:00:00Z", profit_abs: -50 },
  { close_date: "2024-01-17T09:00:00Z", profit_abs: 200 },
];

describe("EquityCurve", () => {
  it("renders nothing when trades is empty", () => {
    const { container } = render(<EquityCurve trades={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders heading when trades are provided", () => {
    render(<EquityCurve trades={mockTrades} />);
    expect(screen.getByText("Equity Curve")).toBeTruthy();
  });

  it("renders chart container when trades are provided", () => {
    const { container } = render(<EquityCurve trades={mockTrades} />);
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("accepts custom initialBalance", () => {
    render(<EquityCurve trades={mockTrades} initialBalance={50000} />);
    expect(screen.getByText("Equity Curve")).toBeTruthy();
  });

  it("accepts custom height", () => {
    render(<EquityCurve trades={mockTrades} height={500} />);
    expect(screen.getByText("Equity Curve")).toBeTruthy();
  });

  it("handles trades with no close_date (early return after sort)", () => {
    const badTrades = [
      { profit_abs: 100 },  // no close_date
      { close_date: undefined, profit_abs: 50 },  // undefined close_date
    ];
    const { container } = render(<EquityCurve trades={badTrades} />);
    // trades.length > 0 so outer check passes, but sorted is empty
    // chart is created then removed via early return
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("triggers ResizeObserver callback", () => {
    // Use a real-ish ResizeObserver that invokes the callback
    let resizeCallback: ResizeObserverCallback | null = null;
    const mockObserve = vi.fn();
    const mockDisconnect = vi.fn();

    vi.stubGlobal("ResizeObserver", class {
      constructor(cb: ResizeObserverCallback) { resizeCallback = cb; }
      observe = mockObserve;
      disconnect = mockDisconnect;
      unobserve = vi.fn();
    });

    render(<EquityCurve trades={mockTrades} />);
    expect(mockObserve).toHaveBeenCalled();

    // Invoke the callback to cover lines 96-97
    if (resizeCallback) {
      resizeCallback(
        [{ contentRect: { width: 500 } } as ResizeObserverEntry],
        {} as ResizeObserver,
      );
    }
    // chart.applyOptions should have been called (mocked)
  });
});
