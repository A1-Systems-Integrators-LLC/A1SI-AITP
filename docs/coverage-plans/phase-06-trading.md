# Phase 6: backend/trading/ (83% → 100%)

**Created**: 2026-03-09
**Subsystem**: `backend/trading/` — Paper trading, order sync, live trading, performance, models, views
**Risk**: Paper trading and order sync are running live. Untested paths = undetected operational failures.

---

## Current Coverage

| File | Stmts | Miss | Cover | Missing Lines |
|------|-------|------|-------|---------------|
| `services/paper_trading.py` | 177 | 50 | 72% | 44, 67-69, 78-79, 97-99, 113, 134-137, 163-169, 218-219, 230-244, 247-248, 251-254, 257-258, 261-262, 265-266, 277-278, 282, 291-292 |
| `views.py` | 313 | 80 | 74% | 80, 82, 87, 92-94, 99, 103, 158-182, 188-207, 219-245, 251-312, 374-375, 414-424, 438, 491, 586 |
| `models.py` | 97 | 22 | 77% | 125-135, 138, 180-188, 191 |
| `services/generic_paper_trading.py` | 52 | 13 | 75% | 44-45, 59-63, 79-83, 87-93, 127 |
| `services/forex_paper_trading.py` | 124 | 13 | 90% | 61, 136, 148, 217-218, 285-293 |
| `services/order_sync.py` | 37 | 7 | 81% | 36-40, 43-45 |
| `services/live_trading.py` | 114 | 3 | 97% | 161, 229-230 |
| `services/performance.py` | 72 | 1 | 99% | 30 |
| `serializers.py` | 70 | 1 | 99% | 161 |

**Total**: 190 uncovered lines

---

## Test Strategy

### `services/paper_trading.py` (50 uncovered lines)
- **Lines 44, 67-69**: `_read_ft_config` error path (JSONDecodeError, OSError)
- **Lines 78-79**: `_api_alive()` returns False on exception
- **Lines 97-99**: `_find_freqtrade_pid()` /proc iteration with ValueError/OSError
- **Line 113**: `start()` config file not found
- **Lines 134-137**: `start()` FileNotFoundError and generic Exception from Popen
- **Lines 163-169**: `stop()` external process kill via API alive + PID found/not found
- **Lines 218-219**: `get_status()` API alive but show_config fails
- **Lines 230-244**: `get_status()` external process status from show_config API
- **Lines 247-292**: Async methods `_ft_get`, `get_open_trades`, `get_trade_history`, `get_profit`, `get_performance`, `get_balance`, `_log_event` error, `get_log_entries`

### `views.py` (80 uncovered lines)
- **Lines 80-103**: `OrderListView.get` filter branches (mode, asset_class, symbol, status, date_from, date_to)
- **Lines 158-182**: `OrderCancelView.post` (terminal status, live mode cancel)
- **Lines 188-207**: `LiveTradingStatusView.get`
- **Lines 219-245**: `_get_cached_exchange_status()` TTL cache + refresh
- **Lines 251-312**: `OrderExportView.get` CSV export
- **Lines 374-375**: `PaperTradingStatusView` forex exception path
- **Lines 414-424**: `PaperTradingTradesView` forex orders append
- **Lines 438, 491, 586**: Various paper trading view lines

### `models.py` (22 uncovered lines)
- **Lines 125-135**: `Order.clean()` validation (negative amount, negative price, limit order no price, invalid side)
- **Line 138**: `Order.__str__`
- **Lines 180-188**: `OrderFillEvent.clean()` validation
- **Line 191**: `OrderFillEvent.__str__`

### `services/generic_paper_trading.py` (13 uncovered lines)
- **Lines 44-45**: Equity market hours ImportError fallback
- **Lines 59-63**: Risk check rejection
- **Lines 79-83**: Invalid price (zero/negative)
- **Lines 87-93**: Limit order unfilled (buy above limit, sell below limit)
- **Line 127**: `get_status()` static method

### `services/forex_paper_trading.py` (13 uncovered lines)
- **Line 61**: Max positions reached early return
- **Line 136**: Sell-side entry order fallback in `_check_exits`
- **Line 148**: No entry order → continue
- **Lines 217-218**: Exit order submit failure (exception)
- **Lines 285-293**: `_get_price()` exception path

### `services/order_sync.py` (7 uncovered lines)
- **Lines 36-40**: Sync loop body — order iteration + sync_order call + per-order exception
- **Lines 43-45**: Loop-level exception + sleep

### `services/live_trading.py` (3 uncovered lines)
- **Line 161**: Partial fill detection (open + filled > 0 + filled < amount)
- **Lines 229-230**: `cancel_all_open_orders` per-order exception logging

### `services/performance.py` (1 uncovered line)
- **Line 30**: Zero-price order warning skip

### `serializers.py` (1 uncovered line)
- **Line 161**: `validate_exchange_id` invalid exchange_id error

---

## Deliverable
- `backend/tests/test_trading_phase6.py` — all new tests
- 100% coverage on all backend/trading/ files
