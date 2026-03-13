import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAssetClass } from "../hooks/useAssetClass";
import { signalsApi } from "../api/signals";
import { QueryError } from "../components/QueryError";
import type {
  AssetClass,
  CompositeSignal,
  SourceAccuracyData,
  StrategyStatus,
  WeightRecommendation,
} from "../types";

const WATCHLISTS: Record<AssetClass, string[]> = {
  crypto: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT", "DOT/USDT", "AVAX/USDT"],
  equity: ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"],
  forex: ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "NZD/USD"],
};

const SCORE_COLOR = (score: number): string => {
  if (score >= 75) return "bg-green-500/20 text-green-400";
  if (score >= 60) return "bg-blue-500/20 text-blue-400";
  if (score >= 45) return "bg-yellow-500/20 text-yellow-400";
  if (score >= 30) return "bg-orange-500/20 text-orange-400";
  return "bg-red-500/20 text-red-400";
};

const SCORE_BAR_COLOR = (score: number): string => {
  if (score >= 75) return "bg-green-400";
  if (score >= 50) return "bg-yellow-400";
  return "bg-red-400";
};

const ACTION_STYLE: Record<string, string> = {
  active: "bg-green-500/20 text-green-400",
  reduce_size: "bg-yellow-500/20 text-yellow-400",
  pause: "bg-red-500/20 text-red-400",
};

const SOURCE_LABELS: Record<string, string> = {
  technical: "Technical",
  regime: "Regime",
  ml: "ML",
  sentiment: "Sentiment",
  scanner: "Scanner",
  win_rate: "Win Rate",
};

export function ConvictionDashboard() {
  const { assetClass } = useAssetClass();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Conviction | A1SI-AITP";
  }, []);

  // Reset selection on asset class change
  useEffect(() => {
    setSelectedSymbol(null);
  }, [assetClass]);

  const watchlist = WATCHLISTS[assetClass] ?? WATCHLISTS.crypto;

  // Batch signals for the watchlist
  const signalsQuery = useQuery<CompositeSignal[]>({
    queryKey: ["signals-batch", assetClass],
    queryFn: () => signalsApi.batchSignals(watchlist, assetClass),
    refetchInterval: 60000,
  });

  // Strategy status
  const strategyQuery = useQuery<StrategyStatus[]>({
    queryKey: ["strategy-status", assetClass],
    queryFn: () => signalsApi.strategyStatus(assetClass),
    refetchInterval: 60000,
  });

  // Source accuracy
  const accuracyQuery = useQuery<SourceAccuracyData>({
    queryKey: ["signal-accuracy", assetClass],
    queryFn: () => signalsApi.accuracy({ asset_class: assetClass }),
    refetchInterval: 300000,
  });

  // Weight recommendations
  const weightsQuery = useQuery<WeightRecommendation>({
    queryKey: ["signal-weights", assetClass],
    queryFn: () => signalsApi.weights({ asset_class: assetClass }),
    refetchInterval: 300000,
  });

  // Single symbol detail
  const detailQuery = useQuery<CompositeSignal>({
    queryKey: ["signal-detail", selectedSymbol, assetClass],
    queryFn: () => signalsApi.getSignal(selectedSymbol!, assetClass),
    enabled: !!selectedSymbol,
    refetchInterval: 30000,
  });

  return (
    <div>
      <section aria-labelledby="page-heading">
        <h2 id="page-heading" className="mb-6 text-2xl font-bold">
          Conviction Dashboard
        </h2>

        {/* Conviction Heatmap */}
        <div className="mb-6">
          <h3 className="mb-3 text-lg font-semibold">Signal Heatmap</h3>
          {signalsQuery.isError && (
            <QueryError error={signalsQuery.error} onRetry={() => signalsQuery.refetch()} />
          )}
          {signalsQuery.isLoading && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6" data-testid="heatmap-skeleton">
              {watchlist.map((s) => (
                <div key={s} className="h-24 animate-pulse rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" />
              ))}
            </div>
          )}
          {signalsQuery.data && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
              {signalsQuery.data.map((signal) => (
                <button
                  key={signal.symbol}
                  onClick={() => setSelectedSymbol(signal.symbol)}
                  aria-label={`View signal for ${signal.symbol}`}
                  className={`rounded-xl border p-3 text-left transition-colors ${
                    selectedSymbol === signal.symbol
                      ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10"
                      : "border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-bg)]"
                  }`}
                >
                  <p className="truncate text-sm font-medium">{signal.symbol}</p>
                  <p className={`mt-1 text-xl font-bold ${signal.composite_score >= 60 ? "text-green-400" : signal.composite_score >= 40 ? "text-yellow-400" : "text-red-400"}`}>
                    {signal.composite_score.toFixed(0)}
                  </p>
                  <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${SCORE_COLOR(signal.composite_score)}`}>
                    {signal.signal_label.replace(/_/g, " ")}
                  </span>
                </button>
              ))}
            </div>
          )}
          {signalsQuery.data && signalsQuery.data.length === 0 && (
            <p className="text-sm text-[var(--color-text-muted)]">No signal data available. Ensure the signal service is running.</p>
          )}
        </div>

        {/* Signal Detail Panel */}
        {selectedSymbol && (
          <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">
                Signal Detail: {selectedSymbol}
              </h3>
              <button
                onClick={() => setSelectedSymbol(null)}
                aria-label="Close signal detail"
                className="rounded px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-bg)]"
              >
                Close
              </button>
            </div>
            {detailQuery.isLoading && (
              <div className="space-y-3" data-testid="detail-skeleton">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-6 animate-pulse rounded bg-[var(--color-border)]" />
                ))}
              </div>
            )}
            {detailQuery.isError && (
              <QueryError error={detailQuery.error} onRetry={() => detailQuery.refetch()} />
            )}
            {detailQuery.data && (
              <div>
                {/* Score + meta */}
                <div className="mb-4 flex items-center gap-4">
                  <div className={`rounded-xl px-4 py-2 text-center ${SCORE_COLOR(detailQuery.data.composite_score)}`}>
                    <p className="text-2xl font-bold">{detailQuery.data.composite_score.toFixed(1)}</p>
                    <p className="text-xs">{detailQuery.data.signal_label.replace(/_/g, " ")}</p>
                  </div>
                  <div className="space-y-1 text-sm">
                    <p>Entry: <span className={detailQuery.data.entry_approved ? "text-green-400" : "text-red-400"}>{detailQuery.data.entry_approved ? "Approved" : "Blocked"}</span></p>
                    <p>Position Modifier: <span className="font-medium">{detailQuery.data.position_modifier.toFixed(2)}x</span></p>
                    {detailQuery.data.hard_disabled && (
                      <p className="font-bold text-red-400">Hard Disabled</p>
                    )}
                  </div>
                </div>

                {/* Component breakdown */}
                <h4 className="mb-2 text-sm font-semibold text-[var(--color-text-muted)]">Signal Components</h4>
                <div className="space-y-2">
                  {Object.entries(detailQuery.data.components).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-3">
                      <span className="w-20 text-xs text-[var(--color-text-muted)]">{SOURCE_LABELS[key] ?? key}</span>
                      <div className="h-2 flex-1 rounded-full bg-[var(--color-border)]">
                        <div
                          className={`h-2 rounded-full ${SCORE_BAR_COLOR(value)}`}
                          style={{ width: `${Math.min(value, 100)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-xs font-medium">{value.toFixed(0)}</span>
                    </div>
                  ))}
                </div>

                {/* Reasoning */}
                {detailQuery.data.reasoning.length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-2 text-sm font-semibold text-[var(--color-text-muted)]">Reasoning</h4>
                    <ul className="space-y-1 text-xs text-[var(--color-text-muted)]">
                      {detailQuery.data.reasoning.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Strategy Orchestrator Status */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <h3 className="mb-4 text-lg font-semibold">Strategy Status</h3>
            {strategyQuery.isError && (
              <QueryError error={strategyQuery.error} onRetry={() => strategyQuery.refetch()} />
            )}
            {strategyQuery.isLoading && (
              <div className="space-y-2" data-testid="strategy-skeleton">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-[var(--color-border)]" />
                ))}
              </div>
            )}
            {strategyQuery.data && strategyQuery.data.length > 0 && (
              <div className="space-y-3">
                {strategyQuery.data.map((s) => (
                  <div key={s.strategy_name} className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3">
                    <div>
                      <p className="text-sm font-medium">{s.strategy_name}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">
                        Regime: {s.regime.replace(/_/g, " ")} | Alignment: {s.alignment_score}
                      </p>
                    </div>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${ACTION_STYLE[s.recommended_action] ?? "bg-gray-500/20 text-gray-400"}`}>
                      {s.recommended_action.replace(/_/g, " ")}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {strategyQuery.data && strategyQuery.data.length === 0 && (
              <p className="text-sm text-[var(--color-text-muted)]">No strategy data available.</p>
            )}
          </div>

          {/* Source Accuracy */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <h3 className="mb-4 text-lg font-semibold">Signal Source Accuracy</h3>
            {accuracyQuery.isError && (
              <QueryError error={accuracyQuery.error} onRetry={() => accuracyQuery.refetch()} />
            )}
            {accuracyQuery.isLoading && (
              <div className="space-y-2" data-testid="accuracy-skeleton">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 animate-pulse rounded bg-[var(--color-border)]" />
                ))}
              </div>
            )}
            {accuracyQuery.data && (
              <div>
                <div className="mb-4 flex gap-4 text-sm">
                  <div>
                    <span className="text-[var(--color-text-muted)]">Trades: </span>
                    <span className="font-medium">{accuracyQuery.data.total_trades}</span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)]">Win Rate: </span>
                    <span className="font-medium">{(accuracyQuery.data.overall_win_rate * 100).toFixed(1)}%</span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-muted)]">Window: </span>
                    <span className="font-medium">{accuracyQuery.data.window_days}d</span>
                  </div>
                </div>
                {accuracyQuery.data.sources && Object.keys(accuracyQuery.data.sources).length > 0 ? (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                        <th className="pb-2 text-left text-xs">Source</th>
                        <th className="pb-2 text-right text-xs">Win Avg</th>
                        <th className="pb-2 text-right text-xs">Loss Avg</th>
                        <th className="pb-2 text-right text-xs">Accuracy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(accuracyQuery.data.sources).map(([source, data]) => (
                        <tr key={source} className="border-b border-[var(--color-border)] last:border-0">
                          <td className="py-2 text-xs font-medium">{SOURCE_LABELS[source] ?? source}</td>
                          <td className="py-2 text-right text-xs text-green-400">{data.win_avg.toFixed(1)}</td>
                          <td className="py-2 text-right text-xs text-red-400">{data.loss_avg.toFixed(1)}</td>
                          <td className="py-2 text-right text-xs font-medium">{(data.accuracy * 100).toFixed(0)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="text-sm text-[var(--color-text-muted)]">No accuracy data yet. Trades must be recorded first.</p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Weight Recommendations */}
        {weightsQuery.data && (
          <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <h3 className="mb-4 text-lg font-semibold">Weight Recommendations</h3>
            {weightsQuery.isError && (
              <QueryError error={weightsQuery.error} onRetry={() => weightsQuery.refetch()} />
            )}
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              {/* Weights table */}
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                    <th className="pb-2 text-left text-xs">Source</th>
                    <th className="pb-2 text-right text-xs">Current</th>
                    <th className="pb-2 text-right text-xs">Recommended</th>
                    <th className="pb-2 text-right text-xs">Adj</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(weightsQuery.data.current_weights).map((source) => {
                    const adj = weightsQuery.data!.adjustments[source] ?? 0;
                    return (
                      <tr key={source} className="border-b border-[var(--color-border)] last:border-0">
                        <td className="py-2 text-xs font-medium">{SOURCE_LABELS[source] ?? source}</td>
                        <td className="py-2 text-right text-xs">{((weightsQuery.data!.current_weights[source] ?? 0) * 100).toFixed(0)}%</td>
                        <td className="py-2 text-right text-xs font-medium">{((weightsQuery.data!.recommended_weights[source] ?? 0) * 100).toFixed(0)}%</td>
                        <td className={`py-2 text-right text-xs font-medium ${adj > 0 ? "text-green-400" : adj < 0 ? "text-red-400" : ""}`}>
                          {adj > 0 ? "+" : ""}{(adj * 100).toFixed(0)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Reasoning */}
              <div>
                <p className="mb-2 text-xs text-[var(--color-text-muted)]">
                  Based on {weightsQuery.data.total_trades} trades ({(weightsQuery.data.win_rate * 100).toFixed(1)}% win rate)
                </p>
                {weightsQuery.data.reasoning.length > 0 && (
                  <ul className="space-y-1">
                    {weightsQuery.data.reasoning.map((r, i) => (
                      <li key={i} className="text-xs text-[var(--color-text-muted)]">{r}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
