import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { portfoliosApi } from "../api/portfolios";
import { useToast } from "../hooks/useToast";
import type { Holding } from "../types";

interface HoldingsTableProps {
  holdings: Holding[];
  portfolioId: number;
  priceMap?: Record<string, number>;
}

export function HoldingsTable({ holdings, portfolioId, priceMap = {} }: HoldingsTableProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editAmount, setEditAmount] = useState("");
  const [editPrice, setEditPrice] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [newPrice, setNewPrice] = useState("");

  const updateMutation = useMutation({
    mutationFn: ({ holdingId, data }: { holdingId: number; data: { amount?: number; avg_buy_price?: number } }) =>
      portfoliosApi.updateHolding(portfolioId, holdingId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setEditingId(null);
    },
    onError: (err) => toast((err as Error).message || "Failed to update holding", "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: (holdingId: number) => portfoliosApi.deleteHolding(portfolioId, holdingId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portfolios"] }),
    onError: (err) => toast((err as Error).message || "Failed to delete holding", "error"),
  });

  const addMutation = useMutation({
    mutationFn: (data: { symbol: string; amount?: number; avg_buy_price?: number }) =>
      portfoliosApi.addHolding(portfolioId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setShowAddForm(false);
      setNewSymbol("");
      setNewAmount("");
      setNewPrice("");
    },
    onError: (err) => toast((err as Error).message || "Failed to add holding", "error"),
  });

  const startEdit = (h: Holding) => {
    setEditingId(h.id);
    setEditAmount(String(h.amount ?? 0));
    setEditPrice(String(h.avg_buy_price ?? 0));
  };

  const saveEdit = (holdingId: number) => {
    updateMutation.mutate({
      holdingId,
      data: { amount: Number(editAmount), avg_buy_price: Number(editPrice) },
    });
  };

  const addHoldingForm = showAddForm && (
    <div className="mb-3 flex flex-wrap items-end gap-2">
      <div>
        <label htmlFor={`add-symbol-${portfolioId}`} className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
        <input
          id={`add-symbol-${portfolioId}`}
          type="text"
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
          placeholder="BTC/USDT"
          className="w-28 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
        />
      </div>
      <div>
        <label htmlFor={`add-amount-${portfolioId}`} className="mb-1 block text-xs text-[var(--color-text-muted)]">Amount</label>
        <input
          id={`add-amount-${portfolioId}`}
          type="number"
          value={newAmount}
          onChange={(e) => setNewAmount(e.target.value)}
          placeholder="0.0"
          step="any"
          className="w-24 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
        />
      </div>
      <div>
        <label htmlFor={`add-price-${portfolioId}`} className="mb-1 block text-xs text-[var(--color-text-muted)]">Avg Buy Price</label>
        <input
          id={`add-price-${portfolioId}`}
          type="number"
          value={newPrice}
          onChange={(e) => setNewPrice(e.target.value)}
          placeholder="0.00"
          step="any"
          className="w-24 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
        />
      </div>
      <button
        onClick={() =>
          addMutation.mutate({
            symbol: newSymbol.trim(),
            amount: newAmount ? Number(newAmount) : undefined,
            avg_buy_price: newPrice ? Number(newPrice) : undefined,
          })
        }
        disabled={!newSymbol.trim() || addMutation.isPending}
        className="rounded bg-green-500/20 px-3 py-1 text-sm text-green-400 hover:bg-green-500/30 disabled:opacity-50"
      >
        {addMutation.isPending ? "Adding..." : "Add"}
      </button>
      <button
        onClick={() => setShowAddForm(false)}
        className="rounded bg-[var(--color-bg)] px-3 py-1 text-sm text-[var(--color-text-muted)]"
      >
        Cancel
      </button>
    </div>
  );

  if (holdings.length === 0) {
    return (
      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm text-[var(--color-text-muted)]">No holdings yet.</p>
          {!showAddForm && (
            <button
              onClick={() => setShowAddForm(true)}
              className="rounded bg-[var(--color-primary)]/20 px-3 py-1 text-xs text-[var(--color-primary)] hover:bg-[var(--color-primary)]/30"
            >
              + Add Holding
            </button>
          )}
        </div>
        {addHoldingForm}
      </div>
    );
  }

  const hasLivePrices = holdings.some((h) => priceMap[h.symbol] != null);

  let totalCost = 0;
  let totalValue = 0;
  for (const h of holdings) {
    const amt = h.amount ?? 0;
    const avg = h.avg_buy_price ?? 0;
    const cost = amt * avg;
    const price = priceMap[h.symbol];
    const value = price != null ? amt * price : cost;
    totalCost += cost;
    totalValue += value;
  }
  const totalPnl = totalValue - totalCost;

  return (
    <div className="overflow-x-auto">
      <div className="mb-2 flex justify-end">
        {!showAddForm && (
          <button
            onClick={() => setShowAddForm(true)}
            className="rounded bg-[var(--color-primary)]/20 px-3 py-1 text-xs text-[var(--color-primary)] hover:bg-[var(--color-primary)]/30"
          >
            + Add Holding
          </button>
        )}
      </div>
      {addHoldingForm}
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
            <th className="pb-2">Symbol</th>
            <th className="pb-2">Amount</th>
            <th className="pb-2">Avg Buy Price</th>
            {hasLivePrices && <th className="pb-2">Current Price</th>}
            <th className="pb-2">Cost Basis</th>
            {hasLivePrices && <th className="pb-2">Current Value</th>}
            {hasLivePrices && <th className="pb-2">P&L</th>}
            {hasLivePrices && <th className="pb-2">P&L %</th>}
            <th className="pb-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const amt = h.amount ?? 0;
            const avg = h.avg_buy_price ?? 0;
            const cost = amt * avg;
            const price = priceMap[h.symbol];
            const value = price != null ? amt * price : null;
            const pnl = value != null ? value - cost : null;
            const pnlPct = cost > 0 && pnl != null ? (pnl / cost) * 100 : null;
            const isEditing = editingId === h.id;

            return (
              <tr
                key={h.id}
                className="border-b border-[var(--color-border)]"
              >
                <td className="py-2 font-medium">{h.symbol}</td>
                <td className="py-2">
                  {isEditing ? (
                    <input
                      type="number"
                      value={editAmount}
                      onChange={(e) => setEditAmount(e.target.value)}
                      className="w-24 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs"
                      step="any"
                    />
                  ) : (
                    amt.toFixed(6)
                  )}
                </td>
                <td className="py-2">
                  {isEditing ? (
                    <input
                      type="number"
                      value={editPrice}
                      onChange={(e) => setEditPrice(e.target.value)}
                      className="w-24 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs"
                      step="any"
                    />
                  ) : (
                    `$${avg.toLocaleString()}`
                  )}
                </td>
                {hasLivePrices && (
                  <td className="py-2">
                    {price != null ? `$${price.toLocaleString()}` : "\u2014"}
                  </td>
                )}
                <td className="py-2">${cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                {hasLivePrices && (
                  <td className="py-2">
                    {value != null ? `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "\u2014"}
                  </td>
                )}
                {hasLivePrices && (
                  <td className={`py-2 font-mono ${pnl != null && pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {pnl != null ? `${pnl >= 0 ? "+" : ""}$${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "\u2014"}
                  </td>
                )}
                {hasLivePrices && (
                  <td className={`py-2 font-mono ${pnlPct != null && pnlPct >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {pnlPct != null ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%` : "\u2014"}
                  </td>
                )}
                <td className="py-2 text-right">
                  {isEditing ? (
                    <span className="flex justify-end gap-1">
                      <button
                        onClick={() => saveEdit(h.id)}
                        disabled={updateMutation.isPending}
                        className="rounded bg-green-500/20 px-2 py-1 text-xs text-green-400 hover:bg-green-500/30"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="rounded bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)]"
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <span className="flex justify-end gap-1">
                      <button
                        onClick={() => startEdit(h)}
                        className="rounded bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteMutation.mutate(h.id)}
                        disabled={deleteMutation.isPending}
                        className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-400 hover:bg-red-500/20"
                      >
                        Delete
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
          {/* Total row */}
          <tr className="font-medium">
            <td className="py-2">Total</td>
            <td className="py-2"></td>
            <td className="py-2"></td>
            {hasLivePrices && <td className="py-2"></td>}
            <td className="py-2">${totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
            {hasLivePrices && (
              <td className="py-2">${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
            )}
            {hasLivePrices && (
              <td className={`py-2 font-mono ${totalPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                {totalPnl >= 0 ? "+" : ""}${totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </td>
            )}
            {hasLivePrices && <td className="py-2"></td>}
            <td className="py-2"></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
