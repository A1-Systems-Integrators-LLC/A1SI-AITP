import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { RiskManagement } from "../src/pages/RiskManagement";
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

describe("RiskManagement - VaR Summary", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<RiskManagement />);
    expect(screen.getByText("Risk Management")).toBeInTheDocument();
  });

  it("renders VaR summary card", async () => {
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Value at Risk")).toBeInTheDocument();
    expect(await screen.findByText("VaR 95%")).toBeInTheDocument();
    expect(await screen.findByText("VaR 99%")).toBeInTheDocument();
    expect(await screen.findByText("CVaR 95%")).toBeInTheDocument();
    expect(await screen.findByText("CVaR 99%")).toBeInTheDocument();
  });
});

describe("RiskManagement - Portfolio Health", () => {
  it("renders healthy badge when portfolio is healthy", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
      }),
    );
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
      }),
    );
    renderWithProviders(<RiskManagement />);
    expect(await screen.findByText("Unhealthy")).toBeInTheDocument();
  });
});

describe("RiskManagement - Limits Editor", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/risk/1/status": mockStatus,
        "/api/risk/1/limits": mockLimits,
        "/api/risk/1/var": mockVaR,
        "/api/risk/1/heat-check": mockHeatCheckHealthy,
      }),
    );
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
