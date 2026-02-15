export interface ExchangeInfo {
  id: string;
  name: string;
  countries: string[];
  has_fetch_tickers: boolean;
  has_fetch_ohlcv: boolean;
}

export interface Holding {
  id: number;
  portfolio_id: number;
  symbol: string;
  amount: number;
  avg_buy_price: number;
  created_at: string;
  updated_at: string;
}

export interface Portfolio {
  id: number;
  name: string;
  exchange_id: string;
  description: string;
  holdings: Holding[];
  created_at: string;
  updated_at: string;
}

export interface TickerData {
  symbol: string;
  price: number;
  volume_24h: number;
  change_24h: number;
  high_24h: number;
  low_24h: number;
  timestamp: string;
}

export interface OHLCVData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Order {
  id: number;
  exchange_id: string;
  exchange_order_id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: string;
  amount: number;
  price: number;
  filled: number;
  status: string;
  timestamp: string;
  created_at: string;
  updated_at: string;
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

// Risk types
export interface RiskStatus {
  equity: number;
  peak_equity: number;
  drawdown: number;
  daily_pnl: number;
  total_pnl: number;
  open_positions: number;
  is_halted: boolean;
  halt_reason: string;
}

export interface RiskLimits {
  max_portfolio_drawdown: number;
  max_single_trade_risk: number;
  max_daily_loss: number;
  max_open_positions: number;
  max_position_size_pct: number;
  max_correlation: number;
  min_risk_reward: number;
  max_leverage: number;
}

export interface VaRData {
  var_95: number;
  var_99: number;
  cvar_95: number;
  cvar_99: number;
  method: string;
  window_days: number;
}

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

export interface StrategyInfo {
  name: string;
  framework: string;
  file_path: string;
}

// Regime types
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
