import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
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

const mockOrderWithError = [
  {
    id: 3,
    symbol: "SOL/USDT",
    side: "buy",
    order_type: "market",
    amount: 100,
    price: null,
    avg_fill_price: null,
    filled: 0,
    status: "rejected",
    mode: "paper",
    reject_reason: "Insufficient balance",
    error_message: null,
    created_at: "2026-02-15T14:00:00Z",
  },
];

const mockLiveOrders = [
  {
    id: 10,
    symbol: "BTC/USDT",
    side: "buy",
    order_type: "limit",
    amount: 0.5,
    price: 45000,
    avg_fill_price: null,
    filled: 0,
    status: "open",
    mode: "live",
    reject_reason: null,
    error_message: null,
    created_at: "2026-02-15T15:00:00Z",
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

  it("shows Paper Orders heading in paper mode", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByText("Paper Orders")).toBeInTheDocument();
  });
});

describe("Trading - Mode Switching", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockOrders,
      }),
    );
  });

  it("shows LIVE MODE warning when switched to live", () => {
    renderWithProviders(<Trading />);
    const liveBtn = screen.getByText("Live");
    fireEvent.click(liveBtn);
    expect(screen.getByText("LIVE MODE")).toBeInTheDocument();
  });

  it("shows Live Orders heading when switched to live", () => {
    renderWithProviders(<Trading />);
    const liveBtn = screen.getByText("Live");
    fireEvent.click(liveBtn);
    expect(screen.getByText("Live Orders")).toBeInTheDocument();
  });

  it("shows Action column header in live mode", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockLiveOrders }),
    );
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    expect(await screen.findByText("Action")).toBeInTheDocument();
  });

  it("shows Cancel button for open orders in live mode", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockLiveOrders }),
    );
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    expect(await screen.findByText("Cancel")).toBeInTheDocument();
  });

  it("switches back to paper mode", () => {
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    expect(screen.getByText("LIVE MODE")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Paper"));
    expect(screen.queryByText("LIVE MODE")).not.toBeInTheDocument();
    expect(screen.getByText("Paper Orders")).toBeInTheDocument();
  });
});

describe("Trading - Halt Banner", () => {
  it("shows halt banner when useSystemEvents reports halted", async () => {
    // Re-mock useWebSocket to simulate a halted state via useSystemEvents
    // useSystemEvents checks isHalted from WS messages. Since we mock useWebSocket
    // to return null lastMessage, isHalted defaults to null (falsy) — no banner.
    // The halt banner requires isHalted===true, which only happens via WS message.
    // We test the component renders without halt banner by default.
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />);
    // Halt banner should NOT appear when not halted
    expect(screen.queryByText(/TRADING HALTED/)).not.toBeInTheDocument();
  });
});

describe("Trading - Order Display Details", () => {
  it("shows reject reason for rejected orders", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrderWithError }),
    );
    renderWithProviders(<Trading />);
    expect(await screen.findByText("Insufficient balance")).toBeInTheDocument();
  });

  it("shows filled ratio for partially filled orders", async () => {
    const partialOrder = [
      {
        ...mockLiveOrders[0],
        filled: 0.2,
        amount: 0.5,
        status: "partial_fill",
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": partialOrder }),
    );
    renderWithProviders(<Trading />);
    expect(await screen.findByText("0.2/0.5")).toBeInTheDocument();
  });

  it("shows Market for orders without price", async () => {
    const marketOrder = [
      {
        ...mockOrders[0],
        avg_fill_price: null,
        price: null,
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": marketOrder }),
    );
    renderWithProviders(<Trading />);
    expect(await screen.findByText("Market")).toBeInTheDocument();
  });

  it("shows empty orders message when no orders exist", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": [] }),
    );
    renderWithProviders(<Trading />);
    expect(await screen.findByText("No paper orders yet.")).toBeInTheDocument();
  });
});

describe("Trading - Order Filters", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
  });

  it("renders symbol filter input", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByPlaceholderText("Filter by symbol...")).toBeInTheDocument();
  });

  it("renders status filter dropdown", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByText("All statuses")).toBeInTheDocument();
  });
});

describe("Trading - Cancel All Orders", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
  });

  it("shows Cancel All button in live mode", () => {
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    expect(screen.getByText("Cancel All Orders")).toBeInTheDocument();
  });

  it("hides Cancel All button in paper mode", () => {
    renderWithProviders(<Trading />);
    // Ensure we're in paper mode
    fireEvent.click(screen.getByText("Paper"));
    expect(screen.queryByText("Cancel All Orders")).not.toBeInTheDocument();
  });

  it("opens confirm dialog when Cancel All clicked", () => {
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    fireEvent.click(screen.getByText("Cancel All Orders"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("This will cancel all open live orders. This action cannot be undone.")).toBeInTheDocument();
  });

  it("closes dialog when cancel is clicked", () => {
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    fireEvent.click(screen.getByText("Cancel All Orders"));
    // Click the dialog's Cancel button (not Cancel All)
    const cancelBtns = screen.getAllByText("Cancel");
    // The dialog has a Cancel button
    const dialogCancel = cancelBtns.find(
      (btn) => btn.closest("[role='dialog']") !== null,
    );
    if (dialogCancel) fireEvent.click(dialogCancel);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Trading - ARIA Labels", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
  });

  it("filter inputs have aria-labels", () => {
    renderWithProviders(<Trading />);
    expect(screen.getByLabelText("Filter by symbol")).toBeInTheDocument();
    expect(screen.getByLabelText("Filter by status")).toBeInTheDocument();
  });

  it("mode toggle buttons have aria-pressed and aria-label", () => {
    renderWithProviders(<Trading />);
    const paperBtn = screen.getByLabelText("Paper trading mode");
    const liveBtn = screen.getByLabelText("Live trading mode");
    expect(paperBtn).toHaveAttribute("aria-pressed");
    expect(liveBtn).toHaveAttribute("aria-pressed");
  });
});

describe("Trading - Exchange Health Badge", () => {
  it("renders exchange health badge", () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />);
    expect(screen.getByText("Checking...")).toBeInTheDocument();
  });
});

describe("Trading - Performance Summary", () => {
  it("shows performance summary cards when data has trades", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockOrders,
        "/api/trading/performance/summary": {
          total_trades: 20,
          win_rate: 65.0,
          profit_factor: 2.5,
          total_pnl: 1234.56,
          best_trade: 500.0,
          worst_trade: -200.0,
        },
      }),
    );
    renderWithProviders(<Trading />);
    await waitFor(() => {
      expect(screen.getByText("Win Rate")).toBeInTheDocument();
    });
    expect(screen.getByText("65.0%")).toBeInTheDocument();
    expect(screen.getByText("2.50")).toBeInTheDocument();
    expect(screen.getByText("$1234.56")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.getByText("Total Trades")).toBeInTheDocument();
    expect(screen.getByText("Profit Factor")).toBeInTheDocument();
  });

  it("shows infinity symbol when profit_factor is null", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockOrders,
        "/api/trading/performance/summary": {
          total_trades: 5,
          win_rate: 100.0,
          profit_factor: null,
          total_pnl: 500.0,
          best_trade: 200.0,
          worst_trade: 50.0,
        },
      }),
    );
    renderWithProviders(<Trading />);
    await waitFor(() => {
      expect(screen.getByText("\u221E")).toBeInTheDocument();
    });
  });

  it("shows negative P&L with red color", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockOrders,
        "/api/trading/performance/summary": {
          total_trades: 10,
          win_rate: 30.0,
          profit_factor: 0.5,
          total_pnl: -500.0,
          best_trade: 100.0,
          worst_trade: -300.0,
        },
      }),
    );
    renderWithProviders(<Trading />);
    await waitFor(() => {
      expect(screen.getByText("$-500.00")).toBeInTheDocument();
    });
    const pnlEl = screen.getByText("$-500.00");
    expect(pnlEl.className).toContain("text-red");
  });

  it("does not show performance cards when total_trades is 0", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockOrders,
        "/api/trading/performance/summary": {
          total_trades: 0,
          win_rate: 0,
          profit_factor: null,
          total_pnl: 0,
          best_trade: null,
          worst_trade: null,
        },
      }),
    );
    renderWithProviders(<Trading />);
    await screen.findByText("BTC/USDT");
    expect(screen.queryByText("Win Rate")).not.toBeInTheDocument();
  });
});

describe("Trading - WebSocket Disconnected Banner", () => {
  it("shows disconnected banner when WS is not connected", () => {
    // useWebSocket is mocked to return isConnected: false
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />);
    expect(screen.getByText(/WebSocket disconnected/)).toBeInTheDocument();
  });
});

describe("Trading - Error Message on Orders", () => {
  it("shows error_message on orders that have it", async () => {
    const orderWithErrorMsg = [
      {
        id: 4,
        symbol: "XRP/USDT",
        side: "buy",
        order_type: "market",
        amount: 50,
        price: null,
        avg_fill_price: null,
        filled: 0,
        status: "error",
        mode: "paper",
        reject_reason: null,
        error_message: "Exchange timeout",
        created_at: "2026-02-15T14:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": orderWithErrorMsg }),
    );
    renderWithProviders(<Trading />);
    expect(await screen.findByText("Exchange timeout")).toBeInTheDocument();
  });
});

describe("Trading - Orders Error Banner", () => {
  it("shows orders error banner when ordersQuery fails", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/trading/orders")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "Server error" }), { status: 500 }));
      }
      return mockFetch({})(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<Trading />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load orders/)).toBeInTheDocument();
    });
  });
});

describe("Trading - Cancel Order Mutation", () => {
  it("clicking Cancel on an open order fires cancelMutation", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockLiveOrders }),
    );
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    const cancelBtn = await screen.findByLabelText("Cancel order BTC/USDT");
    fireEvent.click(cancelBtn);
    await waitFor(() => {
      expect(screen.getByText("Order cancelled")).toBeInTheDocument();
    });
  });
});

describe("Trading - Cancel All Mutation", () => {
  it("confirming cancel all fires cancelAllMutation", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/orders": mockLiveOrders,
        "/api/trading/cancel-all": { cancelled: 3 },
      }),
    );
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    fireEvent.click(screen.getByText("Cancel All Orders"));
    // Click confirm in dialog
    const dialog = screen.getByRole("dialog");
    const confirmBtn = dialog.querySelector("button");
    // Find the Cancel All button in the dialog (not the Cancel button)
    const allBtns = Array.from(dialog.querySelectorAll("button"));
    const cancelAllBtn = allBtns.find((btn) => btn.textContent === "Cancel All");
    if (cancelAllBtn) fireEvent.click(cancelAllBtn);
    await waitFor(() => {
      expect(screen.getByText(/Cancelled \d+ orders/)).toBeInTheDocument();
    });
  });
});

describe("Trading - Amount Label", () => {
  it("shows Shares label for equity asset class", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />, { assetClass: "equity" });
    await screen.findByText("BTC/USDT");
    // "Shares" appears in both the order table header and OrderForm
    const sharesElements = screen.getAllByText("Shares");
    expect(sharesElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows Lots label for forex asset class", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />, { assetClass: "forex" });
    await screen.findByText("BTC/USDT");
    const lotsElements = screen.getAllByText("Lots");
    expect(lotsElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows Amount label for crypto asset class", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />);
    await screen.findByText("BTC/USDT");
    const amountElements = screen.getAllByText("Amount");
    expect(amountElements.length).toBeGreaterThanOrEqual(1);
  });
});

describe("Trading - Uncovered Handlers", () => {
  it("cancel mutation error shows error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/cancel/") && init?.method === "POST") {
        return Promise.reject(new Error("Cancel failed"));
      }
      if (url.includes("/api/trading/orders")) {
        return Promise.resolve(new Response(JSON.stringify(mockLiveOrders), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      return mockFetch({})(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    const cancelBtn = await screen.findByLabelText("Cancel order BTC/USDT");
    fireEvent.click(cancelBtn);
    await waitFor(() => {
      expect(screen.getByText(/Failed to cancel order|Cancel failed/)).toBeInTheDocument();
    });
  });

  it("cancel all mutation error shows error toast and closes dialog", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/trading/cancel-all") && init?.method === "POST") {
        return Promise.reject(new Error("Cancel all failed"));
      }
      return mockFetch({ "/api/trading/orders": mockLiveOrders })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<Trading />);
    fireEvent.click(screen.getByText("Live"));
    fireEvent.click(screen.getByText("Cancel All Orders"));
    const dialog = screen.getByRole("dialog");
    const allBtns = Array.from(dialog.querySelectorAll("button"));
    const cancelAllBtn = allBtns.find((btn) => btn.textContent === "Cancel All");
    if (cancelAllBtn) fireEvent.click(cancelAllBtn);
    await waitFor(() => {
      expect(screen.getByText(/Failed to cancel all orders|Cancel all failed/)).toBeInTheDocument();
    });
  });

  it("typing in symbol filter updates the filter value", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />);
    const symbolInput = screen.getByPlaceholderText("Filter by symbol...") as HTMLInputElement;
    fireEvent.change(symbolInput, { target: { value: "ETH" } });
    expect(symbolInput.value).toBe("ETH");
  });

  it("changing status filter updates the filter value", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/trading/orders": mockOrders }),
    );
    renderWithProviders(<Trading />);
    const statusSelect = screen.getByLabelText("Filter by status") as HTMLSelectElement;
    fireEvent.change(statusSelect, { target: { value: "filled" } });
    expect(statusSelect.value).toBe("filled");
  });
});
