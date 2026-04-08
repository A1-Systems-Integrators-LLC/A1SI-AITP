# Quentin — Quant Dev Plan

## Role
Backtest validation, signal research, screening pipeline, statistical analysis of strategy performance.

## Current State (2026-04-08)
- 7 strategies deployed but NO Gate 2/3 backtest reports exist yet
- VectorBT screener exists (research/scripts/vbt_screener.py) but not connected to dynamic pair selection
- VBT screen tasks scheduled every 4h but results not feeding into Freqtrade pair lists
- NautilusTrader backtests scheduled daily but no published results

## Daily Checklist
1. Check VBT screen results: ScreenResult model in DB — any new high-Sharpe signals?
2. Check NautilusTrader backtest results: BacktestResult model (framework=nautilus)
3. Review strategy signal quality — are strategies generating entries on strong signals or noise?
4. Track per-strategy metrics: trades/day, win rate, avg profit, Sharpe estimate

## Active Plan
| Task | Target Date | Status |
|------|------------|--------|
| Run Gate 2 VBT screens on all 7 active strategies | 2026-04-14 | NOT STARTED |
| Produce Gate 3 backtest reports (walk-forward, robustness) for top strategies | 2026-04-20 | NOT STARTED |
| Connect VBT screening output to Freqtrade dynamic pair selection | 2026-04-18 | NOT STARTED |
| Analyze first 7 days of dry-run trade data for statistical significance | 2026-04-14 | NOT STARTED |
| Build strategy correlation matrix — ensure portfolio diversification | 2026-04-16 | NOT STARTED |

## Key Files
- VBT screener: research/scripts/vbt_screener.py
- Freqtrade strategies: freqtrade/user_data/strategies/
- Backtest results: analysis.models.BacktestResult
- Screen results: analysis.models.ScreenResult
- NautilusTrader runner: nautilus/nautilus_runner.py

## Success Criteria for Gate 2
- Sharpe > 1.0, max DD < 20%, > 30 trades, statistically significant (p < 0.05)
- Parameter sensitivity: performance robust to +/- 20% perturbation

## Lessons Learned
- Tight hyperopt params led to zero trades. Use sensible defaults first, optimize later.
- CIV1 had contradictory entry logic for 3+ months. Always verify entry conditions are logically possible.
