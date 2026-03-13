# Phase 9: common/ (94% → 100%)

**Created**: 2026-03-09
**Subsystem**: `common/` — shared libraries (data pipeline, ML, regime, risk, sentiment, market hours, indicators)
**Current**: 95% (91 uncovered lines / 1727 total)
**Target**: 100%

---

## Files & Gaps

| File | Stmts | Miss | Cover | Missing Lines |
|------|-------|------|-------|---------------|
| `data_pipeline/pipeline.py` | 375 | 39 | 90% | 380, 653, 655, 657, 826-875 |
| `ml/registry.py` | 75 | 10 | 87% | 19-21, 66, 111, 133, 137, 140, 168-169 |
| `data_pipeline/news_adapter.py` | 118 | 7 | 94% | 73, 179-180, 195, 213-215 |
| `ml/trainer.py` | 57 | 5 | 91% | 20-22, 83, 162 |
| `market_hours/sessions.py` | 124 | 5 | 96% | 110, 128, 144, 154, 186 |
| `data_pipeline/yfinance_adapter.py` | 92 | 4 | 96% | 184, 215, 246, 262 |
| `indicators/technical.py` | 132 | 3 | 98% | 54, 56, 61 |
| `sentiment/scorer.py` | 53 | 3 | 94% | 123-126 |
| `risk/risk_manager.py` | 254 | 11 | 96% | 335-336, 396, 482-487, 505, 509 |
| `regime/regime_detector.py` | 188 | 2 | 99% | 404, 418 |
| `regime/strategy_router.py` | 68 | 2 | 97% | 244, 296 |

---

## Test Plan

### pipeline.py
- **Line 380**: Crypto timeframe default (else branch) — call `download_watchlist` with `asset_class="crypto"`, `timeframes=None`
- **Lines 653, 655, 657**: Validation issues for NaN columns, outliers, OHLC violations — create DataFrames with NaN values, price spikes, and OHLC integrity violations, then call `validate_data`
- **Lines 826-875**: `__main__` CLI block → `pragma: no cover` (CLI entry point, consistent with phases 5/7)

### registry.py
- **Lines 19-21**: ImportError fallback for lightgbm → mock `HAS_LIGHTGBM=False`
- **Line 66**: `save_model` raises ImportError when no lightgbm
- **Line 111**: `load_model` raises ImportError when no lightgbm
- **Lines 133, 137, 140**: `list_models` skips non-dir entries, dirs without manifest, corrupt JSON manifests
- **Lines 168-169**: `get_model_detail` returns None for corrupt JSON

### news_adapter.py
- **Line 73**: Atom feed fallback (RSS items empty, Atom entries found)
- **Lines 179-180**: NewsAPI article dedup in `fetch_all_news`
- **Line 195**: `_get_text` Atom namespace text extraction
- **Lines 213-215**: `_get_link` Atom link with href attribute

### trainer.py
- **Lines 20-22**: ImportError fallback for lightgbm → mock
- **Line 83**: `train_model` raises ImportError when no lightgbm
- **Line 162**: `predict` raises ImportError when no lightgbm

### sessions.py
- **Line 110**: Friday forex market hours (before 5PM = open)
- **Line 128**: Unknown asset class returns None for next_open
- **Line 144**: Next equity open fallback after 10 iterations
- **Line 154**: Forex next_open on Sunday after open time → next week
- **Line 186**: Unknown asset class returns None for next_close

### yfinance_adapter.py
- **Line 184**: Timezone-aware data (tz_convert path)
- **Line 215**: `fetch_ohlcv_yfinance` async wrapper
- **Line 246**: `fetch_ticker_yfinance` async wrapper
- **Line 262**: `fetch_tickers_yfinance` async wrapper

### technical.py
- **Lines 54, 56, 61**: Supertrend direction changes (close > upper → direction=1, close < lower → direction=-1, direction=1 → max(lower, prev_st))

### scorer.py
- **Lines 123-126**: Negative sentiment label branch

### risk_manager.py
- **Lines 335-336**: Market hours ImportError fallback in `can_trade`
- **Line 396**: Symbol not in correlation matrix
- **Lines 482-487**: Risk summary correlation pair detection
- **Line 505**: High correlation pairs issue
- **Line 509**: VaR warning issue

### regime_detector.py
- **Line 404**: Transition probabilities with <2 data points → empty dict
- **Line 418**: Transition probabilities with zero matching transitions → empty dict

### strategy_router.py
- **Line 244**: Unknown regime fallback to RANGING
- **Line 296**: Strategy switch — current strategy in weights with weight >= 0.5

---

## Deliverable
- `docs/coverage-plans/phase-09-common.md` (this file)
- `backend/tests/test_common_phase9.py` (~45 new tests)
- `pragma: no cover` on pipeline.py `__main__` block (lines 825-875)
