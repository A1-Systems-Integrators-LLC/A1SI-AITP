import { useApi } from "../hooks/useApi";
import { tradingApi } from "../api/trading";
import { OrderForm } from "../components/OrderForm";
import type { Order } from "../types";

export function Trading() {
  const { data: orders, isLoading } = useApi<Order[]>(
    ["orders"],
    () => tradingApi.listOrders(),
  );

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Trading</h2>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Order form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">New Order</h3>
          <OrderForm />
        </div>

        {/* Order history */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 lg:col-span-2">
          <h3 className="mb-4 text-lg font-semibold">Order History</h3>
          {isLoading && <p className="text-sm">Loading orders...</p>}
          {orders && orders.length === 0 && (
            <p className="text-sm text-[var(--color-text-muted)]">
              No orders yet.
            </p>
          )}
          {orders && orders.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                    <th className="pb-2">Symbol</th>
                    <th className="pb-2">Side</th>
                    <th className="pb-2">Amount</th>
                    <th className="pb-2">Price</th>
                    <th className="pb-2">Status</th>
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
                        {o.price ? `$${o.price.toLocaleString()}` : "Market"}
                      </td>
                      <td className="py-2">{o.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
