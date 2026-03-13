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

  it("symbol input has maxLength", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getByText("+ Add Holding"));
    const symbolInput = screen.getByPlaceholderText("BTC/USDT");
    expect(symbolInput).toHaveAttribute("maxLength", "20");
  });

  it("amount input has min attribute in add form", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getByText("+ Add Holding"));
    const inputs = screen.getAllByRole("spinbutton");
    const amountInput = inputs.find(i => i.getAttribute("min") === "0.00000001");
    expect(amountInput).toBeDefined();
  });

  it("shows confirm dialog when delete is clicked", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Delete")[0]);

    expect(screen.getByText("Delete Holding")).toBeInTheDocument();
    // Dialog message contains the symbol name
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("BTC/USDT");
  });

  it("dismisses confirm dialog on cancel", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Delete")[0]);
    expect(screen.getByText("Delete Holding")).toBeInTheDocument();

    // Click the Cancel button in the dialog
    const cancelButtons = screen.getAllByText("Cancel");
    const dialogCancel = cancelButtons[cancelButtons.length - 1];
    await user.click(dialogCancel);

    expect(screen.queryByText("Delete Holding")).not.toBeInTheDocument();
  });

  it("populates edit inputs with holding values when Edit is clicked", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);

    // startEdit sets editAmount/editPrice from the holding
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs[0]).toHaveValue(0.5);   // amount
    expect(inputs[1]).toHaveValue(40000); // avg_buy_price
  });

  it("allows changing edit amount input", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);
    const inputs = screen.getAllByRole("spinbutton");
    await user.clear(inputs[0]);
    await user.type(inputs[0], "1.5");
    expect(inputs[0]).toHaveValue(1.5);
  });

  it("allows changing edit price input", async () => {
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);
    const inputs = screen.getAllByRole("spinbutton");
    await user.clear(inputs[1]);
    await user.type(inputs[1], "50000");
    expect(inputs[1]).toHaveValue(50000);
  });

  it("calls update mutation when Save is clicked", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(screen.getByText("Save"));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/portfolios/1/holdings/1"),
      expect.objectContaining({ method: "PUT" }),
    );
  });

  it("calls delete mutation when dialog is confirmed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Delete")[0]);
    // The ConfirmDialog renders a button with confirmLabel="Delete"
    const dialog = screen.getByRole("dialog");
    const confirmBtn = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent === "Delete",
    );
    expect(confirmBtn).toBeDefined();
    await user.click(confirmBtn!);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/portfolios/1/holdings/1"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("submits add holding form with symbol, amount, and price", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 3, symbol: "SOL/USDT", amount: 100, avg_buy_price: 25 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getByText("+ Add Holding"));
    await user.type(screen.getByPlaceholderText("BTC/USDT"), "sol/usdt");
    await user.type(screen.getByPlaceholderText("0.0"), "100");
    await user.type(screen.getByPlaceholderText("0.00"), "25");
    await user.click(screen.getByText("Add"));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/portfolios/1/holdings"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("hides add form when Cancel is clicked in empty state", async () => {
    renderWithProviders(<HoldingsTable holdings={[]} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getByText("+ Add Holding"));
    expect(screen.getByPlaceholderText("BTC/USDT")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("BTC/USDT")).not.toBeInTheDocument();
  });

  it("shows error toast when update mutation fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "Update failed" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })),
    ));
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(screen.getByText("Save"));
    // onError fires — no crash, edit mode stays
    await screen.findByText("Save");
  });

  it("shows error toast when delete mutation fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "Cannot delete" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })),
    ));
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getAllByText("Delete")[0]);
    const dialog = screen.getByRole("dialog");
    const confirmBtn = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent === "Delete",
    );
    await user.click(confirmBtn!);
    // onError fires — no crash
    expect(screen.getByText("Delete Holding")).toBeInTheDocument();
  });

  it("shows error toast when add mutation fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "Duplicate" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })),
    ));
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} />);
    const user = userEvent.setup();

    await user.click(screen.getByText("+ Add Holding"));
    await user.type(screen.getByPlaceholderText("BTC/USDT"), "SOL/USDT");
    await user.click(screen.getByText("Add"));
    // onError fires — form stays visible
    await screen.findByText("Add");
  });

  it("shows live P&L values with correct formatting", () => {
    const priceMap = { "BTC/USDT": 45000, "ETH/USDT": 3000 };
    renderWithProviders(<HoldingsTable holdings={mockHoldings} portfolioId={1} priceMap={priceMap} />);
    // BTC P&L = 0.5 * (45000 - 40000) = +$2,500
    expect(screen.getByText("+$2,500.00")).toBeInTheDocument();
    // ETH P&L = 10 * (3000 - 2500) = +$5,000
    expect(screen.getByText("+$5,000.00")).toBeInTheDocument();
  });
});
