# Dara — Data Engineer Plan

## Role
Data quality, pipeline operations, data freshness, Parquet data store, feature store.

## Current State (2026-04-08)
- ~198 Parquet files in data/processed/ (crypto via Kraken, forex/equity via yfinance)
- 44/198 files flagged as stale in last preflight check
- 24/198 passed quality check (gaps, outliers detected in others)
- Data refresh tasks scheduled: crypto every 30min, forex/equity hourly
- Shared Parquet format used by all frameworks (Freqtrade, NautilusTrader, VectorBT, hftbacktest)

## Daily Checklist
1. Check data freshness: how many files stale? (preflight log: "Data Freshness: X/198 files stale")
2. Verify crypto data refresh running (scheduled_data_refresh task, every 30min)
3. Check data quality pass rate — target > 90% files passing
4. Verify alt data feeds active: Fear&Greed, Reddit, funding rates, FRED, news sentiment
5. Check for any new exchange pairs that need data downloads

## Active Plan
| Task | Target Date | Status |
|------|------------|--------|
| Investigate 44 stale data files — are refresh tasks running? | 2026-04-09 | NOT STARTED |
| Fix data quality failures (174/198 failing — gaps, outliers) | 2026-04-12 | NOT STARTED |
| Ensure all Freqtrade strategy pairs have fresh data | 2026-04-10 | NOT STARTED |
| Verify alt data pipeline delivers to SignalAggregator | 2026-04-11 | NOT STARTED |
| Document data refresh schedule and expected freshness SLAs | 2026-04-14 | NOT STARTED |

## Key Files
- Pipeline: common/data_pipeline/pipeline.py
- Data dir: data/processed/*.parquet
- Quality check: data_quality_check scheduled task
- Refresh tasks: data_refresh_crypto (30min), data_refresh_equity (1h), data_refresh_forex (1h)

## Lessons Learned
- 174/198 files failing quality checks. Need to distinguish between real data quality issues and overly strict checks (forex weekend gaps are expected, not bugs).
