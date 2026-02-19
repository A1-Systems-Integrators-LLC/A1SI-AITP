import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSystemEvents } from "../hooks/useSystemEvents";
import { useToast } from "../hooks/useToast";
import { tradingApi } from "../api/trading";
import { OrderForm } from "../components/OrderForm";
import { QueryResult } from "../components/QueryResult";
import type { Order, OrderStatus, TradingMode } from "../types";

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
  const [mode, setMode] = useState<TradingMode>("paper");
  const { isHalted } = useSystemEvents();

  const ordersQuery = useQuery<Order[]>({
    queryKey: ["orders", mode],
    queryFn: () => tradingApi.listOrders(50, mode),
  });

  const cancelMutation = useMutation({
    mutationFn: tradingApi.cancelOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      toast("Order cancelled", "info");
    },
    onError: (err) => toast((err as Error).message || "Failed to cancel order", "error"),
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold">Trading</h2>
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

      {/* Live mode warning banner */}
      {mode === "live" && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          <span className="font-bold">LIVE MODE</span> — Orders will be
          submitted to the exchange. Real money is at risk.
        </div>
      )}

      {/* Halt banner */}
      {isHalted && (
        <div className="mb-4 animate-pulse rounded-lg border border-red-500/50 bg-red-500/20 p-3 text-sm font-bold text-red-400">
          TRADING HALTED — All live order submissions are blocked
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
          <h3 className="mb-4 text-lg font-semibold">
            {mode === "live" ? "Live" : "Paper"} Orders
          </h3>
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
                      <th className="pb-2">Amount</th>
                      <th className="pb-2">Price</th>
                      <th className="pb-2">Filled</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((o) => (
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
              </div>
            )}
          </QueryResult>
        </div>
      </div>
    </div>
  );
}
