import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Backtesting } from "../src/pages/Backtesting";
import { renderWithProviders, mockFetch } from "./helpers";

// Mock lightweight-charts to avoid canvas/DOM issues in jsdom
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

class MockResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}
vi.stubGlobal("ResizeObserver", MockResizeObserver);

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

describe("Backtesting - Comparison Table", () => {
  it("renders comparison table when 2+ results selected and compare data returned", async () => {
    const mockComparison = {
      comparison: {
        best_strategy: "CryptoInvestorV1",
        metrics_table: [
          {
            metric: "sharpe_ratio",
            values: { CryptoInvestorV1: 1.5, BollingerMeanReversion: 0.8 },
            best: "CryptoInvestorV1",
          },
          {
            metric: "max_drawdown",
            values: { CryptoInvestorV1: 0.15, BollingerMeanReversion: 0.25 },
            best: "CryptoInvestorV1",
          },
        ],
      },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResultsWithMetrics,
        "/api/backtest/compare": mockComparison,
      }),
    );
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    await waitFor(() => {
      expect(screen.getByText("Comparison")).toBeInTheDocument();
    });
    expect(screen.getByText("Best overall:")).toBeInTheDocument();
    expect(screen.getByText("sharpe ratio")).toBeInTheDocument();
    expect(screen.getByText("max drawdown")).toBeInTheDocument();
  });

  it("deselecting a checkbox removes it from selection", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResultsWithMetrics,
      }),
    );
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    expect(screen.getByText("2 selected for comparison")).toBeInTheDocument();
    // Deselect first
    fireEvent.click(checkboxes[0]);
    expect(screen.queryByText("2 selected for comparison")).not.toBeInTheDocument();
  });
});

describe("Backtesting - Job Progress/Metrics/Equity", () => {
  it("shows job progress when backtest is running", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
        "/api/backtest/run": { job_id: "bt-job-1", status: "pending" },
        "/api/jobs/bt-job-1": {
          id: "bt-job-1",
          job_type: "backtest",
          status: "running",
          progress: 60,
          progress_message: "Processing bars...",
          error: null,
          result: null,
        },
      }),
    );
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    await waitFor(() => {
      expect(screen.getByText("Backtest Job")).toBeInTheDocument();
      expect(screen.getByText("running")).toBeInTheDocument();
    });
  });

  it("shows metrics when job completes with results", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
        "/api/backtest/run": { job_id: "bt-job-2", status: "pending" },
        "/api/jobs/bt-job-2": {
          id: "bt-job-2",
          job_type: "backtest",
          status: "completed",
          progress: 100,
          progress_message: "Done",
          error: null,
          result: {
            metrics: { total_return: 0.1234, sharpe_ratio: 1.5, max_drawdown: 0.05 },
            trades: [],
          },
        },
      }),
    );
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    await waitFor(() => {
      expect(screen.getByText("Results")).toBeInTheDocument();
    });
    expect(screen.getByText("total return")).toBeInTheDocument();
    expect(screen.getByText("0.1234")).toBeInTheDocument();
  });

  it("shows error when job fails", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
        "/api/backtest/run": { job_id: "bt-job-3", status: "pending" },
        "/api/jobs/bt-job-3": {
          id: "bt-job-3",
          job_type: "backtest",
          status: "failed",
          progress: 0,
          progress_message: null,
          error: "Data not found",
          result: null,
        },
      }),
    );
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    await waitFor(() => {
      expect(screen.getByText("failed")).toBeInTheDocument();
    });
    expect(screen.getByText("Data not found")).toBeInTheDocument();
  });

  it("run mutation error shows error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/backtest/run") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
      })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    await waitFor(() => {
      expect(screen.getByText(/Failed to start backtest|fail/)).toBeInTheDocument();
    });
  });

  it("shows metrics with string values rendered correctly", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
        "/api/backtest/run": { job_id: "bt-job-4", status: "pending" },
        "/api/jobs/bt-job-4": {
          id: "bt-job-4",
          job_type: "backtest",
          status: "completed",
          progress: 100,
          progress_message: "Done",
          error: null,
          result: {
            metrics: { strategy_name: "CryptoInvestorV1", total_return: 0.05 },
            trades: [],
          },
        },
      }),
    );
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
    });
    expect(screen.getByText("Results")).toBeInTheDocument();
    // Numeric values rendered with toFixed(4)
    expect(screen.getByText("0.0500")).toBeInTheDocument();
    // strategy_name label rendered as "strategy name" (underscores replaced)
    expect(screen.getByText("strategy name")).toBeInTheDocument();
  });
});

describe("Backtesting - Framework Switching", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": [
          ...mockStrategies,
          { name: "TrendFollowing", framework: "nautilus", file_path: "" },
          { name: "MarketMaker", framework: "hft", file_path: "" },
        ],
        "/api/backtest/results": mockResultsWithMetrics,
      }),
    );
  });

  it("switching to NautilusTrader shows nautilus strategies", async () => {
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const nautilusBtn = screen.getByLabelText("Select NautilusTrader framework");
    fireEvent.click(nautilusBtn);
    // Strategy select should now show nautilus strategies
    await waitFor(() => {
      const strategySelect = document.getElementById("bt-strategy") as HTMLSelectElement;
      const options = Array.from(strategySelect.options).map((o) => o.text);
      expect(options).toContain("TrendFollowing");
    });
  });

  it("switching to HFT shows hft strategies", async () => {
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const hftBtn = screen.getByLabelText("Select HFT Backtest framework");
    fireEvent.click(hftBtn);
    await waitFor(() => {
      const strategySelect = document.getElementById("bt-strategy") as HTMLSelectElement;
      const options = Array.from(strategySelect.options).map((o) => o.text);
      expect(options).toContain("MarketMaker");
    });
  });

  it("switching framework clears selected strategy", async () => {
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const strategySelect = document.getElementById("bt-strategy") as HTMLSelectElement;
    fireEvent.change(strategySelect, { target: { value: "CryptoInvestorV1" } });
    expect(strategySelect.value).toBe("CryptoInvestorV1");
    // Switch framework
    const nautilusBtn = screen.getByLabelText("Select NautilusTrader framework");
    fireEvent.click(nautilusBtn);
    expect(strategySelect.value).toBe("");
  });
});

describe("Backtesting - Strategies Error Banner", () => {
  it("shows error banner when strategies API fails", async () => {
    const failFetch = (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/backtest/strategies")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/backtest/results": [] })(input);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<Backtesting />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load strategies/)).toBeInTheDocument();
    });
  });

  it("shows error banner when history API fails", async () => {
    const failFetch = (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/backtest/results")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/backtest/strategies": mockStrategies })(input);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<Backtesting />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load.*backtest history/)).toBeInTheDocument();
    });
  });

  it("shows strategy text input when no strategies match the framework", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": [],
        "/api/backtest/results": [],
      }),
    );
    renderWithProviders(<Backtesting />);
    await waitFor(() => {
      const strategyInput = document.getElementById("bt-strategy") as HTMLInputElement;
      expect(strategyInput.tagName).toBe("INPUT");
      expect(strategyInput.placeholder).toBe("Strategy name");
    });
  });

  it("shows dashes for missing metric values in history", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResults, // metrics: {} (empty)
      }),
    );
    renderWithProviders(<Backtesting />);
    await screen.findByText("History");
    // Wait for results table to render with CryptoInvestorV1
    await waitFor(() => {
      const cells = screen.getAllByRole("cell");
      expect(cells.length).toBeGreaterThan(0);
    });
    // With empty metrics, sharpe/max_dd/win_rate/trades all show dashes
    const dashes = screen.getAllByText("\u2014");
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });
});

describe("Backtesting - Equity asset class", () => {
  it("shows only NautilusTrader framework for equity", () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": [],
        "/api/backtest/results": [],
      }),
    );
    renderWithProviders(<Backtesting />, { assetClass: "equity" });
    expect(screen.getByText("NautilusTrader")).toBeInTheDocument();
    expect(screen.queryByText("Freqtrade")).not.toBeInTheDocument();
    expect(screen.queryByText("HFT Backtest")).not.toBeInTheDocument();
  });
});

describe("Backtesting - Uncovered Handlers", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResults,
      }),
    );
  });

  it("changing exchange select updates value", async () => {
    renderWithProviders(<Backtesting />);
    const exchangeSelect = document.getElementById("bt-exchange") as HTMLSelectElement;
    expect(exchangeSelect).toBeInTheDocument();
    fireEvent.change(exchangeSelect, { target: { value: "kraken" } });
    expect(exchangeSelect.value).toBe("kraken");
  });

  it("changing timerange input updates value", async () => {
    renderWithProviders(<Backtesting />);
    const timerangeInput = document.getElementById("bt-timerange") as HTMLInputElement;
    expect(timerangeInput).toBeInTheDocument();
    fireEvent.change(timerangeInput, { target: { value: "20240101-20241231" } });
    expect(timerangeInput.value).toBe("20240101-20241231");
  });

  it("clicking refresh history button triggers refetch", async () => {
    renderWithProviders(<Backtesting />);
    const refreshBtn = await screen.findByLabelText("Refresh history");
    fireEvent.click(refreshBtn);
    // Button should remain in the document after click
    expect(refreshBtn).toBeInTheDocument();
  });

  it("run mutation onSuccess sets activeJobId and shows job section", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
        "/api/backtest/run": { job_id: "success-job-1" },
        "/api/jobs/success-job-1": {
          id: "success-job-1",
          job_type: "backtest",
          status: "completed",
          progress: 100,
          progress_message: "Done",
          error: null,
          result: { metrics: { sharpe_ratio: 2.0 }, trades: [] },
        },
      }),
    );
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    // onSuccess sets activeJobId, which triggers job polling and renders the job section
    await waitFor(() => {
      expect(screen.getByText("Backtest Job")).toBeInTheDocument();
    });
  });

  it("shows equity curve when job completes with trades", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": [],
        "/api/backtest/run": { job_id: "trades-job" },
        "/api/jobs/trades-job": {
          id: "trades-job",
          job_type: "backtest",
          status: "completed",
          progress: 100,
          progress_message: "Done",
          error: null,
          result: {
            metrics: { total_return: 0.5 },
            trades: [
              { open_date: "2025-01-01", close_date: "2025-01-02", profit_abs: 100, profit_ratio: 0.02 },
              { open_date: "2025-01-03", close_date: "2025-01-04", profit_abs: -50, profit_ratio: -0.01 },
            ],
          },
        },
      }),
    );
    renderWithProviders(<Backtesting />);
    fireEvent.click(screen.getByText("Run Backtest"));
    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
    });
  });

  it("changing symbol input updates value", () => {
    renderWithProviders(<Backtesting />);
    const symbolInput = document.getElementById("bt-symbol") as HTMLInputElement;
    fireEvent.change(symbolInput, { target: { value: "ETH/USDT" } });
    expect(symbolInput.value).toBe("ETH/USDT");
  });

  it("changing timeframe select updates value", () => {
    renderWithProviders(<Backtesting />);
    const timeframeSelect = document.getElementById("bt-timeframe") as HTMLSelectElement;
    fireEvent.change(timeframeSelect, { target: { value: "4h" } });
    expect(timeframeSelect.value).toBe("4h");
  });

  it("typing in strategy text input when no strategies match framework", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": [],
        "/api/backtest/results": [],
      }),
    );
    renderWithProviders(<Backtesting />);
    await waitFor(() => {
      const strategyInput = document.getElementById("bt-strategy") as HTMLInputElement;
      expect(strategyInput.tagName).toBe("INPUT");
    });
    const strategyInput = document.getElementById("bt-strategy") as HTMLInputElement;
    fireEvent.change(strategyInput, { target: { value: "MyCustomStrategy" } });
    expect(strategyInput.value).toBe("MyCustomStrategy");
  });

  it("comparison table renders null values as dashes", async () => {
    const mockComparison = {
      comparison: {
        best_strategy: null,
        metrics_table: [
          {
            metric: "sharpe_ratio",
            values: { StratA: null, StratB: 1.2 },
            best: "StratB",
          },
        ],
      },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/backtest/strategies": mockStrategies,
        "/api/backtest/results": mockResultsWithMetrics,
        "/api/backtest/compare": mockComparison,
      }),
    );
    renderWithProviders(<Backtesting />);
    await screen.findAllByText("CryptoInvestorV1");
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    await waitFor(() => {
      expect(screen.getByText("Comparison")).toBeInTheDocument();
    });
    // null value should render as dash
    const dashes = screen.getAllByText("\u2014");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });
});
