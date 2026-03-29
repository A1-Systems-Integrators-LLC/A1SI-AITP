# Risk Management System

This document describes the risk management system used by the A1SI-AITP platform. The system operates as a centralized gate that every trade must pass through before execution, backed by persistent state in the Django database, real-time monitoring, and multi-channel alert delivery.

---

## System Architecture

```
┌────────────────────────────────┐
│     Trading Strategies          │
│  CryptoInvestorV1               │
│  BollingerMeanReversion         │
│  VolatilityBreakout             │
└──────────┬─────────────────────┘
           │ POST /api/risk/{id}/check-trade
           ▼
┌────────────────────────────────┐
│     Django REST API             │
│  backend/risk/views.py          │
│  16 endpoints per portfolio     │
└──────────┬─────────────────────┘
           │
           ▼
┌────────────────────────────────┐
│     RiskManagementService       │
│  backend/risk/services/risk.py  │
│  Bridges Django ORM ↔ engine    │
└──────────┬─────────────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐ ┌──────────────────┐
│  Django  │ │  Risk Engine     │
│  ORM     │ │  common/risk/    │
│          │ │  risk_manager.py │
│ RiskState│ │                  │
│ RiskLimits│ │  Position sizing │
│ TradeLog │ │  Drawdown checks │
│ AlertLog │ │  Correlation     │
│ Metrics  │ │  VaR/CVaR        │
└──────────┘ └──────────────────┘
                    │
                    ▼
           ┌───────────────┐
           │  Notifications │
           │  Telegram      │
           │  Webhook       │
           │  Log           │
           └───────────────┘
```

The system has three layers:

1. **Risk engine** (`common/risk/risk_manager.py`) — pure Python, no Django dependency. Contains the math: position sizing, drawdown monitoring, correlation checks, VaR/CVaR computation. Usable standalone by any framework tier.

2. **Service layer** (`backend/risk/services/risk.py`) — bridges the risk engine with Django ORM persistence. Reconstructs a `RiskManager` instance from database state on each request, runs the check, persists results, and sends notifications.

3. **REST API** (`backend/risk/views.py`) — exposes the service layer as authenticated HTTP endpoints. Called by Freqtrade strategies during live/dry-run trading.

---

## Risk Limits

Each portfolio has configurable risk limits stored in the `RiskLimits` database model. Defaults are designed for conservative crypto trading.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_portfolio_drawdown` | 0.20 (20%) | Maximum peak-to-trough decline before halting all trading |
| `max_single_trade_risk` | 0.05 (5%) | Maximum portfolio risk per individual trade |
| `max_daily_loss` | 0.08 (8%) | Maximum daily loss before halting for the day |
| `max_open_positions` | 10 | Maximum number of concurrent open positions |
| `max_position_size_pct` | 0.20 (20%) | Maximum portfolio percentage in a single position |
| `max_correlation` | 0.70 | Maximum allowed correlation between any two open positions |
| `min_risk_reward` | 1.5 | Minimum risk-to-reward ratio (reject trades with wide stops requiring >15% profit) |
| `max_leverage` | 1.0 | No leverage by default (spot only) |

Limits can be viewed and updated via the API:

```
GET  /api/risk/{portfolio_id}/limits/
PUT  /api/risk/{portfolio_id}/limits/
```

The PUT endpoint accepts partial updates — only include the fields you want to change.

---

## Trade Gate

The trade gate is the core safety mechanism. Every trade proposed by a Freqtrade strategy must pass through this check before execution.

### How It Works

Freqtrade strategies call the gate in their `confirm_trade_entry()` method:

```python
resp = requests.post(
    "http://127.0.0.1:8000/api/risk/1/check-trade/",
    json={
        "symbol": "BTC/USDT",
        "side": "buy",
        "size": 0.05,
        "entry_price": 42000.0,
        "stop_loss_price": 39900.0,
    },
    timeout=5,
)
# Response: {"approved": true, "reason": "approved"}
# or:       {"approved": false, "reason": "Max open positions reached (10)"}
```

**Fail-safe:** If the backend is unreachable (network error, timeout, non-200 status), the trade is **rejected**. No execution occurs without explicit risk manager approval.

**Backtesting exception:** During Freqtrade backtest and hyperopt modes, the API call is skipped since the backend may not be running and risk checks are not meaningful for historical simulations.

### Check Sequence

When a trade request arrives, these checks run in order. The first failure stops evaluation and returns the rejection reason.

```
1. Halt status check
   └─ Is trading currently halted?
      "Trading halted: Max drawdown breached: 20.20% >= 20.00%"

2. Open positions limit
   └─ Are we at max_open_positions?
      "Max open positions reached (10)"

3. Duplicate position check
   └─ Already have an open position in this symbol?
      "Already have open position in BTC/USDT"

4. Position size check
   └─ Is trade_value / total_equity > max_position_size_pct?
      "Position too large: 22.50% > 20.00%"

5. Stop loss width check
   └─ Is the per-unit risk > 2x max_single_trade_risk?
      "Stop loss too wide: 8.00% risk per unit"

6. Risk/reward ratio check
   └─ Does the stop width require an unrealistic profit target (>15%)?
      "Risk/reward unfavorable: stop at 6.0% requires 9.0% profit for 1.5:1 R:R"

7. Correlation check
   └─ Is the new symbol too correlated with any existing position?
      "Correlation too high: BTC/USDT vs ETH/USDT = 0.82 > 0.70"

All checks passed → "approved"
```

### Audit Trail

Every trade check — approved or rejected — is logged to the `TradeCheckLog` model with full context:

| Field | Description |
|-------|-------------|
| `symbol` | Trading pair (e.g., BTC/USDT) |
| `side` | buy or sell |
| `size` | Requested position size |
| `entry_price` | Proposed entry price |
| `stop_loss_price` | Proposed stop loss price |
| `approved` | True/False |
| `reason` | Approval or specific rejection reason |
| `equity_at_check` | Portfolio equity at the time of check |
| `drawdown_at_check` | Current drawdown at the time of check |
| `open_positions_at_check` | Number of open positions at the time |
| `checked_at` | Timestamp |

Query the audit trail:

```
GET /api/risk/{portfolio_id}/trade-log/?limit=50
```

---

## Position Sizing

Position size is calculated using the risk-per-trade formula:

```
position_size = (equity * risk_per_trade) / |entry_price - stop_loss_price|
```

**Constraints applied in order:**

1. Cap at `max_position_size_pct` — position value cannot exceed this percentage of total equity
2. Apply regime modifier (0-1) — from the strategy router, reduces size in uncertain market regimes

### Example

```
Equity:          $10,000
Risk per trade:  3% ($300)
Entry price:     $42,000
Stop loss:       $40,000
Price risk:      $2,000

Raw size:        $300 / $2,000 = 0.15 BTC
Position value:  0.15 * $42,000 = $6,300 (63% of equity)
Max allowed:     20% of $10,000 = $2,000 → 0.0476 BTC
Final size:      0.0476 BTC (capped)

With regime modifier of 0.8 (weak uptrend):
Final size:      0.0476 * 0.8 = 0.0381 BTC
```

### API

```
POST /api/risk/{portfolio_id}/position-size/
{
    "entry_price": 42000.0,
    "stop_loss_price": 40000.0,
    "risk_per_trade": 0.03       // optional, defaults to max_single_trade_risk
}

Response:
{
    "size": 0.047619,
    "risk_amount": 300.00,
    "position_value": 2000.0
}
```

---

## Drawdown Monitoring

The risk manager continuously tracks portfolio equity against its peak to detect drawdowns.

### How It Works

```python
drawdown = 1.0 - (current_equity / peak_equity)
```

Every equity update triggers two checks:

1. **Portfolio drawdown** — if `drawdown >= max_portfolio_drawdown` (default 20%), trading is **halted** immediately. The halt persists until manually resumed.

2. **Daily loss** — if `(current_equity - daily_start_equity) / daily_start_equity <= -max_daily_loss` (default 8%), trading is **halted** for the day. Daily halts clear automatically on the next daily reset.

### Equity Updates

Feed current equity to the risk manager:

```
POST /api/risk/{portfolio_id}/equity/
{"equity": 9500.0}
```

The response includes the full status, including whether the update triggered a halt.

### Daily Reset

Reset daily tracking counters (call at the start of each trading day):

```
POST /api/risk/{portfolio_id}/reset-daily/
```

This resets `daily_start_equity` to the current equity, clears `daily_pnl`, and lifts any daily halt (but not drawdown halts).

---

## Trading Halt & Resume

Trading can be halted automatically (drawdown/daily loss breach) or manually (emergency).

### Automatic Halts

| Trigger | Threshold | Halt Behavior |
|---------|-----------|---------------|
| Portfolio drawdown | >= 20% | Permanent until manual resume |
| Daily loss | >= 8% | Clears on next daily reset |

When a halt triggers:
- All subsequent `check-trade` calls are rejected with the halt reason
- A critical-severity notification is sent via Telegram and logged
- The halt reason is persisted in the database

### Manual Halt

Emergency stop — immediately reject all new trades:

```
POST /api/risk/{portfolio_id}/halt/
{"reason": "Market crash — manual intervention"}
```

A critical notification is sent via all configured channels.

### Resume

Lift a halt (manual or automatic):

```
POST /api/risk/{portfolio_id}/resume/
```

An info notification is sent confirming trading has resumed.

---

## Correlation Checking

Before approving a new position, the risk manager checks whether it is too correlated with existing open positions. This prevents over-concentration in correlated assets (e.g., holding both BTC and ETH during a market-wide move).

### How It Works

1. The `ReturnTracker` accumulates up to 252 days of per-symbol price history
2. When a new trade is proposed, the tracker computes a correlation matrix across all open symbols plus the proposed symbol
3. If the absolute correlation between the proposed symbol and any existing position exceeds `max_correlation` (default 0.70), the trade is rejected

### Requirements

- Correlation checking requires at least 20 return observations per symbol for statistical relevance
- If insufficient data exists, the trade is **allowed** with a warning logged (not enough history to make a determination)

### Example Rejection

```json
{
    "approved": false,
    "reason": "Correlation too high: SOL/USDT vs ETH/USDT = 0.82 > 0.70"
}
```

---

## Value at Risk (VaR) and Conditional VaR (CVaR)

The system computes portfolio-level VaR and CVaR at 95% and 99% confidence levels.

### What They Measure

- **VaR (95%):** The maximum loss you can expect with 95% confidence over one period. "There is a 5% chance of losing more than this amount."
- **CVaR (95%):** The expected loss given that the loss exceeds the 95% VaR. "If we're in the worst 5% of scenarios, the average loss is this amount." Also called Expected Shortfall.

### Computation Methods

**Parametric (Gaussian):**

```
VaR = -(μ + z * σ) * portfolio_value
CVaR = -(μ - σ * φ(z)/α) * portfolio_value

where:
  μ = mean portfolio return
  σ = portfolio return std deviation
  z = normal quantile (z_95 = -1.645, z_99 = -2.326)
  φ = standard normal PDF
  α = confidence tail (0.05 or 0.01)
```

**Historical:**

```
1. Sort actual portfolio returns ascending
2. VaR_95 = -returns[5th percentile] * portfolio_value
3. CVaR_95 = -mean(returns below 5th percentile) * portfolio_value
```

### Portfolio Returns

Portfolio returns are computed as a weighted sum of individual symbol returns:

```
portfolio_return = Σ (symbol_weight * symbol_return)

where symbol_weight = position_value / total_equity
```

### API

```
GET /api/risk/{portfolio_id}/var/?method=parametric

Response:
{
    "var_95": 485.23,
    "var_99": 712.50,
    "cvar_95": 612.40,
    "cvar_99": 890.15,
    "method": "parametric",
    "window_days": 90
}
```

---

## Portfolio Heat Check

The heat check is a comprehensive health assessment that aggregates all risk metrics into a single report. Call it before every trade decision for a full picture.

### What It Reports

| Metric | Description |
|--------|-------------|
| `healthy` | Boolean — true if no issues detected |
| `issues` | List of specific issue strings |
| `drawdown` | Current drawdown as decimal |
| `daily_pnl` | Day's profit/loss |
| `open_positions` | Count of open positions |
| `max_correlation` | Highest pairwise correlation among open positions |
| `high_corr_pairs` | List of pairs exceeding `max_correlation` |
| `max_concentration` | Largest single-position weight |
| `position_weights` | Map of symbol to portfolio weight |
| `var_95`, `var_99` | Value at Risk |
| `cvar_95`, `cvar_99` | Conditional VaR |
| `is_halted` | Whether trading is halted |

### Early Warnings

The heat check flags issues before they trigger halts:

| Warning | Condition |
|---------|-----------|
| Drawdown approaching limit | Drawdown > 80% of `max_portfolio_drawdown` (e.g., >16% when limit is 20%) |
| High correlation | Any pair exceeds `max_correlation` |
| Concentration warning | Single position > 90% of `max_position_size_pct` (e.g., >18% when limit is 20%) |
| VaR warning | 99% VaR exceeds 10% of total equity |
| Halt active | Trading is currently halted |

### API

```
GET /api/risk/{portfolio_id}/heat-check/

Response:
{
    "healthy": false,
    "issues": [
        "Drawdown warning: 16.50% approaching limit 20.00%",
        "Concentration warning: 18.50% in single position"
    ],
    "drawdown": 0.125,
    "daily_pnl": -450.0,
    "open_positions": 4,
    "max_correlation": 0.65,
    "high_corr_pairs": [],
    "max_concentration": 0.185,
    "position_weights": {
        "BTC/USDT": 0.185,
        "ETH/USDT": 0.12,
        "SOL/USDT": 0.08,
        "LINK/USDT": 0.05
    },
    "var_95": 485.23,
    "var_99": 712.50,
    "cvar_95": 612.40,
    "cvar_99": 890.15,
    "is_halted": false
}
```

---

## Metric History

Risk metrics can be periodically recorded to build a time series for monitoring and dashboards.

### Recording Metrics

Trigger a snapshot (typically called on a schedule or after equity updates):

```
POST /api/risk/{portfolio_id}/record-metrics/?method=parametric
```

This persists the current VaR, CVaR, drawdown, equity, and position count to the `RiskMetricHistory` table.

### Querying History

```
GET /api/risk/{portfolio_id}/metric-history/?hours=168

Response:
[
    {
        "id": 42,
        "portfolio_id": 1,
        "var_95": 485.23,
        "var_99": 712.50,
        "cvar_95": 612.40,
        "cvar_99": 890.15,
        "method": "parametric",
        "drawdown": 0.125,
        "equity": 8750.0,
        "open_positions_count": 4,
        "recorded_at": "2026-02-18T14:30:00Z"
    },
    ...
]
```

Default lookback is 168 hours (7 days). Ordered by most recent first.

---

## Notifications

The risk system sends alerts through multiple channels when significant events occur.

### Channels

| Channel | Configuration | Description |
|---------|--------------|-------------|
| Log | Always active | Persisted to `AlertLog` database table |
| Telegram | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env` | Bot API messages with HTML formatting |
| Webhook | `NOTIFICATION_WEBHOOK_URL` in `.env` | Generic POST to Slack, Discord, or custom endpoint |

### Events That Trigger Notifications

| Event | Severity | When |
|-------|----------|------|
| `trade_rejected` | warning | A trade fails the risk gate |
| `halt` | critical | Trading is halted (automatic or manual) |
| `resume` | info | Trading is resumed |
| `daily_reset` | info | Daily risk counters are reset |

### Alert Log

Every notification is recorded in the `AlertLog` model with delivery status:

| Field | Description |
|-------|-------------|
| `event_type` | halt, resume, trade_rejected, daily_reset |
| `severity` | info, warning, critical |
| `message` | Human-readable alert text |
| `channel` | log, telegram, webhook |
| `delivered` | Whether delivery succeeded |
| `error` | Error message if delivery failed |
| `created_at` | Timestamp |

Query recent alerts:

```
GET /api/risk/{portfolio_id}/alerts/?limit=50
```

### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your chat ID via [@userinfobot](https://t.me/userinfobot)
3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   TELEGRAM_CHAT_ID=987654321
   ```

Alerts arrive as HTML-formatted messages:

```
[CRITICAL] Trading HALTED: Max drawdown breached: 20.20% >= 20.00%
[WARNING] Trade REJECTED: BTC/USDT buy x0.05 @ 42000.0 — Max open positions reached (10)
```

---

## Database Models

The risk system uses six Django models in the `risk` app.

### RiskState

Tracks the current portfolio state. One row per portfolio.

| Field | Type | Description |
|-------|------|-------------|
| `portfolio_id` | int (unique) | Portfolio identifier |
| `total_equity` | float | Current portfolio value |
| `peak_equity` | float | Highest equity ever recorded |
| `daily_start_equity` | float | Equity at start of current trading day |
| `daily_pnl` | float | Profit/loss since daily reset |
| `total_pnl` | float | Lifetime profit/loss |
| `open_positions` | JSON | Dict of symbol to position details |
| `is_halted` | bool | Whether trading is halted |
| `halt_reason` | string | Reason for halt |
| `updated_at` | datetime | Last update timestamp |

### RiskLimits

Configurable risk parameters. One row per portfolio.

| Field | Type | Default |
|-------|------|---------|
| `max_portfolio_drawdown` | float | 0.20 |
| `max_single_trade_risk` | float | 0.05 |
| `max_daily_loss` | float | 0.08 |
| `max_open_positions` | int | 10 |
| `max_position_size_pct` | float | 0.20 |
| `max_correlation` | float | 0.70 |
| `min_risk_reward` | float | 1.5 |
| `max_leverage` | float | 1.0 |

### TradeCheckLog

Audit trail of every trade gate decision.

### RiskMetricHistory

Time series of risk metric snapshots (VaR, CVaR, drawdown, equity).

### AlertLog

Record of all notifications sent across all channels.

### RiskLimitChange

Audit trail of every change to risk limit parameters. Created automatically when limits are updated via the API.

| Field | Type | Description |
|-------|------|-------------|
| `portfolio_id` | int | Portfolio identifier |
| `field_name` | string (max 50) | Name of the limit field that changed |
| `old_value` | string (max 50) | Previous value (stored as string) |
| `new_value` | string (max 50) | New value (stored as string) |
| `changed_by` | string (max 150) | User who made the change |
| `reason` | string (max 500) | Optional reason for the change |
| `changed_at` | datetime | Timestamp of the change |

---

## REST API Reference

All endpoints require authentication (Django session). Base path: `/api/risk/{portfolio_id}/`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status/` | GET | Current equity, drawdown, PnL, halt status |
| `/limits/` | GET | Current risk limit configuration |
| `/limits/` | PUT | Update risk limits (partial update) |
| `/equity/` | POST | Feed current equity value, triggers drawdown check |
| `/check-trade/` | POST | Gate a proposed trade — returns approved/rejected |
| `/position-size/` | POST | Calculate position size for given entry/stop |
| `/reset-daily/` | POST | Reset daily loss tracking and clear daily halts |
| `/var/` | GET | Compute VaR/CVaR (?method=parametric\|historical) |
| `/heat-check/` | GET | Full portfolio health assessment |
| `/record-metrics/` | POST | Snapshot current metrics to history table |
| `/metric-history/` | GET | Query metric time series (?hours=168) |
| `/halt/` | POST | Manually halt trading |
| `/resume/` | POST | Resume trading after halt |
| `/alerts/` | GET | Recent risk alerts (?limit=50) |
| `/trade-log/` | GET | Trade check audit trail (?limit=50) |

---

## Integration with Trading Strategies

### Freqtrade Integration

Every Freqtrade strategy inherits a `confirm_trade_entry()` method that calls the risk API. The pattern is identical across all three production strategies:

```python
class CryptoInvestorV1(IStrategy):
    risk_api_url = "http://127.0.0.1:8000"
    risk_portfolio_id = 1

    def confirm_trade_entry(self, pair, order_type, amount, rate, ...):
        # Skip in backtest/hyperopt mode
        if self.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT):
            return True

        try:
            stop_loss_price = rate * (1 + self.stoploss)
            resp = requests.post(
                f"{self.risk_api_url}/api/risk/{self.risk_portfolio_id}/check-trade/",
                json={...},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("approved", False):
                    return False  # Trade rejected
                return True
            return False  # Non-200 → reject
        except Exception:
            return False  # Unreachable → reject
```

### Regime-Aware Position Sizing

The strategy router provides a `position_size_modifier` based on the detected market regime. This modifier is passed to `RiskManager.calculate_position_size()` as the `regime_modifier` parameter:

| Regime | Primary Strategy | Position Modifier |
|--------|-----------------|-------------------|
| Strong Trend Up | CryptoInvestorV1 | 1.0 (full) |
| Weak Trend Up | CryptoInvestorV1 | 0.8 |
| Ranging | BollingerMeanReversion | 1.0 (full) |
| Weak Trend Down | BollingerMeanReversion | 0.5 (half) |
| Strong Trend Down | BollingerMeanReversion | 0.3 (defensive) |
| High Volatility | VolatilityBreakout | 0.8 |
| Unknown | BollingerMeanReversion | 0.3 (conservative) |

If regime detection confidence is below 0.4, the modifier is further halved.

---

## Configuration

### Platform Config (`configs/platform_config.yaml`)

```yaml
risk_management:
  max_portfolio_drawdown: 0.20
  max_single_trade_risk: 0.05
  max_daily_loss: 0.08
  max_correlation: 0.7
  min_paper_trade_days: 14
```

### Freqtrade Config (`freqtrade/config.json.example`)

```json
{
  "stoploss": -0.05,
  "trailing_stop": true,
  "trailing_stop_positive": 0.01,
  "trailing_stop_positive_offset": 0.03,
  "max_open_trades": 5
}
```

### Environment Variables (`.env`)

```bash
# Telegram notifications
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# Generic webhook (Slack, Discord, etc.)
NOTIFICATION_WEBHOOK_URL=https://hooks.slack.com/services/...
```

---

## Key Files

| File | Purpose |
|------|---------|
| `common/risk/risk_manager.py` | Core risk engine — position sizing, drawdown, correlation, VaR |
| `backend/risk/models.py` | Django models — RiskState, RiskLimits, TradeCheckLog, AlertLog, RiskMetricHistory, RiskLimitChange |
| `backend/risk/views.py` | REST API views — 16 endpoints |
| `backend/risk/services/risk.py` | Service layer — bridges engine with Django ORM |
| `backend/risk/serializers.py` | DRF serializers for request/response validation |
| `backend/risk/urls.py` | URL routing |
| `backend/core/services/notification.py` | Telegram and webhook delivery |
| `common/regime/regime_detector.py` | Market regime classification |
| `common/regime/strategy_router.py` | Regime-to-strategy mapping with position modifiers |
| `configs/platform_config.yaml` | Global risk limit defaults |
