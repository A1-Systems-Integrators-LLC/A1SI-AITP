---
name: Strategy Fixes 2026-04-06
description: Five root causes fixed after 3+ months of zero profitable trades
type: project
---

## Root causes identified and fixed (2026-04-06):

1. **CryptoInvestorV1 contradictory logic:** Required price above EMA (uptrend) AND RSI < 38 (oversold) simultaneously — nearly impossible on 1h candles. Fixed: it's now a "dip-buyer" that requires EMA fast > EMA slow (uptrend structure) but NOT price > EMA (the pullback IS the entry).

2. **BMR volume gate disabled:** `buy_volume_factor=0.0` meant every BB touch generated an entry — pure noise. Fixed: re-enabled at 1.2x (validates institutional selling pressure).

3. **Conviction pipeline silently killing trades:** Despite "fail-open" design, `check_conviction()` made HTTP calls that could return `approved: false`. No logging of approval/rejection rates. Fixed: disabled entirely for learning phase.

4. **All strategies on same 1h timeframe:** 7 of 8 strategies competed on 1h. Fixed: VB moved to 4h for timeframe diversity (BMR=1h, CIV1=1h, VB=4h, Scalper=15m).

5. **Parameter relaxation death spiral:** Tight hyperopt params → zero trades → relax → still no trades → relax more. Fixed: reset to sensible defaults (BB std 2.0, RSI 40, ADX ceiling 35, volume 1.2x).

**Why:** These were structural bugs, not parameter issues. No amount of hyperopt tuning would have fixed contradictory entry logic or a disabled volume gate.
