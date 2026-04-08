# Director Nakamura — Finance Lead Plan

## Role
Portfolio oversight, strategy approval gates, performance accountability, go-live decisions.

## Current State (2026-04-08)
- 7 strategies in dry-run on Kraken spot. Zero live capital deployed.
- ML models trained (10 LightGBM). Conviction pipeline disabled (learning phase).
- No strategies have passed Gate 2+ yet. No backtest validation reports exist.

## Daily Checklist
1. Review daily PDF report (backend/data/reports/daily_report_YYYY-MM-DD.pdf)
2. Check aggregate P&L across all 7 dry-run strategies
3. Flag any strategy with drawdown > 10% or zero trades in 24h
4. Track days-in-paper-trade for each strategy toward 14-day Gate 5 minimum
5. Review risk limits: portfolio drawdown < 15%, daily loss < 5%

## Active Plan (aligned to Performance Plan Week 2-4)
| Task | Target Date | Status |
|------|------------|--------|
| Collect 7-day dry-run results for all strategies | 2026-04-13 | IN PROGRESS |
| Review conviction pipeline logging-mode results | 2026-04-17 | NOT STARTED |
| Commission Gate 2 backtest reports from Quentin | 2026-04-20 | NOT STARTED |
| Set go-live criteria and publish to team | 2026-04-24 | NOT STARTED |
| Final risk review (Gate 4) for qualifying strategies | 2026-04-27 | NOT STARTED |
| Approve live deployment for strategies meeting Sharpe > 1.0, DD < 15% | 2026-04-28 | NOT STARTED |

## Success Metrics
- At least 3 strategies pass Gate 4 by end of Week 3
- Portfolio Sharpe > 1.0 in paper trading before live capital
- Zero unauthorized live trades

## Lessons Learned
- 4 months of building with zero trading results. Never let infrastructure work delay activation again.
- The 5 strategy bugs (2026-04-06) went undetected because nobody was reviewing trade logs. Daily review is mandatory.
