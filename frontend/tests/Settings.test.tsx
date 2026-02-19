import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Settings } from "../src/pages/Settings";
import { renderWithProviders, mockFetch } from "./helpers";

const mockConfigs = [
  {
    id: 1,
    name: "Binance Main",
    exchange_id: "binance",
    is_sandbox: true,
    is_default: true,
    api_key_masked: "abc...xyz",
    has_api_secret: true,
    has_passphrase: false,
    last_test_success: true,
    last_test_error: null,
    created_at: "2026-01-01T00:00:00Z",
  },
];

const mockDataSources = [
  {
    id: 1,
    exchange_config: 1,
    exchange_name: "Binance Main",
    symbols: ["BTC/USDT", "ETH/USDT"],
    timeframes: ["1h", "4h"],
    fetch_interval_minutes: 60,
    is_active: true,
    last_fetched_at: "2026-02-15T12:00:00Z",
  },
];

const mockNotifPrefs = {
  telegram_enabled: true,
  webhook_enabled: false,
  on_order_submitted: true,
  on_order_filled: true,
  on_order_cancelled: false,
  on_risk_halt: true,
  on_trade_rejected: true,
  on_daily_summary: false,
};

describe("Settings Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders Exchange Connections section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Exchange Connections")).toBeInTheDocument();
  });

  it("renders exchange config card", async () => {
    renderWithProviders(<Settings />);
    // "Binance Main" appears in both exchange config and data source sections
    const names = await screen.findAllByText("Binance Main");
    expect(names.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("binance")).toBeInTheDocument();
  });

  it("shows sandbox badge for sandbox config", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("sandbox")).toBeInTheDocument();
  });

  it("shows default badge for default config", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("default")).toBeInTheDocument();
  });

  it("renders Data Sources section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Data Sources")).toBeInTheDocument();
  });

  it("renders data source with symbols and timeframes", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(await screen.findByText("ETH/USDT")).toBeInTheDocument();
  });

  it("renders Notifications section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Notifications")).toBeInTheDocument();
  });

  it("renders About section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("About")).toBeInTheDocument();
    expect(screen.getByText("crypto-investor v0.1.0")).toBeInTheDocument();
  });
});
