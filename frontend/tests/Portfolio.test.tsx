import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("Portfolio - Create Form", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
  });

  it("renders Create Portfolio button", () => {
    renderWithProviders(<PortfolioPage />);
    expect(screen.getByText("Create Portfolio")).toBeInTheDocument();
  });

  it("toggles create form on button click", () => {
    renderWithProviders(<PortfolioPage />);
    fireEvent.click(screen.getByText("Create Portfolio"));
    const nameInput = document.getElementById("portfolio-name");
    expect(nameInput).toBeInTheDocument();
  });

  it("renders form fields in create form", () => {
    renderWithProviders(<PortfolioPage />);
    fireEvent.click(screen.getByText("Create Portfolio"));
    expect(document.getElementById("portfolio-name")).toBeInTheDocument();
    expect(document.getElementById("portfolio-exchange")).toBeInTheDocument();
  });
});

describe("Portfolio - Portfolio Cards", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
  });

  it("shows empty state when no portfolios", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": [],
        "/api/market/tickers": [],
      }),
    );
    renderWithProviders(<PortfolioPage />);
    // Should show create prompt or empty state
    expect(screen.getByText("Create Portfolio")).toBeInTheDocument();
  });

  it("renders allocation toggle button", async () => {
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const allocationBtn = screen.queryByText(/Allocation/);
    // The allocation toggle should exist
    expect(allocationBtn).toBeInTheDocument();
  });

  it("renders edit and delete buttons for portfolio", async () => {
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const editButtons = screen.getAllByText("Edit");
    expect(editButtons.length).toBeGreaterThanOrEqual(1);
    const deleteButtons = screen.getAllByText("Delete");
    expect(deleteButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows confirm dialog on portfolio delete", async () => {
    renderWithProviders(<PortfolioPage />);
    const user = userEvent.setup();
    await screen.findByText("Main Portfolio");

    // Click the first portfolio-level Delete button
    const deleteButtons = screen.getAllByText("Delete");
    await user.click(deleteButtons[0]);

    expect(screen.getByText("Delete Portfolio")).toBeInTheDocument();
    // Dialog message contains the portfolio name
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Main Portfolio");
  });

  it("dismisses portfolio delete dialog on cancel", async () => {
    renderWithProviders(<PortfolioPage />);
    const user = userEvent.setup();
    await screen.findByText("Main Portfolio");

    const deleteButtons = screen.getAllByText("Delete");
    await user.click(deleteButtons[0]);
    expect(screen.getByText("Delete Portfolio")).toBeInTheDocument();

    // Click Cancel in the dialog
    const cancelButtons = screen.getAllByText("Cancel");
    const dialogCancel = cancelButtons[cancelButtons.length - 1];
    await user.click(dialogCancel);

    expect(screen.queryByText("Delete Portfolio")).not.toBeInTheDocument();
  });
});

describe("Portfolio - Allocation Section", () => {
  it("shows Show Allocation Breakdown button", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": [
          { id: 1, name: "Main", exchange_id: "binance", holdings: [
            { id: 1, symbol: "BTC/USDT", amount: 1.5, avg_buy_price: 40000 }
          ], created_at: "", updated_at: "" },
        ],
        "/api/market/tickers": [{ symbol: "BTC/USDT", price: 42000, change_pct: 2.5 }],
        "/api/portfolios/1/allocation": [
          { symbol: "BTC/USDT", amount: 1.5, current_price: 42000, market_value: 63000, cost_basis: 60000, pnl: 3000, pnl_pct: 5.0, weight: 100.0, price_stale: false },
        ],
      }),
    );
    renderWithProviders(<PortfolioPage />);
    expect(await screen.findByText("Show Allocation Breakdown")).toBeInTheDocument();
  });
});

describe("Portfolio - Empty State", () => {
  it("shows message when no portfolios exist", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": [],
        "/api/market/tickers": [],
      }),
    );
    renderWithProviders(<PortfolioPage />);
    await waitFor(() => {
      expect(screen.getByText(/No portfolios/i)).toBeInTheDocument();
    });
  });
});
