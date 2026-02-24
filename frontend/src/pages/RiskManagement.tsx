import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { portfoliosApi } from "../api/portfolios";
import { riskApi } from "../api/risk";
import { useToast } from "../hooks/useToast";
import { useSystemEvents } from "../hooks/useSystemEvents";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useAssetClass } from "../hooks/useAssetClass";
import { Pagination } from "../components/Pagination";
import { DEFAULT_SYMBOL } from "../constants/assetDefaults";
import { getErrorMessage } from "../utils/errors";
import type { Portfolio, RiskLimits, RiskStatus, VaRData, HeatCheckData, RiskMetricHistoryEntry, TradeCheckLogEntry, AlertLogEntry } from "../types";

const PAGE_SIZE = 15;

export function RiskManagement() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();
  const { isHalted: wsHalted, haltReason: wsHaltReason } = useSystemEvents();
  const [portfolioId, setPortfolioId] = useLocalStorage("ci:risk-portfolio", 1);
  const [varHistoryPage, setVarHistoryPage] = useState(1);
  const [tradeLogPage, setTradeLogPage] = useState(1);
  const [alertsPage, setAlertsPage] = useState(1);
  const [alertSeverityFilter, setAlertSeverityFilter] = useState("");
  const [alertEventFilter, setAlertEventFilter] = useState("");

  useEffect(() => { document.title = "Risk Management | A1SI-AITP"; }, []);

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: ["portfolios"],
    queryFn: () => portfoliosApi.list(),
  });

  const { data: status, isError: statusError } = useQuery<RiskStatus>({
    queryKey: ["risk-status", portfolioId],
    queryFn: () => riskApi.getStatus(portfolioId),
  });

  const { data: limits } = useQuery<RiskLimits>({
    queryKey: ["risk-limits", portfolioId],
    queryFn: () => riskApi.getLimits(portfolioId),
  });

  // VaR query
  const [varMethod, setVarMethod] = useLocalStorage("ci:risk-var-method", "parametric");
  const { data: varData } = useQuery<VaRData>({
    queryKey: ["risk-var", portfolioId, varMethod],
    queryFn: () => riskApi.getVaR(portfolioId, varMethod),
  });

  // Heat check query with 30s auto-refresh
  const { data: heatCheck } = useQuery<HeatCheckData>({
    queryKey: ["risk-heat-check", portfolioId],
    queryFn: () => riskApi.getHeatCheck(portfolioId),
    refetchInterval: 30000,
  });

  // Metric history query
  const [historyHours, setHistoryHours] = useLocalStorage("ci:risk-history-hours", 168);
  const { data: metricHistory } = useQuery<RiskMetricHistoryEntry[]>({
    queryKey: ["risk-metric-history", portfolioId, historyHours],
    queryFn: () => riskApi.getMetricHistory(portfolioId, historyHours),
  });

  // Trade log query
  const { data: tradeLog } = useQuery<TradeCheckLogEntry[]>({
    queryKey: ["risk-trade-log", portfolioId],
    queryFn: () => riskApi.getTradeLog(portfolioId, 50),
  });

  // Alert log query
  const alertFilters = {
    ...(alertSeverityFilter && { severity: alertSeverityFilter }),
    ...(alertEventFilter && { event_type: alertEventFilter }),
  };
  const { data: alerts } = useQuery<AlertLogEntry[]>({
    queryKey: ["risk-alerts", portfolioId, alertFilters],
    queryFn: () => riskApi.getAlerts(portfolioId, 50, alertFilters),
  });

  // Halt/resume mutations
  const [haltReason, setHaltReason] = useState("");
  const [showHaltConfirm, setShowHaltConfirm] = useState(false);

  const haltMutation = useMutation({
    mutationFn: (reason: string) => riskApi.haltTrading(portfolioId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-status", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["risk-alerts", portfolioId] });
      toast("Trading halted", "error");
      setShowHaltConfirm(false);
      setHaltReason("");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to halt trading", "error"),
  });

  const resumeMutation = useMutation({
    mutationFn: () => riskApi.resumeTrading(portfolioId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-status", portfolioId] });
      queryClient.invalidateQueries({ queryKey: ["risk-alerts", portfolioId] });
      toast("Trading resumed", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to resume trading", "error"),
  });

  const recordMetricsMutation = useMutation({
    mutationFn: () => riskApi.recordMetrics(portfolioId, varMethod),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-metric-history", portfolioId] });
      toast("Metrics snapshot recorded", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to record metrics", "error"),
  });

  // Limits editor state
  const [isEditing, setIsEditing] = useState(false);
  const [editLimits, setEditLimits] = useState<Partial<RiskLimits>>({});

  const limitsMutation = useMutation({
    mutationFn: (updates: Partial<RiskLimits>) => riskApi.updateLimits(portfolioId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-limits", portfolioId] });
      setIsEditing(false);
      toast("Risk limits saved", "success");
    },
    onError: () => {
      toast("Failed to save risk limits", "error");
    },
  });

  // Position sizer state
  const positionDefaults: Record<string, { entry: number; stop: number; size: number }> = {
    crypto: { entry: 50000, stop: 48000, size: 0.1 },
    equity: { entry: 200, stop: 194, size: 10 },
    forex: { entry: 1.1, stop: 1.098, size: 10000 },
  };
  const [entryPrice, setEntryPrice] = useState(positionDefaults[assetClass].entry);
  const [stopLoss, setStopLoss] = useState(positionDefaults[assetClass].stop);
  const [posResult, setPosResult] = useState<{ size: number; risk_amount: number; position_value: number } | null>(null);

  const positionMutation = useMutation({
    mutationFn: () => riskApi.positionSize(portfolioId, { entry_price: entryPrice, stop_loss_price: stopLoss }),
    onSuccess: (data) => setPosResult(data),
    onError: (err) => toast(getErrorMessage(err) || "Position sizing failed", "error"),
  });

  // Trade checker state
  const [tradeSymbol, setTradeSymbol] = useState(DEFAULT_SYMBOL[assetClass]);
  const [tradeSide, setTradeSide] = useState("buy");
  const [tradeSize, setTradeSize] = useState(positionDefaults[assetClass].size);
  const [tradeEntry, setTradeEntry] = useState(positionDefaults[assetClass].entry);
  const [tradeResult, setTradeResult] = useState<{ approved: boolean; reason: string } | null>(null);

  const tradeMutation = useMutation({
    mutationFn: () =>
      riskApi.checkTrade(portfolioId, {
        symbol: tradeSymbol,
        side: tradeSide,
        size: tradeSize,
        entry_price: tradeEntry,
      }),
    onSuccess: (data) => {
      setTradeResult(data);
      queryClient.invalidateQueries({ queryKey: ["risk-trade-log", portfolioId] });
    },
    onError: (err) => toast(getErrorMessage(err) || "Trade check failed", "error"),
  });

  const resetMutation = useMutation({
    mutationFn: () => riskApi.resetDaily(portfolioId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-status", portfolioId] });
      toast("Daily counters reset", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to reset daily counters", "error"),
  });

  // Prefer WS-driven halt status for instant feedback, fall back to query data
  const effectiveHalted = wsHalted ?? status?.is_halted ?? false;
  const effectiveHaltReason = wsHaltReason || status?.halt_reason || "";

  const drawdownPct = status ? (status.drawdown * 100).toFixed(2) : "0.00";
  const drawdownColor = status
    ? status.drawdown > 0.1
      ? "text-red-400"
      : status.drawdown > 0.05
        ? "text-yellow-400"
        : "text-green-400"
    : "text-[var(--color-text-muted)]";

  function startEditing() {
    if (limits) {
      setEditLimits({ ...limits });
    }
    setIsEditing(true);
  }

  function cancelEditing() {
    setIsEditing(false);
    setEditLimits({});
  }

  function saveLimits() {
    if (!limits) return;
    const changes: Partial<RiskLimits> = {};
    for (const key of Object.keys(editLimits) as (keyof RiskLimits)[]) {
      if (editLimits[key] !== limits[key]) {
        (changes as Record<string, unknown>)[key] = editLimits[key];
      }
    }
    if (Object.keys(changes).length > 0) {
      limitsMutation.mutate(changes);
    } else {
      setIsEditing(false);
    }
  }

  const limitFields: { key: keyof RiskLimits; label: string; step: number; pct?: boolean; suffix?: string }[] = [
    { key: "max_portfolio_drawdown", label: "Max Drawdown", step: 0.01, pct: true },
    { key: "max_single_trade_risk", label: "Single Trade Risk", step: 0.005, pct: true },
    { key: "max_daily_loss", label: "Max Daily Loss", step: 0.01, pct: true },
    { key: "max_open_positions", label: "Max Open Positions", step: 1 },
    { key: "max_position_size_pct", label: "Max Position Size", step: 0.01, pct: true },
    { key: "max_correlation", label: "Max Correlation", step: 0.05 },
    { key: "min_risk_reward", label: "Min Risk/Reward", step: 0.1 },
    { key: "max_leverage", label: "Max Leverage", step: 0.5, suffix: "x" },
  ];

  return (
    <div>
      <section aria-labelledby="page-heading">
      <div className="mb-6 flex items-center justify-between">
        <h2 id="page-heading" className="text-2xl font-bold">Risk Management</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["risk-status", portfolioId] });
              queryClient.invalidateQueries({ queryKey: ["risk-limits", portfolioId] });
              queryClient.invalidateQueries({ queryKey: ["risk-heat-check", portfolioId] });
            }}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
            title="Refresh status"
          >
            &#8635; Refresh
          </button>
          <label htmlFor="risk-portfolio-id" className="text-sm text-[var(--color-text-muted)]">Portfolio:</label>
          <select
            id="risk-portfolio-id"
            value={portfolioId}
            onChange={(e) => setPortfolioId(Number(e.target.value))}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
          >
            {portfolios && portfolios.length > 0 ? (
              portfolios.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))
            ) : (
              <option value={1}>Portfolio 1</option>
            )}
          </select>
        </div>
      </div>

      {statusError && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Failed to load risk status. Data shown may be stale.
        </div>
      )}

      {/* Status Cards — 5 columns with Total PnL */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatusCard label="Equity" value={`$${(status?.equity ?? 0).toLocaleString()}`} />
        <StatusCard label="Drawdown" value={`${drawdownPct}%`} className={drawdownColor} />
        <StatusCard label="Daily PnL" value={`$${(status?.daily_pnl ?? 0).toFixed(2)}`}
          className={status && status.daily_pnl >= 0 ? "text-green-400" : "text-red-400"} />
        <StatusCard
          label="Total PnL"
          value={`$${(status?.total_pnl ?? 0).toFixed(2)}`}
          className={status && status.total_pnl >= 0 ? "text-green-400" : "text-red-400"}
        />
        <StatusCard
          label="Status"
          value={effectiveHalted ? "HALTED" : "Active"}
          className={effectiveHalted ? "text-red-400" : "text-green-400"}
        />
      </div>

      {/* Kill Switch Controls */}
      {effectiveHalted ? (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-red-400">
              <span className="font-bold">TRADING HALTED:</span> {effectiveHaltReason}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => resumeMutation.mutate()}
                disabled={resumeMutation.isPending}
                className="rounded bg-green-500/20 px-3 py-1.5 text-sm font-medium text-green-400 hover:bg-green-500/30 disabled:opacity-50"
              >
                Resume Trading
              </button>
              <button
                onClick={() => resetMutation.mutate()}
                className="rounded bg-red-500/20 px-3 py-1.5 text-sm text-red-400 hover:bg-red-500/30"
              >
                Reset Daily
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="mb-6">
          {!showHaltConfirm ? (
            <button
              onClick={() => setShowHaltConfirm(true)}
              className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/20"
            >
              Halt Trading
            </button>
          ) : (
            <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3">
              <input
                type="text"
                placeholder="Reason for halt..."
                value={haltReason}
                onChange={(e) => setHaltReason(e.target.value)}
                className="flex-1 rounded border border-red-500/30 bg-[var(--color-bg)] px-3 py-1.5 text-sm"
              />
              <button
                onClick={() => haltReason && haltMutation.mutate(haltReason)}
                disabled={!haltReason || haltMutation.isPending}
                className="rounded bg-red-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50"
              >
                Confirm Halt
              </button>
              <button
                onClick={() => { setShowHaltConfirm(false); setHaltReason(""); }}
                className="rounded bg-[var(--color-bg)] px-3 py-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Limits Config — Editable */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Risk Limits</h3>
            {!isEditing ? (
              <button
                onClick={startEditing}
                className="rounded bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              >
                Edit
              </button>
            ) : (
              <div className="flex gap-1">
                <button
                  onClick={saveLimits}
                  disabled={limitsMutation.isPending}
                  className="rounded bg-green-500/20 px-2 py-1 text-xs text-green-400 hover:bg-green-500/30 disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  onClick={cancelEditing}
                  className="rounded bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
          {limits && (
            <div className="space-y-2 text-sm">
              {limitFields.map((f) => (
                isEditing ? (
                  <div key={f.key} className="flex items-center justify-between gap-2">
                    <label className="text-[var(--color-text-muted)]">{f.label}</label>
                    <input
                      type="number"
                      step={f.step}
                      min={0}
                      value={editLimits[f.key] ?? limits[f.key]}
                      onChange={(e) => setEditLimits((prev) => ({ ...prev, [f.key]: Number(e.target.value) }))}
                      className="w-24 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-right font-mono text-sm"
                    />
                  </div>
                ) : (
                  <LimitRow
                    key={f.key}
                    label={f.label}
                    value={
                      f.pct
                        ? `${((limits[f.key] as number) * 100).toFixed(1)}%`
                        : f.suffix
                          ? `${limits[f.key]}${f.suffix}`
                          : String(limits[f.key])
                    }
                  />
                )
              ))}
            </div>
          )}
        </div>

        {/* Position Sizer */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Position Sizer</h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="risk-entry-price" className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry Price</label>
              <input
                id="risk-entry-price"
                type="number"
                value={entryPrice}
                onChange={(e) => setEntryPrice(Number(e.target.value))}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="risk-stop-loss" className="mb-1 block text-xs text-[var(--color-text-muted)]">Stop Loss</label>
              <input
                id="risk-stop-loss"
                type="number"
                value={stopLoss}
                onChange={(e) => setStopLoss(Number(e.target.value))}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => positionMutation.mutate()}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white"
            >
              Calculate
            </button>
            {posResult && (
              <div className="mt-2 space-y-1 rounded-lg bg-[var(--color-bg)] p-3 text-sm">
                <div className="flex justify-between"><span className="text-[var(--color-text-muted)]">Size:</span> <span className="font-mono">{posResult.size}</span></div>
                <div className="flex justify-between"><span className="text-[var(--color-text-muted)]">Risk Amount:</span> <span className="font-mono">${posResult.risk_amount}</span></div>
                <div className="flex justify-between"><span className="text-[var(--color-text-muted)]">Position Value:</span> <span className="font-mono">${posResult.position_value}</span></div>
              </div>
            )}
          </div>
        </div>

        {/* Trade Checker */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Trade Checker</h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="risk-trade-symbol" className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
              <input
                id="risk-trade-symbol"
                value={tradeSymbol}
                onChange={(e) => setTradeSymbol(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setTradeSide("buy")}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${tradeSide === "buy" ? "bg-green-500 text-white" : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"}`}
              >
                Buy
              </button>
              <button
                onClick={() => setTradeSide("sell")}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${tradeSide === "sell" ? "bg-red-500 text-white" : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"}`}
              >
                Sell
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="risk-trade-size" className="mb-1 block text-xs text-[var(--color-text-muted)]">Size</label>
                <input
                  id="risk-trade-size"
                  type="number"
                  step="0.01"
                  value={tradeSize}
                  onChange={(e) => setTradeSize(Number(e.target.value))}
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label htmlFor="risk-trade-entry" className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry</label>
                <input
                  id="risk-trade-entry"
                  type="number"
                  value={tradeEntry}
                  onChange={(e) => setTradeEntry(Number(e.target.value))}
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                />
              </div>
            </div>
            <button
              onClick={() => tradeMutation.mutate()}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white"
            >
              Check Trade
            </button>
            {tradeResult && (
              <div
                className={`mt-2 rounded-lg p-3 text-sm ${tradeResult.approved ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}
              >
                <span className="font-medium">{tradeResult.approved ? "Approved" : "Rejected"}</span>
                : {tradeResult.reason}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* VaR Summary + Portfolio Health */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* VaR Summary */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Value at Risk</h3>
            <select
              value={varMethod}
              onChange={(e) => setVarMethod(e.target.value)}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs"
            >
              <option value="parametric">Parametric</option>
              <option value="historical">Historical</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-[var(--color-bg)] p-3">
              <p className="text-xs text-[var(--color-text-muted)]">VaR 95%</p>
              <p className="font-mono text-lg font-bold">${(varData?.var_95 ?? 0).toFixed(2)}</p>
            </div>
            <div className="rounded-lg bg-[var(--color-bg)] p-3">
              <p className="text-xs text-[var(--color-text-muted)]">VaR 99%</p>
              <p className="font-mono text-lg font-bold">${(varData?.var_99 ?? 0).toFixed(2)}</p>
            </div>
            <div className="rounded-lg bg-[var(--color-bg)] p-3">
              <p className="text-xs text-[var(--color-text-muted)]">CVaR 95%</p>
              <p className="font-mono text-lg font-bold">${(varData?.cvar_95 ?? 0).toFixed(2)}</p>
            </div>
            <div className="rounded-lg bg-[var(--color-bg)] p-3">
              <p className="text-xs text-[var(--color-text-muted)]">CVaR 99%</p>
              <p className="font-mono text-lg font-bold">${(varData?.cvar_99 ?? 0).toFixed(2)}</p>
            </div>
          </div>
          <p className="mt-3 text-xs text-[var(--color-text-muted)]">
            Method: {varData?.method ?? "parametric"} | Window: {varData?.window_days ?? 0} days
          </p>
        </div>

        {/* Portfolio Health */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Portfolio Health</h3>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                heatCheck?.healthy ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
              }`}
            >
              {heatCheck?.healthy ? "Healthy" : "Unhealthy"}
            </span>
          </div>

          {heatCheck?.issues && heatCheck.issues.length > 0 && (
            <div className="mb-4 space-y-1">
              {heatCheck.issues.map((issue, i) => (
                <div key={i} className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-400">
                  {issue}
                </div>
              ))}
            </div>
          )}

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">Drawdown</span>
              <span className="font-mono">{((heatCheck?.drawdown ?? 0) * 100).toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">Open Positions</span>
              <span className="font-mono">{heatCheck?.open_positions ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">Max Correlation</span>
              <span className="font-mono">{(heatCheck?.max_correlation ?? 0).toFixed(3)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">Max Concentration</span>
              <span className="font-mono">{((heatCheck?.max_concentration ?? 0) * 100).toFixed(1)}%</span>
            </div>
          </div>

          {heatCheck?.high_corr_pairs && heatCheck.high_corr_pairs.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-[var(--color-text-muted)]">High Correlation Pairs</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[var(--color-text-muted)]">
                      <th className="pb-1 text-left">Pair A</th>
                      <th className="pb-1 text-left">Pair B</th>
                      <th className="pb-1 text-right">Corr</th>
                    </tr>
                  </thead>
                  <tbody>
                    {heatCheck.high_corr_pairs.map(([a, b, corr], i) => (
                      <tr key={i}>
                        <td className="py-0.5">{a}</td>
                        <td className="py-0.5">{b}</td>
                        <td className="py-0.5 text-right font-mono text-red-400">{corr.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {heatCheck?.position_weights && Object.keys(heatCheck.position_weights).length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-[var(--color-text-muted)]">Position Weights</p>
              <div className="space-y-1">
                {Object.entries(heatCheck.position_weights).map(([symbol, weight]) => (
                  <div key={symbol} className="flex items-center gap-2">
                    <span className="w-20 truncate text-xs">{symbol}</span>
                    <div className="flex-1 rounded-full bg-[var(--color-bg)] h-2">
                      <div
                        className="h-2 rounded-full bg-blue-500"
                        style={{ width: `${Math.min(weight * 100, 100)}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs">{(weight * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* VaR History */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">VaR History</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => recordMetricsMutation.mutate()}
              disabled={recordMetricsMutation.isPending}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1 text-xs transition-colors hover:bg-[var(--color-surface)] disabled:opacity-50"
            >
              {recordMetricsMutation.isPending ? "Recording..." : "Snapshot Now"}
            </button>
            <select
              value={historyHours}
              onChange={(e) => setHistoryHours(Number(e.target.value))}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs"
            >
              <option value={24}>24h</option>
              <option value={168}>7d</option>
              <option value={720}>30d</option>
            </select>
          </div>
        </div>
        {metricHistory && metricHistory.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                  <th className="pb-2 text-left">Time</th>
                  <th className="pb-2 text-right">VaR 95%</th>
                  <th className="pb-2 text-right">VaR 99%</th>
                  <th className="pb-2 text-right">CVaR 95%</th>
                  <th className="pb-2 text-right">CVaR 99%</th>
                  <th className="pb-2 text-right">Equity</th>
                  <th className="pb-2 text-right">Drawdown</th>
                  <th className="pb-2 text-right">Positions</th>
                </tr>
              </thead>
              <tbody>
                {metricHistory.slice((varHistoryPage - 1) * PAGE_SIZE, varHistoryPage * PAGE_SIZE).map((entry) => (
                  <tr key={entry.id} className="border-b border-[var(--color-border)]/30">
                    <td className="py-1.5 text-[var(--color-text-muted)]">
                      {new Date(entry.recorded_at).toLocaleString()}
                    </td>
                    <td className="py-1.5 text-right font-mono">${entry.var_95.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-mono">${entry.var_99.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-mono">${entry.cvar_95.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-mono">${entry.cvar_99.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-mono">${entry.equity.toLocaleString()}</td>
                    <td className="py-1.5 text-right font-mono">{(entry.drawdown * 100).toFixed(2)}%</td>
                    <td className="py-1.5 text-right font-mono">{entry.open_positions_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={varHistoryPage} pageSize={PAGE_SIZE} total={metricHistory.length} onPageChange={setVarHistoryPage} />
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            No metric history yet. Snapshots are recorded via the record-metrics endpoint.
          </p>
        )}
      </div>

      {/* Trade Audit Log */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h3 className="mb-4 text-lg font-semibold">Trade Audit Log</h3>
        {tradeLog && tradeLog.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                  <th className="pb-2 text-left">Time</th>
                  <th className="pb-2 text-left">Symbol</th>
                  <th className="pb-2 text-left">Side</th>
                  <th className="pb-2 text-right">Size</th>
                  <th className="pb-2 text-right">Price</th>
                  <th className="pb-2 text-center">Result</th>
                  <th className="pb-2 text-left">Reason</th>
                </tr>
              </thead>
              <tbody>
                {tradeLog.slice((tradeLogPage - 1) * PAGE_SIZE, tradeLogPage * PAGE_SIZE).map((entry) => (
                  <tr
                    key={entry.id}
                    className={`border-b border-[var(--color-border)]/30 ${
                      entry.approved ? "bg-green-500/5" : "bg-red-500/5"
                    }`}
                  >
                    <td className="py-1.5 text-[var(--color-text-muted)]">
                      {new Date(entry.checked_at).toLocaleString()}
                    </td>
                    <td className="py-1.5 font-mono">{entry.symbol}</td>
                    <td className={`py-1.5 font-medium ${entry.side === "buy" ? "text-green-400" : "text-red-400"}`}>
                      {entry.side.toUpperCase()}
                    </td>
                    <td className="py-1.5 text-right font-mono">{entry.size}</td>
                    <td className="py-1.5 text-right font-mono">${entry.entry_price.toLocaleString()}</td>
                    <td className="py-1.5 text-center">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          entry.approved ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {entry.approved ? "Approved" : "Rejected"}
                      </span>
                    </td>
                    <td className="py-1.5 text-[var(--color-text-muted)]">{entry.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={tradeLogPage} pageSize={PAGE_SIZE} total={tradeLog.length} onPageChange={setTradeLogPage} />
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            No trade checks recorded yet. Use the Trade Checker above to validate trades.
          </p>
        )}
      </div>
      {/* Alert History */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h3 className="mb-4 text-lg font-semibold">Alert History</h3>
        <div className="mb-4 flex gap-3">
          <select
            value={alertSeverityFilter}
            onChange={(e) => { setAlertSeverityFilter(e.target.value); setAlertsPage(1); }}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs"
          >
            <option value="">All Severities</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </select>
          <input
            type="text"
            placeholder="Filter by event type"
            value={alertEventFilter}
            onChange={(e) => { setAlertEventFilter(e.target.value); setAlertsPage(1); }}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs"
          />
        </div>
        {alerts && alerts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                  <th className="pb-2 text-left">Time</th>
                  <th className="pb-2 text-left">Event</th>
                  <th className="pb-2 text-left">Severity</th>
                  <th className="pb-2 text-left">Channel</th>
                  <th className="pb-2 text-center">Delivered</th>
                  <th className="pb-2 text-left">Message</th>
                </tr>
              </thead>
              <tbody>
                {alerts.slice((alertsPage - 1) * PAGE_SIZE, alertsPage * PAGE_SIZE).map((alert) => (
                  <tr key={alert.id} className="border-b border-[var(--color-border)]/30">
                    <td className="py-1.5 text-[var(--color-text-muted)]">
                      {new Date(alert.created_at).toLocaleString()}
                    </td>
                    <td className="py-1.5 font-mono">{alert.event_type}</td>
                    <td className="py-1.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          alert.severity === "critical"
                            ? "bg-red-500/20 text-red-400"
                            : alert.severity === "warning"
                              ? "bg-yellow-500/20 text-yellow-400"
                              : "bg-blue-500/20 text-blue-400"
                        }`}
                      >
                        {alert.severity}
                      </span>
                    </td>
                    <td className="py-1.5 font-mono">{alert.channel}</td>
                    <td className="py-1.5 text-center">
                      {alert.delivered ? (
                        <span className="text-green-400">Yes</span>
                      ) : (
                        <span className="text-red-400" title={alert.error}>No</span>
                      )}
                    </td>
                    <td className="py-1.5 max-w-xs truncate text-[var(--color-text-muted)]">{alert.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={alertsPage} pageSize={PAGE_SIZE} total={alerts.length} onPageChange={setAlertsPage} />
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            No alerts recorded yet. Alerts are generated on trade rejections, halts, and daily resets.
          </p>
        )}
      </div>
      </section>
    </div>
  );
}

function StatusCard({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
      <p className={`text-xl font-bold ${className}`}>{value}</p>
    </div>
  );
}

function LimitRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-[var(--color-text-muted)]">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}
