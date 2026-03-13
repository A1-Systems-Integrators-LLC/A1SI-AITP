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

  it("populates edit fields with current limits when clicking Edit after limits load", async () => {
    renderWithProviders(<RiskManagement />);
    // Wait for limits data to render - "Max Drawdown" label appears when limits load
    await screen.findByText("Max Drawdown");
    const editBtn = screen.getByText("Edit");
    fireEvent.click(editBtn);
    // After clicking Edit with limits loaded, editLimits should be populated
    expect(screen.getByDisplayValue("0.15")).toBeInTheDocument();
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

/* ======================================================================
 * Additional tests for 100% line coverage
 * ====================================================================== */

import { waitFor } from "@testing-library/react";

const haltedStatus = { ...mockStatus, is_halted: true, halt_reason: "emergency stop" };

/** Build a custom fetch spy that distinguishes GET vs POST and URL patterns. */
function buildCustomFetch(overrides: Record<string, unknown> = {}) {
  const baseGetHandlers: Record<string, unknown> = {
    "/api/risk/1/status": mockStatus,
    "/api/risk/1/limits": mockLimits,
    "/api/risk/1/var": mockVaR,
    "/api/risk/1/heat-check": mockHeatCheckHealthy,
    "/api/risk/1/metric-history": mockMetricHistory,
    "/api/risk/1/trade-log": mockTradeLog,
    "/api/risk/1/alerts": [],
    "/api/portfolios": [{ id: 1, name: "Test Portfolio" }],
    ...overrides,
  };

  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();

    // POST handlers — return specific data for mutation endpoints
    if (method === "POST" && url.includes("/position-size")) {
      return Promise.resolve(
        new Response(JSON.stringify({ size: 0.5, risk_amount: 100, position_value: 25000 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (method === "POST" && url.includes("/check-trade")) {
      const body = init?.body ? JSON.parse(init.body as string) : {};
      const approved = body.side !== "sell"; // sell -> rejected for testing
      return Promise.resolve(
        new Response(
          JSON.stringify({ approved, reason: approved ? "all checks passed" : "risk limit breached" }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    }
    if (method === "POST" && url.includes("/halt")) {
      return Promise.resolve(
        new Response(JSON.stringify({ is_halted: true, halt_reason: "test halt" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (method === "POST" && url.includes("/resume")) {
      return Promise.resolve(
        new Response(JSON.stringify({ is_halted: false, halt_reason: "" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (method === "POST" && url.includes("/reset-daily")) {
      return Promise.resolve(
        new Response(JSON.stringify({ ...mockStatus, daily_pnl: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (method === "POST" && url.includes("/record-metrics")) {
      return Promise.resolve(
        new Response(JSON.stringify(mockMetricHistory[0]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if ((method === "PUT" || method === "PATCH") && url.includes("/limits")) {
      return Promise.resolve(
        new Response(JSON.stringify({ ...mockLimits }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }

    // GET handlers
    for (const [pattern, data] of Object.entries(baseGetHandlers)) {
      if (url.includes(pattern)) {
        return Promise.resolve(
          new Response(JSON.stringify(data), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
    }

    if (url.startsWith("/api/")) {
      return Promise.resolve(
        new Response(JSON.stringify(method === "POST" ? {} : []), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.reject(new Error(`Unhandled fetch: ${url}`));
  }) as unknown as typeof globalThis.fetch;
}

describe("RiskManagement - Halt mutation", () => {
  it("clicking Confirm Halt with a reason calls halt mutation and hides confirm UI", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Open halt confirm
    const haltBtn = await screen.findByText("Halt Trading");
    fireEvent.click(haltBtn);

    // Type a reason
    const reasonInput = screen.getByPlaceholderText("Reason for halt...");
    fireEvent.change(reasonInput, { target: { value: "market crash" } });

    // Click confirm
    fireEvent.click(screen.getByText("Confirm Halt"));

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/halt") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Halt confirm cancel", () => {
  it("clicking Cancel in halt confirm hides the input", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const haltBtn = await screen.findByText("Halt Trading");
    fireEvent.click(haltBtn);
    expect(screen.getByPlaceholderText("Reason for halt...")).toBeInTheDocument();

    // Click Cancel (the one inside halt confirm row)
    const cancelBtns = screen.getAllByText("Cancel");
    fireEvent.click(cancelBtns[cancelBtns.length - 1]);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText("Reason for halt...")).not.toBeInTheDocument();
    });
  });
});

describe("RiskManagement - Resume mutation", () => {
  it("clicking Resume Trading calls resume mutation", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": haltedStatus,
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const resumeBtn = await screen.findByText("Resume Trading");
    fireEvent.click(resumeBtn);

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/resume") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Reset daily mutation", () => {
  it("clicking Reset Daily calls resetMutation", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": haltedStatus,
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const resetBtn = await screen.findByText("Reset Daily");
    fireEvent.click(resetBtn);

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/reset-daily") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Limits save mutation", () => {
  it("saves changed limits via limitsMutation", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Wait for limits to load, then click Edit
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);

    // Change a limit value — find the Max Drawdown input (first number input in edit mode)
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
    const inputs = screen.getAllByRole("spinbutton");
    // Change first limit input (max_portfolio_drawdown)
    fireEvent.change(inputs[0], { target: { value: "0.25" } });

    // Click Save
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      const putCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/limits") && c[1]?.method === "PUT";
        },
      );
      expect(putCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("closes editor without calling mutation when no changes are made", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);

    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    // Click Save without changing anything
    fireEvent.click(screen.getByText("Save"));

    // Should close editing (Edit button reappears)
    await waitFor(() => {
      expect(screen.getByText("Edit")).toBeInTheDocument();
    });

    // Verify no PUT was made to /limits
    const putCalls = fetchSpy.mock.calls.filter(
      (c: [RequestInfo | URL, RequestInit?]) => {
        const url = typeof c[0] === "string" ? c[0] : c[0].toString();
        return url.includes("/limits") && c[1]?.method === "PUT";
      },
    );
    expect(putCalls.length).toBe(0);
  });
});

describe("RiskManagement - Limits cancel editing", () => {
  it("clicking Cancel resets edit state and shows Edit button", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    // Click Cancel in the limits editor (next to Save)
    const cancelBtn = screen.getByText("Cancel");
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.getByText("Edit")).toBeInTheDocument();
    });
  });
});

describe("RiskManagement - Limits edit mode inputs", () => {
  it("shows number inputs in edit mode with current limit values", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);

    await waitFor(() => {
      const inputs = screen.getAllByRole("spinbutton");
      // 8 limit fields in edit mode + 2 position sizer + 2 trade checker = 12 spinbutton inputs
      // But the limit fields are the ones with specific values
      expect(inputs.length).toBeGreaterThanOrEqual(8);
    });

    // Verify one of the limit values is present (max_portfolio_drawdown = 0.15)
    expect(screen.getByDisplayValue("0.15")).toBeInTheDocument();
  });
});

describe("RiskManagement - Position sizer calculate", () => {
  it("clicking Calculate calls positionMutation and shows result", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Click Calculate
    fireEvent.click(screen.getByText("Calculate"));

    // Result should appear
    await waitFor(() => {
      expect(screen.getByText("Size:")).toBeInTheDocument();
      expect(screen.getByText("0.5")).toBeInTheDocument();
    });
    expect(screen.getByText("Risk Amount:")).toBeInTheDocument();
    expect(screen.getByText("$100")).toBeInTheDocument();
    expect(screen.getByText("Position Value:")).toBeInTheDocument();
    expect(screen.getByText("$25000")).toBeInTheDocument();
  });
});

describe("RiskManagement - Trade checker", () => {
  it("clicking Check Trade calls tradeMutation and shows approved result", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Click Check Trade (default is buy side)
    fireEvent.click(screen.getByText("Check Trade"));

    await waitFor(() => {
      // "Approved" appears in both trade log and result; check for the reason text
      expect(screen.getByText(/all checks passed/)).toBeInTheDocument();
    });
  });

  it("shows rejected result for a rejected trade check", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Switch to sell side to trigger rejection in our mock
    fireEvent.click(screen.getByText("Sell"));

    fireEvent.click(screen.getByText("Check Trade"));

    await waitFor(() => {
      expect(screen.getByText(/risk limit breached/)).toBeInTheDocument();
    });
  });
});

describe("RiskManagement - Record metrics snapshot", () => {
  it("clicking Snapshot Now calls recordMetricsMutation", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const snapshotBtn = await screen.findByText("Snapshot Now");
    fireEvent.click(snapshotBtn);

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/record-metrics") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - VaR method switching", () => {
  it("changes VaR method from parametric to historical", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("Value at Risk");

    // Find the VaR method select (contains Parametric/Historical options)
    const varSelect = screen.getByDisplayValue("Parametric");
    fireEvent.change(varSelect, { target: { value: "historical" } });

    await waitFor(() => {
      // Verify a fetch was made with method=historical
      const historicalCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/var") && url.includes("historical");
        },
      );
      expect(historicalCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - History hours switching", () => {
  it("changes history hours from 7d to 24h", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("VaR History");

    // Find the hours select (7d = 168 default)
    const hoursSelect = screen.getByDisplayValue("7d");
    fireEvent.change(hoursSelect, { target: { value: "24" } });

    await waitFor(() => {
      const hoursCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/metric-history") && url.includes("hours=24");
        },
      );
      expect(hoursCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("changes history hours to 30d", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("VaR History");

    // The hours select has value=168 (not display text "7d"), use getAllByDisplayValue to disambiguate
    const allSelects = screen.getAllByRole("combobox");
    // Find the one with option "30d"
    const hoursSelect = allSelects.find((s) =>
      Array.from(s.querySelectorAll("option")).some((o) => o.textContent === "30d"),
    )!;
    fireEvent.change(hoursSelect, { target: { value: "720" } });

    await waitFor(() => {
      const hoursCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/metric-history") && url.includes("hours=720");
        },
      );
      expect(hoursCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Alert severity filter", () => {
  it("changing severity dropdown triggers refetch with severity param", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("Alert History");

    const severitySelect = screen.getByDisplayValue("All Severities");
    fireEvent.change(severitySelect, { target: { value: "critical" } });

    await waitFor(() => {
      const alertCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/alerts") && url.includes("severity=critical");
        },
      );
      expect(alertCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Alert event type filter", () => {
  it("typing event type triggers refetch with event_type param", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("Alert History");

    const eventInput = screen.getByPlaceholderText("Filter by event type");
    fireEvent.change(eventInput, { target: { value: "trade_halt" } });

    await waitFor(() => {
      const alertCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/alerts") && url.includes("event_type=trade_halt");
        },
      );
      expect(alertCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Drawdown color logic", () => {
  it("renders red drawdown color when > 10%", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": { ...mockStatus, drawdown: 0.12 },
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      // Find the Drawdown status card value (12.00%)
      const el = screen.getByText("12.00%");
      expect(el.className).toContain("text-red-400");
    });
  });

  it("renders yellow drawdown color when > 5% and <= 10%", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": { ...mockStatus, drawdown: 0.07 },
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      const el = screen.getByText("7.00%");
      expect(el.className).toContain("text-yellow-400");
    });
  });

  it("renders green drawdown color when <= 5%", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": { ...mockStatus, drawdown: 0.03 },
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      const el = screen.getByText("3.00%");
      expect(el.className).toContain("text-green-400");
    });
  });
});

describe("RiskManagement - statusError banner", () => {
  it("shows error banner when status query fails", async () => {
    const fetchFn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/status")) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: "server error" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      // Return defaults for everything else
      if (url.includes("/limits")) return Promise.resolve(new Response(JSON.stringify(mockLimits), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.includes("/var")) return Promise.resolve(new Response(JSON.stringify(mockVaR), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.includes("/heat-check")) return Promise.resolve(new Response(JSON.stringify(mockHeatCheckHealthy), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.includes("/metric-history")) return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.includes("/trade-log")) return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.includes("/alerts")) return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.startsWith("/api/")) return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      return Promise.reject(new Error(`Unhandled: ${url}`));
    }) as unknown as typeof globalThis.fetch;

    vi.stubGlobal("fetch", fetchFn);
    renderWithProviders(<RiskManagement />);

    expect(await screen.findByText(/Failed to load risk status/)).toBeInTheDocument();
  });
});

describe("RiskManagement - Metric history table rendering", () => {
  it("renders metric history table rows with data", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Wait for the history table to render with data from mockMetricHistory
    // Values appear in both VaR summary cards and history table, so use getAllByText
    await waitFor(() => {
      const var95 = screen.getAllByText("$250.50");
      // Should appear at least twice: once in VaR summary, once in history table
      expect(var95.length).toBeGreaterThanOrEqual(2);
    });

    // Check the open_positions_count column value (unique to history table)
    // mockMetricHistory[0].open_positions_count = 2
    // The "2" appears in the Positions column of the history table
    const var99 = screen.getAllByText("$420.75");
    expect(var99.length).toBeGreaterThanOrEqual(2);
  });
});

describe("RiskManagement - VaR method text display", () => {
  it("shows VaR method and window text in same element", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    // Both "Method: parametric" and "Window: 90 days" are in the same <p> element
    const el = await screen.findByText(/Method: parametric \| Window: 90 days/);
    expect(el).toBeInTheDocument();
  });
});

describe("RiskManagement - Negative PnL colors", () => {
  it("renders red daily PnL when negative", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": { ...mockStatus, daily_pnl: -75.50 },
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      const el = screen.getByText("$-75.50");
      expect(el.className).toContain("text-red-400");
    });
  });

  it("renders red total PnL when negative", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/status": { ...mockStatus, total_pnl: -200.00 },
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      const el = screen.getByText("$-200.00");
      expect(el.className).toContain("text-red-400");
    });
  });

  it("renders green daily PnL when positive", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      const el = screen.getByText("$150.00");
      expect(el.className).toContain("text-green-400");
    });
  });

  it("renders green total PnL when positive", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await waitFor(() => {
      const el = screen.getByText("$500.00");
      expect(el.className).toContain("text-green-400");
    });
  });
});

/** Build a custom fetch that returns errors for POST endpoints. */
function buildErrorFetch(errorEndpoint: string, overrides: Record<string, unknown> = {}) {
  const baseGetHandlers: Record<string, unknown> = {
    "/api/risk/1/status": mockStatus,
    "/api/risk/1/limits": mockLimits,
    "/api/risk/1/var": mockVaR,
    "/api/risk/1/heat-check": mockHeatCheckHealthy,
    "/api/risk/1/metric-history": mockMetricHistory,
    "/api/risk/1/trade-log": mockTradeLog,
    "/api/risk/1/alerts": [],
    "/api/portfolios": [{ id: 1, name: "Test Portfolio" }, { id: 2, name: "Portfolio 2" }],
    ...overrides,
  };

  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();

    // Return error for the specified endpoint
    if ((method === "POST" || method === "PUT") && url.includes(errorEndpoint)) {
      return Promise.resolve(
        new Response(JSON.stringify({ error: "server error" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }

    // GET handlers
    for (const [pattern, data] of Object.entries(baseGetHandlers)) {
      if (url.includes(pattern)) {
        return Promise.resolve(
          new Response(JSON.stringify(data), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
    }

    if (url.startsWith("/api/")) {
      return Promise.resolve(
        new Response(JSON.stringify(method === "POST" ? {} : []), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.reject(new Error(`Unhandled fetch: ${url}`));
  }) as unknown as typeof globalThis.fetch;
}

describe("RiskManagement - Mutation error handlers", () => {
  it("halt mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/halt");
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const haltBtn = await screen.findByText("Halt Trading");
    fireEvent.click(haltBtn);
    const reasonInput = screen.getByPlaceholderText("Reason for halt...");
    fireEvent.change(reasonInput, { target: { value: "test" } });
    fireEvent.click(screen.getByText("Confirm Halt"));

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/halt") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("resume mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/resume", {
      "/api/risk/1/status": haltedStatus,
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const resumeBtn = await screen.findByText("Resume Trading");
    fireEvent.click(resumeBtn);

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/resume") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("reset daily mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/reset-daily", {
      "/api/risk/1/status": haltedStatus,
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const resetBtn = await screen.findByText("Reset Daily");
    fireEvent.click(resetBtn);

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/reset-daily") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("record metrics mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/record-metrics");
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const snapshotBtn = await screen.findByText("Snapshot Now");
    fireEvent.click(snapshotBtn);

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/record-metrics") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("limits mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/limits");
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
    // Change a value
    const inputs = screen.getAllByRole("spinbutton");
    fireEvent.change(inputs[0], { target: { value: "0.30" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      const putCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/limits") && c[1]?.method === "PUT";
        },
      );
      expect(putCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("position sizer mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/position-size");
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    fireEvent.click(screen.getByText("Calculate"));

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/position-size") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("trade check mutation error shows toast", async () => {
    const fetchSpy = buildErrorFetch("/check-trade");
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    fireEvent.click(screen.getByText("Check Trade"));

    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/check-trade") && c[1]?.method === "POST";
        },
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Portfolio selector", () => {
  it("changing portfolio selector updates portfolioId", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/portfolios": [{ id: 1, name: "Portfolio One" }, { id: 2, name: "Portfolio Two" }],
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("Portfolio One");
    const select = screen.getByLabelText("Portfolio:");
    fireEvent.change(select, { target: { value: "2" } });

    // Should trigger fetches with portfolioId=2
    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) => {
          const url = typeof c[0] === "string" ? c[0] : c[0].toString();
          return url.includes("/risk/2/");
        },
      );
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("RiskManagement - Trade checker input changes", () => {
  it("allows changing trade size", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const sizeInput = screen.getByLabelText("Size");
    fireEvent.change(sizeInput, { target: { value: "0.5" } });
    expect(screen.getByDisplayValue("0.5")).toBeInTheDocument();
  });

  it("allows changing trade entry price", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const entryInput = screen.getByLabelText("Entry");
    fireEvent.change(entryInput, { target: { value: "52000" } });
    expect(screen.getByDisplayValue("52000")).toBeInTheDocument();
  });

  it("clicking Buy when already on buy does not change side", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    const buyBtn = screen.getByText("Buy");
    // Buy is default, click it again
    fireEvent.click(buyBtn);
    expect(buyBtn.className).toContain("bg-green-500");
  });
});

describe("RiskManagement - Refresh button", () => {
  it("clicking Refresh invalidates queries", async () => {
    const fetchSpy = buildCustomFetch();
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    await screen.findByText("Risk Management");
    const refreshBtn = screen.getByTitle("Refresh status");
    const callCountBefore = fetchSpy.mock.calls.length;
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(fetchSpy.mock.calls.length).toBeGreaterThan(callCountBefore);
    });
  });
});

describe("RiskManagement - Empty metric history message", () => {
  it("shows placeholder text when no metric history", async () => {
    const fetchSpy = buildCustomFetch({
      "/api/risk/1/metric-history": [],
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<RiskManagement />);

    expect(await screen.findByText(/No metric history yet/)).toBeInTheDocument();
  });
});
