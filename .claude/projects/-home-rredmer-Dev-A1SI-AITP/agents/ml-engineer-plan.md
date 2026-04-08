# Priya — ML Engineer Plan

## Role
ML model performance, retraining pipeline, feature engineering, prediction quality monitoring.

## Current State (2026-04-08)
- 10 LightGBM models trained: BTC, ETH, SOL, XRP, DOGE, BNB, ADA, AVAX, DOT, LINK
- Best accuracy: AVAX 66.3%, BTC 61.3%
- Daily retraining scheduled via `ml_training` task
- Models feed into SignalAggregator.compute() for composite scoring
- Conviction pipeline disabled — ML scores computed but don't gate trades

## Daily Checklist
1. Verify ml_training task ran: check ScheduledTask last_run_at for ml_training
2. Check model accuracy trend — is it improving, stable, or decaying?
3. Monitor prediction distribution drift (are predictions clustering?)
4. Verify all 10 models exist in /project/models/
5. Check feature freshness — alt data feeds (Fear&Greed, Reddit, funding rates) still flowing?

## Active Plan
| Task | Target Date | Status |
|------|------------|--------|
| Establish accuracy baselines for all 10 models over 7 days | 2026-04-13 | IN PROGRESS |
| Analyze which features drive predictions (SHAP values) | 2026-04-16 | NOT STARTED |
| Compare ML signal correlation to actual strategy entries | 2026-04-18 | NOT STARTED |
| Prepare conviction pipeline logging-mode analysis for Nakamura | 2026-04-20 | NOT STARTED |
| Tune retraining frequency based on accuracy decay rate | 2026-04-22 | NOT STARTED |

## Key Files
- ML registry: common/ml/registry.py
- Model training: common/ml/ directory
- Signal aggregator: common/indicators/signal_aggregator.py (or similar)
- Scheduled task: settings.py → ml_training (daily)
- Alt data feeds: SignalAggregator integrates Fear&Greed, Reddit, BTC dom, funding rates, FRED, news

## Lessons Learned
- ML was completely disabled for 4 months while infrastructure was being built. Models must be training continuously.
- Daily retraining (not weekly) is necessary — crypto markets shift fast.
