import type { Holding } from "../types";

interface HoldingsTableProps {
  holdings: Holding[];
}

export function HoldingsTable({ holdings }: HoldingsTableProps) {
  if (holdings.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No holdings yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
            <th className="pb-2">Symbol</th>
            <th className="pb-2">Amount</th>
            <th className="pb-2">Avg Buy Price</th>
            <th className="pb-2">Value</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <tr
              key={h.id}
              className="border-b border-[var(--color-border)]"
            >
              <td className="py-2 font-medium">{h.symbol}</td>
              <td className="py-2">{h.amount.toFixed(6)}</td>
              <td className="py-2">${h.avg_buy_price.toLocaleString()}</td>
              <td className="py-2">
                ${(h.amount * h.avg_buy_price).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
