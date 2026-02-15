import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { PortfolioPage } from "../src/pages/Portfolio";
import { renderWithProviders, mockFetch } from "./helpers";

const mockPortfolios = [
  {
    id: 1,
    name: "Main Portfolio",
    exchange_id: "binance",
    description: "Primary trading portfolio",
    holdings: [
      { id: 1, portfolio_id: 1, symbol: "BTC/USDT", amount: 0.5, avg_buy_price: 40000, created_at: "", updated_at: "" },
      { id: 2, portfolio_id: 1, symbol: "ETH/USDT", amount: 5.0, avg_buy_price: 2500, created_at: "", updated_at: "" },
    ],
    created_at: "",
    updated_at: "",
  },
];

const mockTickers = [
  { symbol: "BTC/USDT", price: 50000, volume_24h: 1000000, change_24h: 5.0, high_24h: 51000, low_24h: 49000, timestamp: "" },
  { symbol: "ETH/USDT", price: 3000, volume_24h: 500000, change_24h: 3.0, high_24h: 3100, low_24h: 2900, timestamp: "" },
];

describe("Portfolio Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<PortfolioPage />);
    expect(screen.getByText("Portfolio")).toBeInTheDocument();
  });

  it("renders portfolio name after data loads", async () => {
    renderWithProviders(<PortfolioPage />);
    expect(await screen.findByText("Main Portfolio")).toBeInTheDocument();
  });

  it("renders holdings table with symbols", async () => {
    renderWithProviders(<PortfolioPage />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(screen.getByText("ETH/USDT")).toBeInTheDocument();
  });

  it("renders summary cards when holdings exist", async () => {
    renderWithProviders(<PortfolioPage />);
    expect(await screen.findByText("Total Value")).toBeInTheDocument();
    expect(screen.getByText("Total Cost")).toBeInTheDocument();
  });
});
