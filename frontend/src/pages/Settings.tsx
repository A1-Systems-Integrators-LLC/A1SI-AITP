import { useApi } from "../hooks/useApi";
import { exchangesApi } from "../api/exchanges";
import type { ExchangeInfo } from "../types";

export function Settings() {
  const { data: exchanges } = useApi<ExchangeInfo[]>(
    ["exchanges"],
    exchangesApi.list,
  );

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Settings</h2>

      <div className="max-w-2xl space-y-6">
        {/* Exchange configuration */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Exchange Configuration</h3>
          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            Configure API keys for exchanges. Keys are stored in the .env file
            on the server.
          </p>
          {exchanges && (
            <div className="space-y-2">
              {exchanges.map((ex) => (
                <div
                  key={ex.id}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
                >
                  <div>
                    <p className="font-medium">{ex.name}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Tickers: {ex.has_fetch_tickers ? "Yes" : "No"} | OHLCV:{" "}
                      {ex.has_fetch_ohlcv ? "Yes" : "No"}
                    </p>
                  </div>
                  <span className="rounded-full bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)]">
                    {ex.id}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* About */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-2 text-lg font-semibold">About</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            crypto-investor v0.1.0
          </p>
        </div>
      </div>
    </div>
  );
}
