import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { DataManagement } from "../src/pages/DataManagement";
import { renderWithProviders, mockFetch } from "./helpers";

const mockFiles = [
  {
    file: "binance_BTCUSDT_1h.parquet",
    symbol: "BTC/USDT",
    timeframe: "1h",
    exchange: "binance",
    rows: 2160,
    start: "2025-10-01T00:00:00Z",
    end: "2025-12-31T23:00:00Z",
  },
  {
    file: "binance_ETHUSDT_1h.parquet",
    symbol: "ETH/USDT",
    timeframe: "1h",
    exchange: "binance",
    rows: 2160,
    start: "2025-10-01T00:00:00Z",
    end: "2025-12-31T23:00:00Z",
  },
];

describe("DataManagement Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/": mockFiles,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Data Management")).toBeInTheDocument();
  });

  it("renders Download Data form", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Download Data")).toBeInTheDocument();
    expect(screen.getByText("Download")).toBeInTheDocument();
  });

  it("renders Quick Actions section", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Quick Actions")).toBeInTheDocument();
    expect(screen.getByText("Generate Sample Data")).toBeInTheDocument();
  });

  it("renders data summary with file count", async () => {
    renderWithProviders(<DataManagement />);
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("Parquet files available")).toBeInTheDocument();
  });

  it("renders data files table", async () => {
    renderWithProviders(<DataManagement />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(await screen.findByText("ETH/USDT")).toBeInTheDocument();
  });

  it("shows default symbols in download form", () => {
    renderWithProviders(<DataManagement />);
    const input = screen.getByDisplayValue("BTC/USDT, ETH/USDT, SOL/USDT");
    expect(input).toBeInTheDocument();
  });

  it("renders timeframe toggle buttons", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("1m")).toBeInTheDocument();
    expect(screen.getByText("5m")).toBeInTheDocument();
    expect(screen.getByText("1d")).toBeInTheDocument();
  });

  it("renders Available Data section heading", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Available Data")).toBeInTheDocument();
  });
});
