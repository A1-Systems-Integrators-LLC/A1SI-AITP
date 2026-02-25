import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { RiskManagement } from "../src/pages/RiskManagement";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { WidgetErrorFallback } from "../src/components/WidgetErrorFallback";
import { renderWithProviders, mockFetch } from "./helpers";

const mockStatus = {
  equity: 10000,
  peak_equity: 10000,
  drawdown: 0.02,
  daily_pnl: 150,
  total_pnl: 500,
  open_positions: 2,
  is_halted: false,
  halt_reason: "",
};

const mockLimits = {
  max_portfolio_drawdown: 0.15,
  max_single_trade_risk: 0.02,
  max_daily_loss: 0.05,
  max_open_positions: 10,
  max_position_size_pct: 0.20,
  max_correlation: 0.70,
  min_risk_reward: 1.5,
  max_leverage: 1.0,
};

const mockVaR = {
  var_95: 250.50,
  var_99: 420.75,
  cvar_95: 310.20,
  cvar_99: 530.40,
  method: "parametric",
  window_days: 90,
};

const mockHeatCheckHealthy = {
  healthy: true,
  issues: [],
  drawdown: 0.02,
  daily_pnl: 150,
  open_positions: 2,
  max_correlation: 0.35,
  high_corr_pairs: [],
  max_concentration: 0.15,
  position_weights: { "BTC/USDT": 0.6, "ETH/USDT": 0.4 },
  var_95: 250.50,
  var_99: 420.75,
  cvar_95: 310.20,
  cvar_99: 530.40,
  is_halted: false,
};

const mockHeatCheckUnhealthy = {
  ...mockHeatCheckHealthy,
  healthy: false,
  issues: ["Drawdown warning: 12% approaching limit 15%", "VaR warning: 99% VaR $1200 > 10% of equity"],
};

const mockMetricHistory = [
  {
    id: 1,
    portfolio_id: 1,
    var_95: 250.50,
    var_99: 420.75,
    cvar_95: 310.20,
    cvar_99: 530.40,
    method: "parametric",
    drawdown: 0.02,
    equity: 10000,
    open_positions_count: 2,
    recorded_at: "2026-02-15T12:00:00Z",
  },
];

const mockTradeLog = [
  {
    id: 1,
    portfolio_id: 1,
    symbol: "BTC/USDT",
    side: "buy",
    size: 0.1,
    entry_price: 50000,
    stop_loss_price: 48000,
    approved: true,
    reason: "approved",
    equity_at_check: 10000,
    drawdown_at_check: 0.02,
    open_positions_at_check: 0,
    checked_at: "2026-02-15T11:00:00Z",
  },
  {
    id: 2,
    portfolio_id: 1,
    symbol: "ETH/USDT",
    side: "buy",
    size: 5.0,
    entry_price: 3000,
    stop_loss_price: null,
    approved: false,
    reason: "Position too large: 150.00% > 20.00%",
    equity_at_check: 10000,
    drawdown_at_check: 0.02,
    open_positions_at_check: 1,
    checked_at: "2026-02-15T11:30:00Z",
  },
];

function setupAllMocks() {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "/api/risk/1/status": mockStatus,
      "/api/risk/1/limits": mockLimits,
      "/api/risk/1/var": mockVaR,
      "/api/risk/1/heat-check": mockHeatCheckHealthy,
      "/api/risk/1/metric-history": mockMetricHistory,
      "/api/risk/1/trade-log": mockTradeLog,
    }),
  );
}

describe("RiskManagement - VaR Summary", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders the page heading", () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Risk Management")).toBeInTheDocument();
  });

  it("renders VaR summary card", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Value at Risk")).toBeInTheDocument();
    // VaR labels appear in both summary card and history table
    const var95 = await screen.findAllByText("VaR 95%");
    expect(var95.length).toBeGreaterThanOrEqual(1);
    const var99 = await screen.findAllByText("VaR 99%");
    expect(var99.length).toBeGreaterThanOrEqual(1);
    const cvar95 = await screen.findAllByText("CVaR 95%");
    expect(cvar95.length).toBeGreaterThanOrEqual(1);
    const cvar99 = await screen.findAllByText("CVaR 99%");
    expect(cvar99.length).toBeGreaterThanOrEqual(1);
  });
});

describe("RiskManagement - Portfolio Health", () => {
  it("renders healthy badge when portfolio is healthy", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
  });

  it("renders unhealthy badge and issues when portfolio has problems", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckUnhealthy,
        "/api/risk/1/metric-history": [],
        "/api/risk/1/trade-log": [],
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Unhealthy")).toBeInTheDocument();
  });
});

describe("RiskManagement - Limits Editor", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("shows Edit button in read-only mode", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Edit")).toBeInTheDocument();
  });

  it("shows Save and Cancel buttons in edit mode", async () => {
    renderWithProviders(<RiskManagement />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });
});

describe("RiskManagement - Total PnL Card", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders Total PnL status card", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Total PnL")).toBeInTheDocument();
    expect(await screen.findByText("$500.00")).toBeInTheDocument();
  });
});

describe("RiskManagement - VaR History", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders VaR History section heading", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("VaR History")).toBeInTheDocument();
  });
});

describe("RiskManagement - Kill Switch", () => {
  it("shows Halt Trading button when not halted", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Halt Trading")).toBeInTheDocument();
  });

  it("shows confirmation input after clicking Halt Trading", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    const haltBtn = await screen.findByText("Halt Trading");
    fireEvent.click(haltBtn);
    expect(screen.getByPlaceholderText("Reason for halt...")).toBeInTheDocument();
    expect(screen.getByText("Confirm Halt")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("shows Resume Trading button when halted", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": { ...mockStatus, is_halted: true, halt_reason: "emergency" },
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
        "/api/risk/1/metric-history": [],
        "/api/risk/1/trade-log": [],
        "/api/risk/1/alerts": [],
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Resume Trading")).toBeInTheDocument();
    expect(await screen.findByText(/TRADING HALTED/)).toBeInTheDocument();
  });

  it("shows halt reason in banner when halted", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": { ...mockStatus, is_halted: true, halt_reason: "test reason" },
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
        "/api/risk/1/metric-history": [],
        "/api/risk/1/trade-log": [],
        "/api/risk/1/alerts": [],
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText(/test reason/)).toBeInTheDocument();
  });
});

describe("RiskManagement - Trade Audit Log", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders Trade Audit Log section heading", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Trade Audit Log")).toBeInTheDocument();
  });

  it("renders approved and rejected badges", async () => {
    renderWithProviders(<RiskManagement />);
    const approved = await screen.findAllByText("Approved");
    expect(approved.length).toBeGreaterThanOrEqual(1);
    const rejected = await screen.findAllByText("Rejected");
    expect(rejected.length).toBeGreaterThanOrEqual(1);
  });

  it("renders trade symbols in audit log", async () => {
    renderWithProviders(<RiskManagement />);
    // BTC/USDT appears in both position weights and trade log
    const btcElements = await screen.findAllByText("BTC/USDT");
    expect(btcElements.length).toBeGreaterThanOrEqual(2);
    const ethElements = await screen.findAllByText("ETH/USDT");
    expect(ethElements.length).toBeGreaterThanOrEqual(2);
  });

  it("renders trade sides with correct labels", async () => {
    renderWithProviders(<RiskManagement />);
    const buys = await screen.findAllByText("BUY");
    expect(buys.length).toBeGreaterThanOrEqual(1);
  });

  it("renders rejection reason", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText(/Position too large/)).toBeInTheDocument();
  });
});

describe("RiskManagement - Position Sizer", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders Position Sizer section", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Position Sizer")).toBeInTheDocument();
  });

  it("renders entry price and stop loss inputs", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByLabelText("Entry Price")).toBeInTheDocument();
    expect(screen.getByLabelText("Stop Loss")).toBeInTheDocument();
  });

  it("renders Calculate button", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Calculate")).toBeInTheDocument();
  });

  it("allows changing entry price", async () => {
    renderWithProviders(<RiskManagement />);
    const input = screen.getByLabelText("Entry Price");
    fireEvent.change(input, { target: { value: "55000" } });
    expect(screen.getByDisplayValue("55000")).toBeInTheDocument();
  });

  it("allows changing stop loss", async () => {
    renderWithProviders(<RiskManagement />);
    const input = screen.getByLabelText("Stop Loss");
    fireEvent.change(input, { target: { value: "47000" } });
    expect(screen.getByDisplayValue("47000")).toBeInTheDocument();
  });
});

describe("RiskManagement - Trade Checker", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders Trade Checker section", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Trade Checker")).toBeInTheDocument();
  });

  it("renders symbol input", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByLabelText("Symbol")).toBeInTheDocument();
  });

  it("renders Buy and Sell toggle buttons", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Buy")).toBeInTheDocument();
    expect(screen.getByText("Sell")).toBeInTheDocument();
  });

  it("renders Check Trade button", async () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Check Trade")).toBeInTheDocument();
  });

  it("allows switching to Sell side", async () => {
    renderWithProviders(<RiskManagement />);
    const sellBtn = screen.getByText("Sell");
    fireEvent.click(sellBtn);
    // Sell button should now have the active styling (bg-red-500)
    expect(sellBtn.className).toContain("bg-red-500");
  });

  it("allows changing trade symbol", async () => {
    renderWithProviders(<RiskManagement />);
    const input = screen.getByLabelText("Symbol");
    fireEvent.change(input, { target: { value: "SOL/USDT" } });
    expect(screen.getByDisplayValue("SOL/USDT")).toBeInTheDocument();
  });
});

describe("RiskManagement - Alert History", () => {
  it("renders Alert History section", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Alert History")).toBeInTheDocument();
  });

  it("shows empty alert state when no alerts", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText(/No alerts recorded yet/)).toBeInTheDocument();
  });

  it("renders severity filter dropdown", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(screen.getByDisplayValue("All Severities")).toBeInTheDocument();
  });

  it("renders event type filter input", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(screen.getByPlaceholderText("Filter by event type")).toBeInTheDocument();
  });

  it("renders alerts when present", async () => {
    const mockAlerts = [
      {
        id: 1,
        event_type: "trade_halt",
        severity: "critical",
        channel: "telegram",
        delivered: true,
        error: null,
        message: "Trading halted: drawdown exceeded",
        created_at: "2026-02-24T10:00:00Z",
      },
      {
        id: 2,
        event_type: "daily_summary",
        severity: "info",
        channel: "webhook",
        delivered: false,
        error: "Connection timeout",
        message: "Daily summary report",
        created_at: "2026-02-24T09:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
        "/api/risk/1/metric-history": mockMetricHistory,
        "/api/risk/1/trade-log": mockTradeLog,
        "/api/risk/1/alerts": mockAlerts,
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("trade_halt")).toBeInTheDocument();
    expect(await screen.findByText("critical")).toBeInTheDocument();
    expect(await screen.findByText("telegram")).toBeInTheDocument();
    expect(await screen.findByText("Yes")).toBeInTheDocument();
    expect(await screen.findByText("No")).toBeInTheDocument();
  });
});

describe("RiskManagement - Status Cards", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders Equity status card", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Equity")).toBeInTheDocument();
  });

  it("renders Drawdown status card", async () => {
    renderWithProviders(<RiskManagement />);
    // "Drawdown" appears in both status card and health section
    const drawdownLabels = await screen.findAllByText("Drawdown");
    expect(drawdownLabels.length).toBeGreaterThanOrEqual(2);
    // "2.00%" appears in both status card and health section
    const pctValues = await screen.findAllByText(/2\.00%/);
    expect(pctValues.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Daily PnL status card", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Daily PnL")).toBeInTheDocument();
    expect(await screen.findByText("$150.00")).toBeInTheDocument();
  });

  it("renders Status card as Active", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Status")).toBeInTheDocument();
    expect(await screen.findByText("Active")).toBeInTheDocument();
  });

  it("renders Refresh button", async () => {
    renderWithProviders(<RiskManagement />);
    const refreshButtons = screen.getAllByTitle("Refresh status");
    expect(refreshButtons.length).toBeGreaterThanOrEqual(1);
  });
});

describe("RiskManagement - Snapshot Now", () => {
  beforeEach(() => {
    setupAllMocks();
  });

  it("renders Snapshot Now button", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Snapshot Now")).toBeInTheDocument();
  });
});

describe("RiskManagement - Empty Trade Log", () => {
  it("shows empty message when no trades", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
        "/api/risk/1/metric-history": [],
        "/api/risk/1/trade-log": [],
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText(/No trade checks recorded yet/)).toBeInTheDocument();
  });
});

describe("RiskManagement - Portfolio Health Details", () => {
  it("shows position weights", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Position Weights")).toBeInTheDocument();
    // BTC/USDT and ETH/USDT appear in multiple sections
    const btcElements = await screen.findAllByText("BTC/USDT");
    expect(btcElements.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("60.0%")).toBeInTheDocument();
    expect(await screen.findByText("40.0%")).toBeInTheDocument();
  });

  it("shows open positions count in health", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Open Positions")).toBeInTheDocument();
  });

  it("shows max correlation in health", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Max Correlation")).toBeInTheDocument();
    expect(await screen.findByText("0.350")).toBeInTheDocument();
  });

  it("shows max concentration in health", async () => {
    setupAllMocks();
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Max Concentration")).toBeInTheDocument();
    // 15.0% for max_concentration
    const pctElements = await screen.findAllByText("15.0%");
    expect(pctElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows high correlation pairs when present", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": {
          ...mockHeatCheckHealthy,
          high_corr_pairs: [["BTC/USDT", "ETH/USDT", 0.85]],
        },
        "/api/risk/1/metric-history": [],
        "/api/risk/1/trade-log": [],
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("High Correlation Pairs")).toBeInTheDocument();
    expect(await screen.findByText("0.850")).toBeInTheDocument();
  });

  it("shows issues list when unhealthy", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckUnhealthy,
        "/api/risk/1/metric-history": [],
        "/api/risk/1/trade-log": [],
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText(/Drawdown warning/)).toBeInTheDocument();
    expect(await screen.findByText(/VaR warning/)).toBeInTheDocument();
  });
});

describe("RiskManagement - ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("catches render errors with named fallback", () => {
    function ThrowingChild() { throw new Error("render crash"); }
    renderWithProviders(
      <ErrorBoundary fallback={<WidgetErrorFallback name="Risk Management" />}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Risk Management unavailable")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
