# Multi-Tier Trading Architecture

This document describes the graduated trading system used by the crypto-investor platform. Strategies progress through tiers of increasing fidelity—from rapid parameter discovery to live execution—unified by a shared data pipeline, risk management layer, and market regime detection system.

---

## Architecture Overview

```
                      MARKET DATA (CCXT)
                    Binance, Bybit, Kraken, ...
                            │
                            ▼
               ┌─────────────────────────┐
               │    Shared Data Pipeline  │
               │    Parquet OHLCV Store   │
               │    Quality Validation    │
               │    Format Converters     │
               └────────┬────────────────┘
                        │
          ┌─────────────┼──────────────┬──────────────┐
          ▼             ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐
    │  Tier 1  │  │  Tier 2  │  │  Tier 3   │  │  Tier 4  │
    │ VectorBT │  │ Freqtrade│  │ Nautilus  │  │   HFT    │
    │ Research │  │ Backtest │  │  Trader   │  │ Backtest │
    │          │  │ & Live   │  │           │  │          │
    │ 1000s of │  │ Event-   │  │ Multi-    │  │ Tick-    │
    │ params/  │  │ driven   │  │ asset     │  │ level    │
    │ second   │  │ sims     │  │ execution │  │ microstr │
    └────┬─────┘  └────┬─────┘  └─────┬─────┘  └──────────┘
         │             │              │
         └──────┬──────┘              │
                ▼                     │
    ┌───────────────────┐             │
    │  Market Regime    │─────────────┘
    │  Detector         │
    │  + Strategy Router│
    └───────────────────┘
                │
                ▼
    ┌───────────────────────────────────┐
    │     Risk Management Wrapper       │
    │  Position sizing, drawdown halt,  │
    │  correlation checks, VaR/CVaR     │
    └───────────────────────────────────┘
```

---

## Tier 1: VectorBT — Research & Screening

**Purpose:** Rapidly screen thousands of parameter combinations to find promising strategy configurations before investing time in full backtesting.

**Location:** `research/scripts/vbt_screener.py`

**How it works:** VectorBT uses vectorized NumPy/pandas operations to simulate portfolios for all parameter combinations simultaneously in memory. This trades precision (no realistic order fill simulation) for speed.

### Screening Strategies

| Strategy | Parameters Tested | What It Finds |
|----------|------------------|---------------|
| SMA Crossover | 10 fast windows x 18 slow windows = 180 combos | Optimal moving average pairs for trend signals |
| RSI Mean Reversion | 4 periods x 4 oversold x 4 overbought = 64 combos | Best RSI thresholds for range-bound markets |
| Bollinger Breakout | 5 periods x 4 std deviations = 20 combos | Band settings for breakout detection |
| EMA + RSI Combo | 3 EMA periods x 3 RSI entry levels = 9 combos | Trend filter + momentum entry pairings |
| Volatility Breakout | 5 breakout periods x 4 volume factors x 3 ADX ranges = 60 combos | Multi-factor breakout conditions |

**Total:** 333+ parameter combinations screened in seconds.

### Metrics Computed

Every combination is scored on:
- `total_return` — overall portfolio return
- `sharpe_ratio` — risk-adjusted return (primary ranking metric)
- `max_drawdown` — worst peak-to-trough decline
- `win_rate` — percentage of profitable trades
- `profit_factor` — gross profit / gross loss
- `num_trades` — trade frequency

### Output

Results are saved as ranked CSV files plus a JSON summary:

```
research/results/{SYMBOL}_{TIMEFRAME}_{TIMESTAMP}/
  ├── sma_crossover.csv
  ├── rsi_mean_reversion.csv
  ├── bollinger_breakout.csv
  ├── ema_rsi_combo.csv
  ├── volatility_breakout.csv
  └── summary.json
```

### CLI

```bash
python run.py research screen --symbol BTC/USDT --timeframe 1h --fees 0.001
```

---

## Tier 2: Freqtrade — Backtesting & Live Trading

**Purpose:** Event-driven backtesting with realistic order simulation, fee modeling, and live trading capability. This is the primary execution tier for crypto trading.

**Location:** `freqtrade/user_data/strategies/`

**How it works:** Freqtrade processes candles sequentially, simulates order fills with slippage/fees, and provides hyperparameter optimization (hyperopt). Strategies integrate with the Django backend risk API for trade gating.

### Production Strategies

#### CryptoInvestorV1 — Trend Following

Best for: strong and weak uptrends.

**Entry conditions (all must be true):**
1. EMA alignment: `close > EMA(fast) > EMA(slow)` — uptrend confirmed
2. RSI pullback: `RSI(14) < 40` — momentum reset within uptrend
3. Volume: `volume_ratio > 0.8` — participation above average
4. MACD: histogram positive or turning positive
5. Not chasing: `close < BB_upper * 0.98`

**Exit conditions (any triggers exit):**
- Tiered ROI: 10% immediately, 6% after 1h, 3% after 4h, 1% after 12h
- RSI overbought: `RSI > 80`
- Trend breakdown: price closes below fast EMA
- Stale trade: held >7 days with <1% profit
- ATR trailing stop: tightens from 2x ATR to -2% as profit grows

**Hyperopt parameters:**
| Parameter | Range | Default |
|-----------|-------|---------|
| `buy_ema_fast` | 20-80 | 50 |
| `buy_ema_slow` | 100-300 | 200 |
| `buy_rsi_threshold` | 25-45 | 40 |
| `sell_rsi_threshold` | 70-90 | 80 |
| `atr_multiplier` | 1.5-3.5 | 2.0 |

#### BollingerMeanReversion — Range Trading

Best for: ranging/sideways markets (ADX < 30).

**Entry conditions:**
1. Price below lower Bollinger Band
2. RSI oversold: `RSI < 35`
3. Volume spike: `volume_ratio > 1.5`
4. Ranging market: `ADX < 30`
5. Safety: `RSI > 10` (not extreme crash)

**Exit:** Price reaches middle band (mean reversion target), RSI > 65, or tiered ROI.

#### VolatilityBreakout — Trend Emergence

Best for: high-volatility transitions and new trend starts.

**Entry conditions:**
1. Breakout: `close > N-period high` (shifted to avoid lookahead)
2. Volume spike: `volume_ratio > 1.8`
3. BB expanding: current width > previous width
4. ADX emerging: `15 <= ADX <= 25` and rising
5. RSI neutral: `40 <= RSI <= 70` (fresh move)

**Exit:** RSI exhaustion >85, price below EMA(20) with volume, or -3% hard stop. This strategy uses the tightest stops because failed breakouts reverse quickly.

### Risk API Integration

Every Freqtrade strategy calls the Django backend before executing a trade:

```python
# In confirm_trade_entry() — called on every entry signal
resp = requests.post(
    "http://127.0.0.1:8000/api/risk/{portfolio_id}/check-trade",
    json={
        "symbol": pair,
        "side": side,
        "size": amount,
        "entry_price": rate,
        "stop_loss_price": stop_loss_price,
    },
    timeout=5,
)
```

**Fail-safe behavior:** If the backend is unreachable, the trade is **rejected**. This ensures no execution occurs without risk manager approval.

**In backtesting/hyperopt mode**, the API call is skipped since the backend may not be running and risk checks are not meaningful for historical simulations.

### CLI

```bash
python run.py freqtrade backtest --strategy CryptoInvestorV1
python run.py freqtrade backtest --strategy CryptoInvestorV1 --timerange 20240101-20250101
python run.py freqtrade dry-run --strategy CryptoInvestorV1
python run.py freqtrade hyperopt --strategy CryptoInvestorV1 --epochs 100
python run.py freqtrade list-strategies
```

---

## Tier 3: NautilusTrader — Multi-Asset Execution

**Purpose:** Institutional-grade event-driven backtesting with precise market microstructure simulation and multi-asset portfolio support.

**Location:** `nautilus/nautilus_runner.py`

**How it works:** NautilusTrader provides a full order state machine, venue-specific models, and granular risk controls. Data is converted from the shared Parquet pipeline into Nautilus bar format.

### Data Conversion

The runner converts shared OHLCV Parquet files into Nautilus-compatible CSV:

```python
convert_ohlcv_to_nautilus_csv(symbol="BTC/USDT", timeframe="1h", exchange="binance")
# Output: nautilus/catalog/BTCUSDT_BINANCE_1h_bars.csv
```

Bar type format: `{SYMBOL}.{VENUE}-{TIMEFRAME}-LAST-EXTERNAL`
Example: `BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL`

### Engine Configuration

```python
engine = BacktestEngine(
    config=BacktestEngineConfig(
        trader_id="CRYPTO_INVESTOR-001",
        logging=LoggingConfig(log_level="INFO"),
    )
)
```

### Performance Metrics

A shared `compute_performance_metrics()` function works with output from any framework:
- Total trades, P&L, win rate, profit factor
- Sharpe ratio, max drawdown
- Average win/loss, best/worst trade, average trade duration

### CLI

```bash
python run.py nautilus test                                  # Test engine initialization
python run.py nautilus convert --symbol BTC/USDT --timeframe 1h  # Convert data
```

---

## Tier 4: hftbacktest — High-Frequency Optimization

**Purpose:** Tick-level strategy development for ultra-high-frequency trading.

**Status:** Framework available, integration in progress.

**Capabilities:**
- Tick-level and order book data processing
- Latency modeling and microstructure simulation
- Market-making and statistical arbitrage strategies

**Integration path:**
1. Convert tick data from CCXT `fetch_trades()` to hftbacktest format
2. Develop and backtest HFT strategy models
3. Validate profitability against Freqtrade strategies
4. Deploy outperformers via NautilusTrader for live execution

---

## Shared Data Pipeline

**Location:** `common/data_pipeline/pipeline.py`

The data pipeline is the foundation that all tiers consume. It handles acquisition, storage, validation, and format conversion.

### Data Flow

```
Exchange API (CCXT)
    │
    ▼
fetch_ohlcv()          ← Paginated fetching, rate-limit handling, retry logic
    │
    ▼
save_ohlcv()           ← Parquet (snappy compression), auto-merge, dedup
    │
    ▼
data/processed/        ← binance_BTC_USDT_1h.parquet
    │
    ├── load_ohlcv()           → pandas DataFrame (any tier)
    ├── to_freqtrade_format()  → Freqtrade-compatible DataFrame
    ├── to_vectorbt_format()   → VectorBT-compatible DataFrame
    └── to_nautilus_bars()     → NautilusTrader bar dicts
```

### Data Quality Validation

Before any trading tier uses data, the pipeline can validate it:

| Check | What It Detects |
|-------|----------------|
| Gap detection | Missing candles between timestamps |
| Staleness monitoring | Data older than configurable threshold (default 2h) |
| NaN audit | Null values in price/volume columns |
| Price spike detection | Single-candle moves >20% (configurable) |
| OHLC constraint check | high < max(open, close) or low > min(open, close) |

```bash
python run.py data download --symbols BTC/USDT,ETH/USDT --timeframes 1h,4h --days 365
python run.py data list
python run.py data info BTC/USDT --timeframe 1h
python run.py data generate-sample    # Synthetic data, no API keys needed
```

### Default Watchlist

Defined in `configs/platform_config.yaml`:

```
BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT,
ADA/USDT, AVAX/USDT, DOGE/USDT, DOT/USDT, LINK/USDT
```

Available timeframes: `1m, 5m, 15m, 1h, 4h, 1d`

---

## Shared Technical Indicators

**Location:** `common/indicators/technical.py`

Pure-pandas indicator implementations shared across all tiers. VectorBT screening, Freqtrade strategies, and the regime detector all use these.

| Category | Indicators |
|----------|-----------|
| Trend | SMA, EMA, WMA, Hull MA, Supertrend |
| Momentum | RSI, MACD, Stochastic, CCI, Williams %R, ADX |
| Volatility | ATR, Bollinger Bands, Keltner Channels |
| Volume | OBV, VWAP, Money Flow Index |
| Price Action | Returns, Log Returns |

Freqtrade strategies also use TA-Lib for indicator computation within the Freqtrade framework, but the shared library ensures consistency for research and regime detection.

---

## Market Regime Detection

**Location:** `common/regime/regime_detector.py`

The regime detector classifies current market conditions using a weighted composite of five sub-indicators, enabling the platform to run the right strategy for the right market.

### Regime Types

| Regime | ADX | Direction | Description |
|--------|-----|-----------|-------------|
| `STRONG_TREND_UP` | >40 | Bullish | Clear uptrend, all EMAs aligned |
| `WEAK_TREND_UP` | 25-40 | Bullish | Mild uptrend, some EMA alignment |
| `RANGING` | <25 | Neutral | Sideways, no directional bias |
| `WEAK_TREND_DOWN` | 25-40 | Bearish | Mild downtrend |
| `STRONG_TREND_DOWN` | >40 | Bearish | Clear downtrend, all EMAs aligned |
| `HIGH_VOLATILITY` | Low | Wide BB | Directionless volatility expansion |
| `UNKNOWN` | — | — | Insufficient data (warmup period) |

### Sub-Indicators

1. **ADX (trend strength):** 0-100 scale, measures directional conviction
2. **BB width percentile:** Rolling percentile rank of Bollinger Band width over 100 periods
3. **EMA slope:** Rate of change of EMA(20) normalized by price
4. **Trend alignment:** Score from -1 (bearish) to +1 (bullish) based on EMA(21/50/100/200) ordering
5. **Price structure:** Score from -1 (lower lows) to +1 (higher highs) based on position within recent range

### Classification

Each regime receives a weighted composite score from the five sub-indicators. The highest scorer wins. Confidence reflects the margin between the top two scores.

**Hysteresis:** The detector requires 3 consecutive bars agreeing on a new regime before switching, preventing whipsaws during transitions.

**Transition probabilities:** Markov-chain probabilities computed from recent regime history, showing the empirical likelihood of transitioning to each regime.

---

## Strategy Router

**Location:** `common/regime/strategy_router.py`

Maps detected regimes to optimal strategy combinations with position-sizing adjustments.

### Routing Table

| Regime | Primary Strategy | Weights | Position Modifier |
|--------|-----------------|---------|-------------------|
| Strong Trend Up | CryptoInvestorV1 | CIV1: 100% | 1.0 (full size) |
| Weak Trend Up | CryptoInvestorV1 | CIV1: 70%, VB: 30% | 0.8 |
| Ranging | BollingerMeanReversion | BMR: 100% | 1.0 (full size) |
| Weak Trend Down | BollingerMeanReversion | BMR: 50%, VB: 50% | 0.5 (half size) |
| Strong Trend Down | BollingerMeanReversion | BMR: 100% | 0.3 (defensive) |
| High Volatility | VolatilityBreakout | VB: 100% | 0.8 |
| High Vol + Bearish | BollingerMeanReversion | BMR: 100% | 0.5 (override) |
| Unknown | BollingerMeanReversion | BMR: 100% | 0.3 (conservative) |

**Low confidence penalty:** If regime detection confidence < 0.4, the position modifier is further halved.

**Strategy switch detection:** The router can flag when the current strategy no longer matches the regime, suggesting a switch to the optimal strategy.

---

## Risk Management

**Location:** `common/risk/risk_manager.py`

A centralized risk layer that wraps all trading tiers. Every trade must pass through this gate.

### Risk Limits

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_portfolio_drawdown` | 15% | Halt all trading if breached |
| `max_single_trade_risk` | 3% | Maximum portfolio risk per trade |
| `max_daily_loss` | 5% | Halt trading for the day |
| `max_open_positions` | 10 | Maximum concurrent positions |
| `max_position_size_pct` | 20% | Maximum portfolio % in one position |
| `max_correlation` | 0.70 | Maximum correlation between positions |
| `min_risk_reward` | 1.5:1 | Minimum risk-to-reward ratio |
| `max_leverage` | 1.0 | No leverage by default |

### Trade Gate Checks

When a new trade is proposed, these checks run in order:

1. **Halt status** — Is trading currently halted?
2. **Open positions** — Are we at the limit?
3. **Duplicate check** — Already in this symbol?
4. **Position size** — Trade value vs portfolio percentage
5. **Stop loss width** — Is the risk per unit acceptable?
6. **Risk/reward ratio** — Does the profit target justify the stop?
7. **Correlation** — Is the new position too correlated with existing ones?

If any check fails, the trade is rejected with a specific reason.

### Position Sizing

```
position_size = (equity * risk_per_trade) / |entry_price - stop_loss_price|
```

Capped at `max_position_size_pct` of portfolio, then multiplied by the regime-based position modifier from the strategy router.

### Portfolio Health Monitoring

The `portfolio_heat_check()` function provides a comprehensive assessment:

- Current drawdown vs limit (with 80% early warning)
- Correlation matrix of open positions
- Position concentration (single-name risk)
- VaR/CVaR at 95% and 99% confidence (parametric or historical)
- Overall `healthy` boolean with list of specific issues

### VaR/CVaR

Two computation methods:

- **Parametric (Gaussian):** Assumes normal distribution, uses portfolio mean/std
- **Historical:** Sorts actual return observations, reads loss percentiles

Both methods require a `ReturnTracker` that accumulates up to 252 days of per-symbol price history.

### Django Backend API

The risk manager is exposed via REST endpoints at `/api/risk/{portfolio_id}/`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status` | GET | Current equity, drawdown, PnL |
| `/limits` | GET/PUT | View or update risk limits |
| `/equity-update` | POST | Feed current equity value |
| `/check-trade` | POST | Gate a proposed trade (approve/reject) |
| `/position-size` | POST | Calculate position size for a trade |
| `/reset-daily` | POST | Reset daily loss tracking |
| `/var` | GET | VaR/CVaR calculation |
| `/heat-check` | GET | Full portfolio health assessment |
| `/halt-trading` | POST | Emergency halt |
| `/resume-trading` | POST | Resume after halt |
| `/alerts` | GET | Recent risk alerts |
| `/trade-log` | GET | Trade check audit trail |

---

## Graduation Path: Research to Live Trading

The platform enforces a progressive validation pipeline before real capital is deployed.

### Phase 1: Rapid Discovery (VectorBT)

**Duration:** Minutes to hours.

```bash
python run.py research screen --symbol BTC/USDT --timeframe 1h
```

- Screen 333+ parameter combinations across 5 strategy types
- Identify top configurations by Sharpe ratio
- No realistic order simulation — speed is the priority
- Output: ranked parameter tables for each strategy type

**Gate to Phase 2:** Top VectorBT parameters become starting points for Freqtrade hyperopt.

### Phase 2: Validated Backtesting (Freqtrade)

**Duration:** Hours to days.

```bash
python run.py freqtrade backtest --strategy CryptoInvestorV1
python run.py freqtrade hyperopt --strategy CryptoInvestorV1 --epochs 100
```

- Event-driven simulation with realistic order fills
- Full fee and slippage modeling
- Hyperopt refines parameters using Sharpe optimization
- Requirement to proceed: Sharpe > 1.0, max drawdown < 15%

**Gate to Phase 3:** Strategy must meet performance thresholds.

### Phase 3: Paper Trading (Freqtrade Dry-Run)

**Duration:** Minimum 14 days (configured in `platform_config.yaml`).

```bash
python run.py freqtrade dry-run --strategy CryptoInvestorV1
```

- Trades real market data with simulated capital ($10,000 default)
- Validates signal generation, order execution, and risk gates against live markets
- Risk API gates every trade attempt
- Monitors: win rate stability, drawdown vs backtest, execution quality

**Gate to Phase 4:** 14+ days paper trading, consistent with backtest results.

### Phase 4: Live Trading (Freqtrade)

**Duration:** Ongoing.

Set `"dry_run": false` in `freqtrade/config.json` and configure real API keys.

- Risk manager gates every trade in real-time
- Drawdown monitoring with automatic halt at 15%
- Daily loss limit with automatic halt at 5%
- All trades logged to Django `Order` model for audit
- Telegram alerts on halts and rejections

### Phase 5: Multi-Asset Expansion (NautilusTrader)

- Extend validated strategies beyond crypto
- Institutional risk framework with venue-specific models
- Statistical arbitrage across correlated assets
- Higher-frequency execution capabilities

### Phase 6: HFT Optimization (hftbacktest)

- Tick-level microstructure analysis
- Order book imbalance exploitation
- Market-making strategy development
- Latency-sensitive execution optimization

---

## Configuration Reference

### Platform Config (`configs/platform_config.yaml`)

```yaml
# Risk limits applied across all tiers
risk_management:
  max_portfolio_drawdown: 0.15
  max_single_trade_risk: 0.02
  max_daily_loss: 0.05
  max_correlation: 0.7
  min_paper_trade_days: 14

# VectorBT research defaults
vectorbt:
  default_fees: 0.001        # 0.1%
  default_slippage: 0.0005   # 0.05%
  num_tests: 1000

# Freqtrade execution defaults
freqtrade:
  dry_run: true
  max_open_trades: 5
  stake_currency: USDT

# NautilusTrader engine limits
nautilus:
  risk_engine:
    max_order_submit_rate: "10/00:00:01"
    max_notional_per_order: 10000.0

# Data pipeline
data:
  storage_format: parquet
  history_days: 365
  timeframes: [1m, 5m, 15m, 1h, 4h, 1d]
```

### Freqtrade Config (`freqtrade/config.json`)

```json
{
  "dry_run": true,
  "dry_run_wallet": 10000,
  "max_open_trades": 5,
  "stake_currency": "USDT",
  "trading_mode": "spot",
  "exchange": {
    "name": "binanceus",
    "pair_whitelist": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
  }
}
```

---

## Key Design Decisions

### Why four tiers instead of one?

Each tier serves a distinct purpose in the validation pipeline:

- **VectorBT** can test 1000 parameter combinations in seconds, but its simplified portfolio simulation doesn't model slippage, partial fills, or order book dynamics. It finds candidates, not winners.
- **Freqtrade** provides realistic event-driven simulation that catches issues VectorBT misses (order timing, fee drag, concurrent position interactions), plus a production-ready live trading engine.
- **NautilusTrader** adds institutional-grade features (multi-asset, venue-specific fills, precise risk controls) for scaling beyond crypto or deploying more sophisticated strategies.
- **hftbacktest** enables tick-level alpha discovery that candlestick-based systems cannot capture.

### Why a centralized risk manager?

A single risk layer prevents tier-specific bugs from causing outsized losses. The trade gate pattern (approve/reject before every execution) ensures consistent enforcement regardless of which strategy or framework initiates the trade.

### Why Parquet for data storage?

- Columnar format is efficient for time-series queries (read only the columns needed)
- Snappy compression keeps file sizes manageable on the Jetson's storage
- Native pandas/PyArrow support across all Python frameworks
- Merge-on-save deduplicates overlapping downloads automatically

### Why regime-based strategy routing?

Running a trend-following strategy in a ranging market (or vice versa) guarantees losses. The regime detector + strategy router ensures:
- The right strategy runs in the right conditions
- Position sizes scale down during uncertain regimes
- Strategy switches happen smoothly with hysteresis (no whipsawing)
