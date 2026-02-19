import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { tradingApi } from "../api/trading";
import { useToast } from "../hooks/useToast";
import type { TradingMode } from "../types";

interface OrderFormProps {
  mode?: TradingMode;
}

export function OrderForm({ mode = "paper" }: OrderFormProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("");
  const [price, setPrice] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  const mutation = useMutation({
    mutationFn: tradingApi.createOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      toast(`${side.toUpperCase()} order placed for ${symbol}`, "success");
      setAmount("");
      setPrice("");
      setShowConfirm(false);
    },
    onError: (err) => {
      toast((err as Error).message || "Order failed", "error");
    },
  });

  const orderData = {
    symbol,
    side,
    order_type: price ? ("limit" as const) : ("market" as const),
    amount: parseFloat(amount),
    price: price ? parseFloat(price) : 0,
    exchange_id: "binance",
    mode,
    portfolio_id: 1,
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "live") {
      setShowConfirm(true);
    } else {
      mutation.mutate(orderData);
    }
  };

  const confirmLiveOrder = () => {
    mutation.mutate(orderData);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <input
        type="text"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        placeholder="Symbol (e.g. BTC/USDT)"
        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setSide("buy")}
          className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${
            side === "buy"
              ? "bg-[var(--color-success)] text-white"
              : "border border-[var(--color-border)] text-[var(--color-text-muted)]"
          }`}
        >
          Buy
        </button>
        <button
          type="button"
          onClick={() => setSide("sell")}
          className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium ${
            side === "sell"
              ? "bg-[var(--color-danger)] text-white"
              : "border border-[var(--color-border)] text-[var(--color-text-muted)]"
          }`}
        >
          Sell
        </button>
      </div>
      <input
        type="number"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Amount"
        step="any"
        required
        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
      />
      <input
        type="number"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        placeholder="Price (empty for market)"
        step="any"
        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={mutation.isPending}
        className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${
          mode === "live"
            ? "bg-red-600 hover:bg-red-700"
            : "bg-[var(--color-primary)]"
        }`}
      >
        {mutation.isPending
          ? "Placing..."
          : mode === "live"
            ? "Place Live Order"
            : "Place Paper Order"}
      </button>
      {mutation.isError && (
        <p className="text-sm text-[var(--color-danger)]">
          {(mutation.error as Error).message}
        </p>
      )}

      {/* Live order confirmation dialog */}
      {showConfirm && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 p-4">
          <p className="mb-3 text-sm font-medium text-red-400">
            Confirm LIVE order: {side.toUpperCase()} {amount} {symbol}
            {price ? ` @ $${price}` : " (market)"}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={confirmLiveOrder}
              disabled={mutation.isPending}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {mutation.isPending ? "Submitting..." : "Confirm"}
            </button>
            <button
              type="button"
              onClick={() => setShowConfirm(false)}
              className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
