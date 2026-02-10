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
