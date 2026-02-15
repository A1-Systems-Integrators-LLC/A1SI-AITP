import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { riskApi } from "../api/risk";
import type { RiskLimits, RiskStatus, VaRData, HeatCheckData } from "../types";

export function RiskManagement() {
  const queryClient = useQueryClient();
  const [portfolioId, setPortfolioId] = useState(1);

  const { data: status } = useQuery<RiskStatus>({
    queryKey: ["risk-status", portfolioId],
    queryFn: () => riskApi.getStatus(portfolioId),
  });

  const { data: limits } = useQuery<RiskLimits>({
    queryKey: ["risk-limits", portfolioId],
    queryFn: () => riskApi.getLimits(portfolioId),
  });

  // VaR query
  const [varMethod, setVarMethod] = useState("parametric");
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

  // Limits editor state
  const [isEditing, setIsEditing] = useState(false);
  const [editLimits, setEditLimits] = useState<Partial<RiskLimits>>({});
  const [saveMsg, setSaveMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const limitsMutation = useMutation({
    mutationFn: (updates: Partial<RiskLimits>) => riskApi.updateLimits(portfolioId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-limits", portfolioId] });
      setIsEditing(false);
      setSaveMsg({ type: "success", text: "Limits saved" });
      setTimeout(() => setSaveMsg(null), 3000);
    },
    onError: () => {
      setSaveMsg({ type: "error", text: "Failed to save limits" });
      setTimeout(() => setSaveMsg(null), 3000);
    },
  });

  // Position sizer state
  const [entryPrice, setEntryPrice] = useState(50000);
  const [stopLoss, setStopLoss] = useState(48000);
  const [posResult, setPosResult] = useState<{ size: number; risk_amount: number; position_value: number } | null>(null);

  const positionMutation = useMutation({
    mutationFn: () => riskApi.positionSize(portfolioId, { entry_price: entryPrice, stop_loss_price: stopLoss }),
    onSuccess: (data) => setPosResult(data),
  });

  // Trade checker state
  const [tradeSymbol, setTradeSymbol] = useState("BTC/USDT");
  const [tradeSide, setTradeSide] = useState("buy");
  const [tradeSize, setTradeSize] = useState(0.1);
  const [tradeEntry, setTradeEntry] = useState(50000);
  const [tradeResult, setTradeResult] = useState<{ approved: boolean; reason: string } | null>(null);

  const tradeMutation = useMutation({
    mutationFn: () =>
      riskApi.checkTrade(portfolioId, {
        symbol: tradeSymbol,
        side: tradeSide,
        size: tradeSize,
        entry_price: tradeEntry,
      }),
    onSuccess: (data) => setTradeResult(data),
  });

  const resetMutation = useMutation({
    mutationFn: () => riskApi.resetDaily(portfolioId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["risk-status", portfolioId] }),
  });

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
    setSaveMsg(null);
  }

  function cancelEditing() {
    setIsEditing(false);
    setEditLimits({});
    setSaveMsg(null);
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
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold">Risk Management</h2>
        <div className="flex items-center gap-2">
          <label className="text-sm text-[var(--color-text-muted)]">Portfolio ID:</label>
          <input
            type="number"
            value={portfolioId}
            onChange={(e) => setPortfolioId(Number(e.target.value))}
            className="w-20 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
          />
        </div>
      </div>

      {/* Status Cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatusCard label="Equity" value={`$${(status?.equity ?? 0).toLocaleString()}`} />
        <StatusCard label="Drawdown" value={`${drawdownPct}%`} className={drawdownColor} />
        <StatusCard label="Daily PnL" value={`$${(status?.daily_pnl ?? 0).toFixed(2)}`}
          className={status && status.daily_pnl >= 0 ? "text-green-400" : "text-red-400"} />
        <StatusCard
          label="Status"
          value={status?.is_halted ? "HALTED" : "Active"}
          className={status?.is_halted ? "text-red-400" : "text-green-400"}
        />
      </div>

      {status?.is_halted && (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Trading halted: {status.halt_reason}
          <button
            onClick={() => resetMutation.mutate()}
            className="ml-3 rounded bg-red-500/20 px-2 py-1 text-xs hover:bg-red-500/30"
          >
            Reset Daily
          </button>
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
          {saveMsg && (
            <div className={`mb-3 rounded p-2 text-xs ${saveMsg.type === "success" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
              {saveMsg.text}
            </div>
          )}
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
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry Price</label>
              <input
                type="number"
                value={entryPrice}
                onChange={(e) => setEntryPrice(Number(e.target.value))}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Stop Loss</label>
              <input
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
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
              <input
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
                <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Size</label>
                <input
                  type="number"
                  step="0.01"
                  value={tradeSize}
                  onChange={(e) => setTradeSize(Number(e.target.value))}
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry</label>
                <input
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
