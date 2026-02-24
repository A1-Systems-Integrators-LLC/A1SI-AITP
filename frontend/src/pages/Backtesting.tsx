import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backtestApi } from "../api/backtest";
import { useJobPolling } from "../hooks/useJobPolling";
import { useToast } from "../hooks/useToast";
import { useAssetClass } from "../hooks/useAssetClass";
import { ProgressBar } from "../components/ProgressBar";
import { EquityCurve } from "../components/EquityCurve";
import {
  BACKTEST_FRAMEWORKS,
  DEFAULT_SYMBOL,
  EXCHANGE_OPTIONS,
  TIMEFRAME_OPTIONS,
} from "../constants/assetDefaults";
import type { BacktestComparison, BacktestResult, StrategyInfo } from "../types";

export function Backtesting() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();

  useEffect(() => { document.title = "Backtesting | A1SI-AITP"; }, []);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [framework, setFramework] = useState(BACKTEST_FRAMEWORKS[assetClass][0]?.value ?? "freqtrade");
  const [strategy, setStrategy] = useState("");
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL[assetClass]);
  const [timeframe, setTimeframe] = useState("1h");
  const [timerange, setTimerange] = useState("");
  const [exchange, setExchange] = useState(EXCHANGE_OPTIONS[assetClass][0]?.value ?? "binance");

  const { data: strategies, isError: strategiesError } = useQuery<StrategyInfo[]>({
    queryKey: ["backtest-strategies"],
    queryFn: backtestApi.strategies,
  });

  const { data: history, isLoading: historyLoading, isError: historyError } = useQuery<BacktestResult[]>({
    queryKey: ["backtest-results"],
    queryFn: () => backtestApi.results(10),
  });

  const job = useJobPolling(activeJobId);

  const runMutation = useMutation({
    mutationFn: () =>
      backtestApi.run({ framework, strategy, symbol, timeframe, timerange, exchange, asset_class: assetClass }),
    onSuccess: (data) => setActiveJobId(data.job_id),
    onError: (err) => toast((err as Error).message || "Failed to start backtest", "error"),
  });

  const compareQuery = useQuery<BacktestComparison>({
    queryKey: ["backtest-compare", Array.from(selectedIds).sort().join(",")],
    queryFn: () => backtestApi.compare(Array.from(selectedIds)),
    enabled: selectedIds.size >= 2,
  });

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const isJobActive = job.data?.status === "pending" || job.data?.status === "running";
  const jobResult = job.data?.result as Record<string, unknown> | undefined;
  const metrics = (jobResult?.metrics ?? {}) as Record<string, unknown>;
  const trades = (jobResult?.trades ?? []) as Record<string, unknown>[];

  const filteredStrategies = strategies?.filter((s) => s.framework === framework) ?? [];

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Backtesting</h2>

      {(strategiesError || historyError) && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Failed to load {strategiesError ? "strategies" : "backtest history"}. Some features may be unavailable.
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Config Form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Configuration</h3>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Framework</label>
              <div className="flex gap-1">
                {BACKTEST_FRAMEWORKS[assetClass].map((fw) => (
                  <button
                    key={fw.value}
                    onClick={() => { setFramework(fw.value); setStrategy(""); }}
                    className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium ${
                      framework === fw.value
                        ? "bg-[var(--color-primary)] text-white"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {fw.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label htmlFor="bt-strategy" className="mb-1 block text-xs text-[var(--color-text-muted)]">Strategy</label>
              {filteredStrategies.length > 0 ? (
                <select
                  id="bt-strategy"
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                >
                  <option value="">Select strategy...</option>
                  {filteredStrategies.map((s) => (
                    <option key={s.name} value={s.name}>{s.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  id="bt-strategy"
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  placeholder="Strategy name"
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                />
              )}
            </div>
            <div>
              <label htmlFor="bt-symbol" className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
              <input
                id="bt-symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="bt-timeframe" className="mb-1 block text-xs text-[var(--color-text-muted)]">Timeframe</label>
              <select
                id="bt-timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                {TIMEFRAME_OPTIONS[assetClass].map((tf) => (
                  <option key={tf.value} value={tf.value}>{tf.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="bt-exchange" className="mb-1 block text-xs text-[var(--color-text-muted)]">Exchange</label>
              <select
                id="bt-exchange"
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="sample">Sample</option>
                {EXCHANGE_OPTIONS[assetClass].map((ex) => (
                  <option key={ex.value} value={ex.value}>{ex.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="bt-timerange" className="mb-1 block text-xs text-[var(--color-text-muted)]">Time Range</label>
              <input
                id="bt-timerange"
                value={timerange}
                onChange={(e) => setTimerange(e.target.value)}
                placeholder="e.g. 20230101-20231231"
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => runMutation.mutate()}
              disabled={isJobActive || runMutation.isPending}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {runMutation.isPending ? "Starting..." : "Run Backtest"}
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="lg:col-span-3 space-y-4">
          {/* Job progress */}
          {activeJobId && job.data && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-medium">Backtest Job</h3>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    job.data.status === "completed"
                      ? "bg-green-500/20 text-green-400"
                      : job.data.status === "failed"
                        ? "bg-red-500/20 text-red-400"
                        : "bg-blue-500/20 text-blue-400"
                  }`}
                >
                  {job.data.status}
                </span>
              </div>
              {isJobActive && (
                <ProgressBar progress={job.data.progress} message={job.data.progress_message} />
              )}
              {job.data.error && (
                <p className="mt-2 text-xs text-red-400">{job.data.error}</p>
              )}
            </div>
          )}

          {/* Metrics */}
          {job.data?.status === "completed" && Object.keys(metrics).length > 0 && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <h3 className="mb-4 text-lg font-semibold">Results</h3>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.entries(metrics)
                  .filter(([k]) => k !== "stdout_tail")
                  .map(([key, value]) => (
                    <div key={key} className="rounded-lg bg-[var(--color-bg)] p-3">
                      <p className="text-xs text-[var(--color-text-muted)]">{key.replace(/_/g, " ")}</p>
                      <p className="font-mono text-sm font-medium">
                        {typeof value === "number" ? value.toFixed(4) : String(value)}
                      </p>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Equity Curve */}
          {job.data?.status === "completed" && trades.length > 0 && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <EquityCurve trades={trades} />
            </div>
          )}

          {/* History */}
          {historyLoading && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <h3 className="mb-4 text-lg font-semibold">History</h3>
              <div className="space-y-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-[var(--color-border)]" />
                ))}
              </div>
            </div>
          )}
          {history && history.length > 0 && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-lg font-semibold">History</h3>
                <div className="flex gap-2">
                  {selectedIds.size >= 2 && (
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {selectedIds.size} selected for comparison
                    </span>
                  )}
                  <button
                    onClick={() => queryClient.invalidateQueries({ queryKey: ["backtest-results"] })}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
                    title="Refresh history"
                  >
                    &#8635; Refresh
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                      <th className="pb-2 pr-2 w-8"></th>
                      <th className="pb-2 pr-4">Framework</th>
                      <th className="pb-2 pr-4">Strategy</th>
                      <th className="pb-2 pr-4">Symbol</th>
                      <th className="pb-2 pr-4">Timeframe</th>
                      <th className="pb-2 pr-4 text-right">Sharpe</th>
                      <th className="pb-2 pr-4 text-right">Max DD</th>
                      <th className="pb-2 pr-4 text-right">Win Rate</th>
                      <th className="pb-2 pr-4 text-right">Trades</th>
                      <th className="pb-2">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((r) => (
                      <tr key={r.id} className={`border-b border-[var(--color-border)] last:border-0 ${selectedIds.has(r.id) ? "bg-[var(--color-primary)]/5" : ""}`}>
                        <td className="py-2 pr-2">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(r.id)}
                            onChange={() => toggleSelect(r.id)}
                            className="rounded"
                            aria-label={`Select ${r.strategy_name} for comparison`}
                          />
                        </td>
                        <td className="py-2 pr-4 capitalize">{r.framework}</td>
                        <td className="truncate max-w-[200px] py-2 pr-4 font-medium" title={r.strategy_name}>{r.strategy_name}</td>
                        <td className="py-2 pr-4">{r.symbol}</td>
                        <td className="py-2 pr-4">{r.timeframe}</td>
                        <td className="py-2 pr-4 text-right font-mono text-xs">
                          {typeof r.metrics?.sharpe_ratio === "number" ? r.metrics.sharpe_ratio.toFixed(2) : "—"}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-xs">
                          {typeof r.metrics?.max_drawdown === "number" ? `${(r.metrics.max_drawdown * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-xs">
                          {typeof r.metrics?.win_rate === "number" ? `${(r.metrics.win_rate * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-xs">
                          {typeof r.metrics?.total_trades === "number" ? r.metrics.total_trades : "—"}
                        </td>
                        <td className="py-2 text-xs text-[var(--color-text-muted)]">
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Comparison Table */}
          {compareQuery.data?.comparison && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <h3 className="mb-4 text-lg font-semibold">Comparison</h3>
              {compareQuery.data.comparison.best_strategy && (
                <p className="mb-3 text-sm">
                  Best overall: <span className="font-bold text-green-400">{compareQuery.data.comparison.best_strategy}</span>
                </p>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                      <th className="pb-2 pr-4">Metric</th>
                      {compareQuery.data.comparison.metrics_table[0] &&
                        Object.keys(compareQuery.data.comparison.metrics_table[0].values).map((key) => (
                          <th key={key} className="pb-2 pr-4 text-right">{key}</th>
                        ))}
                    </tr>
                  </thead>
                  <tbody>
                    {compareQuery.data.comparison.metrics_table.map((row) => (
                      <tr key={row.metric} className="border-b border-[var(--color-border)] last:border-0">
                        <td className="py-2 pr-4 font-medium capitalize">{row.metric.replace(/_/g, " ")}</td>
                        {Object.entries(row.values).map(([key, val]) => {
                          const isBest = key === row.best;
                          return (
                            <td
                              key={key}
                              className={`py-2 pr-4 text-right font-mono text-xs ${isBest ? "font-bold text-green-400" : ""}`}
                            >
                              {val != null ? (typeof val === "number" ? val.toFixed(4) : String(val)) : "—"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!activeJobId && (!history || history.length === 0) && (
            <div className="flex h-64 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <p className="text-sm text-[var(--color-text-muted)]">
                Configure a backtest and click Run to see results.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
