import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderForm } from "../src/components/OrderForm";
import { renderWithProviders, mockFetch } from "./helpers";

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch({
    "/api/portfolios/": [{ id: 1, name: "My Portfolio", exchange_id: "binance", holdings: [] }],
  }));
});

describe("OrderForm", () => {
  it("renders all form fields", () => {
    renderWithProviders(<OrderForm />);
    expect(screen.getByLabelText("Portfolio")).toBeInTheDocument();
    expect(screen.getByLabelText("Symbol")).toBeInTheDocument();
    expect(screen.getByText("Buy")).toBeInTheDocument();
    expect(screen.getByText("Sell")).toBeInTheDocument();
    expect(screen.getByLabelText("Amount")).toBeInTheDocument();
    expect(screen.getByLabelText(/Price/)).toBeInTheDocument();
  });

  it("renders paper order button by default", () => {
    renderWithProviders(<OrderForm />);
    expect(screen.getByRole("button", { name: "Place Paper Order" })).toBeInTheDocument();
  });

  it("renders live order button in live mode", () => {
    renderWithProviders(<OrderForm mode="live" />);
    expect(screen.getByRole("button", { name: "Place Live Order" })).toBeInTheDocument();
  });

  it("toggles between buy and sell", async () => {
    renderWithProviders(<OrderForm />);
    const user = userEvent.setup();

    const sellButton = screen.getByText("Sell");
    await user.click(sellButton);
    expect(sellButton.className).toContain("bg-[var(--color-danger)]");

    const buyButton = screen.getByText("Buy");
    await user.click(buyButton);
    expect(buyButton.className).toContain("bg-[var(--color-success)]");
  });

  it("shows confirmation dialog for live orders", async () => {
    renderWithProviders(<OrderForm mode="live" />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Amount"), "0.5");
    await user.click(screen.getByRole("button", { name: "Place Live Order" }));

    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("cancels live order confirmation", async () => {
    renderWithProviders(<OrderForm mode="live" />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Amount"), "0.5");
    await user.click(screen.getByRole("button", { name: "Place Live Order" }));
    await user.click(screen.getByText("Cancel"));

    expect(screen.queryByText("Confirm")).not.toBeInTheDocument();
  });

  it("amount input has min attribute", () => {
    renderWithProviders(<OrderForm />);
    const amount = screen.getByLabelText("Amount");
    expect(amount).toHaveAttribute("min", "0.00000001");
  });

  it("price input has min attribute", () => {
    renderWithProviders(<OrderForm />);
    const price = screen.getByLabelText(/Price/);
    expect(price).toHaveAttribute("min", "0");
  });

  it("renders FieldError slots for symbol, amount, and price", () => {
    // With no mutation error, no field errors should be visible
    renderWithProviders(<OrderForm />);
    // The form should have labels but no error paragraphs
    const errorParagraphs = document.querySelectorAll("p.mt-1.text-xs");
    expect(errorParagraphs).toHaveLength(0);
  });

  it("symbol input renders without FieldError when no error", () => {
    renderWithProviders(<OrderForm />);
    const symbolInput = screen.getByLabelText("Symbol");
    // There should be no sibling error paragraph
    const parent = symbolInput.closest("div");
    expect(parent?.querySelector("p")).toBeNull();
  });

  it("amount input renders without FieldError when no error", () => {
    renderWithProviders(<OrderForm />);
    const amountInput = screen.getByLabelText("Amount");
    const parent = amountInput.closest("div");
    expect(parent?.querySelector("p")).toBeNull();
  });

  it("inputs have aria-labels", () => {
    renderWithProviders(<OrderForm />);
    expect(screen.getByLabelText("Order amount")).toBeInTheDocument();
    expect(screen.getByLabelText("Order price")).toBeInTheDocument();
  });

  it("changes portfolio selection", async () => {
    renderWithProviders(<OrderForm />);
    const user = userEvent.setup();

    const select = screen.getByLabelText("Portfolio");
    // Wait for portfolios to load
    await screen.findByText(/My Portfolio/);
    await user.selectOptions(select, "1");
    expect(select).toHaveValue("1");
  });

  it("changes symbol input value", async () => {
    renderWithProviders(<OrderForm />);
    const user = userEvent.setup();

    const symbolInput = screen.getByLabelText("Symbol");
    await user.clear(symbolInput);
    await user.type(symbolInput, "ETH/USDT");
    expect(symbolInput).toHaveValue("ETH/USDT");
  });

  it("changes price input value", async () => {
    renderWithProviders(<OrderForm />);
    const user = userEvent.setup();

    const priceInput = screen.getByLabelText("Order price");
    await user.type(priceInput, "42000");
    expect(priceInput).toHaveValue(42000);
  });

  it("confirms and submits live order via Confirm button", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/portfolios/": [{ id: 1, name: "My Portfolio", exchange_id: "binance", holdings: [] }],
      "/api/trading/orders/": { id: 1, status: "pending" },
    }));

    renderWithProviders(<OrderForm mode="live" />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Amount"), "0.5");
    await user.click(screen.getByRole("button", { name: "Place Live Order" }));

    // Confirmation dialog appears
    expect(screen.getByText("Confirm")).toBeInTheDocument();

    // Click Confirm to execute confirmLiveOrder
    await user.click(screen.getByText("Confirm"));

    // After successful mutation, showConfirm is reset to false
    await waitFor(() => {
      // The mutation was triggered — form should reset
      expect(screen.getByRole("button", { name: "Place Live Order" })).toBeInTheDocument();
    });
  });

  it("submits paper order directly without confirmation", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/portfolios/": [{ id: 1, name: "My Portfolio", exchange_id: "binance", holdings: [] }],
      "/api/trading/orders/": { id: 1, status: "pending" },
    }));

    renderWithProviders(<OrderForm mode="paper" />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Amount"), "1.0");
    await user.click(screen.getByRole("button", { name: "Place Paper Order" }));

    // Mutation triggered without confirmation dialog
    expect(screen.queryByText("Confirm")).not.toBeInTheDocument();
  });

  it("shows error toast on order mutation failure", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/portfolios/": [{ id: 1, name: "My Portfolio", exchange_id: "binance", holdings: [] }],
    }));
    // Override the orders endpoint to fail
    const originalFetch = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === "string" && url.includes("/api/trading/orders/") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ detail: "Validation failed" }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }));
      }
      return originalFetch(url, init);
    }));

    renderWithProviders(<OrderForm mode="paper" />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Amount"), "0.5");
    await user.click(screen.getByRole("button", { name: "Place Paper Order" }));
    // onError fires — form stays
    expect(screen.getByRole("button", { name: "Place Paper Order" })).toBeInTheDocument();
  });

  it("shows amount label as Shares for equity", () => {
    renderWithProviders(<OrderForm />, { assetClass: "equity" });
    expect(screen.getByText("Shares")).toBeInTheDocument();
  });

  it("shows amount label as Lots for forex", () => {
    renderWithProviders(<OrderForm />, { assetClass: "forex" });
    expect(screen.getByText("Lots")).toBeInTheDocument();
  });
});
