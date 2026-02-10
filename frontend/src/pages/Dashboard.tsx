import { useApi } from "../hooks/useApi";
import { exchangesApi } from "../api/exchanges";
import { portfoliosApi } from "../api/portfolios";
import type { ExchangeInfo, Portfolio } from "../types";

export function Dashboard() {
  const exchanges = useApi<ExchangeInfo[]>(["exchanges"], exchangesApi.list);
  const portfolios = useApi<Portfolio[]>(["portfolios"], portfoliosApi.list);

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Dashboard</h2>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Portfolios summary */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-3 text-sm font-medium text-[var(--color-text-muted)]">
            Portfolios
          </h3>
          {portfolios.isLoading && <p className="text-sm">Loading...</p>}
          {portfolios.data && (
            <p className="text-3xl font-bold">{portfolios.data.length}</p>
          )}
        </div>

        {/* Exchanges */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-3 text-sm font-medium text-[var(--color-text-muted)]">
            Supported Exchanges
          </h3>
          {exchanges.isLoading && <p className="text-sm">Loading...</p>}
          {exchanges.data && (
            <p className="text-3xl font-bold">{exchanges.data.length}</p>
          )}
        </div>

        {/* Status */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-3 text-sm font-medium text-[var(--color-text-muted)]">
            Status
          </h3>
          <p className="text-3xl font-bold text-[var(--color-success)]">
            Online
          </p>
        </div>
      </div>

      {/* Exchange list */}
      {exchanges.data && (
        <div className="mt-8 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Available Exchanges</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {exchanges.data.map((ex) => (
              <div
                key={ex.id}
                className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] p-3"
              >
                <div>
                  <p className="font-medium">{ex.name}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {ex.id}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
