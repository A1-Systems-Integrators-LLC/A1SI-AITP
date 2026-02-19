import { useState } from "react";
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

  const portfoliosQuery = useQuery<Portfolio[]>({
    queryKey: ["portfolios"],
    queryFn: portfoliosApi.list,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      portfoliosApi.create({ name: newName, exchange_id: newExchange }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setShowCreateForm(false);
      setNewName("");
      setNewDescription("");
      toast("Portfolio created", "success");
    },
    onError: (err) => toast((err as Error).message || "Failed to create portfolio", "error"),
  });

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
                    <h3 className="mb-1 text-lg font-semibold">{p.name}</h3>
                    <p className="mb-4 text-sm text-[var(--color-text-muted)]">
                      {p.exchange_id} &middot; {p.description || "No description"}
                    </p>

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
