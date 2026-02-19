import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
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
});
