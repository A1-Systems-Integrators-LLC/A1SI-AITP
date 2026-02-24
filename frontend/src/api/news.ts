import { api } from "./client";
import type { AssetClass, NewsArticle, SentimentSummary } from "../types";

export const newsApi = {
  list: (assetClass?: AssetClass, symbol?: string, limit?: number) => {
    const parts: string[] = [];
    if (assetClass) parts.push(`asset_class=${assetClass}`);
    if (symbol) parts.push(`symbol=${symbol}`);
    if (limit) parts.push(`limit=${limit}`);
    const qs = parts.length > 0 ? `?${parts.join("&")}` : "";
    return api.get<NewsArticle[]>(`/market/news/${qs}`);
  },
  sentiment: (assetClass?: AssetClass, hours?: number) => {
    const parts: string[] = [];
    if (assetClass) parts.push(`asset_class=${assetClass}`);
    if (hours) parts.push(`hours=${hours}`);
    const qs = parts.length > 0 ? `?${parts.join("&")}` : "";
    return api.get<SentimentSummary>(`/market/news/sentiment/${qs}`);
  },
  fetch: (assetClass: AssetClass) =>
    api.post<{ asset_class: string; articles_fetched: number; message: string }>(
      "/market/news/fetch/",
      { asset_class: assetClass },
    ),
};
