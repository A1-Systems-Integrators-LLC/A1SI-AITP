import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { marketApi } from "../api/market";
import { PriceChart } from "../components/PriceChart";
import type { OHLCVData } from "../types";

const DEFAULT_SYMBOL = "BTC/USDT";

export function MarketAnalysis() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState("1h");

  const { data: ohlcv, isLoading } = useApi<OHLCVData[]>(
    ["ohlcv", symbol, timeframe],
    () => marketApi.ohlcv(symbol, timeframe),
  );

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Market Analysis</h2>

      <div className="mb-4 flex gap-3">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="Symbol"
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        />
        <select
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        >
          <option value="1m">1m</option>
          <option value="5m">5m</option>
          <option value="15m">15m</option>
          <option value="1h">1h</option>
          <option value="4h">4h</option>
          <option value="1d">1d</option>
        </select>
      </div>

      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        {isLoading && <p className="text-sm">Loading chart data...</p>}
        {ohlcv && <PriceChart data={ohlcv} />}
      </div>
    </div>
  );
}
