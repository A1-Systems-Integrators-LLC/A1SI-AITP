import { useApi } from "../hooks/useApi";
import { portfoliosApi } from "../api/portfolios";
import { marketApi } from "../api/market";
import { HoldingsTable } from "../components/HoldingsTable";
import { useQuery } from "@tanstack/react-query";
import type { Portfolio, TickerData } from "../types";

export function PortfolioPage() {
  const { data: portfolios, isLoading } = useApi<Portfolio[]>(
    ["portfolios"],
    portfoliosApi.list,
  );

  // Collect all unique symbols across all portfolios
  const allSymbols = portfolios
    ?.flatMap((p) => p.holdings.map((h) => h.symbol))
    .filter((s, i, arr) => arr.indexOf(s) === i) ?? [];

  const { data: tickers } = useQuery<TickerData[]>({
    queryKey: ["tickers", allSymbols.join(",")],
    queryFn: () => marketApi.tickers(allSymbols.length > 0 ? allSymbols : undefined),
    enabled: allSymbols.length > 0,
    refetchInterval: 30000,
  });

  // Build a price lookup map from tickers
  const priceMap: Record<string, number> = {};
  tickers?.forEach((t) => {
    priceMap[t.symbol] = t.price;
  });

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Portfolio</h2>

      {isLoading && <p>Loading portfolios...</p>}

      {portfolios && portfolios.length === 0 && (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <p className="text-[var(--color-text-muted)]">
            No portfolios yet. Create one to get started.
          </p>
        </div>
      )}

      {portfolios?.map((p) => {
        const totalCost = p.holdings.reduce((sum, h) => sum + h.amount * h.avg_buy_price, 0);
        const totalValue = p.holdings.reduce((sum, h) => {
          const price = priceMap[h.symbol];
          return sum + (price != null ? h.amount * price : h.amount * h.avg_buy_price);
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

            <HoldingsTable holdings={p.holdings} priceMap={priceMap} />
          </div>
        );
      })}
    </div>
  );
}
