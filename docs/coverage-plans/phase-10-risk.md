# Phase 10: backend/risk/ (92% → 100%)

**Created**: 2026-03-10
**Current**: 576 stmts, 45 missed, 92% coverage (292 existing tests)
**Target**: 100% line coverage on all 13 files

---

## Files & Gaps

| File | Stmts | Miss | Coverage | Missing Lines |
|------|-------|------|----------|---------------|
| `models.py` | 105 | 8 | 92% | 20, 46, 50, 55, 80, 115-116, 143 |
| `services/risk.py` | 247 | 4 | 98% | 310-311, 328-329 |
| `views.py` | 110 | 33 | 70% | 68-71, 107-110, 123, 129-130, 136, 142-144, 150-152, 162-170, 176-179, 199-208, 214-216 |

---

## Uncovered Lines — Detailed Analysis

### models.py (8 lines)

| Line(s) | Code | Test Case |
|---------|------|-----------|
| 20 | `RiskState.__str__` | Create RiskState, call `str()` |
| 46-47 | `RiskLimits.clean()` — `min_risk_reward < 0` | Set `min_risk_reward=-1`, call `clean()`, expect ValidationError |
| 50 | `RiskLimits.clean()` — `max_leverage < 0` | Set `max_leverage=-1`, call `clean()`, expect ValidationError |
| 55 | `RiskLimits.__str__` | Create RiskLimits, call `str()` |
| 80-83 | `RiskMetricHistory.__str__` | Create instance, call `str()` |
| 115-116 | `TradeCheckLog.__str__` | Create approved + rejected instances, call `str()` |
| 143 | `AlertLog.__str__` | Create instance, call `str()` |

### services/risk.py (4 lines)

| Line(s) | Code | Test Case |
|---------|------|-----------|
| 310-311 | `periodic_risk_check` — daily loss auto-halt notification exception | Mock `send_notification` to raise on 2nd call (after halt), verify auto_halted still returned |
| 328-329 | `periodic_risk_check` — risk warning notification exception | Mock `send_notification` to raise, verify warning status still returned |

### views.py (33 lines)

| Line(s) | View | Test Case |
|---------|------|-----------|
| 68-71 | `EquityUpdateView.post` | POST equity update, verify response |
| 107-110 | `PositionSizeView.post` | POST position size calculation |
| 123 | `ResetDailyView.post` | POST reset daily |
| 129-130 | `VaRView.get` | GET VaR with method param |
| 136 | `HeatCheckView.get` | GET heat check |
| 142-144 | `MetricHistoryView.get` | GET metric history with hours param |
| 150-152 | `RecordMetricsView.post` | POST record metrics |
| 162-170 | `HaltTradingView.post` | POST halt with reason (mock async halt) |
| 176-179 | `ResumeTradingView.post` | POST resume (mock async resume) |
| 199-208 | `AlertListView.get` | GET alerts with filter params |
| 214-216 | `TradeLogView.get` | GET trade log |

---

## Test File

`backend/tests/test_risk_phase10.py` — ~30 new tests covering all 45 uncovered lines.
