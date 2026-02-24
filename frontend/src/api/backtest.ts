import { api } from "./client";
import type { AssetClass, BacktestComparison, BacktestResult, StrategyInfo } from "../types";

export const backtestApi = {
  run: (params: {
    framework: string;
    strategy: string;
    symbol: string;
    timeframe: string;
    timerange?: string;
    exchange?: string;
    asset_class?: AssetClass;
  }) => api.post<{ job_id: string }>("/backtest/run/", params),

  results: (limit?: number) =>
    api.get<BacktestResult[]>(`/backtest/results/${limit ? `?limit=${limit}` : ""}`),

  result: (id: number) => api.get<BacktestResult>(`/backtest/results/${id}/`),

  strategies: () => api.get<StrategyInfo[]>("/backtest/strategies/"),

  compare: (ids: number[]) =>
    api.get<BacktestComparison>(`/backtest/compare/?ids=${ids.join(",")}`),
};
