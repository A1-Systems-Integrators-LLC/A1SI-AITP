import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { paperTradingApi } from "../api/paperTrading";
import { backtestApi } from "../api/backtest";
import { useToast } from "../hooks/useToast";
import { useAssetClass } from "../hooks/useAssetClass";
import { BACKTEST_FRAMEWORKS, ASSET_CLASS_LABELS } from "../constants/assetDefaults";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { WidgetErrorFallback } from "../components/WidgetErrorFallback";
import { getErrorMessage } from "../utils/errors";
import type {
  PaperTradingStatus,
  PaperTrade,
  PaperTradingProfit,
  PaperTradingPerformance,
  PaperTradingLogEntry,
  StrategyInfo,
} from "../types";

export function PaperTrading() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();
  const frameworkList = BACKTEST_FRAMEWORKS[assetClass];
  const frameworks = frameworkList.map((f) => f.label).join(", ");
  const [selectedStrategy, setSelectedStrategy] = useState("");

  useEffect(() => { document.title = "Paper Trading | A1SI-AITP"; }, []);

  const { data: statuses, isError: statusError } = useQuery<PaperTradingStatus[]>({
    queryKey: ["paper-trading-status"],
    queryFn: paperTradingApi.status,
    refetchInterval: 5000,
  });

  const { data: strategies } = useQuery<StrategyInfo[]>({
    queryKey: ["strategies"],
    queryFn: backtestApi.strategies,
  });

  // Filter strategies by frameworks available for this asset class
  const frameworkValues = frameworkList.map((f) => f.value);
  const filteredStrategies = strategies?.filter((s) => frameworkValues.includes(s.framework)) ?? [];

  // Derive running state from instance list
  const anyRunning = statuses?.some((s) => s.running) ?? false;
  const runningCount = statuses?.filter((s) => s.running).length ?? 0;

  const { data: openTrades } = useQuery<PaperTrade[]>({
    queryKey: ["paper-trading-trades"],
    queryFn: paperTradingApi.openTrades,
    refetchInterval: 5000,
    enabled: anyRunning,
  });

  const { data: profits } = useQuery<PaperTradingProfit[]>({
    queryKey: ["paper-trading-profit"],
    queryFn: paperTradingApi.profit,
    refetchInterval: 10000,
    enabled: anyRunning,
  });

  const { data: performance } = useQuery<PaperTradingPerformance[]>({
    queryKey: ["paper-trading-performance"],
    queryFn: paperTradingApi.performance,
    refetchInterval: 10000,
    enabled: anyRunning,
  });

  const { data: history } = useQuery<PaperTrade[]>({
    queryKey: ["paper-trading-history"],
    queryFn: () => paperTradingApi.history(50),
    refetchInterval: 10000,
    enabled: anyRunning,
  });

  const { data: logEntries } = useQuery<PaperTradingLogEntry[]>({
    queryKey: ["paper-trading-log"],
    queryFn: () => paperTradingApi.log(50),
    refetchInterval: 10000,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["paper-trading-status"] });
    queryClient.invalidateQueries({ queryKey: ["paper-trading-trades"] });
    queryClient.invalidateQueries({ queryKey: ["paper-trading-profit"] });
    queryClient.invalidateQueries({ queryKey: ["paper-trading-log"] });
  };

  const startMutation = useMutation({
    mutationFn: () => paperTradingApi.start(selectedStrategy),
    onSuccess: invalidateAll,
    onError: (err) => toast(getErrorMessage(err) || "Failed to start paper trading", "error"),
  });

  const stopMutation = useMutation({
    mutationFn: paperTradingApi.stop,
    onSuccess: invalidateAll,
    onError: (err) => toast(getErrorMessage(err) || "Failed to stop paper trading", "error"),
  });

  // Aggregate profit across instances
  const totalProfit = profits?.reduce((sum, p) => sum + (p.profit_all_coin ?? 0), 0) ?? 0;
  const totalTrades = profits?.reduce((sum, p) => sum + (p.trade_count ?? 0), 0) ?? 0;
  const totalClosed = profits?.reduce((sum, p) => sum + (p.closed_trade_count ?? 0), 0) ?? 0;
  const totalWinning = profits?.reduce((sum, p) => sum + (p.winning_trades ?? 0), 0) ?? 0;
  const totalClosedPct = profits?.reduce((sum, p) => sum + (p.profit_closed_percent ?? 0), 0) ?? 0;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold">Paper Trading</h2>
        <div className="flex items-center gap-3">
          {!anyRunning && (
            <select
              value={selectedStrategy}
              onChange={(e) => setSelectedStrategy(e.target.value)}
              aria-label="Select trading strategy"
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            >
              <option value="">Select strategy...</option>
              {filteredStrategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
          {anyRunning ? (
            <button
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
              aria-label="Stop paper trading"
              className="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600 disabled:opacity-50"
            >
              {stopMutation.isPending ? "Stopping..." : "Stop"}
            </button>
          ) : (
            <button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              aria-label="Start paper trading"
              className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {startMutation.isPending ? "Starting..." : "Start"}
            </button>
          )}
        </div>
      </div>

      {/* Error display */}
      {startMutation.error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          {startMutation.error.message}
        </div>
      )}

      {statusError && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Failed to connect to paper trading service. Status may be unavailable.
        </div>
      )}

      {assetClass !== "crypto" && (
        <div className="mb-4 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-400">
          {ASSET_CLASS_LABELS[assetClass]} paper trading uses: {frameworks}
        </div>
      )}

      <ErrorBoundary fallback={<WidgetErrorFallback name="Paper Trading" />}>
      {/* Instance Status Cards */}
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-3">
        {statuses?.map((inst) => (
          <div
            key={inst.instance ?? inst.strategy}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          >
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`h-3 w-3 rounded-full ${inst.running ? "animate-pulse bg-green-400" : "bg-gray-500"}`}
              />
              <span className="font-medium text-sm">
                {inst.instance ?? inst.strategy ?? "Unknown"}
              </span>
            </div>
            <div className="space-y-1 text-xs text-[var(--color-text-muted)]">
              <div>Status: <span className={inst.running ? "text-green-400" : "text-red-400"}>{inst.running ? "Running" : "Stopped"}</span></div>
              {inst.strategy && <div>Strategy: <span className="font-mono">{inst.strategy}</span></div>}
              {inst.exchange && <div>Exchange: <span className="font-mono">{inst.exchange}</span></div>}
              {inst.dry_run != null && <div>Mode: {inst.dry_run ? "Dry Run" : "Live"}</div>}
            </div>
          </div>
        )) ?? (
          <div className="col-span-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-gray-500" />
              <span className="font-medium">No instances configured</span>
            </div>
          </div>
        )}
      </div>

      {/* Overall Status Bar */}
      <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span
              className={`h-3 w-3 rounded-full ${anyRunning ? "animate-pulse bg-green-400" : "bg-gray-500"}`}
            />
            <span className="font-medium">
              {anyRunning ? `${runningCount} Instance${runningCount > 1 ? "s" : ""} Running` : "All Stopped"}
            </span>
          </div>
          {anyRunning && (
            <span className="text-sm text-[var(--color-text-muted)]">
              Strategies: <span className="font-mono">{statuses?.filter((s) => s.running).map((s) => s.strategy).join(", ")}</span>
            </span>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total Profit"
          value={
            profits && profits.length > 0
              ? `${totalProfit >= 0 ? "+" : ""}${totalProfit.toFixed(4)}`
              : "—"
          }
          className={totalProfit >= 0 ? "text-green-400" : "text-red-400"}
        />
        <StatCard
          label="Win Rate"
          value={
            totalClosed > 0
              ? `${((totalWinning / totalClosed) * 100).toFixed(1)}%`
              : "—"
          }
        />
        <StatCard
          label="Trades"
          value={profits && profits.length > 0 ? String(totalTrades) : "—"}
        />
        <StatCard
          label="Closed P/L"
          value={
            profits && profits.length > 0
              ? `${totalClosedPct >= 0 ? "+" : ""}${totalClosedPct.toFixed(2)}%`
              : "—"
          }
          className={totalClosedPct >= 0 ? "text-green-400" : "text-red-400"}
        />
      </div>

      {/* Two-column: Open Trades + Performance */}
      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Open Trades */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Open Trades</h3>
          {!anyRunning ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              Start paper trading to see open trades
            </p>
          ) : openTrades && openTrades.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-text-muted)]">
                    <th className="pb-2">Pair</th>
                    <th className="pb-2">Amount</th>
                    <th className="pb-2">Open Rate</th>
                    <th className="pb-2">Profit</th>
                  </tr>
                </thead>
                <tbody>
                  {openTrades.map((t, i) => (
                    <tr
                      key={t.trade_id ?? i}
                      className="border-b border-[var(--color-border)]/30"
                    >
                      <td className="py-1.5 font-mono text-xs">
                        {t.pair ?? "—"}
                      </td>
                      <td className="py-1.5 font-mono">
                        {t.amount?.toFixed(6) ?? "—"}
                      </td>
                      <td className="py-1.5 font-mono">
                        {t.open_rate?.toFixed(2) ?? "—"}
                      </td>
                      <td
                        className={`py-1.5 font-mono ${(t.profit_ratio ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                      >
                        {t.profit_ratio != null
                          ? `${(t.profit_ratio * 100).toFixed(2)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              No open trades
            </p>
          )}
        </div>

        {/* Performance by Pair */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Performance by Pair</h3>
          {performance && performance.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-text-muted)]">
                    <th className="pb-2">Pair</th>
                    <th className="pb-2">Profit</th>
                    <th className="pb-2">Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {performance.map((p) => (
                    <tr
                      key={p.pair}
                      className="border-b border-[var(--color-border)]/30"
                    >
                      <td className="py-1.5 font-mono text-xs">{p.pair}</td>
                      <td
                        className={`py-1.5 font-mono ${p.profit >= 0 ? "text-green-400" : "text-red-400"}`}
                      >
                        {p.profit >= 0 ? "+" : ""}
                        {p.profit.toFixed(2)}%
                      </td>
                      <td className="py-1.5 font-mono">{p.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              {anyRunning ? "No performance data yet" : "Start paper trading to see performance"}
            </p>
          )}
        </div>
      </div>

      {/* Trade History */}
      <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h3 className="mb-4 text-lg font-semibold">Trade History</h3>
        {history && history.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-text-muted)]">
                  <th className="pb-2">Pair</th>
                  <th className="pb-2">Open</th>
                  <th className="pb-2">Close</th>
                  <th className="pb-2">Profit</th>
                  <th className="pb-2">Duration</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t, i) => (
                  <tr
                    key={t.trade_id ?? i}
                    className="border-b border-[var(--color-border)]/30"
                  >
                    <td className="py-1.5 font-mono text-xs">
                      {t.pair ?? "—"}
                    </td>
                    <td className="py-1.5 font-mono text-xs">
                      {t.open_date
                        ? new Date(t.open_date).toLocaleString()
                        : "—"}
                    </td>
                    <td className="py-1.5 font-mono text-xs">
                      {t.close_date
                        ? new Date(t.close_date).toLocaleString()
                        : "—"}
                    </td>
                    <td
                      className={`py-1.5 font-mono ${(t.profit_ratio ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                    >
                      {t.profit_ratio != null
                        ? `${(t.profit_ratio * 100).toFixed(2)}%`
                        : "—"}
                    </td>
                    <td className="py-1.5 text-xs text-[var(--color-text-muted)]">
                      {t.open_date && t.close_date
                        ? formatDuration(t.open_date, t.close_date)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            {anyRunning ? "No closed trades yet" : "No trade history available"}
          </p>
        )}
      </div>

      {/* Event Log */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h3 className="mb-4 text-lg font-semibold">Event Log</h3>
        {logEntries && logEntries.length > 0 ? (
          <div className="max-h-64 overflow-y-auto">
            <div className="space-y-1">
              {[...logEntries].reverse().map((entry, i) => (
                <div
                  key={i}
                  className="flex gap-3 rounded px-2 py-1 text-xs font-mono hover:bg-[var(--color-bg)]"
                >
                  <span className="shrink-0 text-[var(--color-text-muted)]">
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                  <span
                    className={
                      entry.event === "started"
                        ? "text-green-400"
                        : entry.event === "stopped"
                          ? "text-red-400"
                          : "text-[var(--color-text)]"
                    }
                  >
                    {entry.event}
                  </span>
                  {"strategy" in entry && entry.strategy != null && (
                    <span className="text-[var(--color-text-muted)]">
                      {String(entry.strategy)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            No log entries
          </p>
        )}
      </div>
      </ErrorBoundary>
    </div>
  );
}

function StatCard({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
      <p className={`text-xl font-bold ${className}`}>{value}</p>
    </div>
  );
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  if (hours > 24) {
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h`;
  }
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
