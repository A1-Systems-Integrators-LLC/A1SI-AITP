import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { tradingApi } from "../api/trading";

export function OrderForm() {
  const queryClient = useQueryClient();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("");
  const [price, setPrice] = useState("");

  const mutation = useMutation({
    mutationFn: tradingApi.createOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setAmount("");
      setPrice("");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      symbol,
      side,
      order_type: price ? "limit" : "market",
      amount: parseFloat(amount),
      price: price ? parseFloat(price) : undefined,
    });
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
        className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {mutation.isPending ? "Placing..." : "Place Order"}
      </button>
      {mutation.isError && (
        <p className="text-sm text-[var(--color-danger)]">
          {(mutation.error as Error).message}
        </p>
      )}
    </form>
  );
}
