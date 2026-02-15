import type { Holding } from "../types";

interface HoldingsTableProps {
  holdings: Holding[];
  priceMap?: Record<string, number>;
}

export function HoldingsTable({ holdings, priceMap = {} }: HoldingsTableProps) {
  if (holdings.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No holdings yet.
      </p>
    );
  }

  const hasLivePrices = holdings.some((h) => priceMap[h.symbol] != null);

  // Totals
  let totalCost = 0;
  let totalValue = 0;
  for (const h of holdings) {
    const cost = h.amount * h.avg_buy_price;
    const price = priceMap[h.symbol];
    const value = price != null ? h.amount * price : cost;
    totalCost += cost;
    totalValue += value;
  }
  const totalPnl = totalValue - totalCost;

  return (
    <div className="overflow-x-auto">
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
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const cost = h.amount * h.avg_buy_price;
            const price = priceMap[h.symbol];
            const value = price != null ? h.amount * price : null;
            const pnl = value != null ? value - cost : null;
            const pnlPct = cost > 0 && pnl != null ? (pnl / cost) * 100 : null;

            return (
              <tr
                key={h.id}
                className="border-b border-[var(--color-border)]"
              >
                <td className="py-2 font-medium">{h.symbol}</td>
                <td className="py-2">{h.amount.toFixed(6)}</td>
                <td className="py-2">${h.avg_buy_price.toLocaleString()}</td>
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
          </tr>
        </tbody>
      </table>
    </div>
  );
}
