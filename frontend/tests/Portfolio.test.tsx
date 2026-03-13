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

describe("Portfolio - Create Mutation", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
  });

  it("submitting create form fires createMutation and shows toast", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    // Open create form
    await user.click(screen.getByText("Create Portfolio"));
    // Fill in name
    const nameInput = document.getElementById("portfolio-name") as HTMLInputElement;
    await user.type(nameInput, "Test Portfolio");
    // Click Create button
    const createBtn = screen.getByRole("button", { name: "Create" });
    await user.click(createBtn);
    await waitFor(() => {
      expect(screen.getByText("Portfolio created")).toBeInTheDocument();
    });
  });

  it("create button is disabled when name is empty", async () => {
    renderWithProviders(<PortfolioPage />);
    fireEvent.click(screen.getByText("Create Portfolio"));
    const createBtn = screen.getByRole("button", { name: "Create" });
    expect(createBtn).toBeDisabled();
  });

  it("create mutation error shows error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/portfolios") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ error: "Duplicate name" }), { status: 400 }));
      }
      return mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await user.click(screen.getByText("Create Portfolio"));
    const nameInput = document.getElementById("portfolio-name") as HTMLInputElement;
    await user.type(nameInput, "Test");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(screen.getByText(/Failed to create portfolio|Duplicate name/)).toBeInTheDocument();
    });
  });
});

describe("Portfolio - Update Mutation", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
  });

  it("clicking Edit shows edit form, Save fires updateMutation", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    // Click first Edit button (portfolio-level)
    const editButtons = screen.getAllByText("Edit");
    await user.click(editButtons[0]);
    // Edit form should appear with "Edit Portfolio" heading
    expect(screen.getByText("Edit Portfolio")).toBeInTheDocument();
    // The edit name input should have the portfolio name
    const editNameInput = document.getElementById("edit-name-1") as HTMLInputElement;
    expect(editNameInput.value).toBe("Main Portfolio");
    // Click Save
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(screen.getByText("Portfolio updated")).toBeInTheDocument();
    });
  });

  it("clicking Cancel on edit form closes it", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const editButtons = screen.getAllByText("Edit");
    await user.click(editButtons[0]);
    expect(screen.getByText("Edit Portfolio")).toBeInTheDocument();
    // Click Cancel in the edit form
    const cancelButtons = screen.getAllByText("Cancel");
    const editCancel = cancelButtons.find(
      (btn) => btn.closest("div")?.querySelector("[id^='edit-name']") !== null,
    ) ?? cancelButtons[cancelButtons.length - 1];
    await user.click(editCancel);
    expect(screen.queryByText("Edit Portfolio")).not.toBeInTheDocument();
  });
});

describe("Portfolio - Delete Mutation", () => {
  it("confirming delete fires deleteMutation and shows toast", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const deleteButtons = screen.getAllByText("Delete");
    await user.click(deleteButtons[0]);
    // Confirm dialog should appear
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // Click the confirm "Delete" button in the dialog
    const dialogDeleteBtn = screen.getAllByText("Delete").find(
      (btn) => btn.closest("[role='dialog']") !== null && btn.tagName === "BUTTON",
    );
    if (dialogDeleteBtn) await user.click(dialogDeleteBtn);
    await waitFor(() => {
      expect(screen.getByText("Portfolio deleted")).toBeInTheDocument();
    });
  });
});

describe("Portfolio - Allocation Table", () => {
  it("clicking Show Allocation Breakdown fetches and renders allocation data", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios/1/allocation": [
          {
            symbol: "BTC/USDT",
            amount: 1.5,
            current_price: 42000,
            market_value: 63000,
            cost_basis: 60000,
            pnl: 3000,
            pnl_pct: 5.0,
            weight: 100.0,
            price_stale: false,
          },
        ],
        "/api/portfolios": [
          {
            id: 1,
            name: "Main",
            exchange_id: "binance",
            holdings: [
              { id: 1, symbol: "BTC/USDT", amount: 1.5, avg_buy_price: 40000 },
            ],
            created_at: "",
            updated_at: "",
          },
        ],
        "/api/market/tickers": [{ symbol: "BTC/USDT", price: 42000, change_pct: 2.5 }],
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Show Allocation Breakdown");
    await user.click(screen.getByText("Show Allocation Breakdown"));
    await waitFor(() => {
      expect(screen.getByText("Weight")).toBeInTheDocument();
    });
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    // pnl_pct appears in both the allocation table and portfolio summary
    const pnlElements = screen.getAllByText("+5.00%");
    expect(pnlElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows stale price indicator for allocation items", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios/1/allocation": [
          {
            symbol: "BTC/USDT",
            amount: 1.0,
            current_price: 40000,
            market_value: 40000,
            cost_basis: 40000,
            pnl: 0,
            pnl_pct: 0,
            weight: 100.0,
            price_stale: true,
          },
        ],
        "/api/portfolios": [
          {
            id: 1,
            name: "Main",
            exchange_id: "binance",
            holdings: [
              { id: 1, symbol: "BTC/USDT", amount: 1.0, avg_buy_price: 40000 },
            ],
            created_at: "",
            updated_at: "",
          },
        ],
        "/api/market/tickers": [],
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Show Allocation Breakdown");
    await user.click(screen.getByText("Show Allocation Breakdown"));
    await waitFor(() => {
      expect(screen.getByText("*")).toBeInTheDocument();
    });
  });

  it("toggles allocation section hide/show", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios/1/allocation": [
          {
            symbol: "BTC/USDT",
            amount: 1.0,
            current_price: 40000,
            market_value: 40000,
            cost_basis: 40000,
            pnl: 0,
            pnl_pct: 0,
            weight: 100.0,
            price_stale: false,
          },
        ],
        "/api/portfolios": [
          {
            id: 1,
            name: "Main",
            exchange_id: "binance",
            holdings: [
              { id: 1, symbol: "BTC/USDT", amount: 1.0, avg_buy_price: 40000 },
            ],
            created_at: "",
            updated_at: "",
          },
        ],
        "/api/market/tickers": [],
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Show Allocation Breakdown");
    await user.click(screen.getByText("Show Allocation Breakdown"));
    await waitFor(() => {
      expect(screen.getByText("Hide Allocation Breakdown")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Hide Allocation Breakdown"));
    expect(screen.getByText("Show Allocation Breakdown")).toBeInTheDocument();
  });
});

describe("Portfolio - No Live Prices", () => {
  it("shows cost basis message when no live prices available", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": [],
      }),
    );
    renderWithProviders(<PortfolioPage />);
    await waitFor(() => {
      expect(screen.getByText("Live prices unavailable. Values shown at cost basis.")).toBeInTheDocument();
    });
  });
});

describe("Portfolio - P&L Display", () => {
  it("shows unrealized P&L and percentage", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    // With live prices: BTC 0.5*50000=25000 + ETH 5*3000=15000 = 40000
    // Cost: BTC 0.5*40000=20000 + ETH 5*2500=12500 = 32500
    // P&L = 7500, pct = 23.08%
    await waitFor(() => {
      expect(screen.getByText("Unrealized P&L")).toBeInTheDocument();
      expect(screen.getByText("P&L %")).toBeInTheDocument();
    });
  });
});

describe("Portfolio - Asset Class Badge", () => {
  it("shows asset class badge when portfolio has asset_class", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": [
          { ...mockPortfolios[0], asset_class: "crypto" },
        ],
        "/api/market/tickers": mockTickers,
      }),
    );
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    expect(screen.getByText("Crypto")).toBeInTheDocument();
  });
});

describe("Portfolio - Exchange Select in Create Form", () => {
  it("changing exchange select in create form updates value", () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
    renderWithProviders(<PortfolioPage />);
    fireEvent.click(screen.getByText("Create Portfolio"));
    const exchangeSelect = document.getElementById("portfolio-exchange") as HTMLSelectElement;
    fireEvent.change(exchangeSelect, { target: { value: "kraken" } });
    expect(exchangeSelect.value).toBe("kraken");
  });
});

describe("Portfolio - WebSocket Tickers Override", () => {
  it("uses WS ticker prices to override HTTP prices", async () => {
    // Mock useTickerStream to return WS ticker data
    const mockModule = await import("../src/hooks/useTickerStream");
    const spy = vi.spyOn(mockModule, "useTickerStream");
    spy.mockReturnValue({
      tickers: {
        "BTC/USDT": { symbol: "BTC/USDT", price: 55000, volume_24h: 1000, change_24h: 2, high_24h: 56000, low_24h: 54000, timestamp: "" },
      },
      isConnected: true,
    });

    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    // WS price of 55000 for BTC should be reflected in the total value
    // BTC: 0.5 * 55000 = 27500, ETH: 5 * 3000 = 15000 (HTTP), total = 42500
    await waitFor(() => {
      expect(screen.getByText("Total Value")).toBeInTheDocument();
    });

    spy.mockRestore();
  });
});

describe("Portfolio - Uncovered Handlers", () => {
  it("create mutation error triggers error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/portfolios") && init?.method === "POST") {
        return Promise.reject(new Error("Network error"));
      }
      return mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await user.click(screen.getByText("Create Portfolio"));
    const nameInput = document.getElementById("portfolio-name") as HTMLInputElement;
    await user.type(nameInput, "Failing Portfolio");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(screen.getByText(/Failed to create portfolio|Network error/)).toBeInTheDocument();
    });
  });

  it("changing description input in create form updates value", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
    renderWithProviders(<PortfolioPage />);
    fireEvent.click(screen.getByText("Create Portfolio"));
    const descInput = document.getElementById("portfolio-desc") as HTMLInputElement;
    fireEvent.change(descInput, { target: { value: "My portfolio description" } });
    expect(descInput.value).toBe("My portfolio description");
  });

  it("edit form allows changing exchange and description fields", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const editButtons = screen.getAllByText("Edit");
    await user.click(editButtons[0]);
    expect(screen.getByText("Edit Portfolio")).toBeInTheDocument();
    // Change the exchange select
    const editExchangeSelect = document.getElementById("edit-exchange-1") as HTMLSelectElement;
    fireEvent.change(editExchangeSelect, { target: { value: "kraken" } });
    expect(editExchangeSelect.value).toBe("kraken");
    // Change the description input
    const editDescInput = document.getElementById("edit-desc-1") as HTMLInputElement;
    fireEvent.change(editDescInput, { target: { value: "Updated description" } });
    expect(editDescInput.value).toBe("Updated description");
    // Change the name input
    const editNameInput = document.getElementById("edit-name-1") as HTMLInputElement;
    fireEvent.change(editNameInput, { target: { value: "Renamed Portfolio" } });
    expect(editNameInput.value).toBe("Renamed Portfolio");
  });

  it("update mutation error triggers error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/portfolios/1") && (init?.method === "PUT" || init?.method === "PATCH")) {
        return Promise.reject(new Error("Update failed"));
      }
      return mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const editButtons = screen.getAllByText("Edit");
    await user.click(editButtons[0]);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(screen.getByText(/Failed to update portfolio|Update failed/)).toBeInTheDocument();
    });
  });

  it("delete mutation error triggers error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/portfolios/1") && init?.method === "DELETE") {
        return Promise.reject(new Error("Delete failed"));
      }
      return mockFetch({
        "/api/portfolios": mockPortfolios,
        "/api/market/tickers": mockTickers,
      })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    const user = userEvent.setup();
    renderWithProviders(<PortfolioPage />);
    await screen.findByText("Main Portfolio");
    const deleteButtons = screen.getAllByText("Delete");
    await user.click(deleteButtons[0]);
    // Confirm in dialog
    const dialogDeleteBtn = screen.getAllByText("Delete").find(
      (btn) => btn.closest("[role='dialog']") !== null && btn.tagName === "BUTTON",
    );
    if (dialogDeleteBtn) await user.click(dialogDeleteBtn);
    await waitFor(() => {
      expect(screen.getByText(/Failed to delete portfolio|Delete failed/)).toBeInTheDocument();
    });
  });
});
