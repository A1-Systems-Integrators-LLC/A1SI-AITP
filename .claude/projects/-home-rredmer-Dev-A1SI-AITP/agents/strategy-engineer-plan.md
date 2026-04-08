# Mira — Strategy Engineer Plan

## Role
Live trading operations, execution monitoring, strategy health, conviction pipeline management.

## Current State (2026-04-08)
- 7 Freqtrade strategies running in prod (dry-run, Kraken spot)
- BMR (1h), CIV1 (1h), VB (4h), Scalp (15m), Grid, Sentiment, Reversal
- MomentumShort DISABLED (needs futures exchange)
- Conviction gates disabled for learning phase — strategies trade on raw signals only
- GenericPaperTradingService exists but equity/forex paper trading NOT active

## Daily Checklist
1. Verify all 7 strategy containers healthy: `docker ps --filter name=aitp-prod-ft`
2. Check each strategy's trade count and open positions via Freqtrade API (:4180-4189)
3. Identify strategies with zero trades in 24h — investigate signal generation
4. Monitor fill quality: slippage, rejected orders, partial fills
5. Check kill switch readiness: `GET /api/health/?detailed=true` → risk limits

## Active Plan
| Task | Target Date | Status |
|------|------------|--------|
| Collect baseline trade metrics for all 7 strategies (first 7 days) | 2026-04-13 | IN PROGRESS |
| Re-enable conviction pipeline in LOGGING mode (score, don't block) | 2026-04-15 | NOT STARTED |
| Activate equity paper trading via GenericPaperTradingService | 2026-04-17 | NOT STARTED |
| Activate forex paper trading via GenericPaperTradingService | 2026-04-17 | NOT STARTED |
| Build trade-vs-backtest comparison for each strategy | 2026-04-20 | NOT STARTED |
| Prepare Gate 5 paper trading reports for Nakamura | 2026-04-24 | NOT STARTED |

## Key Files
- Strategies: freqtrade/user_data/strategies/
- Conviction: backend/trading/services/conviction.py
- Paper trading: backend/trading/services/paper_trading.py
- Kill switch: common/risk/risk_manager.py

## Lessons Learned
- Conviction pipeline was silently blocking all trades for months. When re-enabling, use LOGGING mode first.
- All strategies on 1h timeframe caused signal collision. Maintain timeframe diversity.
