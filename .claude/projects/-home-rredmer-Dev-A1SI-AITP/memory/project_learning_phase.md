---
name: Learning Phase — ML Activated
description: Trading system exited pure learning phase 2026-04-07 — ML models trained, 7 strategies live, alt data flowing
type: project
---

## Status as of 2026-04-07

**ML Pipeline**: ACTIVE — 10 LightGBM models trained (BTC, ETH, SOL, XRP, DOGE, BNB, ADA, AVAX, DOT, LINK)
- Best: AVAX 66.3% accuracy, BTC 61.3%
- Daily retraining scheduled (was weekly)
- ML predictions feed into SignalAggregator compute()

**Strategies Running** (7 of 8):
- BMR (1h mean-reversion), CIV1 (1h dip-buy), VB (4h breakout)
- MomentumScalper15m, GridDCA, SentimentEventTrader, TrendReversal
- All on Kraken spot mode, dry_run=true
- MomentumShort DISABLED (short-only, needs futures exchange)

**Conviction Gates**: Still disabled for Freqtrade strategies (learning phase).
The SignalAggregator IS computing composite scores for the API — it just doesn't gate Freqtrade entries yet.

**Alternative Data**: All connected and flowing through SignalAggregator:
- Fear & Greed index, Reddit sentiment, BTC dominance, CoinGecko trending
- Funding rates, FRED macro data (VIX, yield curve, fed funds, DXY)
- News sentiment (RSS + optional NewsAPI)
- All feed as modifiers into composite score computation

**Why:** User directive 2026-04-07 to stop building and start trading. All existing infrastructure activated.

**How to apply:** Focus on PERFORMANCE now, not features. Monitor trade outcomes, retrain models, tune strategy parameters based on results.
