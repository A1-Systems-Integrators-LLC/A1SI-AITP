---
name: Performance Improvement Plan
description: 4-week plan to activate disabled ML, strategies, alternative data, and multi-asset trading — approved 2026-04-07
type: project
---

## Problem (2026-04-07)
After 4 months of development, the platform had enterprise-grade infrastructure but almost none active. Zero trained ML models, only 3 of 8 strategies running on sandbox, no equity/forex trading, alternative data collected but unused.

## Week 1 — COMPLETED (2026-04-07)
1. **ML models trained** — 10 LightGBM models (BTC, ETH, SOL, XRP, DOGE, BNB, ADA, AVAX, DOT, LINK). Best: AVAX 66.3%, BTC 61.3%. Daily retraining enabled.
2. **7 strategies deployed** — Added MomentumScalper15m, GridDCA, SentimentEventTrader, TrendReversal. MomentumShort excluded (short-only, needs futures exchange). All healthy on Kraken spot dry-run.
3. **Alternative data confirmed wired** — SignalAggregator already integrates Fear&Greed, Reddit, BTC dominance, CoinGecko trending, funding rates, FRED macro, news sentiment. Now functional with ML models feeding scores.

## Week 2 (2026-04-14 to 2026-04-20)
4. Re-enable conviction pipeline in **logging mode** (score trades, don't block)
5. Activate equity + forex **paper trading** via GenericPaperTradingService
6. Connect VectorBT screening output to dynamic pair selection

## Week 3 (2026-04-21 to 2026-04-27)
7. Run backtest validation (Gate 2 + Gate 3) on all 7 active strategies, publish results
8. Set concrete go-live criteria and timeline

## Week 4 (2026-04-28+)
9. Go live with real capital on strategies meeting criteria (Sharpe > 1.0, drawdown < 15% over 30 days)

**Why:** User directive — stop perpetual infrastructure building, activate what exists, generate actual trading performance.

**How to apply:** Every task should be about ENABLING existing code, not writing new modules. If a choice is between building something new vs. turning on something existing, always turn on existing.
