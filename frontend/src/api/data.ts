import { api } from "./client";
import type { DataFileInfo } from "../types";

export const dataApi = {
  list: () => api.get<DataFileInfo[]>("/data/"),

  getInfo: (exchange: string, symbol: string, timeframe: string) => {
    const safeSymbol = symbol.replace("/", "_");
    return api.get<DataFileInfo>(`/data/${exchange}/${safeSymbol}/${timeframe}`);
  },

  download: (params: {
    symbols: string[];
    timeframes: string[];
    exchange: string;
    since_days: number;
  }) => api.post<{ job_id: string }>("/data/download/", params),

  generateSample: (params: {
    symbols: string[];
    timeframes: string[];
    days: number;
  }) => api.post<{ job_id: string }>("/data/generate-sample/", params),
};
