import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { portfoliosApi } from "../api/portfolios";
import { marketApi } from "../api/market";
import { HoldingsTable } from "../components/HoldingsTable";
import { QueryResult } from "../components/QueryResult";
import { useToast } from "../hooks/useToast";
import { useTickerStream } from "../hooks/useTickerStream";
import type { Portfolio, TickerData } from "../types";

export function PortfolioPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newExchange, setNewExchange] = useState("binance");
  const [newDescription, setNewDescription] = useState("");
  const [editingPortfolioId, setEditingPortfolioId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editExchange, setEditExchange] = useState("binance");
  const [editDescription, setEditDescription] = useState("");

  useEffect(() => { document.title = "Portfolio | Crypto Investor"; }, []);

  const portfoliosQuery = useQuery<Portfolio[]>({
    queryKey: ["portfolios"],
    queryFn: portfoliosApi.list,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      portfoliosApi.create({ name: newName, exchange_id: newExchange, description: newDescription }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setShowCreateForm(false);
      setNewName("");
      setNewDescription("");
      toast("Portfolio created", "success");
    },
    onError: (err) => toast((err as Error).message || "Failed to create portfolio", "error"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; exchange_id?: string; description?: string } }) =>
      portfoliosApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setEditingPortfolioId(null);
      toast("Portfolio updated", "success");
    },
    onError: (err) => toast((err as Error).message || "Failed to update portfolio", "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => portfoliosApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      toast("Portfolio deleted", "info");
    },
    onError: (err) => toast((err as Error).message || "Failed to delete portfolio", "error"),
  });

  const startEditPortfolio = (p: Portfolio) => {
    setEditingPortfolioId(p.id);
    setEditName(p.name);
    setEditExchange(p.exchange_id ?? "binance");
    setEditDescription(p.description || "");
  };

  const cancelEditPortfolio = () => {
    setEditingPortfolioId(null);
  };

  const saveEditPortfolio = (id: number) => {
    updateMutation.mutate({ id, data: { name: editName, exchange_id: editExchange, description: editDescription } });
  };

  const handleDeletePortfolio = (id: number, name: string) => {
    if (window.confirm(`Are you sure you want to delete portfolio "${name}"? This action cannot be undone.`)) {
      deleteMutation.mutate(id);
    }
  };

  // Collect all unique symbols across all portfolios
  const allSymbols = portfoliosQuery.data
    ?.flatMap((p) => p.holdings.map((h) => h.symbol))
    .filter((s, i, arr) => arr.indexOf(s) === i) ?? [];

  const { data: tickers } = useQuery<TickerData[]>({
    queryKey: ["tickers", allSymbols.join(",")],
    queryFn: () => marketApi.tickers(allSymbols.length > 0 ? allSymbols : undefined),
    enabled: allSymbols.length > 0,
    refetchInterval: 30000,
  });

  // Real-time ticker data via WebSocket (overrides HTTP polling)
  const { tickers: wsTickers } = useTickerStream();

  // Build a price lookup map: WS tickers override HTTP tickers
  const priceMap: Record<string, number> = {};
  tickers?.forEach((t) => {
    priceMap[t.symbol] = t.price;
  });
  for (const [symbol, data] of Object.entries(wsTickers)) {
    priceMap[symbol] = data.price;
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold">Portfolio</h2>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white"
        >
          {showCreateForm ? "Cancel" : "Create Portfolio"}
        </button>
      </div>

      {showCreateForm && (
        <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">New Portfolio</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label htmlFor="portfolio-name" className="mb-1 block text-xs text-[var(--color-text-muted)]">Name</label>
              <input
                id="portfolio-name"
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="My Portfolio"
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="portfolio-exchange" className="mb-1 block text-xs text-[var(--color-text-muted)]">Exchange</label>
              <select
                id="portfolio-exchange"
                value={newExchange}
                onChange={(e) => setNewExchange(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="binance">Binance</option>
                <option value="bybit">Bybit</option>
                <option value="kraken">Kraken</option>
              </select>
            </div>
            <div>
              <label htmlFor="portfolio-desc" className="mb-1 block text-xs text-[var(--color-text-muted)]">Description</label>
              <input
                id="portfolio-desc"
                type="text"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Optional description"
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
          </div>
          <button
            onClick={() => createMutation.mutate()}
            disabled={!newName.trim() || createMutation.isPending}
            className="mt-3 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {createMutation.isPending ? "Creating..." : "Create"}
          </button>
        </div>
      )}

      {portfoliosQuery.isLoading && (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-[var(--color-border)]" />
            ))}
          </div>
        </div>
      )}

      <QueryResult query={portfoliosQuery}>
        {(portfolios) =>
          portfolios.length === 0 ? (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <p className="text-[var(--color-text-muted)]">
                No portfolios yet. Create one to get started.
              </p>
            </div>
          ) : (
            <>
              {portfolios.map((p) => {
                const totalCost = p.holdings.reduce((sum, h) => sum + (h.amount ?? 0) * (h.avg_buy_price ?? 0), 0);
                const totalValue = p.holdings.reduce((sum, h) => {
                  const amt = h.amount ?? 0;
                  const price = priceMap[h.symbol];
                  return sum + (price != null ? amt * price : amt * (h.avg_buy_price ?? 0));
                }, 0);
                const unrealizedPnl = totalValue - totalCost;
                const pnlPct = totalCost > 0 ? (unrealizedPnl / totalCost) * 100 : 0;
                const hasLivePrices = p.holdings.some((h) => priceMap[h.symbol] != null);

                return (
                  <div
                    key={p.id}
                    className="mb-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6"
                  >
                    {editingPortfolioId === p.id ? (
                      <div className="mb-4">
                        <h3 className="mb-3 text-lg font-semibold">Edit Portfolio</h3>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                          <div>
                            <label htmlFor={`edit-name-${p.id}`} className="mb-1 block text-xs text-[var(--color-text-muted)]">Name</label>
                            <input
                              id={`edit-name-${p.id}`}
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                            />
                          </div>
                          <div>
                            <label htmlFor={`edit-exchange-${p.id}`} className="mb-1 block text-xs text-[var(--color-text-muted)]">Exchange</label>
                            <select
                              id={`edit-exchange-${p.id}`}
                              value={editExchange}
                              onChange={(e) => setEditExchange(e.target.value)}
                              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                            >
                              <option value="binance">Binance</option>
                              <option value="bybit">Bybit</option>
                              <option value="kraken">Kraken</option>
                            </select>
                          </div>
                          <div>
                            <label htmlFor={`edit-desc-${p.id}`} className="mb-1 block text-xs text-[var(--color-text-muted)]">Description</label>
                            <input
                              id={`edit-desc-${p.id}`}
                              type="text"
                              value={editDescription}
                              onChange={(e) => setEditDescription(e.target.value)}
                              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                            />
                          </div>
                        </div>
                        <div className="mt-3 flex gap-2">
                          <button
                            onClick={() => saveEditPortfolio(p.id)}
                            disabled={!editName.trim() || updateMutation.isPending}
                            className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                          >
                            {updateMutation.isPending ? "Saving..." : "Save"}
                          </button>
                          <button
                            onClick={cancelEditPortfolio}
                            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm text-[var(--color-text-muted)]"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="mb-4 flex items-start justify-between">
                        <div>
                          <h3 className="mb-1 text-lg font-semibold">{p.name}</h3>
                          <p className="text-sm text-[var(--color-text-muted)]">
                            {p.exchange_id} &middot; {p.description || "No description"}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          <button
                            onClick={() => startEditPortfolio(p)}
                            className="rounded bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeletePortfolio(p.id, p.name)}
                            disabled={deleteMutation.isPending}
                            className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-400 hover:bg-red-500/20 disabled:opacity-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    )}

                    {p.holdings.length > 0 && (
                      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                        <div className="rounded-lg bg-[var(--color-bg)] p-3">
                          <p className="text-xs text-[var(--color-text-muted)]">Total Value</p>
                          <p className="font-mono text-lg font-bold">${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                        </div>
                        <div className="rounded-lg bg-[var(--color-bg)] p-3">
                          <p className="text-xs text-[var(--color-text-muted)]">Total Cost</p>
                          <p className="font-mono text-lg font-bold">${totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                        </div>
                        <div className="rounded-lg bg-[var(--color-bg)] p-3">
                          <p className="text-xs text-[var(--color-text-muted)]">Unrealized P&L</p>
                          <p className={`font-mono text-lg font-bold ${unrealizedPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {unrealizedPnl >= 0 ? "+" : ""}${unrealizedPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </p>
                        </div>
                        <div className="rounded-lg bg-[var(--color-bg)] p-3">
                          <p className="text-xs text-[var(--color-text-muted)]">P&L %</p>
                          <p className={`font-mono text-lg font-bold ${pnlPct >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                          </p>
                        </div>
                      </div>
                    )}

                    {!hasLivePrices && p.holdings.length > 0 && (
                      <p className="mb-2 text-xs text-[var(--color-text-muted)]">
                        Live prices unavailable. Values shown at cost basis.
                      </p>
                    )}

                    <HoldingsTable holdings={p.holdings} portfolioId={p.id} priceMap={priceMap} />
                  </div>
                );
              })}
            </>
          )
        }
      </QueryResult>
    </div>
  );
}
