# Phase 3: backend/market/ — 60% → 100%

**Created**: 2026-03-09
**Current**: 1811 stmts, 732 uncovered (60% coverage)
**Target**: 100% line coverage

---

## Coverage Gaps by File

| File | Stmts | Miss | Cover | Missing Lines |
|------|-------|------|-------|---------------|
| views.py | 468 | 233 | 50% | 58-66, 72-79, 85-97, 103-114, 189, 199, 207-258, 269-346, 381-382, 386-389, 397-403, 409, 429-445, 463-505, 529-555, 569-588, 611-629, 652, 680, 718, 738-740, 744-755, 790, 798, 856-860, 866-871 |
| exchange.py | 120 | 90 | 25% | 23-24, 28, 30-37, 44, 50-79, 82-84, 103-121, 134-167, 170-188 |
| consumers.py | 81 | 81 | 0% | 3-179 (entire file) |
| circuit_breaker.py | 80 | 80 | 0% | 3-140 (entire file) |
| market_scanner.py | 190 | 60 | 68% | 121-130, 135-144, 170-179, 186-199, 227, 232, 263, 270-271, 285-286, 313, 323, 329, 363, 404, 410-421, 447-449, 453-454, 465-494 |
| daily_report.py | 164 | 39 | 76% | 60, 79-81, 104-106, 136-139, 166-168, 196-201, 212-214, 235, 245-247, 259, 275-277, 327-335 |
| ticker_poller.py | 37 | 37 | 0% | 3-66 (entire file) |
| models.py | 125 | 28 | 78% | 45-51, 54, 83, 88, 121-132, 135, 175, 200-208, 211 |
| indicators.py | 32 | 22 | 31% | 52-81 (compute method) |
| data_router.py | 33 | 18 | 45% | 29-41, 50-62 |
| migrate_env_credentials.py | 18 | 18 | 0% | 3-44 (entire file) |
| yfinance_service.py | 33 | 9 | 73% | 12-17, 55-66 |
| news.py | 70 | 6 | 91% | 57-63, 84, 167 |
| routing.py | 3 | 3 | 0% | 3-7 |
| serializers.py | 181 | 3 | 98% | 12-14 |
| fields.py | 11 | 2 | 82% | 14, 19 |
| regime.py | 117 | 3 | 97% | 13, 178-179 |

---

## Test Strategy

### New test file: `backend/tests/test_market_phase3.py`

**1. Models** — clean() validation, __str__, save() default enforcement
**2. Circuit Breaker** — Full state machine: CLOSED→OPEN→HALF_OPEN→CLOSED, reset, registry
**3. Exchange Service** — DB config loading, async _get_exchange, fetch_ticker/tickers/ohlcv with circuit breaker, close
**4. Indicators** — compute() with mocked pipeline data
**5. Data Router** — fetch_tickers and fetch_ohlcv for crypto/equity/forex paths
**6. YFinance Service** — fetch_ticker, fetch_ohlcv with actual data rows
**7. News Service** — cap enforcement (>1000 articles), symbol filter, negative sentiment label
**8. Daily Report** — no regimes, empty data coverage, strategy performance with orders, sentiment in recommendations
**9. Market Scanner** — scan_all full loop, all 5 detectors individually, alert broadcasting
**10. Views** — All uncovered API endpoints (news, exchange test/rotate, data source CRUD, ticker/OHLCV errors, regime, circuit breaker, opportunities, daily report, indicator compute)
**11. Consumers** — WebSocket connect/disconnect, auth, connection limits, message handlers
**12. Ticker Poller** — start/stop/poll loop
**13. Management Commands** — migrate_env_credentials (no key, existing config, success)
**14. Fields** — EncryptedTextField short value masking
**15. Serializers** — _mask_value with short strings
**16. Routing** — Import coverage
**17. Regime** — _load_data exception path

---

## Deliverable

- `docs/coverage-plans/phase-03-market.md` (this file)
- `backend/tests/test_market_phase3.py` — comprehensive test file
- 100% coverage on all `backend/market/` files
