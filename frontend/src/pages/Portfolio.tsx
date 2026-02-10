import { useApi } from "../hooks/useApi";
import { portfoliosApi } from "../api/portfolios";
import { HoldingsTable } from "../components/HoldingsTable";
import type { Portfolio } from "../types";

export function PortfolioPage() {
  const { data: portfolios, isLoading } = useApi<Portfolio[]>(
    ["portfolios"],
    portfoliosApi.list,
  );

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

      {portfolios?.map((p) => (
        <div
          key={p.id}
          className="mb-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6"
        >
          <h3 className="mb-1 text-lg font-semibold">{p.name}</h3>
          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            {p.exchange_id} &middot; {p.description || "No description"}
          </p>
          <HoldingsTable holdings={p.holdings} />
        </div>
      ))}
    </div>
  );
}
