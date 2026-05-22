# 2026-05-22 — Consolidation Plan

**Status:** EXECUTED
**Owner:** Claude (with user approval at every step)
**Trigger:** User stepped away ~1 month after April 15. System was down by April 16 morning. Pattern recognized: 30+ commits in two months, all "fix instability" — system was too big to maintain solo, kept falling over.

## Premise

A1SI-AITP currently runs **~95K LOC of Django backend**, **18K LOC of frontend**, **5K LOC of Nautilus/research/hftbacktest**, **11 containers**, **38 scheduled background tasks running ~58 executions/hour**, **7 Freqtrade strategy containers** — all to paper-trade **$500 of speculative crypto capital**.

The over-engineering is on me (Claude). The user asked me to triage and consolidate.

## What was wrong

### 1. Scheduler doing too much, too often, all at once

38 scheduled tasks. Many for asset classes (equity, forex) that aren't actually traded. Many for "research tier" frameworks (VectorBT, NautilusTrader, hftbacktest) that don't connect to anything live. All tasks at the same interval (`interval_seconds`) started at scheduler boot, so they aligned on the same wall-clock minutes — every :00 and :30 of the hour, **11 tasks fired simultaneously**, with the worst spike on every hour-boundary when 30-min + 1-h tasks collided. The April 15 fix (process-isolating the scheduler into a worker container) treated the symptom (Daphne starvation) not the cause (too much work, badly distributed).

### 2. One Freqtrade container per strategy

7 separate containers (BMR, CIV1, VB, Scalp, Grid, Sentiment, Reversal), each ~600 MB RSS, each making its own exchange API calls. Five of the seven were known losers as of April 15: Grid 0/7, CIV1 0/3, BMR 0/1, VB 1/3 losing, Sentiment 0/0 (signal pipeline was broken until April 15 fix). Only Scalp (3-0 wins) and Reversal (first close +$0.14) had any positive signal. We were spending memory and rate-limit budget on negative-EV strategies.

### 3. Multi-tier framework dead weight

VectorBT → Freqtrade → NautilusTrader → hftbacktest "tiers" exist in code and in the scheduler, but only Freqtrade actually trades. The other three contribute zero to P&L while contributing to startup complexity, scheduled task count, and "things that can fail."

## What changed in this PR

### Scheduled tasks: 38 → 22

**Deleted** (16 tasks; executors retained in `task_registry.py` for manual invocation):

| Category | Tasks |
|---|---|
| Asset classes not traded | `data_refresh_equity`, `data_refresh_forex`, `data_refresh_forex_4h`, `vbt_screen_equity`, `vbt_screen_forex`, `market_scan_forex`, `forex_paper_trading`, `nautilus_backtest_equity`, `nautilus_backtest_forex` |
| Unused frameworks | `vbt_screen_crypto`, `nautilus_backtest_crypto`, `hft_backtest` |
| Redundant / unused | `order_sync` (no live trading), `daily_report` (duplicate of `pdf_report_daily`), `autonomous_check` (a fragile auto-remediator), `adaptive_weighting` (operates on ML output that hasn't earned its keep) |

**Frequency reductions** (8 tasks, see [`backend/config/settings.py`](../backend/config/settings.py)):
- `data_refresh_crypto`, `regime_detection`, `news_fetch`: 30 min → hourly
- `reddit_sentiment_refresh`, `coingecko_trending_refresh`: 30 min → every 4h
- `fear_greed_refresh`, `ml_predict`: hourly → every 4h
- `ml_feedback`: hourly → daily (7:15 UTC)

**Stagger**: All 22 remaining tasks converted from `interval_seconds` to `cron_schedule` with staggered minute offsets. At most 2 tasks fire on any given minute (vs 11 before).

### Freqtrade containers: 7 → 3

Kept: `freqtrade-scalp`, `freqtrade-sentiment`, `freqtrade-reversal`.
Cut: `freqtrade-bmr`, `freqtrade-civ1`, `freqtrade-vb`, `freqtrade-grid`.

Strategy `.py` files remain on disk. `FREQTRADE_INSTANCES` entries in [`backend/config/settings.py`](../backend/config/settings.py) for cut strategies are flipped to `"enabled": False` (not deleted — tests still resolve, and reactivation is one boolean flip + restoring the docker-compose service block).

### Container count: 11 → 7

| Before | After |
|---|---|
| backend, worker, frontend, postgres | backend, worker, frontend, postgres |
| freqtrade-bmr, -civ1, -vb, -scalp, -grid, -sentiment, -reversal | freqtrade-scalp, -sentiment, -reversal |

### Scheduler robustness fix

[`backend/core/services/scheduler.py`](../backend/core/services/scheduler.py) `_sync_tasks_to_db()` now pauses any `ScheduledTask` DB rows that aren't in `SCHEDULED_TASKS`. Prevents removed tasks from continuing to fire from stale DB state.

## What was NOT done (deliberately)

- **No `docker compose down/up` yet** — user starts Docker Desktop and runs the deploy step manually after reviewing the diff. The agent does not restart prod autonomously.
- **No code deletion** for cut strategies, NautilusTrader, hftbacktest, or VectorBT — the code stays on disk. This PR is deactivation, not amputation.
- **No test changes** — `FREQTRADE_BMR_API_URL` / `FREQTRADE_VB_API_URL` settings keys still exist (they default to empty), so the three test files that reference them keep passing.
- **No dev compose changes** — only `docker-compose.prod.yml`. Dev stays flexible.

## Going-forward rules (the ones I should have been following)

1. **No new scheduled task** unless a specific consumer (strategy, dashboard, alert) reads its output. Background work that produces unused output is dead weight.
2. **No new container** unless an existing one can't do the job. Process boundaries cost memory, complexity, and failure surface.
3. **No new framework tier** (VectorBT/Nautilus/HFT) unless it's about to be wired into live trading. Research code lives in notebooks until it's earning its keep.
4. **Stagger by default** — anything cron-scheduled goes at a non-zero, non-30 minute mark, unless a specific event (midnight reset, daily report at user-specified time) requires otherwise.
5. **Pause-not-delete on removal** — orphaned tasks/containers should be marked disabled in code, not removed. Preserves history and makes reactivation a one-line change.

## Verification protocol (post-deploy)

1. User starts Docker Desktop on Windows; verifies WSL daemon reachable (`docker info`).
2. `make docker-prod-down` (clean stop of whatever's running).
3. `make docker-prod-deploy` with `--profile trading` (the standing rule from `feedback_prod_deploy.md`).
4. Confirm exactly **7 containers** healthy: `docker ps --filter name=aitp-prod`.
5. Confirm scheduler logs show **22 jobs scheduled** and **0 orphans active** (`docker logs aitp-prod-worker | grep -E "scheduled|orphan"`).
6. Verify at least one cron minute that previously had simultaneous fires (`:00`, `:30`) now has at most 1 task firing.
7. 24h watch: backend health check should remain HTTP 200 throughout. No `ERR_CONNECTION_RESET` events in nginx logs.
8. 72h watch: at least one full PDF report cycle (`pdf_report_daily`) should complete; daily backup (`db_backup_daily`) should produce a `.sql.gz` in the backup volume.

## Reactivation path

If we later decide to bring back a cut strategy or task:

- **Re-enable a Freqtrade strategy**: flip `enabled: True` in `FREQTRADE_INSTANCES`, restore the service block in `docker-compose.prod.yml` from git history, `make docker-prod-deploy`.
- **Re-enable a scheduled task**: add the entry back to `SCHEDULED_TASKS` with a non-colliding cron minute (check `docs/2026-05-22-consolidation-plan.md` minute map first).
- **Re-enable a framework tier**: not recommended without a live-trading consumer. If insisted, add the scheduled tasks back individually with the lowest reasonable frequency (daily or weekly).
