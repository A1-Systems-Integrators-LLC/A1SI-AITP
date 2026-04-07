---
name: Learning Phase
description: Trading system in learning phase — conviction/risk gates disabled to observe raw strategy signal quality
type: project
---

All 8 Freqtrade strategies have conviction/risk API gates DISABLED since 2026-04-06.
This is the "learning phase" — paper trading with fake money to observe raw strategy behavior.

**Why:** After 3+ months and 181 commits, the system produced zero profitable trades. The conviction pipeline (`_conviction_helpers.py`) was silently blocking trades, and strategy parameters had been over-relaxed in a death spiral. Stripping all gates lets us see whether the strategies themselves generate viable signals.

**How to apply:** Do NOT re-enable conviction gates until at least 2 weeks of raw signal data has been collected. When re-enabling, add logging/metrics to track how often conviction approves vs. rejects trades before blocking anything.

ML is also disabled (`platform_config.yaml: ml.enabled: false`) due to insufficient training data. Re-enable after 6+ months of data collection.
