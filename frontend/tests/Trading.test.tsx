import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Trading } from "../src/pages/Trading";
import { renderWithProviders, mockFetch } from "./helpers";

// Mock useWebSocket to avoid real WebSocket connections
vi.mock("../src/hooks/useWebSocket", () => ({
  useWebSocket: () => ({ isConnected: false, lastMessage: null, send: vi.fn() }),
}));

const mockOrders = [
  {
    id: 1,
    symbol: "BTC/USDT",
    side: "buy",
    order_type: "market",
    amount: 0.1,
    price: null,
    avg_fill_price: 50000,
    filled: 0.1,
    status: "filled",
    mode: "paper",
    reject_reason: null,
    error_message: null,
    created_at: "2026-02-15T12:00:00Z",
  },
  {
    id: 2,
    symbol: "ETH/USDT",
    side: "sell",
    order_type: "limit",
    amount: 5,
    price: 3000,
    avg_fill_price: null,
    filled: 0,
    status: "open",
    mode: "paper",
    reject_reason: null,
    error_message: null,
    created_at: "2026-02-15T13:00:00Z",
  },
];

describe("Trading Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockOrders,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByText("Trading")).toBeInTheDocument();
  });

  it("renders Paper and Live mode buttons", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByText("Paper")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("renders New Order section", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByText("New Order")).toBeInTheDocument();
  });

  it("renders order table with data", async () => {
    renderWithProviders(<Trading />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(await screen.findByText("BUY")).toBeInTheDocument();
    expect(await screen.findByText("SELL")).toBeInTheDocument();
  });

  it("shows LIVE MODE warning when switched to live", () => {
    renderWithProviders(<Trading />);
    const liveBtn = screen.getByText("Live");
    fireEvent.click(liveBtn);
    expect(screen.getByText("LIVE MODE")).toBeInTheDocument();
  });

  it("shows Paper Orders heading in paper mode", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByText("Paper Orders")).toBeInTheDocument();
  });

  it("shows Live Orders heading when switched to live", () => {
    renderWithProviders(<Trading />);
    const liveBtn = screen.getByText("Live");
    fireEvent.click(liveBtn);
    expect(screen.getByText("Live Orders")).toBeInTheDocument();
  });
});
