# Degraded-State Analysis & Performance Plan

**Analysis date:** 2026-06-25 (live state re-verified 2026-06-25/26)
**Period analyzed:** since the 2026-06-10 restart (~15 days of runtime)
**Trigger:** system reported "Degraded" after running ~1 week unattended
**Status of plan:** PROPOSAL — nothing in this document has been executed. Authority mode (propose, never execute).
**Method:** direct inspection (docker/curl/FT REST API/code reads) + a 35-agent diagnostic workflow with adversarial verification. Several workflow conclusions were **corrected by live verification** — see "Corrections" below.

---

## TL;DR

"Degraded" is **two unrelated problems wearing one badge**, and one root cause drives most of the infra symptoms.

1. **Infra — host memory/swap exhaustion (the keystone).** The 7.7 GB WSL2 box swap-thrashes (swap pinned 2.0/2.0 GiB, 0 free). The backend process is so starved that even `/api/health/` — a pure in-memory endpoint — times out at 5 s, so Docker marks the backend **unhealthy** (FailingStreak ~3954). The same starvation:
   - 500s the dashboard KPI endpoints (DNS resolver for `postgres` gets starved → `failed to resolve host 'postgres'`),
   - and stalls the **sentiment** strategy (its call to the backend times out at 5 s → no signals → idle since 2026-06-22).
2. **Trading — broken stops + risk-reward asymmetry (paper/dry-run, no real money).** All three live strategies are net-negative since the restart, driven by a confirmed bug: `custom_stoploss` reads the raw (un-analyzed) dataframe → `KeyError('atr')` ~80–90×/min continuously → the ATR stop is inert and trades fall back to the wide static stop.

**Single highest-impact fix:** raise WSL2 memory (#1). It clears the badge, restores the dashboard, and re-enables sentiment trading in one move.

---

## Evidence (live, verified)

### Containers / runtime
- 7 prod containers, started 2026-06-10, `restart: unless-stopped`.
- `aitp-prod-backend`: **unhealthy**, `FailingStreak=3954`. Health log: repeated `Health check exceeded timeout (5s)` on `curl -sf http://localhost:8000/api/health/` (interval 15 s, timeout 5 s).
- `aitp-prod-ft-scalp`: `RestartCount=1` (OOM-related restart during the analysis window).
- All other containers healthy, 0 restarts.

### Host (WSL2)
- 8 cores, **7.66 GiB** RAM (`MemTotal 8032476 kB`), **~197 MiB free**.
- **Swap 2.0/2.0 GiB used, ~280 KiB free** — fully exhausted, thrashing.
- Windows physical RAM: **15.8 GB**. No `/mnt/c/Users/ronal/.wslconfig` present (WSL on defaults).
- Container memory at snapshot: ft-scalp 1.245 GiB, ft-reversal 1.114 GiB, worker 860 MiB, ft-sentiment 674 MiB, backend 570 MiB, postgres 158 MiB. VS Code/Claude tooling adds ~1.5 GiB when the IDE is open.

### Infra error pattern
- `psycopg.OperationalError: failed to resolve host 'postgres': [Errno -3] Temporary failure in name resolution` — bursts (e.g. 25 in a 42 s top-of-hour window) → HTTP 500 on `/api/dashboard/kpis/`, `/api/jobs/`, `/api/market/tickers/`, `/api/market/opportunities/summary/`.
- Secondary symptom: `AttributeError: 'SessionStore' object has no attribute '_session_cache'` when the DB is briefly unreachable.
- Dashboard renders "Degraded" when `system_health.scheduler_running` is falsy / KPIs 500 (`frontend/src/pages/Dashboard.tsx:196`).

### Sentiment drought (keystone confirmation)
- `aitp-prod-ft-sentiment` logs, continuous: `Sentiment API fetch failed: ... Connection to backend timed out. (connect timeout=5)` for `GET http://backend:8000/api/market/news/signal/?asset_class=crypto`.
- Live balance: **148.09 USDT free, 0 open trades** → NOT balance-locked. The endpoint exists (`backend/market/urls.py:87`, `SentimentSignalView`) and the strategy URL matches — the only failure is the backend timing out (memory starvation).

### Broken stop-loss (trading keystone)
- `KeyError('atr')` count in last 2 h: **ft-scalp 9,284**, **ft-reversal 11,204**, ft-sentiment 0 (idle).
- Cause: `self.dp.get_pair_dataframe(pair, self.timeframe)["atr"]` returns the **raw** OHLCV df (no indicators). `atr` is populated by `ta.ATR` in `populate_indicators` (line 62/94/56), which only the **analyzed** df carries.

### Trading performance since restart (all dry_run=True, 200 USDT simulated wallet each)
| Strategy | Port | Return (all) | Trades | W/L | Note |
|---|---|---|---|---|---|
| MomentumScalper15m (scalp) | 4187 | −14.5% | 33 | 27 / 5 | High win rate, PF ~0.19 — winners capped by ROI, losers ran to static −10% |
| SentimentEventTrader (sentiment) | 4188 | −27.3% | 40 | 19 / 21 | Idle since 06-22 (backend timeout, not balance) |
| TrendReversal (reversal) | 4189 | −17.4% | 25 | 14 / 9 | Avg loser −5.7% vs winner +0.84% |

Combined ≈ −112 USDT **paper** loss. No real capital at risk.

---

## Root causes (ranked)

| # | Issue | Sev | Evidence | Verification |
|---|---|---|---|---|
| 1 | Host memory/swap exhaustion → OOM kills, backend unhealthy, DNS starvation, sentiment timeout | Critical | swap 2.0/2.0 GiB; backend healthcheck 5 s timeout; ft-scalp restart=1; sentiment "connect timeout=5" | Confirmed live; **upgraded over** the original DNS/CONN_MAX_AGE theory |
| 2 | `custom_stoploss` broken on all 3 (raw df, not analyzed) | Critical | `KeyError('atr')` ~80–90/min, continuous | Confirmed live |
| 3 | R:R asymmetry — ROI caps winners, losers run to static stop | Critical | scalp PF 0.19; reversal loser −5.7% vs winner +0.84% | Confirmed; "fee-negative ROI" refuted |
| 4 | ft-* + postgres containers have no `mem_limit` | High | `docker inspect` Memory=0 | Confirmed |
| 5 | `scheduled_ml_feedback` wastes ~6 h/day, 0 updates | High | `ml.py:184 .distinct()` defeated by `MLPrediction.Meta.ordering` (`models.py:269`) | Confirmed live |
| 6 | Docker embedded-DNS blips → kpis 500 → badge | Medium | psycopg "failed to resolve host postgres" | Confirmed symptom of #1 |
| 7 | `DashboardKPIView` 500s on any DB blip (unguarded `.first()`) | Medium | `dashboard.py:71` | Confirmed |
| 8 | Equity data stale (3-char ticker misread as forex) | Medium | `data.py _infer_asset_class` sends `WMT/USD`→`WMTUSD=X` | Confirmed |

---

## Corrections to the original diagnostic draft (made by live verification)

1. **`.wslconfig memory=6GB` was wrong.** Windows has 15.8 GB; WSL gets 7.66 GB by default. Lowering it would worsen starvation. Correct = **raise** to `memory=11GB, swap=6GB`.
2. **Sentiment was NOT balance-locked.** It has 148 USDT free, 0 open trades. The real cause is the backend timing out (#1). Do **not** lower its stake as a "fix"; it resumes when #1 lands.
3. **Container limits of `1200m` would instantly OOM** scalp/reversal (they use ~1.2 GiB now). Limits must sit above steady-state (≥1800m).
4. **My initial `CONN_MAX_AGE=0` + scheduler-burst hypothesis was refuted.** `CONN_MAX_AGE=600` is already set (`settings.py:105`); the pool is healthy. DNS failures are a symptom of #1.

---

## The plan

All items are single-line edits or config additions, reversible, and fix/activate existing code (no new modules).

### Tier 1 — apply now (root-cause fixes)

**#1 — Relieve memory (keystone).** NEW file `/mnt/c/Users/ronal/.wslconfig` (Windows-side; requires `wsl --shutdown`):
```ini
[wsl2]
memory=11GB    # up from default ~7.66GB; leaves ~4.8GB for Windows (16GB total)
swap=6GB       # up from 2GB; eliminates the OOM-kill / swap-thrash condition
```
Apply: save → PowerShell `wsl --shutdown` (briefly stops the paper bots) → Docker Desktop restarts the engine → containers return via `restart: unless-stopped` → verify `free -h` ~11 Gi and all containers healthy.

**#2 — Fix `custom_stoploss` on all three strategies.** Same change in `MomentumScalper15m.py:161`, `SentimentEventTrader.py:177`, `TrendReversal.py:185`:
```python
# OLD — raw df has no 'atr' column → KeyError
        atr = self.dp.get_pair_dataframe(pair, self.timeframe)["atr"].iloc[-1]
# NEW — analyzed df carries populate_indicators output
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr" not in df.columns:
            return self.stoploss   # fall back to static stop until indicators warm up
        atr = df["atr"].iloc[-1]
```

**#3 — Fix the ML feedback job** in `backend/core/services/executors/ml.py`:
```python
# Line ~167 — make .distinct() actually distinct on model_id:
        .order_by("model_id")
        .values_list("model_id", flat=True)
        .distinct()[:50]
# Line 184 — same for the regime loop:
        for regime_name in preds.order_by("regime").values_list("regime", flat=True).distinct():
```
Root: `MLPrediction.Meta.ordering=['-predicted_at']` (`models.py:269`) injects `predicted_at` into the `DISTINCT`. Overriding the order fixes it (21,804 queries → 12). No migration.

### Tier 2 — apply alongside Tier 1 (cheap hardening)

- **Container memory limits (defense-in-depth)** in `docker-compose.prod.yml`: add to the `&freqtrade-base` anchor `deploy.resources.limits.memory: 1800m` (above the ~1.2 GiB steady-state) and `postgres` `512m`. Optional cleanliness: backend `8g→3g` (line 53), worker `6g→3g` (line 167) — they use 570/860 MiB. Purpose: per-container OOM (Docker kills + auto-restarts the offender) instead of the kernel OOM-killer hitting a random container.
- **#7 Guard the KPI view** at `backend/core/services/dashboard.py:71`: wrap `Portfolio.objects.order_by("id").first()` in `try/except OperationalError → portfolio_id=None` so a DB blip returns HTTP 200 partial data instead of 500.
- **Offset watchdog cron** off `:00`: host crontab `*/5 * * * *` → `2-59/5 * * * *`, `0 0` → `2 0`.
- **#8 Fix equity misclassification** in `backend/core/services/executors/data.py:62`: only label a yfinance `BASE/QUOTE` pair "forex" when BOTH sides are currency codes (today `WMT/USD` → both 3-char → mislabeled → dead `WMTUSD=X` ticker). Reuse a currency set, e.g.:
```python
    _CURRENCIES = {"USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF","CNY","HKD","SGD"}
    if exchange == "yfinance":
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            if base in _CURRENCIES and quote in _CURRENCIES:
                return "forex"
        return "equity"
```

### Tier 3 — deferred one observation cycle

Strategies are paper/dry-run, so fix the one real bug (#2), then watch a week of clean data before tuning. Changing stops AND ROI/entries at once muddies the learning signal.
- Reversal/scalp ROI, trailing stops, time-stops — the ROI tables are reasonable; the asymmetry was the broken stop. Re-evaluate after #2 produces real R:R data.
- Sentiment stake/threshold — don't touch; it resumes when #1 lands. Re-assess edge with post-fix data.
- `SESSION_ENGINE`→`cached_db` (`settings.py:133`) — marginal; touches auth. Skip unless DB load stays high after #1.

---

## What NOT to do (over-engineering guardrails)

- No pgbouncer / connection pooler — `CONN_MAX_AGE=600` already pools; conns ~44/100, no exhaustion.
- No bigger box / no new containers — the fix is *capping/sizing* memory, not adding services.
- No hardcoded `extra_hosts: postgres:<IP>` — the IP is dynamic; this silently breaks on stack recreate.
- Don't chase the DNS-burst / async-connection / `CONN_MAX_AGE=0` theories — refuted; #1 makes them moot.
- Don't stop or disable any strategy for being down — it's paper-phase learning data; fix the logic instead.

---

## Verification plan (no fix claimed without evidence)

```bash
# #1 memory (after wsl --shutdown + redeploy)
free -h                                                            # swap free > 0; ~11Gi total
docker inspect aitp-prod-backend -f '{{.State.Health.Status}} streak={{.State.Health.FailingStreak}}'  # healthy streak=0

# DNS + endpoints (24h after)
docker logs aitp-prod-backend --since 24h 2>&1 | grep -c "failed to resolve host 'postgres'"  # 0
curl -s -o /dev/null -w '%{http_code}' http://localhost:4100/api/dashboard/kpis/              # 200
curl -s http://localhost:4100/api/dashboard/kpis/ | python3 -m json.tool | grep scheduler_running  # true

# #2 stop-loss (per container, after redeploy)
for c in ft-scalp ft-sentiment ft-reversal; do docker logs aitp-prod-$c --since 1h 2>&1 | grep -c "KeyError"; done  # 0

# sentiment resumes (creds via: docker exec aitp-prod-ft-sentiment printenv FREQTRADE__API_SERVER__USERNAME/_PASSWORD)
curl -s -u U:P http://localhost:4188/api/v1/count                 # current > 0 over time

# #3 ml job
docker exec aitp-prod-worker python manage.py shell -c \
 "from analysis.models import BackgroundJob as J; j=J.objects.filter(job_type='scheduled_ml_feedback').latest('created_at'); print(j.status,(j.completed_at-j.created_at).total_seconds())"  # completed, < 60s

# trading expectancy (track over a week)
curl -s -u U:P http://localhost:4187/api/v1/profit | python3 -c "import sys,json;d=json.load(sys.stdin);print('PF',d.get('profit_factor'),'exp',d.get('expectancy'))"
```

---

## Relevant files
- `docker-compose.prod.yml` (anchors: backend deploy line 49-56, frontend 80-87, freqtrade-base 98-105, worker 163-170; services 198-281)
- `backend/config/settings.py` (DB 105, session 133/139)
- `backend/core/services/executors/ml.py` (167, 184)
- `backend/analysis/models.py:269` (`MLPrediction.Meta.ordering`)
- `backend/core/services/dashboard.py:71`
- `backend/core/services/executors/data.py:60` (`_infer_asset_class`)
- `backend/market/urls.py:87` (`market/news/signal/`)
- `freqtrade/user_data/strategies/{MomentumScalper15m.py:161, SentimentEventTrader.py:177, TrendReversal.py:185}`
- Host crontab; `/mnt/c/Users/ronal/.wslconfig` (new)

**Nothing was executed — proposal only. All changes are reversible (single-line edits / config additions / revert cron line).**
