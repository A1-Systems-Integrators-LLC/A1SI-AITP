# Phase 8: backend/portfolio/ (83% → 100%)

**Created**: 2026-03-09
**Current**: 83% (51 uncovered lines / 296 total)
**Target**: 100%

## Files & Gaps

| File | Stmts | Miss | Cover | Missing Lines |
|------|-------|------|-------|---------------|
| models.py | 35 | 9 | 74% | 27, 58-64, 67 |
| services/analytics.py | 65 | 4 | 94% | 121-124 |
| views.py | 113 | 38 | 66% | 57-66, 74-83, 102-111, 115-120, 140-141 |

## Test Plan

### models.py (9 lines)

1. **Line 27 — `Portfolio.__str__`**: Create Portfolio, assert `str(p) == p.name`
2. **Lines 58-64 — `Holding.clean()` validation**: Test negative amount, negative avg_buy_price, both negative, valid values
3. **Line 67 — `Holding.__str__`**: Create Holding, assert `str(h) == f"{h.symbol} x{h.amount}"`

### services/analytics.py (4 lines)

4. **Line 121 — ImportError on ExchangeService import**: Mock `builtins.__import__` to raise ImportError for `market.services.exchange`
5. **Lines 123-124 — ConnectionError/TimeoutError/OSError**: Mock ExchangeService to raise ConnectionError during fetch

### views.py (38 lines)

6. **Lines 57-66 — `PortfolioDetailView.put`**: PUT with valid data, PUT with 404
7. **Lines 74-83 — `PortfolioDetailView.patch`**: PATCH with partial data, PATCH with 404
8. **Lines 102-111 — `HoldingDetailView.put`**: PUT holding with valid data, PUT with 404
9. **Lines 115-120 — `HoldingDetailView.delete`**: DELETE holding, DELETE with 404
10. **Lines 140-141 — `HoldingCreateView.post` IntegrityError**: POST duplicate holding symbol

## Deliverable

- `backend/tests/test_portfolio_phase8.py`
