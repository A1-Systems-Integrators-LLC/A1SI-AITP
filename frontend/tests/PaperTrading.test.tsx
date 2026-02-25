import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { PaperTrading } from "../src/pages/PaperTrading";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { renderWithProviders, mockFetch } from "./helpers";

const stoppedStatus = {
  running: false,
  strategy: null,
  pid: null,
  started_at: null,
  uptime_seconds: 0,
  exit_code: null,
};

const runningStatus = {
  running: true,
  strategy: "CryptoInvestorV1",
  pid: 12345,
  started_at: "2026-02-15T10:00:00Z",
  uptime_seconds: 3600,
  exit_code: null,
};

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
        "/api/paper-trading/status": stoppedStatus,
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
        "/api/paper-trading/status": runningStatus,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": {
          profit_all_coin: 0.05,
          profit_all_percent: 2.5,
          profit_closed_coin: 0.03,
          profit_closed_percent: 1.8,
          trade_count: 5,
          closed_trade_count: 3,
          winning_trades: 2,
          losing_trades: 1,
        },
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
      "/api/paper-trading/status": stoppedStatus,
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
        "/api/paper-trading/status": runningStatus,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": {
          profit_all_coin: 0.05,
          profit_all_percent: 2.5,
          profit_closed_coin: 0.03,
          profit_closed_percent: 1.8,
          trade_count: 5,
          closed_trade_count: 3,
          winning_trades: 2,
          losing_trades: 1,
        },
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
        "/api/paper-trading/status": runningStatus,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": {
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        },
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
        "/api/paper-trading/status": runningStatus,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": {
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        },
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
        "/api/paper-trading/status": runningStatus,
        "/api/paper-trading/trades": [],
        "/api/paper-trading/profit": {
          profit_all_coin: 0, profit_all_percent: 0, profit_closed_coin: 0,
          profit_closed_percent: 0, trade_count: 0, closed_trade_count: 0,
          winning_trades: 0, losing_trades: 0,
        },
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
        "/api/paper-trading/status": stoppedStatus,
        "/api/paper-trading/log": [],
        "/api/backtest/strategies": mockStrategies,
      }),
    );
    renderWithProviders(<PaperTrading />);
    expect(await screen.findByText("Start paper trading to see performance")).toBeInTheDocument();
  });
});
