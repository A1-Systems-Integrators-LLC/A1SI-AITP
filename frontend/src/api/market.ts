import { api } from "./client";
import type { TickerData, OHLCVData } from "../types";

export const marketApi = {
  ticker: (symbol: string) => api.get<TickerData>(`/market/ticker/${symbol}`),
  tickers: (symbols?: string[]) => {
    const params = symbols ? `?symbols=${symbols.join(",")}` : "";
    return api.get<TickerData[]>(`/market/tickers${params}`);
  },
  ohlcv: (symbol: string, timeframe = "1h", limit = 100) =>
    api.get<OHLCVData[]>(
      `/market/ohlcv/${symbol}?timeframe=${timeframe}&limit=${limit}`,
    ),
};
