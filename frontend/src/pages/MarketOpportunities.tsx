import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { opportunitiesApi } from "../api/opportunities";
import { signalsApi } from "../api/signals";
import { QueryError } from "../components/QueryError";
import type { AssetClass, CompositeSignal, DailyReport, MarketOpportunity, OpportunitySummary } from "../types";

const TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All Types" },
  { value: "volume_surge", label: "Volume Surge" },
  { value: "rsi_bounce", label: "RSI Bounce" },
  { value: "breakout", label: "Breakout" },
  { value: "trend_pullback", label: "Trend Pullback" },
  { value: "momentum_shift", label: "Momentum Shift" },
];

const ASSET_CLASS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All Assets" },
  { value: "crypto", label: "Crypto" },
  { value: "forex", label: "Forex" },
  { value: "equity", label: "Equities" },
];

const TYPE_COLORS: Record<string, string> = {
  volume_surge: "bg-blue-400/15 text-blue-400",
  rsi_bounce: "bg-cyan-400/15 text-cyan-400",
  breakout: "bg-green-400/15 text-green-400",
  trend_pullback: "bg-amber-400/15 text-amber-400",
  momentum_shift: "bg-purple-400/15 text-purple-400",
};

export function MarketOpportunities() {
  const [typeFilter, setTypeFilter] = useState("");
  const [assetClassFilter, setAssetClassFilter] = useState("");
  const [minScore, setMinScore] = useState(0);

  useEffect(() => {
    document.title = "Market Opportunities | A1SI-AITP";
  }, []);

  const acParam = assetClassFilter ? (assetClassFilter as AssetClass) : undefined;

  const opportunities = useQuery<MarketOpportunity[]>({
    queryKey: ["opportunities", typeFilter, minScore, assetClassFilter],
    queryFn: () =>
      opportunitiesApi.list({
        type: typeFilter || undefined,
        min_score: minScore || undefined,
        asset_class: acParam,
        limit: 100,
      }),
    refetchInterval: 60000,
  });

  const summary = useQuery<OpportunitySummary>({
    queryKey: ["opportunity-summary", assetClassFilter],
    queryFn: () => opportunitiesApi.summary(acParam),
    refetchInterval: 60000,
  });

  // Fetch conviction signals for displayed opportunity symbols
  const oppSymbols = opportunities.data?.map((o) => o.symbol).filter((v, i, a) => a.indexOf(v) === i).slice(0, 20) ?? [];
  const signalsBatch = useQuery<CompositeSignal[]>({
    queryKey: ["opp-signals", oppSymbols.join(","), assetClassFilter],
    queryFn: () => signalsApi.batchSignals(oppSymbols, (acParam ?? "crypto")),
    enabled: oppSymbols.length > 0,
    refetchInterval: 120000,
  });
  const signalMap = new Map<string, CompositeSignal>();
  if (Array.isArray(signalsBatch.data)) {
    signalsBatch.data.forEach((s) => signalMap.set(s.symbol, s));
  }

  const report = useQuery<DailyReport>({
    queryKey: ["daily-report"],
    queryFn: opportunitiesApi.dailyReport,
    refetchInterval: 300000,
  });

  return (
    <div>
      <section aria-labelledby="page-heading">
        <h2 id="page-heading" className="mb-6 text-2xl font-bold">
          Market Opportunities
        </h2>

        {/* Summary Cards */}
        {summary.data && (
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <p className="text-sm text-[var(--color-text-muted)]">Active</p>
              <p className="text-2xl font-bold">{summary.data.total_active}</p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <p className="text-sm text-[var(--color-text-muted)]">Avg Score</p>
              <p className="text-2xl font-bold">{summary.data.avg_score}</p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <p className="text-sm text-[var(--color-text-muted)]">High Score (75+)</p>
              <p className="text-2xl font-bold text-green-400">
                {summary.data.top_opportunities.filter((o) => o.score >= 75).length}
              </p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <p className="text-sm text-[var(--color-text-muted)]">Types Active</p>
              <p className="text-2xl font-bold">{Object.keys(summary.data.by_type).length}</p>
            </div>
          </div>
        )}

        {/* System Status */}
        {report.data?.system_status && (
          <div className="mb-6 flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <div
              className={`h-3 w-3 rounded-full ${report.data.system_status.is_ready ? "bg-green-400" : "bg-yellow-400 animate-pulse"}`}
            />
            <div>
              <p className="font-medium">{report.data.system_status.readiness}</p>
              <p className="text-xs text-[var(--color-text-muted)]">
                Day {report.data.system_status.days_paper_trading} of{" "}
                {report.data.system_status.min_days_required} minimum paper trading
              </p>
            </div>
          </div>
        )}

        {/* Scanner Status */}
        {report.data?.scanner_status && Object.keys(report.data.scanner_status).length > 0 && (
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            {Object.entries(report.data.scanner_status).map(([key, scanner]) => (
              <div
                key={key}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
              >
                <div className="mb-2 flex items-center gap-2">
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      scanner.last_run_status === "completed" ? "bg-green-400" :
                      scanner.last_run_status === "error" ? "bg-red-400" :
                      "bg-gray-400"
                    }`}
                  />
                  <span className="text-sm font-medium capitalize">
                    {key.replace("market_scan_", "")} Scanner
                  </span>
                </div>
                <div className="space-y-1 text-xs text-[var(--color-text-muted)]">
                  <div>
                    Last run:{" "}
                    {scanner.last_run_at
                      ? new Date(scanner.last_run_at).toLocaleString([], {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "Never"}
                  </div>
                  <div>Run count: {scanner.run_count}</div>
                  {scanner.next_run_at && (
                    <div>
                      Next run:{" "}
                      {new Date(scanner.next_run_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Type Distribution */}
        {summary.data && Object.keys(summary.data.by_type).length > 0 && (
          <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--color-text-muted)]">
              Distribution by Type
            </h3>
            <div className="flex flex-wrap gap-3">
              {Object.entries(summary.data.by_type).map(([type, count]) => (
                <button
                  key={type}
                  onClick={() => setTypeFilter(typeFilter === type ? "" : type)}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                    typeFilter === type
                      ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10"
                      : "border-[var(--color-border)] hover:bg-[var(--color-bg)]"
                  }`}
                  aria-label={`Filter by ${type.replace(/_/g, " ")}`}
                >
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[type] ?? "bg-gray-400/15 text-gray-400"}`}>
                    {type.replace(/_/g, " ")}
                  </span>
                  <span className="font-medium">{count}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="mb-4 flex items-center gap-4">
          <select
            value={assetClassFilter}
            onChange={(e) => setAssetClassFilter(e.target.value)}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            aria-label="Filter by asset class"
          >
            {ASSET_CLASS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            aria-label="Filter by opportunity type"
          >
            {TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            Min Score:
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-24"
              aria-label="Minimum score filter"
            />
            <span className="w-8 font-medium text-[var(--color-text)]">{minScore}</span>
          </label>
        </div>

        {/* Error */}
        {opportunities.isError && (
          <QueryError error={opportunities.error} onRetry={() => opportunities.refetch()} />
        )}

        {/* Opportunities Table */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg)]">
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Symbol</th>
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Asset</th>
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Type</th>
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Score</th>
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Signal</th>
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Details</th>
                <th className="px-4 py-3 text-left font-medium text-[var(--color-text-muted)]">Detected</th>
              </tr>
            </thead>
            <tbody>
              {opportunities.isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--color-border)]">
                    <td colSpan={7} className="px-4 py-3">
                      <div className="h-6 animate-pulse rounded bg-[var(--color-border)]" />
                    </td>
                  </tr>
                ))
              ) : opportunities.data && opportunities.data.length > 0 ? (
                opportunities.data.map((opp) => (
                  <tr key={opp.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg)]">
                    <td className="px-4 py-3 font-medium">{opp.symbol}</td>
                    <td className="px-4 py-3 text-xs capitalize text-[var(--color-text-muted)]">{opp.asset_class}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[opp.opportunity_type] ?? "bg-gray-400/15 text-gray-400"}`}
                      >
                        {opp.opportunity_type.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 rounded-full bg-[var(--color-border)]">
                          <div
                            className={`h-1.5 rounded-full ${opp.score >= 75 ? "bg-green-400" : opp.score >= 50 ? "bg-yellow-400" : "bg-gray-400"}`}
                            style={{ width: `${opp.score}%` }}
                          />
                        </div>
                        <span className="font-medium">{opp.score}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {(() => {
                        const sig = signalMap.get(opp.symbol);
                        if (!sig) return <span className="text-xs text-[var(--color-text-muted)]">--</span>;
                        return (
                          <span
                            data-testid="signal-quality"
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                              sig.composite_score >= 75
                                ? "bg-green-500/20 text-green-400"
                                : sig.composite_score >= 50
                                  ? "bg-yellow-500/20 text-yellow-400"
                                  : "bg-red-500/20 text-red-400"
                            }`}
                          >
                            {sig.composite_score.toFixed(0)}
                          </span>
                        );
                      })()}
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-xs text-[var(--color-text-muted)]">
                      {(opp.details as Record<string, unknown>).reason as string ?? ""}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-muted)]">
                      {new Date(opp.detected_at).toLocaleString([], {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-[var(--color-text-muted)]">
                    No active opportunities{typeFilter ? ` of type "${typeFilter.replace(/_/g, " ")}"` : ""}.
                    Scanner runs every 15 minutes.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Daily Report Details */}
        {report.data && (
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Data Coverage */}
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <h3 className="mb-3 text-lg font-semibold">Data Coverage</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[var(--color-text-muted)]">Pairs with data</span>
                  <span>
                    {(report.data.data_coverage as Record<string, unknown>).pairs_with_data as number ?? 0} /{" "}
                    {(report.data.data_coverage as Record<string, unknown>).total_pairs as number ?? 0}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--color-text-muted)]">Coverage</span>
                  <span>{(report.data.data_coverage as Record<string, unknown>).coverage_pct as number ?? 0}%</span>
                </div>
              </div>
            </div>

            {/* Strategy Performance */}
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <h3 className="mb-3 text-lg font-semibold">Strategy Performance</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[var(--color-text-muted)]">Total Orders</span>
                  <span>{(report.data.strategy_performance as Record<string, unknown>).total_orders as number ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--color-text-muted)]">Win Rate</span>
                  <span>{(report.data.strategy_performance as Record<string, unknown>).win_rate as number ?? 0}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--color-text-muted)]">Total P&L</span>
                  <span className={(report.data.strategy_performance as Record<string, unknown>).total_pnl as number >= 0 ? "text-green-400" : "text-red-400"}>
                    ${(report.data.strategy_performance as Record<string, unknown>).total_pnl as number ?? 0}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
