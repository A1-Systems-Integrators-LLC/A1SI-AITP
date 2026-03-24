import { useState, useEffect, memo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { dashboardApi } from "../api/dashboard";
import { formatPrice, formatVolume } from "../utils/formatters";
import { marketApi } from "../api/market";
import { opportunitiesApi } from "../api/opportunities";
import { platformApi } from "../api/platform";
import { jobsApi } from "../api/jobs";
import { regimeApi } from "../api/regime";
import { useAssetClass } from "../hooks/useAssetClass";
import { ProgressBar } from "../components/ProgressBar";
import { MarketStatusBadge } from "../components/MarketStatusBadge";
import { PriceChart } from "../components/PriceChart";
import { AssetClassBadge } from "../components/AssetClassBadge";
import { NewsFeed } from "../components/NewsFeed";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { WidgetErrorFallback } from "../components/WidgetErrorFallback";
import {
  DEFAULT_SYMBOLS,
  DEFAULT_SYMBOL,
  EXCHANGE_OPTIONS,
  BACKTEST_FRAMEWORKS,
  ASSET_CLASS_LABELS,
} from "../constants/assetDefaults";
import type {
  ActivityFeedItem,
  AssetClass,
  BackgroundJob,
  DailyReport,
  DashboardKPIs,
  FrameworkStatus,
  LearningStatus,
  OHLCVData,
  OpportunitySummary,
  PaperTradingKPIs,
  PlatformStatus,
  RegimeState,
  RegimeType,
  SystemHealth,
  TickerData,
} from "../types";

function getFrameworkStatusColor(status: FrameworkStatus["status"]): string {
  switch (status) {
    case "running":
      return "bg-green-400 animate-pulse";
    case "idle":
      return "bg-blue-400";
    case "not_installed":
      return "bg-red-400";
    default:
      return "bg-gray-400";
  }
}


const TickerButton = memo(function TickerButton({ symbol, ticker, isActive, onClick, assetClass }: { symbol: string; ticker?: TickerData; isActive: boolean; onClick: () => void; assetClass: AssetClass }) {
  return (
    <button
      onClick={onClick}
      className={`grid w-full grid-cols-4 rounded-lg border p-3 text-left transition-colors hover:bg-[var(--color-bg)] ${
        isActive
          ? "border-[var(--color-primary)] bg-[var(--color-bg)]"
          : "border-[var(--color-border)]"
      }`}
    >
      <span className="font-medium">{symbol}</span>
      <span className="text-right">{ticker ? formatPrice(ticker.price, assetClass) : "\u2014"}</span>
      <span className={`text-right ${ticker && ticker.change_24h >= 0 ? "text-green-400" : "text-red-400"}`}>
        {ticker ? `${ticker.change_24h >= 0 ? "+" : ""}${ticker.change_24h.toFixed(2)}%` : "\u2014"}
      </span>
      <span className="text-right text-[var(--color-text-muted)]">
        {ticker ? formatVolume(ticker.volume_24h) : "\u2014"}
      </span>
    </button>
  );
});

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
    queryKey: ["regime-overview", assetClass],
    queryFn: () => regimeApi.getCurrentAll(assetClass),
    refetchInterval: 120000,
  });

  const tickers = useQuery<TickerData[]>({
    queryKey: ["watchlist-tickers", assetClass],
    queryFn: () => marketApi.tickers(DEFAULT_SYMBOLS[assetClass], assetClass),
    refetchInterval: 30000,
    retry: 1,
  });
  const tickerData = tickers.data;
  const tickersLoading = tickers.isLoading;

  const { data: ohlcvData, isLoading: ohlcvLoading } = useQuery<OHLCVData[]>({
    queryKey: ["dashboard-ohlcv", chartSymbol, assetClass],
    queryFn: () => marketApi.ohlcv(chartSymbol, "1d", 30, assetClass),
    retry: 1,
  });

  const { data: oppSummary } = useQuery<OpportunitySummary>({
    queryKey: ["opportunity-summary"],
    queryFn: () => opportunitiesApi.summary(),
    refetchInterval: 60000,
  });

  const { data: dailyReport } = useQuery<DailyReport>({
    queryKey: ["daily-report"],
    queryFn: opportunitiesApi.dailyReport,
    refetchInterval: 300000,
  });

  const frameworkLabels = BACKTEST_FRAMEWORKS[assetClass].map((f) => f.label);
  const filteredFrameworks = platformStatus?.frameworks.filter(
    (fw) => fw.name === "CCXT" || fw.name === "VectorBT" || frameworkLabels.includes(fw.name),
  );

  const dailyPnl = kpis.data?.risk?.daily_pnl;

  return (
    <div>
      <section aria-labelledby="page-heading">
      <div className="mb-6 flex items-center gap-3">
        <h2 id="page-heading" className="text-2xl font-bold">Dashboard</h2>
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
        <SummaryCard
          label="Status"
          text={kpis.data?.system_health?.scheduler_running ? "Running" : "Degraded"}
          textColor={kpis.data?.system_health?.scheduler_running ? "text-[var(--color-success)]" : "text-red-400"}
          pulse={kpis.data?.system_health?.scheduler_running}
        />
      </div>
      {kpis.dataUpdatedAt > 0 && (
        <p className="mt-1 text-right text-xs text-[var(--color-text-muted)]" data-testid="kpi-timestamp">
          Updated {new Date(kpis.dataUpdatedAt).toLocaleTimeString()}
        </p>
      )}

      {/* Paper Trading */}
      {kpis.data?.paper_trading && (
        <PaperTradingWidget data={kpis.data.paper_trading} />
      )}

      {/* System Health + Agent Learning */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {kpis.data?.system_health && (
          <SystemHealthCard data={kpis.data.system_health} />
        )}
        {kpis.data?.learning_status && (
          <AgentLearningCard data={kpis.data.learning_status} />
        )}
      </div>

      {/* Activity Feed */}
      {kpis.data?.activity_feed && kpis.data.activity_feed.length > 0 && (
        <ActivityFeedWidget events={kpis.data.activity_feed} />
      )}

      {/* Watchlist */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center gap-3">
          <h3 className="text-lg font-semibold">{ASSET_CLASS_LABELS[assetClass]} Watchlist</h3>
          <AssetClassBadge assetClass={assetClass} />
          {tickers.dataUpdatedAt > 0 && (
            <span className="text-xs text-[var(--color-text-muted)]" data-testid="watchlist-timestamp">
              as of {new Date(tickers.dataUpdatedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["watchlist-tickers", assetClass] })}
            className="ml-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
            title="Refresh prices"
            aria-label="Refresh prices"
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
              <TickerButton
                key={t.symbol}
                symbol={t.symbol}
                ticker={t}
                isActive={chartSymbol === t.symbol}
                onClick={() => setChartSymbol(t.symbol)}
                assetClass={assetClass}
              />
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
          <ErrorBoundary fallback={<WidgetErrorFallback name="Price Chart" />}>
            <PriceChart data={ohlcvData} height={300} assetClass={assetClass} />
          </ErrorBoundary>
        ) : (
          <div className="flex h-[300px] items-center justify-center text-sm text-[var(--color-text-muted)]">
            No chart data available for {chartSymbol}
          </div>
        )}
      </div>

      {/* News Feed */}
      <ErrorBoundary fallback={<WidgetErrorFallback name="News Feed" />}>
        <NewsFeed />
      </ErrorBoundary>

      {/* Market Opportunities */}
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Market Opportunities</h3>
            <Link
              to="/opportunities"
              className="text-xs text-[var(--color-primary)] hover:underline"
            >
              View All
            </Link>
          </div>

          {/* System Status */}
          {dailyReport?.system_status && (
            <div className="mb-4 flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
              <div className={`h-2.5 w-2.5 rounded-full ${dailyReport.system_status.is_ready ? "bg-green-400" : "bg-yellow-400 animate-pulse"}`} />
              <div>
                <p className="text-sm font-medium">{dailyReport.system_status.readiness}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  Coverage: {String((dailyReport.data_coverage as Record<string, unknown>).coverage_pct ?? 0)}% |{" "}
                  Regime: {String((dailyReport.regime as Record<string, unknown>).dominant_regime ?? "unknown")}
                </p>
              </div>
            </div>
          )}

          {/* Top Opportunities */}
          {oppSummary && oppSummary.top_opportunities.length > 0 ? (
            <div className="space-y-2">
              {oppSummary.top_opportunities.map((opp) => (
                <div
                  key={opp.id}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-medium">{opp.symbol}</span>
                    <AssetClassBadge assetClass={opp.asset_class} />
                    <OpportunityTypeBadge type={opp.opportunity_type} />
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-24">
                      <div className="h-1.5 rounded-full bg-[var(--color-border)]">
                        <div
                          className={`h-1.5 rounded-full ${opp.score >= 75 ? "bg-green-400" : opp.score >= 50 ? "bg-yellow-400" : "bg-gray-400"}`}
                          style={{ width: `${opp.score}%` }}
                        />
                      </div>
                    </div>
                    <span className="w-8 text-right text-xs font-medium">{opp.score}</span>
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {new Date(opp.detected_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                </div>
              ))}
              <p className="text-right text-xs text-[var(--color-text-muted)]">
                {oppSummary.total_active} active opportunities | Avg score: {oppSummary.avg_score}
              </p>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              No active opportunities. Scanner runs every 15 minutes.
            </p>
          )}
        </div>

      {/* Regime Overview */}
      {regimeStates && regimeStates.length > 0 ? (
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center gap-3">
            <h3 className="text-lg font-semibold">Regime Overview</h3>
            <AssetClassBadge assetClass={assetClass} />
          </div>
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
      ) : (
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Regime Overview</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            No regime data available for {ASSET_CLASS_LABELS[assetClass].toLowerCase()}.
          </p>
        </div>
      )}

      {/* Trading Performance Card — always visible */}
      {kpis.data?.trading && (
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Trading Performance</h3>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Filled Orders</p>
              <p className="text-xl font-bold">{kpis.data.trading.filled_orders ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Win Rate</p>
              <p className="text-xl font-bold">{(kpis.data.trading.win_rate ?? 0).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Total P&L</p>
              <p className={`text-xl font-bold ${(kpis.data.trading.total_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                ${(kpis.data.trading.total_pnl ?? 0).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Total Orders</p>
              <p className="text-xl font-bold">{kpis.data.trading.total_orders ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Rejection Rate</p>
              <p className={`text-xl font-bold ${(kpis.data.trading.rejection_rate ?? 0) > 50 ? "text-red-400" : (kpis.data.trading.rejection_rate ?? 0) > 20 ? "text-yellow-400" : "text-green-400"}`}>
                {(kpis.data.trading.rejection_rate ?? 0).toFixed(1)}%
              </p>
            </div>
          </div>
          {kpis.data.trading.total_trades === 0 && kpis.data.paper_trading && (
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">
              No live trades yet. Paper trading P&L: ${kpis.data.paper_trading.total_pnl.toFixed(2)}
            </p>
          )}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Framework Status */}
        {filteredFrameworks && filteredFrameworks.length > 0 && (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <h3 className="mb-2 text-lg font-semibold">Framework Status</h3>
            <div className="mb-3 flex items-center gap-4 text-xs text-[var(--color-text-muted)]">
              <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full bg-green-400 animate-pulse" />Active</span>
              <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full bg-blue-400" />Ready</span>
              <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full bg-red-400" />Not Installed</span>
            </div>
            <div className="space-y-2">
              {filteredFrameworks.map((fw) => (
                  <div
                    key={fw.name}
                    className="rounded-lg border border-[var(--color-border)] p-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div
                          className={`h-2.5 w-2.5 rounded-full ${getFrameworkStatusColor(fw.status)}`}
                        />
                        <span className="font-medium">{fw.name}</span>
                      </div>
                      <span className="text-xs text-[var(--color-text-muted)]">
                        {fw.status_label}
                      </span>
                    </div>
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
              aria-label="Refresh jobs"
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
      </section>
    </div>
  );
}

function SystemHealthCard({ data }: { data: SystemHealth }) {
  const dataAge = data.last_data_refresh
    ? Math.round((Date.now() - new Date(data.last_data_refresh).getTime()) / 60000)
    : null;
  const dataFresh = dataAge !== null && dataAge < 60;
  const dataStale = dataAge !== null && dataAge >= 240;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6" data-testid="system-health-card">
      <h3 className="mb-4 text-lg font-semibold">System Health</h3>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm">Scheduler</span>
          <span className={`flex items-center gap-1.5 text-sm ${data.scheduler_running ? "text-green-400" : "text-red-400"}`}>
            <span className={`h-2 w-2 rounded-full ${data.scheduler_running ? "bg-green-400 animate-pulse" : "bg-red-400"}`} />
            {data.scheduler_running ? "Running" : "Stopped"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Active Tasks</span>
          <span className="text-sm font-medium">{data.active_tasks}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Data Freshness</span>
          <span className={`text-sm ${dataFresh ? "text-green-400" : dataStale ? "text-red-400" : "text-yellow-400"}`}>
            {dataAge !== null ? `${dataAge}m ago` : "Unknown"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Jobs</span>
          <span className="text-sm">
            <span className="text-green-400">{data.total_jobs_completed.toLocaleString()}</span>
            {data.total_jobs_failed > 0 && (
              <> / <span className="text-red-400">{data.total_jobs_failed} failed</span></>
            )}
          </span>
        </div>
        {data.freqtrade_instances.length > 0 && (
          <div>
            <p className="mb-1 text-xs text-[var(--color-text-muted)]">Trading Engines</p>
            <div className="flex flex-wrap gap-2">
              {data.freqtrade_instances.map((ft) => (
                <span
                  key={ft.name}
                  className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs ${
                    ft.running
                      ? "bg-green-500/15 text-green-400"
                      : ft.enabled
                        ? "bg-red-500/15 text-red-400"
                        : "bg-gray-500/15 text-gray-400"
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${ft.running ? "bg-green-400" : ft.enabled ? "bg-red-400" : "bg-gray-400"}`} />
                  {ft.name.replace("CryptoInvestorV1", "CIV1").replace("BollingerMeanReversion", "BMR").replace("VolatilityBreakout", "VB")}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AgentLearningCard({ data }: { data: LearningStatus }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6" data-testid="agent-learning-card">
      <h3 className="mb-4 text-lg font-semibold">Agent Learning</h3>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm">ML Accuracy</span>
          <span className={`text-sm font-medium ${
            data.ml_accuracy === null ? "text-[var(--color-text-muted)]"
              : data.ml_accuracy >= 55 ? "text-green-400"
                : data.ml_accuracy >= 50 ? "text-yellow-400" : "text-red-400"
          }`}>
            {data.ml_accuracy !== null ? `${data.ml_accuracy}%` : "No data"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Predictions Made</span>
          <span className="text-sm font-medium">{data.ml_predictions_total.toLocaleString()}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Signal Attributions</span>
          <span className={`text-sm font-medium ${data.signal_attributions === 0 ? "text-red-400" : ""}`}>
            {data.signal_attributions}
            {data.signal_attributions === 0 && " (broken)"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm">Last Training</span>
          <span className="text-sm text-[var(--color-text-muted)]">
            {data.ml_last_trained
              ? new Date(data.ml_last_trained).toLocaleDateString()
              : "Never"}
          </span>
        </div>
        {data.orchestrator_states.length > 0 && (
          <div>
            <p className="mb-1 text-xs text-[var(--color-text-muted)]">Strategy Orchestrator</p>
            <div className="flex flex-wrap gap-2">
              {data.orchestrator_states.map((s) => (
                <span
                  key={s.strategy}
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    s.action === "active"
                      ? "bg-green-500/15 text-green-400"
                      : s.action === "reduce_size"
                        ? "bg-yellow-500/15 text-yellow-400"
                        : "bg-red-500/15 text-red-400"
                  }`}
                >
                  {s.strategy.replace("CryptoInvestorV1", "CIV1").replace("BollingerMeanReversion", "BMR").replace("VolatilityBreakout", "VB").replace("EquityMomentum", "EqMom").replace("EquityMeanReversion", "EqMR").replace("ForexTrend", "FxTr").replace("ForexRange", "FxRa")}: {s.action}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ActivityFeedWidget({ events }: { events: ActivityFeedItem[] }) {
  const typeIcons: Record<string, string> = { job: "\u2699", alert: "\u26A0", task: "\u23F0" };
  return (
    <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6" data-testid="activity-feed">
      <h3 className="mb-4 text-lg font-semibold">Recent Activity</h3>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {events.map((evt, i) => (
          <div key={i} className="flex items-start gap-3 rounded-lg border border-[var(--color-border)] p-2">
            <span className="mt-0.5 text-sm">{typeIcons[evt.type] ?? "\u2022"}</span>
            <div className="min-w-0 flex-1">
              <p className={`truncate text-sm ${evt.severity === "error" || evt.severity === "critical" ? "text-red-400" : ""}`}>
                {evt.message}
              </p>
              <p className="text-xs text-[var(--color-text-muted)]">
                {new Date(evt.timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
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

const OPPORTUNITY_TYPE_COLORS: Record<string, string> = {
  volume_surge: "bg-blue-400/15 text-blue-400",
  rsi_bounce: "bg-cyan-400/15 text-cyan-400",
  breakout: "bg-green-400/15 text-green-400",
  trend_pullback: "bg-amber-400/15 text-amber-400",
  momentum_shift: "bg-purple-400/15 text-purple-400",
};

function OpportunityTypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${OPPORTUNITY_TYPE_COLORS[type] ?? "bg-gray-400/15 text-gray-400"}`}
    >
      {type.replace(/_/g, " ")}
    </span>
  );
}

function PaperTradingWidget({ data }: { data: PaperTradingKPIs }) {
  return (
    <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6" data-testid="paper-trading-widget">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Paper Trading</h3>
        <Link
          to="/paper-trading"
          className="text-xs text-[var(--color-primary)] hover:underline"
        >
          View Details &rarr;
        </Link>
      </div>

      {/* Instance status */}
      {data.instances.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {data.instances.map((inst) => (
            <div
              key={inst.name}
              className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5"
            >
              <span
                className={`h-2 w-2 rounded-full ${inst.running ? "bg-green-400 animate-pulse" : "bg-gray-500"}`}
              />
              <span className="text-sm font-medium">{inst.strategy ?? inst.name}</span>
              {inst.pnl !== 0 && (
                <span className={`text-xs ${inst.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                  ${inst.pnl.toFixed(2)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">Total P&L</p>
          <p className={`text-xl font-bold ${data.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            ${data.total_pnl.toFixed(2)}
          </p>
          {data.total_pnl_pct !== 0 && (
            <p className={`text-xs ${data.total_pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
              {data.total_pnl_pct >= 0 ? "+" : ""}{data.total_pnl_pct.toFixed(2)}%
            </p>
          )}
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">Open Trades</p>
          <p className="text-xl font-bold">{data.open_trades}</p>
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">Win Rate</p>
          <p className="text-xl font-bold">{data.win_rate.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">Closed Trades</p>
          <p className="text-xl font-bold">{data.closed_trades}</p>
        </div>
      </div>

      {data.instances_running === 0 && (
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">
          No Freqtrade instances detected. Start paper trading to see live data.
        </p>
      )}
    </div>
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
