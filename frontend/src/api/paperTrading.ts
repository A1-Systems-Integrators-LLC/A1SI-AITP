import { api } from "./client";
import type {
  PaperTradingStatus,
  PaperTradingAction,
  PaperTrade,
  PaperTradingProfit,
  PaperTradingPerformance,
  PaperTradingLogEntry,
} from "../types";

export const paperTradingApi = {
  status: () => api.get<PaperTradingStatus>("/paper-trading/status"),

  start: (strategy: string) =>
    api.post<PaperTradingAction>("/paper-trading/start/", { strategy }),

  stop: () => api.post<PaperTradingAction>("/paper-trading/stop/"),

  openTrades: () => api.get<PaperTrade[]>("/paper-trading/trades"),

  history: (limit = 50) =>
    api.get<PaperTrade[]>(`/paper-trading/history?limit=${limit}`),

  profit: () => api.get<PaperTradingProfit>("/paper-trading/profit"),

  performance: () =>
    api.get<PaperTradingPerformance[]>("/paper-trading/performance"),

  balance: () =>
    api.get<Record<string, unknown>>("/paper-trading/balance"),

  log: (limit = 100) =>
    api.get<PaperTradingLogEntry[]>(`/paper-trading/log?limit=${limit}`),
};
