import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HoldingsTable } from "../src/components/HoldingsTable";
import { renderWithProviders, mockFetch } from "./helpers";

const mockHoldings = [
  { id: 1, portfolio_id: 1, symbol: "BTC/USDT", amount: 0.5, avg_buy_price: 40000, created_at: "2024-01-01", updated_at: "2024-01-01" },
  { id: 2, portfolio_id: 1, symbol: "ETH/USDT", amount: 10, avg_buy_price: 2500, created_at: "2024-01-01", updated_at: "2024-01-01" },
];

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch({}));
});

describe("HoldingsTable", () => {
  it("renders empty state when no holdings", () => {
    renderWithProviders(<HoldingsTable holdings={[]} portfolioId={1} />);
    expect(screen.getByText("No holdings yet.")).toBeInTheDocument();
    expect(screen.getByText("+ Add Holding")).toBeInTheDocument();
  });

  it("renders holdings with symbol and amount", () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    expect(screen.getByText("BTC/USDT")).toBeInTheDocument();
    expect(screen.getByText("ETH/USDT")).toBeInTheDocument();
    expect(screen.getByText("0.500000")).toBeInTheDocument();
    expect(screen.getByText("10.000000")).toBeInTheDocument();
  });

  it("renders total row", () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    expect(screen.getByText("Total")).toBeInTheDocument();
  });

  it("shows edit and delete buttons for each holding", () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const editButtons = screen.getAllByText("Edit");
    const deleteButtons = screen.getAllByText("Delete");
    expect(editButtons).toHaveLength(2);
    expect(deleteButtons).toHaveLength(2);
  });

  it("shows add holding button when holdings exist", () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    expect(screen.getByText("+ Add Holding")).toBeInTheDocument();
  });

  it("enters edit mode when Edit is clicked", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);

    expect(screen.getByText("Save")).toBeInTheDocument();
    // Cancel button appears in edit row
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("cancels edit mode", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(screen.getByText("Cancel"));

    expect(screen.queryByText("Save")).not.toBeInTheDocument();
    expect(screen.getAllByText("Edit")).toHaveLength(2);
  });

  it("shows P&L columns when live prices available", () => {
    const priceMap = { "BTC/USDT": 45000, "ETH/USDT": 3000 };
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} priceMap={priceMap} />);
    expect(screen.getByText("Current Price")).toBeInTheDocument();
    expect(screen.getByText("Current Value")).toBeInTheDocument();
    expect(screen.getByText("P&L")).toBeInTheDocument();
    expect(screen.getByText("P&L %")).toBeInTheDocument();
  });

  it("shows add holding form when button clicked", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getByText("+ Add Holding"));

    expect(screen.getByLabelText("Symbol")).toBeInTheDocument();
    expect(screen.getByLabelText("Amount")).toBeInTheDocument();
    expect(screen.getByLabelText("Avg Buy Price")).toBeInTheDocument();
    expect(screen.getByText("Add")).toBeInTheDocument();
  });
});
