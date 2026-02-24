export type AssetClass = "crypto" | "equity" | "forex";

export interface MarketStatus {
  is_open: boolean;
  next_open: string | null;
  next_close: string | null;
  timezone: string;
  session: string;
}

// ── Generated types from OpenAPI schema (via openapi-typescript) ──
// Run `npm run generate:types` or `make generate-types` to regenerate.
import type { components } from "./api-schema";

// Portfolio
export type Holding = components["schemas"]["Holding"];
export type HoldingCreate = components["schemas"]["HoldingCreate"];
export type Portfolio = components["schemas"]["Portfolio"];
export type PortfolioCreate = components["schemas"]["PortfolioCreate"];

// Trading — orders and enums
export type Order = components["schemas"]["Order"];
export type OrderCreate = components["schemas"]["OrderCreate"];
export type OrderFillEvent = components["schemas"]["OrderFillEvent"];
export type OrderStatus = components["schemas"]["StatusEnum"];
export type TradingMode = components["schemas"]["OrderModeEnum"];

// Market — exchange info, tickers, OHLCV
export type ExchangeInfo = components["schemas"]["ExchangeInfo"];
export type TickerData = components["schemas"]["TickerData"];
export type OHLCVData = components["schemas"]["OHLCVData"];
export type ExchangeTestResult = components["schemas"]["ExchangeTestResult"];

// Risk — core types
export type RiskStatus = components["schemas"]["RiskStatus"];
export type RiskLimits = components["schemas"]["RiskLimits"];
export type VaRData = components["schemas"]["VaRResponse"];
export type HaltResponse = components["schemas"]["HaltResponse"];
export type AlertLogEntry = components["schemas"]["AlertLog"];
export type StrategyInfo = components["schemas"]["StrategyInfo"];

// Analysis — jobs and backtests
export type BacktestRequest = components["schemas"]["BacktestRequest"];

// ── Manual types (need more specific types than schema provides) ──

export interface LiveTradingStatus {
  exchange_connected: boolean;
  exchange_error: string;
  is_halted: boolean;
  active_live_orders: number;
}

// Background Job types
export interface BackgroundJob {
  id: string;
  job_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  progress_message: string;
  params: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

// Data Pipeline types
export interface DataFileInfo {
  exchange: string;
  symbol: string;
  timeframe: string;
  rows: number;
  start: string | null;
  end: string | null;
  file: string;
}

// Screening types
export interface ScreenResult {
  id: number;
  job_id: string;
  symbol: string;
  timeframe: string;
  strategy_name: string;
  top_results: Record<string, unknown>[];
  summary: Record<string, unknown>;
  total_combinations: number;
  created_at: string;
}

// Risk — types with complex nested structures
export interface HeatCheckData {
  healthy: boolean;
  issues: string[];
  drawdown: number;
  daily_pnl: number;
  open_positions: number;
  max_correlation: number;
  high_corr_pairs: [string, string, number][];
  max_concentration: number;
  position_weights: Record<string, number>;
  var_95: number;
  var_99: number;
  cvar_95: number;
  cvar_99: number;
  is_halted: boolean;
}

export interface RiskMetricHistoryEntry {
  id: number;
  portfolio_id: number;
  var_95: number;
  var_99: number;
  cvar_95: number;
  cvar_99: number;
  method: string;
  drawdown: number;
  equity: number;
  open_positions_count: number;
  recorded_at: string;
}

export interface TradeCheckLogEntry {
  id: number;
  portfolio_id: number;
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  stop_loss_price: number | null;
  approved: boolean;
  reason: string;
  equity_at_check: number;
  drawdown_at_check: number;
  open_positions_at_check: number;
  checked_at: string;
}

// Notification preferences
export interface NotificationPreferences {
  portfolio_id: number;
  telegram_enabled: boolean;
  webhook_enabled: boolean;
  on_order_submitted: boolean;
  on_order_filled: boolean;
  on_order_cancelled: boolean;
  on_risk_halt: boolean;
  on_trade_rejected: boolean;
  on_daily_summary: boolean;
}

// Backtest types
export interface BacktestResult {
  id: number;
  job_id: string;
  framework: string;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  timerange: string;
  metrics: Record<string, unknown>;
  trades: Record<string, unknown>[];
  config: Record<string, unknown>;
  created_at: string;
}

// Regime types — need RegimeType union (schema only has string)
export type RegimeType =
  | "strong_trend_up"
  | "weak_trend_up"
  | "ranging"
  | "weak_trend_down"
  | "strong_trend_down"
  | "high_volatility"
  | "unknown";

export interface RegimeState {
  symbol: string;
  regime: RegimeType;
  confidence: number;
  adx_value: number;
  bb_width_percentile: number;
  ema_slope: number;
  trend_alignment: number;
  price_structure_score: number;
  transition_probabilities: Record<string, number>;
}

export interface StrategyWeight {
  strategy_name: string;
  weight: number;
  position_size_factor: number;
}

export interface RoutingDecision {
  symbol: string;
  regime: RegimeType;
  confidence: number;
  primary_strategy: string;
  weights: StrategyWeight[];
  position_size_modifier: number;
  reasoning: string;
}

export interface RegimeHistoryEntry {
  timestamp: string;
  regime: RegimeType;
  confidence: number;
  adx_value: number;
  bb_width_percentile: number;
}

export interface RegimePositionSize {
  symbol: string;
  regime: RegimeType;
  regime_modifier: number;
  position_size: number;
  entry_price: number;
  stop_loss_price: number;
  primary_strategy: string;
}

// Paper Trading types
export interface PaperTradingStatus {
  running: boolean;
  strategy: string | null;
  pid: number | null;
  started_at: string | null;
  uptime_seconds: number;
  exit_code: number | null;
}

export interface PaperTradingAction {
  status: string;
  strategy: string | null;
  pid: number | null;
  started_at: string | null;
  error: string | null;
}

export interface PaperTrade {
  trade_id?: number;
  pair?: string;
  stake_amount?: number;
  amount?: number;
  open_date?: string;
  close_date?: string;
  open_rate?: number;
  close_rate?: number;
  profit_ratio?: number;
  profit_abs?: number;
  is_open?: boolean;
  [key: string]: unknown;
}

export interface PaperTradingProfit {
  profit_all_coin?: number;
  profit_all_percent?: number;
  profit_closed_coin?: number;
  profit_closed_percent?: number;
  trade_count?: number;
  closed_trade_count?: number;
  winning_trades?: number;
  losing_trades?: number;
  [key: string]: unknown;
}

export interface PaperTradingPerformance {
  pair: string;
  profit: number;
  count: number;
  [key: string]: unknown;
}

export interface PaperTradingLogEntry {
  timestamp: string;
  event: string;
  [key: string]: unknown;
}

// Exchange Config types — manual (generated has enum exchange_id)
export interface ExchangeConfig {
  id: number;
  name: string;
  exchange_id: string;
  api_key_masked: string;
  has_api_key: boolean;
  has_api_secret: boolean;
  has_passphrase: boolean;
  is_sandbox: boolean;
  is_default: boolean;
  is_active: boolean;
  last_tested_at: string | null;
  last_test_success: boolean | null;
  last_test_error: string;
  options: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ExchangeConfigCreate {
  name: string;
  exchange_id: string;
  api_key?: string;
  api_secret?: string;
  passphrase?: string;
  is_sandbox: boolean;
  is_default: boolean;
  is_active?: boolean;
  options?: Record<string, unknown>;
}

export interface DataSourceConfig {
  id: number;
  exchange_config: number;
  exchange_name: string;
  symbols: string[];
  timeframes: string[];
  is_active: boolean;
  fetch_interval_minutes: number;
  last_fetched_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DataSourceConfigCreate {
  exchange_config: number;
  symbols: string[];
  timeframes: string[];
  is_active?: boolean;
  fetch_interval_minutes?: number;
}

// WebSocket event types — discriminated unions for type-safe message routing
export interface HaltStatusEvent {
  type: "halt_status";
  data: {
    is_halted: boolean;
    halt_reason: string;
  };
}

export interface OrderUpdateEvent {
  type: "order_update";
  data: {
    id: number;
    symbol: string;
    side: string;
    status: string;
    amount: number;
    filled: number;
    avg_fill_price: number | null;
  };
}

export interface RiskAlertEvent {
  type: "risk_alert";
  data: {
    severity: "info" | "warning" | "critical";
    event_type: string;
    message: string;
    portfolio_id: number;
  };
}

export type SystemEvent = HaltStatusEvent | OrderUpdateEvent | RiskAlertEvent;

// News types
export interface NewsArticle {
  article_id: string;
  title: string;
  url: string;
  source: string;
  summary: string;
  published_at: string;
  symbols: string[];
  asset_class: AssetClass;
  sentiment_score: number;
  sentiment_label: "positive" | "negative" | "neutral";
  created_at: string;
}

export interface SentimentSummary {
  asset_class: string;
  hours: number;
  total_articles: number;
  avg_score: number;
  overall_label: "positive" | "negative" | "neutral";
  positive_count: number;
  negative_count: number;
  neutral_count: number;
}

// Platform types
export interface FrameworkStatus {
  name: string;
  installed: boolean;
  version: string | null;
}

export interface PlatformStatus {
  frameworks: FrameworkStatus[];
  data_files: number;
  active_jobs: number;
}
