import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSystemEvents } from "../hooks/useSystemEvents";
import { useToast } from "../hooks/useToast";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useAssetClass } from "../hooks/useAssetClass";
import { tradingApi } from "../api/trading";
import { OrderForm } from "../components/OrderForm";
import { QueryResult } from "../components/QueryResult";
import { Pagination } from "../components/Pagination";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ExchangeHealthBadge } from "../components/ExchangeHealthBadge";
import { getErrorMessage } from "../utils/errors";
import type { Order, OrderStatus, TradingMode, TradingPerformanceSummary } from "../types";

const PAGE_SIZE = 15;

const STATUS_COLORS: Record<OrderStatus, string> = {
  pending: "bg-gray-500/20 text-gray-400",
  submitted: "bg-blue-500/20 text-blue-400",
  open: "bg-blue-500/20 text-blue-400",
  partial_fill: "bg-yellow-500/20 text-yellow-400",
  filled: "bg-green-500/20 text-green-400",
  cancelled: "bg-gray-500/20 text-gray-400",
  rejected: "bg-red-500/20 text-red-400",
  error: "bg-red-500/20 text-red-400",
};

const CANCELLABLE: Set<OrderStatus> = new Set([
  "pending",
  "submitted",
  "open",
  "partial_fill",
]);

export function Trading() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();
  const [mode, setMode] = useLocalStorage<TradingMode>("ci:trading-mode", "paper");
  const [page, setPage] = useState(1);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showCancelAll, setShowCancelAll] = useState(false);
  const { isConnected, isHalted } = useSystemEvents();

  const amountLabel = assetClass === "equity" ? "Shares" : assetClass === "forex" ? "Lots" : "Amount";

  useEffect(() => { document.title = "Trading | A1SI-AITP"; }, []);

  const { data: perfSummary } = useQuery<TradingPerformanceSummary>({
    queryKey: ["trading-performance", mode, assetClass],
    queryFn: () => tradingApi.performanceSummary({ mode, asset_class: assetClass }),
  });

  const ordersQuery = useQuery<Order[]>({
    queryKey: ["orders", mode, assetClass, symbolFilter, statusFilter],
    queryFn: () => tradingApi.listOrders(50, mode, assetClass, symbolFilter || undefined, statusFilter || undefined),
  });

  const cancelMutation = useMutation({
    mutationFn: tradingApi.cancelOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      toast("Order cancelled", "info");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to cancel order", "error"),
  });

  const cancelAllMutation = useMutation({
    mutationFn: () => tradingApi.cancelAll(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      toast(`Cancelled ${data.cancelled ?? 0} orders`, "info");
      setShowCancelAll(false);
    },
    onError: (err) => {
      toast(getErrorMessage(err) || "Failed to cancel all orders", "error");
      setShowCancelAll(false);
    },
  });

  return (
    <div>
      <section aria-labelledby="page-heading">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 id="page-heading" className="text-2xl font-bold">Trading</h2>
          <ExchangeHealthBadge />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMode("paper")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              mode === "paper"
                ? "bg-blue-600 text-white"
                : "border border-[var(--color-border)] text-[var(--color-text-muted)]"
            }`}
          >
            Paper
          </button>
          <button
            onClick={() => setMode("live")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              mode === "live"
                ? "bg-red-600 text-white"
                : "border border-[var(--color-border)] text-[var(--color-text-muted)]"
            }`}
          >
            Live
          </button>
        </div>
      </div>

      {/* WebSocket disconnected banner */}
      {!isConnected && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          WebSocket disconnected — live order updates and halt notifications are unavailable. Reconnecting...
        </div>
      )}

      {/* Orders query error banner */}
      {ordersQuery.isError && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Failed to load orders: {ordersQuery.error instanceof Error ? ordersQuery.error.message : "Unknown error"}
        </div>
      )}

      {/* Live mode warning banner */}
      {mode === "live" && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          <span>
            <span className="font-bold">LIVE MODE</span> — Orders will be
            submitted to the exchange. Real money is at risk.
          </span>
          <button
            onClick={() => setShowCancelAll(true)}
            className="rounded border border-red-600 px-3 py-1 text-xs font-medium text-red-400 hover:bg-red-900/30"
          >
            Cancel All Orders
          </button>
        </div>
      )}

      {/* Halt banner */}
      {isHalted && (
        <div className="mb-4 animate-pulse rounded-lg border border-red-500/50 bg-red-500/20 p-3 text-sm font-bold text-red-400">
          TRADING HALTED — All live order submissions are blocked
        </div>
      )}

      {/* Performance Summary */}
      {perfSummary && perfSummary.total_trades > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <p className="text-xs text-[var(--color-text-muted)]">Win Rate</p>
            <p className="text-lg font-bold">{perfSummary.win_rate.toFixed(1)}%</p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <p className="text-xs text-[var(--color-text-muted)]">Profit Factor</p>
            <p className="text-lg font-bold">{perfSummary.profit_factor != null ? perfSummary.profit_factor.toFixed(2) : "\u221E"}</p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <p className="text-xs text-[var(--color-text-muted)]">Total P&L</p>
            <p className={`text-lg font-bold ${perfSummary.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
              ${perfSummary.total_pnl.toFixed(2)}
            </p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <p className="text-xs text-[var(--color-text-muted)]">Total Trades</p>
            <p className="text-lg font-bold">{perfSummary.total_trades}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Order form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">New Order</h3>
          <OrderForm mode={mode} />
        </div>

        {/* Order history */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">
              {mode === "live" ? "Live" : "Paper"} Orders
            </h3>
            <a
              href={`/api/trading/orders/export/?mode=${mode}&asset_class=${assetClass}`}
              className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-bg)]"
            >
              Export CSV
            </a>
          </div>
          <div className="mb-3 flex gap-2">
            <input
              type="text"
              placeholder="Filter by symbol..."
              value={symbolFilter}
              onChange={(e) => { setSymbolFilter(e.target.value); setPage(1); }}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs"
            />
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs"
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="submitted">Submitted</option>
              <option value="open">Open</option>
              <option value="partial_fill">Partial Fill</option>
              <option value="filled">Filled</option>
              <option value="cancelled">Cancelled</option>
              <option value="rejected">Rejected</option>
              <option value="error">Error</option>
            </select>
          </div>
          <QueryResult query={ordersQuery}>
            {(orders) => orders.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)]">
                No {mode} orders yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                      <th className="pb-2">Symbol</th>
                      <th className="pb-2">Side</th>
                      <th className="pb-2">{amountLabel}</th>
                      <th className="pb-2">Price</th>
                      <th className="pb-2">Filled</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((o) => (
                      <tr
                        key={o.id}
                        className="border-b border-[var(--color-border)]"
                      >
                        <td className="py-2">{o.symbol}</td>
                        <td
                          className={`py-2 font-medium ${
                            o.side === "buy"
                              ? "text-[var(--color-success)]"
                              : "text-[var(--color-danger)]"
                          }`}
                        >
                          {o.side.toUpperCase()}
                        </td>
                        <td className="py-2">{o.amount}</td>
                        <td className="py-2">
                          {o.avg_fill_price
                            ? `$${o.avg_fill_price.toLocaleString()}`
                            : o.price
                              ? `$${o.price.toLocaleString()}`
                              : "Market"}
                        </td>
                        <td className="py-2">
                          {o.filled > 0
                            ? `${o.filled}/${o.amount}`
                            : "\u2014"}
                        </td>
                        <td className="py-2">
                          <span
                            className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                              STATUS_COLORS[o.status] ?? ""
                            }`}
                          >
                            {o.status.replace("_", " ")}
                          </span>
                          {o.reject_reason && (
                            <p className="mt-0.5 text-xs text-red-400">
                              {o.reject_reason}
                            </p>
                          )}
                          {o.error_message && (
                            <p className="mt-0.5 text-xs text-red-400">
                              {o.error_message}
                            </p>
                          )}
                        </td>
                        <td className="py-2">
                          {CANCELLABLE.has(o.status) && (
                            <button
                              onClick={() => cancelMutation.mutate(o.id)}
                              disabled={cancelMutation.isPending}
                              className="rounded border border-red-700 px-2 py-0.5 text-xs text-red-400 hover:bg-red-900/30 disabled:opacity-50"
                            >
                              Cancel
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination page={page} pageSize={PAGE_SIZE} total={orders.length} onPageChange={setPage} />
              </div>
            )}
          </QueryResult>
        </div>
      </div>

      <ConfirmDialog
        open={showCancelAll}
        title="Cancel All Orders"
        message="This will cancel all open live orders. This action cannot be undone."
        confirmLabel="Cancel All"
        variant="danger"
        isPending={cancelAllMutation.isPending}
        onConfirm={() => cancelAllMutation.mutate()}
        onCancel={() => setShowCancelAll(false)}
      />
      </section>
    </div>
  );
}
