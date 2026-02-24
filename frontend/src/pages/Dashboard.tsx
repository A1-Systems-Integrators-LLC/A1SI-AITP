import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardApi } from "../api/dashboard";
import { marketApi } from "../api/market";
import { platformApi } from "../api/platform";
import { jobsApi } from "../api/jobs";
import { regimeApi } from "../api/regime";
import { useAssetClass } from "../hooks/useAssetClass";
import { ProgressBar } from "../components/ProgressBar";
import { MarketStatusBadge } from "../components/MarketStatusBadge";
import { PriceChart } from "../components/PriceChart";
import { AssetClassBadge } from "../components/AssetClassBadge";
import { NewsFeed } from "../components/NewsFeed";
import {
  DEFAULT_SYMBOLS,
  DEFAULT_SYMBOL,
  EXCHANGE_OPTIONS,
  BACKTEST_FRAMEWORKS,
  ASSET_CLASS_LABELS,
} from "../constants/assetDefaults";
import type {
  AssetClass,
  BackgroundJob,
  DashboardKPIs,
  OHLCVData,
  PlatformStatus,
  RegimeState,
  RegimeType,
  TickerData,
} from "../types";

const ALWAYS_SHOW_FRAMEWORKS = ["VectorBT", "CCXT", "Pandas", "TA-Lib"];

function formatPrice(price: number, assetClass: AssetClass): string {
  if (assetClass === "forex") return price.toFixed(5);
  if (price < 1) return price.toFixed(6);
  return `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatVolume(volume: number): string {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
  return volume.toFixed(0);
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const { assetClass } = useAssetClass();
  const [chartSymbol, setChartSymbol] = useState(DEFAULT_SYMBOL[assetClass]);

  useEffect(() => { document.title = "Dashboard | A1SI-AITP"; }, []);

  // Aggregated KPI query — replaces portfolios, risk status, trading performance, and data_files
  const kpis = useQuery<DashboardKPIs>({
    queryKey: ["dashboard-kpis", assetClass],
    queryFn: () => dashboardApi.kpis(assetClass),
    refetchInterval: 30000,
  });

  const { data: platformStatus } = useQuery<PlatformStatus>({
    queryKey: ["platform-status"],
    queryFn: platformApi.status,
  });

  const { data: recentJobs } = useQuery<BackgroundJob[]>({
    queryKey: ["recent-jobs"],
    queryFn: () => jobsApi.list(undefined, 5),
    refetchInterval: 30000,
  });

  const activeJobs = recentJobs?.filter(
    (j) => j.status === "pending" || j.status === "running",
  );

  const { data: regimeStates } = useQuery<RegimeState[]>({
    queryKey: ["regime-overview"],
    queryFn: regimeApi.getCurrentAll,
    refetchInterval: 120000,
    enabled: assetClass === "crypto",
  });

  const { data: tickerData, isLoading: tickersLoading } = useQuery<TickerData[]>({
    queryKey: ["watchlist-tickers", assetClass],
    queryFn: () => marketApi.tickers(DEFAULT_SYMBOLS[assetClass], assetClass),
    refetchInterval: 30000,
    retry: 1,
  });

  const { data: ohlcvData, isLoading: ohlcvLoading } = useQuery<OHLCVData[]>({
    queryKey: ["dashboard-ohlcv", chartSymbol, assetClass],
    queryFn: () => marketApi.ohlcv(chartSymbol, "1d", 30, assetClass),
    retry: 1,
  });

  const frameworkLabels = BACKTEST_FRAMEWORKS[assetClass].map((f) => f.label);
  const filteredFrameworks = platformStatus?.frameworks.filter(
    (fw) => ALWAYS_SHOW_FRAMEWORKS.includes(fw.name) || frameworkLabels.includes(fw.name),
  );

  const dailyPnl = kpis.data?.risk?.daily_pnl;

  return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <MarketStatusBadge assetClass={assetClass} />
      </div>

      {kpis.isError && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          <p>Failed to load dashboard data: {kpis.error instanceof Error ? kpis.error.message : "Unknown error"}</p>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-7">
        <SummaryCard
          label="Portfolios"
          value={kpis.data?.portfolio.count ?? 0}
          loading={kpis.isLoading}
        />
        <SummaryCard
          label="Data Sources"
          value={EXCHANGE_OPTIONS[assetClass].length}
        />
        <SummaryCard
          label="Data Files"
          value={kpis.data?.platform.data_files ?? 0}
          loading={kpis.isLoading}
        />
        <SummaryCard
          label="Active Jobs"
          value={activeJobs?.length ?? 0}
          pulse={activeJobs !== undefined && activeJobs.length > 0}
        />
        <SummaryCard
          label="Portfolio Value"
          text={`$${(kpis.data?.portfolio.total_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`}
          loading={kpis.isLoading}
        />
        <SummaryCard
          label="Daily P&L"
          text={dailyPnl != null ? `$${dailyPnl.toFixed(2)}` : "\u2014"}
          textColor={dailyPnl != null && dailyPnl >= 0 ? "text-green-400" : dailyPnl != null && dailyPnl < 0 ? "text-red-400" : ""}
        />
        <SummaryCard label="Status" text="Online" textColor="text-[var(--color-success)]" />
      </div>

      {/* Watchlist */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center gap-3">
          <h3 className="text-lg font-semibold">{ASSET_CLASS_LABELS[assetClass]} Watchlist</h3>
          <AssetClassBadge assetClass={assetClass} />
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["watchlist-tickers", assetClass] })}
            className="ml-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
            title="Refresh prices"
          >
            &#8635; Refresh
          </button>
        </div>
        {tickersLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-[var(--color-border)]" />
            ))}
          </div>
        ) : tickerData && tickerData.length > 0 ? (
          <div className="space-y-1">
            <div className="grid grid-cols-4 px-3 py-1 text-xs font-medium text-[var(--color-text-muted)]">
              <span>Symbol</span>
              <span className="text-right">Price</span>
              <span className="text-right">24h Change</span>
              <span className="text-right">Volume</span>
            </div>
            {tickerData.map((t) => (
              <button
                key={t.symbol}
                onClick={() => setChartSymbol(t.symbol)}
                className={`grid w-full grid-cols-4 rounded-lg border p-3 text-left transition-colors hover:bg-[var(--color-bg)] ${
                  chartSymbol === t.symbol
                    ? "border-[var(--color-primary)] bg-[var(--color-bg)]"
                    : "border-[var(--color-border)]"
                }`}
              >
                <span className="font-medium">{t.symbol}</span>
                <span className="text-right">{formatPrice(t.price, assetClass)}</span>
                <span className={`text-right ${t.change_24h >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {t.change_24h >= 0 ? "+" : ""}{t.change_24h.toFixed(2)}%
                </span>
                <span className="text-right text-[var(--color-text-muted)]">
                  {formatVolume(t.volume_24h)}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">
            <p>No price data available</p>
            <p className="mt-1 text-xs">
              {assetClass === "crypto"
                ? "Connect an exchange to see live prices"
                : "Download data to see prices"}
            </p>
          </div>
        )}
      </div>

      {/* Daily Chart */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center gap-3">
          <h3 className="text-lg font-semibold">{chartSymbol}</h3>
          <span className="rounded-full bg-[var(--color-bg)] px-2 py-0.5 text-xs text-[var(--color-text-muted)]">
            Daily
          </span>
        </div>
        {ohlcvLoading ? (
          <div className="h-[300px] animate-pulse rounded-lg bg-[var(--color-border)]" />
        ) : ohlcvData && ohlcvData.length > 0 ? (
          <PriceChart data={ohlcvData} height={300} assetClass={assetClass} />
        ) : (
          <div className="flex h-[300px] items-center justify-center text-sm text-[var(--color-text-muted)]">
            No chart data available for {chartSymbol}
          </div>
        )}
      </div>

      {/* News Feed */}
      <NewsFeed />

      {/* Regime Overview */}
      {assetClass === "crypto" ? (
        regimeStates && regimeStates.length > 0 ? (
          <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <h3 className="mb-4 text-lg font-semibold">Regime Overview</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {regimeStates.map((rs) => (
                <div
                  key={rs.symbol}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
                >
                  <div>
                    <p className="font-medium">{rs.symbol}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Confidence: {(rs.confidence * 100).toFixed(1)}%
                    </p>
                  </div>
                  <RegimeBadge regime={rs.regime} />
                </div>
              ))}
            </div>
          </div>
        ) : null
      ) : (
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Regime Overview</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Regime detection for {ASSET_CLASS_LABELS[assetClass].toLowerCase()} is not yet available.
          </p>
        </div>
      )}

      {/* Trading Performance Card */}
      {kpis.data?.trading && kpis.data.trading.total_trades > 0 && (
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Trading Performance</h3>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Win Rate</p>
              <p className="text-xl font-bold">{kpis.data.trading.win_rate.toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Total P&L</p>
              <p className={`text-xl font-bold ${kpis.data.trading.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                ${kpis.data.trading.total_pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Profit Factor</p>
              <p className="text-xl font-bold">{kpis.data.trading.profit_factor != null ? kpis.data.trading.profit_factor.toFixed(2) : "\u221E"}</p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Trades</p>
              <p className="text-xl font-bold">{kpis.data.trading.total_trades}</p>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Framework Status */}
        {filteredFrameworks && filteredFrameworks.length > 0 && (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <h3 className="mb-4 text-lg font-semibold">Framework Status</h3>
            <div className="space-y-2">
              {filteredFrameworks.map((fw) => (
                <div
                  key={fw.name}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-2.5 w-2.5 rounded-full ${fw.installed ? "bg-green-400" : "bg-red-400"}`}
                    />
                    <span className="font-medium">{fw.name}</span>
                  </div>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {fw.version ?? "not installed"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Active / Recent Jobs */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Recent Jobs</h3>
            <button
              onClick={() => queryClient.invalidateQueries({ queryKey: ["recent-jobs"] })}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
              title="Refresh jobs"
            >
              &#8635; Refresh
            </button>
          </div>
          {(!recentJobs || recentJobs.length === 0) && (
            <div className="text-sm text-[var(--color-text-muted)]">
              <p>No recent jobs.</p>
              <p className="mt-1 text-xs">Jobs will appear when you run backtests or data downloads.</p>
            </div>
          )}
          {recentJobs && recentJobs.length > 0 && (
            <div className="space-y-3">
              {recentJobs.map((job) => (
                <div
                  key={job.id}
                  className="rounded-lg border border-[var(--color-border)] p-3"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm font-medium">
                      {job.job_type.replace(/_/g, " ")}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        job.status === "completed"
                          ? "bg-green-500/20 text-green-400"
                          : job.status === "failed"
                            ? "bg-red-500/20 text-red-400"
                            : job.status === "running" || job.status === "pending"
                              ? "bg-blue-500/20 text-blue-400"
                              : "bg-gray-500/20 text-gray-400"
                      }`}
                    >
                      {job.status}
                    </span>
                  </div>
                  {(job.status === "running" || job.status === "pending") && (
                    <ProgressBar
                      progress={job.progress}
                      message={job.progress_message}
                    />
                  )}
                  {job.status === "completed" && (
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Completed{" "}
                      {job.completed_at
                        ? new Date(job.completed_at).toLocaleString()
                        : ""}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Data Sources */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h3 className="mb-4 text-lg font-semibold">
          {assetClass === "crypto" ? "Available Exchanges" : "Data Sources"}
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EXCHANGE_OPTIONS[assetClass].map((ex) => (
            <div
              key={ex.value}
              className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] p-3"
            >
              <div>
                <p className="font-medium">{ex.label}</p>
                <p className="text-xs text-[var(--color-text-muted)]">{ex.value}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const REGIME_COLORS: Record<RegimeType, string> = {
  strong_trend_up: "bg-green-400/15 text-green-400",
  weak_trend_up: "bg-emerald-400/15 text-emerald-400",
  ranging: "bg-yellow-400/15 text-yellow-400",
  weak_trend_down: "bg-orange-400/15 text-orange-400",
  strong_trend_down: "bg-red-400/15 text-red-400",
  high_volatility: "bg-purple-400/15 text-purple-400",
  unknown: "bg-gray-400/15 text-gray-400",
};

function formatRegime(regime: RegimeType): string {
  return regime
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function RegimeBadge({ regime }: { regime: RegimeType }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${REGIME_COLORS[regime] ?? "bg-gray-400/15 text-gray-400"}`}
    >
      {formatRegime(regime)}
    </span>
  );
}

function SummaryCard({
  label,
  value,
  text,
  loading,
  textColor = "",
  pulse = false,
}: {
  label: string;
  value?: number;
  text?: string;
  loading?: boolean;
  textColor?: string;
  pulse?: boolean;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-[var(--color-text-muted)]">{label}</h3>
        {pulse && (
          <span className="h-2 w-2 animate-pulse rounded-full bg-blue-400" />
        )}
      </div>
      {loading ? (
        <div className="h-8 w-16 animate-pulse rounded bg-[var(--color-border)]" />
      ) : text ? (
        <p className={`text-2xl font-bold ${textColor}`}>{text}</p>
      ) : (
        <p className="text-2xl font-bold">{value ?? 0}</p>
      )}
    </div>
  );
}
