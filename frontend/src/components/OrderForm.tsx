import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tradingApi } from "../api/trading";
import { portfoliosApi } from "../api/portfolios";
import { useToast } from "../hooks/useToast";
import { useAssetClass } from "../hooks/useAssetClass";
import { DEFAULT_SYMBOL } from "../constants/assetDefaults";
import { getErrorMessage } from "../utils/errors";
import type { Portfolio, TradingMode } from "../types";

interface OrderFormProps {
  mode?: TradingMode;
}

export function OrderForm({ mode = "paper" }: OrderFormProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();
  const amountLabel = assetClass === "equity" ? "Shares" : assetClass === "forex" ? "Lots" : "Amount";
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL[assetClass]);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("");
  const [price, setPrice] = useState("");
  const [selectedPortfolio, setSelectedPortfolio] = useState<string>("");
  const [showConfirm, setShowConfirm] = useState(false);

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: ["portfolios"],
    queryFn: portfoliosApi.list,
  });

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
      toast(getErrorMessage(err) || "Order failed", "error");
    },
  });

  const activePortfolio = portfolios?.find((p) => String(p.id) === selectedPortfolio);
  const orderData = {
    symbol,
    side,
    order_type: price ? ("limit" as const) : ("market" as const),
    amount: parseFloat(amount),
    price: price ? parseFloat(price) : 0,
    exchange_id: activePortfolio?.exchange_id ?? "binance",
    mode,
    portfolio_id: activePortfolio?.id ?? 1,
    asset_class: assetClass,
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
      <div>
        <label htmlFor="order-portfolio" className="mb-1 block text-xs text-[var(--color-text-muted)]">Portfolio</label>
        <select
          id="order-portfolio"
          value={selectedPortfolio}
          onChange={(e) => setSelectedPortfolio(e.target.value)}
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        >
          <option value="">Select portfolio...</option>
          {portfolios?.map((p) => (
            <option key={p.id} value={String(p.id)}>
              {p.name} ({p.exchange_id})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="order-symbol" className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
        <input
          id="order-symbol"
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="BTC/USDT"
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        />
      </div>
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
      <div>
        <label htmlFor="order-amount" className="mb-1 block text-xs text-[var(--color-text-muted)]">{amountLabel}</label>
        <input
          id="order-amount"
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.0"
          step="any"
          required
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label htmlFor="order-price" className="mb-1 block text-xs text-[var(--color-text-muted)]">Price (empty for market)</label>
        <input
          id="order-price"
          type="number"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="0.00"
          step="any"
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        />
      </div>
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
