import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  exchangeConfigsApi,
  dataSourcesApi,
} from "../../api/exchangeConfigs";
import { useToast } from "../../hooks/useToast";
import { getErrorMessage } from "../../utils/errors";
import type {
  ExchangeConfig,
  DataSourceConfig,
  DataSourceConfigCreate,
} from "../../types";

const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"];

function DataSourceForm({
  exchanges,
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  exchanges: ExchangeConfig[];
  onSubmit: (data: DataSourceConfigCreate) => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  const [exchangeConfigId, setExchangeConfigId] = useState(exchanges[0]?.id ?? 0);
  const [symbolsText, setSymbolsText] = useState("");
  const [selectedTimeframes, setSelectedTimeframes] = useState<string[]>(["1h"]);
  const [fetchInterval, setFetchInterval] = useState(60);

  const toggleTimeframe = (tf: string) => {
    setSelectedTimeframes((prev) =>
      prev.includes(tf) ? prev.filter((t) => t !== tf) : [...prev, tf],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const symbols = symbolsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    onSubmit({
      exchange_config: exchangeConfigId,
      symbols,
      timeframes: selectedTimeframes,
      fetch_interval_minutes: fetchInterval,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Exchange</label>
        <select
          value={exchangeConfigId}
          onChange={(e) => setExchangeConfigId(Number(e.target.value))}
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        >
          {exchanges.map((ex) => (
            <option key={ex.id} value={ex.id}>{ex.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Symbols (comma-separated)
        </label>
        <input
          type="text"
          value={symbolsText}
          onChange={(e) => setSymbolsText(e.target.value)}
          required
          placeholder="BTC/USDT, ETH/USDT"
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm font-mono"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Timeframes</label>
        <div className="flex flex-wrap gap-2">
          {TIMEFRAME_OPTIONS.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => toggleTimeframe(tf)}
              className={`rounded-lg border px-3 py-1 text-sm ${
                selectedTimeframes.includes(tf)
                  ? "border-blue-500 bg-blue-600 text-white"
                  : "border-[var(--color-border)] bg-[var(--color-bg)]"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Fetch interval (minutes)
        </label>
        <input
          type="number"
          value={fetchInterval}
          onChange={(e) => setFetchInterval(Number(e.target.value))}
          min={1}
          className="w-32 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        />
      </div>

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isSubmitting ? "Saving..." : "Add Data Source"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function DataSourceSection() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: configs } = useQuery({
    queryKey: ["exchange-configs"],
    queryFn: exchangeConfigsApi.list,
  });

  const { data: dataSources } = useQuery({
    queryKey: ["data-sources"],
    queryFn: dataSourcesApi.list,
  });

  const [showAddDataSource, setShowAddDataSource] = useState(false);

  const createDSMutation = useMutation({
    mutationFn: dataSourcesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-sources"] });
      setShowAddDataSource(false);
      toast("Data source created", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to create data source", "error"),
  });

  const deleteDSMutation = useMutation({
    mutationFn: dataSourcesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-sources"] });
      toast("Data source deleted", "info");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to delete data source", "error"),
  });

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Data Sources</h3>
        {!showAddDataSource && configs && configs.length > 0 && (
          <button
            onClick={() => setShowAddDataSource(true)}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
          >
            Add Data Source
          </button>
        )}
      </div>

      <p className="mb-4 text-sm text-[var(--color-text-muted)]">
        Configure which symbols and timeframes to fetch from each exchange.
      </p>

      {dataSources && dataSources.length > 0 && (
        <div className="mb-4 space-y-2">
          {dataSources.map((ds: DataSourceConfig) => (
            <div
              key={ds.id}
              className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium">{ds.exchange_name}</p>
                  {!ds.is_active && (
                    <span className="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">
                      inactive
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {ds.symbols.map((s) => (
                    <span
                      key={s}
                      className="rounded bg-[var(--color-bg)] px-1.5 py-0.5 text-xs font-mono"
                    >
                      {s}
                    </span>
                  ))}
                  <span className="text-xs text-[var(--color-text-muted)]">|</span>
                  {ds.timeframes.map((tf) => (
                    <span
                      key={tf}
                      className="rounded bg-blue-900/30 px-1.5 py-0.5 text-xs text-blue-300"
                    >
                      {tf}
                    </span>
                  ))}
                </div>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                  Every {ds.fetch_interval_minutes}min
                  {ds.last_fetched_at &&
                    ` | Last: ${new Date(ds.last_fetched_at).toLocaleString()}`}
                </p>
              </div>
              <button
                onClick={() => deleteDSMutation.mutate(ds.id)}
                className="rounded-lg border border-red-700 px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/30"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}

      {showAddDataSource && configs && (
        <div className="rounded-lg border border-blue-500/50 bg-[var(--color-bg)] p-4">
          <DataSourceForm
            exchanges={configs}
            onSubmit={(data) => createDSMutation.mutate(data)}
            onCancel={() => setShowAddDataSource(false)}
            isSubmitting={createDSMutation.isPending}
          />
        </div>
      )}
    </div>
  );
}
