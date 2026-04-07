---
name: Strategy Deployment Order
description: Staged strategy rollout — one new strategy per day for learning phase observation
type: project
---

Staged deployment using Docker Compose profiles (since 2026-04-06):

- **Day 1 (2026-04-06):** BMR only (1h mean-reversion) — `docker compose --profile trading-day1 up -d`
- **Day 2:** + CIV1 (1h dip-buyer) — add `--profile trading-day2`, set `FREQTRADE_CIV1_ENABLED=true`
- **Day 3:** + VB (4h breakout) — add `--profile trading-day3`, set `FREQTRADE_VB_ENABLED=true`
- **All at once:** `docker compose --profile trading up -d`

**Why:** Running 8 strategies simultaneously on the same timeframe/pairs made it impossible to diagnose which strategies worked. One-at-a-time lets us observe each strategy's raw signal quality.

**How to apply:** When user asks to add the next strategy, use the next profile. Check previous strategy's trades/performance before adding new ones.

Timeframe diversity: BMR=1h, CIV1=1h, VB=4h, MomentumScalper=15m.
