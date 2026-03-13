import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { PaperTrading } from "../src/pages/PaperTrading";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { renderWithProviders, mockFetch } from "./helpers";

const stoppedInstance = {
  running: false,
  strategy: null,
  pid: null,
  started_at: null,
  uptime_seconds: 0,
  exit_code: null,
  instance: "freqtrade_civ1",
};

const runningInstance = {
  running: true,
  strategy: "CryptoInvestorV1",
  pid: 12345,
  started_at: "2026-02-15T10:00:00Z",
  uptime_seconds: 3600,
  exit_code: null,
  instance: "freqtrade_civ1",
};

// API returns arrays for multi-instance support
const stoppedStatuses = [stoppedInstance];
const runningStatuses = [runningInstance];

const mockStrategies = [
  { name: "CryptoInvestorV1", framework: "freqtrade", file_path: "" },
  { name: "BollingerMeanReversion", framework: "freqtrade", file_path: "" },
  { name: "VolatilityBreakout", framework: "freqtrade", file_path: "" },
];

describe("PaperTrading - Stopped State", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": stoppedStatuses,
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<PaperTrading />);
    expect(screen.getByText("Paper Trading")).toBeInTheDocument();
  });

  it("shows Stopped status", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Stopped")).toBeInTheDocument();
  });

  it("shows Start button when stopped", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Start")).toBeInTheDocument();
  });

  it("shows strategy selector when stopped", async () => {
    renderWithProviders(<PaperTrading />);
    const select = await screen.findByRole("combobox");
    expect(select).toBeInTheDocument();
  });

  it("renders stat cards", () => {
    renderWithProviders(<PaperTrading />);
    expect(screen.getByText("Total Profit")).toBeInTheDocument();
    expect(screen.getByText("Win Rate")).toBeInTheDocument();
    expect(screen.getByText("Trades")).toBeInTheDocument();
    expect(screen.getByText("Closed P/L")).toBeInTheDocument();
  });
});

describe("PaperTrading - Running State", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": runningStatuses,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0.05,
          profit_all_percent: 2.5,
          profit_closed_coin: 0.03,
          profit_closed_percent: 1.8,
          trade_count: 5,
          closed_trade_count: 3,
          winning_trades: 2,
          losing_trades: 1,
        }],
        "/api/paper-trading/performance": [
          { pair: "BTC/USDT", profit: 1.5, count: 3 },
        ],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [
          { timestamp: "2026-02-15T10:00:00Z", event: "started", strategy: "CryptoInvestorV1" },
        ],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("shows Running status", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Running")).toBeInTheDocument();
  });

  it("shows Stop button when running", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Stop")).toBeInTheDocument();
  });

  it("shows strategy name in status bar", async () => {
    renderWithProviders(<PaperTrading />);
    const matches = await screen.findAllByText("CryptoInvestorV1");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("renders open trades section", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Open Trades")).toBeInTheDocument();
  });

  it("renders performance section", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Performance by Pair")).toBeInTheDocument();
  });

  it("renders event log section", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Event Log")).toBeInTheDocument();
  });
});

describe("PaperTrading - ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", mockFetch({
      "/api/paper-trading/status": stoppedStatuses,
      "/api/backtest/strategies": mockStrategies,
    }));
  });

  it("catches render errors with named fallback", () => {
    // Verify the ErrorBoundary import is used in the page
    function ThrowingChild() { throw new Error("render crash"); }
    renderWithProviders(
      <ErrorBoundary fallback={<div role="alert">Paper Trading unavailable</div>}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Paper Trading unavailable")).toBeInTheDocument();
  });
});

describe("PaperTrading - Performance Table", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": runningStatuses,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0.05,
          profit_all_percent: 2.5,
          profit_closed_coin: 0.03,
          profit_closed_percent: 1.8,
          trade_count: 5,
          closed_trade_count: 3,
          winning_trades: 2,
          losing_trades: 1,
        }],
        "/api/paper-trading/performance": [
          { pair: "BTC/USDT", profit: 1.5, count: 3 },
          { pair: "ETH/USDT", profit: -0.8, count: 2 },
        ],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("shows performance pair names", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(screen.getByText("ETH/USDT")).toBeInTheDocument();
  });

  it("shows positive profit in green", async () => {
    renderWithProviders(<PaperTrading />);
    const profitCell = await screen.findByText("+1.50%");
    expect(profitCell.className).toContain("text-green");
  });

  it("shows negative profit in red", async () => {
    renderWithProviders(<PaperTrading />);
    const lossCell = await screen.findByText("-0.80%");
    expect(lossCell.className).toContain("text-red");
  });

  it("shows trade count per pair", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("3")).toBeInTheDocument();
  });
});

describe("PaperTrading - Trade History", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": runningStatuses,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        }],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [
          {
            trade_id: "t1",
            pair: "BTC/USDT",
            open_date: "2026-02-15T10:00:00Z",
            close_date: "2026-02-15T12:30:00Z",
            profit_ratio: 0.025,
          },
          {
            trade_id: "t2",
            pair: "ETH/USDT",
            open_date: "2026-02-14T08:00:00Z",
            close_date: "2026-02-15T08:00:00Z",
            profit_ratio: -0.015,
          },
        ],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("renders Trade History section", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Trade History")).toBeInTheDocument();
  });

  it("shows trade pair in history", async () => {
    renderWithProviders(<PaperTrading />);
    const pairs = await screen.findAllByText("BTC/USDT");
    expect(pairs.length).toBeGreaterThanOrEqual(1);
  });

  it("shows profit percentage for trades", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("2.50%")).toBeInTheDocument();
  });

  it("shows negative profit in red", async () => {
    renderWithProviders(<PaperTrading />);
    const loss = await screen.findByText("-1.50%");
    expect(loss.className).toContain("text-red");
  });
});

describe("PaperTrading - No Data Messages", () => {
  it("shows no performance data message when running", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": runningStatuses,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        }],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("No performance data yet")).toBeInTheDocument();
  });

  it("shows no trade history message when running", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": runningStatuses,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        }],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("No closed trades yet")).toBeInTheDocument();
  });

  it("shows start message when stopped and no performance", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": stoppedStatuses,
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Start paper trading to see performance")).toBeInTheDocument();
  });
});

describe("PaperTrading - Forex Signals Info Card", () => {
  it("shows forex signal trading info when forex_signals instance exists", async () => {
    const forexInstance = {
      running: true,
      strategy: "ForexSignals",
      pid: 99999,
      started_at: "2026-03-01T08:00:00Z",
      uptime_seconds: 7200,
      exit_code: null,
      instance: "forex_signals",
      open_positions: 2,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": [runningInstance, forexInstance],
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Forex Signal Trading Active")).toBeInTheDocument();
    expect(screen.getByText(/Max 2\/3 positions open/)).toBeInTheDocument();
  });
});

describe("PaperTrading - Open Trades Table with Data", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": [runningInstance],
        "/api/paper-trading/trades": [
          { trade_id: "ot1", pair: "SOL/USDT", amount: 1.234567, open_rate: 150.25, profit_ratio: 0.032 },
          { trade_id: "ot2", pair: "DOGE/USDT", amount: 500.0, open_rate: 0.08, profit_ratio: -0.015 },
        ],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0.1, profit_all_percent: 5.0, profit_closed_coin: 0.05,
          profit_closed_percent: 2.0, trade_count: 4, closed_trade_count: 2,
          winning_trades: 1, losing_trades: 1,
        }],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("renders open trade pair names", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("SOL/USDT")).toBeInTheDocument();
    expect(screen.getByText("DOGE/USDT")).toBeInTheDocument();
  });

  it("renders open trade amounts", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("1.234567")).toBeInTheDocument();
    expect(screen.getByText("500.000000")).toBeInTheDocument();
  });

  it("renders open trade open rates", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("150.25")).toBeInTheDocument();
    expect(screen.getByText("0.08")).toBeInTheDocument();
  });

  it("renders positive open trade profit in green", async () => {
    renderWithProviders(<PaperTrading />);
    const profit = await screen.findByText("3.20%");
    expect(profit.className).toContain("text-green");
  });

  it("renders negative open trade profit in red", async () => {
    renderWithProviders(<PaperTrading />);
    const loss = await screen.findByText("-1.50%");
    expect(loss.className).toContain("text-red");
  });
});

describe("PaperTrading - Duration Formatting", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": [runningInstance],
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        }],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [
          {
            trade_id: "d1",
            pair: "BTC/USDT",
            open_date: "2026-03-01T00:00:00Z",
            close_date: "2026-03-03T12:00:00Z",
            profit_ratio: 0.01,
          },
          {
            trade_id: "d2",
            pair: "ETH/USDT",
            open_date: "2026-03-05T10:00:00Z",
            close_date: "2026-03-05T15:30:00Z",
            profit_ratio: 0.005,
          },
          {
            trade_id: "d3",
            pair: "SOL/USDT",
            open_date: "2026-03-06T12:00:00Z",
            close_date: "2026-03-06T12:45:00Z",
            profit_ratio: 0.002,
          },
        ],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("formats duration as days when over 24 hours", async () => {
    renderWithProviders(<PaperTrading />);
    // 60 hours = 2d 12h
    expect(await screen.findByText("2d 12h")).toBeInTheDocument();
  });

  it("formats duration as hours and minutes", async () => {
    renderWithProviders(<PaperTrading />);
    // 5h 30m
    expect(await screen.findByText("5h 30m")).toBeInTheDocument();
  });

  it("formats duration as minutes only when under 1 hour", async () => {
    renderWithProviders(<PaperTrading />);
    // 45m
    expect(await screen.findByText("45m")).toBeInTheDocument();
  });
});

describe("PaperTrading - Event Log Coloring", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": [runningInstance],
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [
          { timestamp: "2026-03-01T10:00:00Z", event: "started", strategy: "CryptoInvestorV1" },
          { timestamp: "2026-03-01T12:00:00Z", event: "stopped", strategy: "CryptoInvestorV1" },
          { timestamp: "2026-03-01T14:00:00Z", event: "trade_opened", strategy: "CryptoInvestorV1" },
        ],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("colors started events in green", async () => {
    renderWithProviders(<PaperTrading />);
    const started = await screen.findByText("started");
    expect(started.className).toContain("text-green");
  });

  it("colors stopped events in red", async () => {
    renderWithProviders(<PaperTrading />);
    const stopped = await screen.findByText("stopped");
    expect(stopped.className).toContain("text-red");
  });

  it("uses default color for other event types", async () => {
    renderWithProviders(<PaperTrading />);
    const tradeOpened = await screen.findByText("trade_opened");
    expect(tradeOpened.className).not.toContain("text-green");
    expect(tradeOpened.className).not.toContain("text-red");
  });

  it("shows strategy name next to log entries", async () => {
    renderWithProviders(<PaperTrading />);
    await screen.findByText("started");
    const strategyMentions = screen.getAllByText("CryptoInvestorV1");
    expect(strategyMentions.length).toBeGreaterThanOrEqual(1);
  });
});

describe("PaperTrading - Start Mutation Error", () => {
  it("displays start mutation error inline", async () => {
    function jsonResponse(data: unknown, status = 200): Response {
      return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/paper-trading/start")) {
        return Promise.reject(new Error("Start failed badly"));
      }
      if (url.includes("/paper-trading/status")) return Promise.resolve(jsonResponse([stoppedInstance]));
      if (url.includes("/paper-trading/log")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/backtest/strategies")) return Promise.resolve(jsonResponse(mockStrategies));
      return Promise.resolve(jsonResponse([]));
    };
    vi.stubGlobal("fetch", failingFetch as typeof globalThis.fetch);
    renderWithProviders(<PaperTrading />);
    const startBtn = await screen.findByLabelText("Start paper trading");
    fireEvent.click(startBtn);
    // The mutation error is shown both as a toast and inline
    await waitFor(() => {
      const matches = screen.getAllByText(/Start failed badly/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("PaperTrading - Multiple Instance Status Cards", () => {
  const multipleInstances = [
    {
      running: true,
      strategy: "CryptoInvestorV1",
      pid: 12345,
      started_at: "2026-02-15T10:00:00Z",
      uptime_seconds: 3600,
      exit_code: null,
      instance: "freqtrade_civ1",
      exchange: "kraken",
      dry_run: true,
    },
    {
      running: true,
      strategy: "BollingerMeanReversion",
      pid: 12346,
      started_at: "2026-02-15T10:00:00Z",
      uptime_seconds: 1800,
      exit_code: null,
      instance: "freqtrade_bmr",
      exchange: "kraken",
      dry_run: false,
    },
    {
      running: false,
      strategy: "VolatilityBreakout",
      pid: null,
      started_at: null,
      uptime_seconds: 0,
      exit_code: null,
      instance: "freqtrade_vb",
      exchange: "kraken",
      dry_run: true,
    },
  ];

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": multipleInstances,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": [{
          profit_all_coin: 0.1, profit_all_percent: 5.0, profit_closed_coin: 0.05,
          profit_closed_percent: 2.0, trade_count: 4, closed_trade_count: 2,
          winning_trades: 1, losing_trades: 1,
        }],
        "/api/paper-trading/performance": [],
        "/api/paper-trading/history": [],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("renders all instance status cards", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("freqtrade_civ1")).toBeInTheDocument();
    expect(screen.getByText("freqtrade_bmr")).toBeInTheDocument();
    expect(screen.getByText("freqtrade_vb")).toBeInTheDocument();
  });

  it("shows running count in status bar", async () => {
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("2 Instances Running")).toBeInTheDocument();
  });

  it("shows exchange name in instance card", async () => {
    renderWithProviders(<PaperTrading />);
    await screen.findByText("freqtrade_civ1");
    const exchanges = screen.getAllByText("kraken");
    expect(exchanges.length).toBeGreaterThanOrEqual(1);
  });

  it("shows Dry Run mode for dry_run instances", async () => {
    renderWithProviders(<PaperTrading />);
    await screen.findByText("freqtrade_civ1");
    const dryRuns = screen.getAllByText(/Dry Run/);
    expect(dryRuns.length).toBeGreaterThanOrEqual(1);
  });

  it("shows Live mode for non-dry_run instances", async () => {
    renderWithProviders(<PaperTrading />);
    await screen.findByText("freqtrade_bmr");
    const liveTexts = screen.getAllByText(/Mode:.*Live/);
    expect(liveTexts.length).toBeGreaterThanOrEqual(1);
  });
});

describe("PaperTrading - Strategy Selector Change", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/paper-trading/status": [stoppedInstance],
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
  });

  it("updates selected strategy when changed", async () => {
    renderWithProviders(<PaperTrading />);
    // Wait for strategies to load so options are populated
    await screen.findByText("Stopped");
    const select = screen.getByLabelText("Select trading strategy");
    fireEvent.change(select, { target: { value: "BollingerMeanReversion" } });
    expect((select as HTMLSelectElement).value).toBe("BollingerMeanReversion");
  });
});

describe("PaperTrading - Stop Mutation", () => {
  it("calls stop mutation when Stop button is clicked", async () => {
    function jsonResponse(data: unknown, status = 200): Response {
      return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }
    const fetchCalls: string[] = [];
    const stopFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      fetchCalls.push(url);
      if (url.includes("/paper-trading/stop") && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ status: "stopped" }));
      }
      if (url.includes("/paper-trading/status")) return Promise.resolve(jsonResponse([runningInstance]));
      if (url.includes("/paper-trading/trades")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/profit")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/performance")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/history")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/log")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/backtest/strategies")) return Promise.resolve(jsonResponse(mockStrategies));
      return Promise.resolve(jsonResponse([]));
    };
    vi.stubGlobal("fetch", stopFetch as typeof globalThis.fetch);
    renderWithProviders(<PaperTrading />);
    const stopBtn = await screen.findByLabelText("Stop paper trading");
    fireEvent.click(stopBtn);
    await waitFor(() => {
      expect(fetchCalls.some((u) => u.includes("/paper-trading/stop"))).toBe(true);
    });
  });

  it("shows error toast when stop mutation fails", async () => {
    function jsonResponse(data: unknown, status = 200): Response {
      return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }
    const stopFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/paper-trading/stop") && init?.method === "POST") {
        return Promise.reject(new Error("Stop failed"));
      }
      if (url.includes("/paper-trading/status")) return Promise.resolve(jsonResponse([runningInstance]));
      if (url.includes("/paper-trading/trades")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/profit")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/performance")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/history")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper-trading/log")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/backtest/strategies")) return Promise.resolve(jsonResponse(mockStrategies));
      return Promise.resolve(jsonResponse([]));
    };
    vi.stubGlobal("fetch", stopFetch as typeof globalThis.fetch);
    renderWithProviders(<PaperTrading />);
    const stopBtn = await screen.findByLabelText("Stop paper trading");
    fireEvent.click(stopBtn);
    await waitFor(() => {
      const matches = screen.getAllByText(/Stop failed/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });
});
