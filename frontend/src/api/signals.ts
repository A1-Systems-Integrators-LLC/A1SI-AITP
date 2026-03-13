import { api } from "./client";
import type {
  AssetClass,
  CompositeSignal,
  EntryCheckResponse,
  MLModelPerformanceData,
  MLPredictionEntry,
  SignalAttributionEntry,
  SourceAccuracyData,
  StrategyStatus,
  WeightRecommendation,
} from "../types";

export const signalsApi = {
  /** Composite conviction signal for a single symbol. */
  getSignal: (symbol: string, assetClass?: AssetClass, strategy?: string) => {
    const encoded = symbol.replace("/", "-");
    const params = new URLSearchParams();
    if (assetClass) params.set("asset_class", assetClass);
    if (strategy) params.set("strategy", strategy);
    const qs = params.toString();
    return api.get<CompositeSignal>(`/signals/${encoded}/${qs ? `?${qs}` : ""}`);
  },

  /** Batch composite signals for multiple symbols. */
  batchSignals: (symbols: string[], assetClass?: AssetClass, strategyName?: string) =>
    api.post<CompositeSignal[]>("/signals/batch/", {
      symbols,
      asset_class: assetClass ?? "crypto",
      strategy_name: strategyName ?? "CryptoInvestorV1",
    }),

  /** Entry gate check. */
  entryCheck: (symbol: string, strategy: string, assetClass?: AssetClass) => {
    const encoded = symbol.replace("/", "-");
    return api.post<EntryCheckResponse>(`/signals/${encoded}/entry-check/`, {
      strategy,
      asset_class: assetClass ?? "crypto",
    });
  },

  /** Strategy orchestrator status. */
  strategyStatus: (assetClass?: AssetClass) => {
    const qs = assetClass ? `?asset_class=${assetClass}` : "";
    return api.get<StrategyStatus[]>(`/signals/strategy-status/${qs}`);
  },

  /** List signal attributions. */
  attributionList: (params?: {
    asset_class?: AssetClass;
    strategy?: string;
    outcome?: "win" | "loss" | "open";
    limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.asset_class) sp.set("asset_class", params.asset_class);
    if (params?.strategy) sp.set("strategy", params.strategy);
    if (params?.outcome) sp.set("outcome", params.outcome);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return api.get<SignalAttributionEntry[]>(`/signals/attribution/${qs ? `?${qs}` : ""}`);
  },

  /** Get single attribution by order ID. */
  attributionDetail: (orderId: string) =>
    api.get<SignalAttributionEntry>(`/signals/attribution/${orderId}/`),

  /** Source accuracy statistics. */
  accuracy: (params?: {
    asset_class?: AssetClass;
    strategy?: string;
    window_days?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.asset_class) sp.set("asset_class", params.asset_class);
    if (params?.strategy) sp.set("strategy", params.strategy);
    if (params?.window_days) sp.set("window_days", String(params.window_days));
    const qs = sp.toString();
    return api.get<SourceAccuracyData>(`/signals/accuracy/${qs ? `?${qs}` : ""}`);
  },

  /** Signal weight recommendations. */
  weights: (params?: {
    asset_class?: AssetClass;
    strategy?: string;
    window_days?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.asset_class) sp.set("asset_class", params.asset_class);
    if (params?.strategy) sp.set("strategy", params.strategy);
    if (params?.window_days) sp.set("window_days", String(params.window_days));
    const qs = sp.toString();
    return api.get<WeightRecommendation>(`/signals/weights/${qs ? `?${qs}` : ""}`);
  },

  /** Recent ML predictions for a symbol. */
  mlPredictions: (symbol: string, limit?: number) => {
    const encoded = symbol.replace("/", "-");
    const qs = limit ? `?limit=${limit}` : "";
    return api.get<MLPredictionEntry[]>(`/ml/predictions/${encoded}/${qs}`);
  },

  /** Model performance metrics. */
  mlModelPerformance: (modelId: string) =>
    api.get<MLModelPerformanceData>(`/ml/models/${modelId}/performance/`),
};
