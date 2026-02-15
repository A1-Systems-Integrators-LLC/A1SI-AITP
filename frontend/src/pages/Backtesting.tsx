import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { backtestApi } from "../api/backtest";
import { useJobPolling } from "../hooks/useJobPolling";
import { ProgressBar } from "../components/ProgressBar";
import { EquityCurve } from "../components/EquityCurve";
import type { BacktestResult, StrategyInfo } from "../types";

export function Backtesting() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [framework, setFramework] = useState("freqtrade");
  const [strategy, setStrategy] = useState("");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [timerange, setTimerange] = useState("");
  const [exchange, setExchange] = useState("binance");

  const { data: strategies } = useQuery<StrategyInfo[]>({
    queryKey: ["backtest-strategies"],
    queryFn: backtestApi.strategies,
  });

  const { data: history } = useQuery<BacktestResult[]>({
    queryKey: ["backtest-results"],
    queryFn: () => backtestApi.results(10),
  });

  const job = useJobPolling(activeJobId);

  const runMutation = useMutation({
    mutationFn: () =>
      backtestApi.run({ framework, strategy, symbol, timeframe, timerange, exchange }),
    onSuccess: (data) => setActiveJobId(data.job_id),
  });

  const isJobActive = job.data?.status === "pending" || job.data?.status === "running";
  const jobResult = job.data?.result as Record<string, unknown> | undefined;
  const metrics = (jobResult?.metrics ?? {}) as Record<string, unknown>;
  const trades = (jobResult?.trades ?? []) as Record<string, unknown>[];

  const filteredStrategies = strategies?.filter((s) => s.framework === framework) ?? [];

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Backtesting</h2>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Config Form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Configuration</h3>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Framework</label>
              <div className="flex gap-1">
                {["freqtrade", "nautilus"].map((fw) => (
                  <button
                    key={fw}
                    onClick={() => { setFramework(fw); setStrategy(""); }}
                    className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium capitalize ${
                      framework === fw
                        ? "bg-[var(--color-primary)] text-white"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {fw}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Strategy</label>
              {filteredStrategies.length > 0 ? (
                <select
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
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  placeholder="Strategy name"
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                />
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Timeframe</label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                {["1m", "5m", "15m", "1h", "4h", "1d"].map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Exchange</label>
              <select
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="binance">Binance</option>
                <option value="sample">Sample</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Time Range</label>
              <input
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
          {history && history.length > 0 && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <h3 className="mb-4 text-lg font-semibold">History</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                      <th className="pb-2 pr-4">Framework</th>
                      <th className="pb-2 pr-4">Strategy</th>
                      <th className="pb-2 pr-4">Symbol</th>
                      <th className="pb-2 pr-4">Timeframe</th>
                      <th className="pb-2">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((r) => (
                      <tr key={r.id} className="border-b border-[var(--color-border)] last:border-0">
                        <td className="py-2 pr-4 capitalize">{r.framework}</td>
                        <td className="py-2 pr-4 font-medium">{r.strategy_name}</td>
                        <td className="py-2 pr-4">{r.symbol}</td>
                        <td className="py-2 pr-4">{r.timeframe}</td>
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
