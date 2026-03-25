# Daily PDF Report System — Plan

## Architecture
- **WeasyPrint** + **Jinja2** + **matplotlib** (HTML/CSS → PDF with embedded charts)
- Data collector aggregates from existing services (no logic duplication)
- Chart renderer produces base64 PNGs via matplotlib Agg backend
- Scheduled daily via task registry, downloadable via API

## Files
- `backend/market/services/pdf_report/__init__.py`
- `backend/market/services/pdf_report/data_collector.py`
- `backend/market/services/pdf_report/chart_renderer.py`
- `backend/market/services/pdf_report/generator.py`
- `backend/market/services/pdf_report/templates/daily_report.html`
- `backend/core/management/commands/generate_pdf_report.py`
- Task executor in `task_registry.py`, scheduled task in `settings.py`

## Report Sections (6 pages)
1. **Cover + Executive Summary**: Key metrics grid, overall status
2. **Portfolio & Risk**: Equity, drawdown, VaR, equity curve chart, drawdown chart
3. **Strategy Performance**: Per-strategy table, comparison chart, orchestrator state
4. **Market Analysis**: Regime, opportunities, signal scores, regime timeline chart
5. **What Was Learned**: ML accuracy, signal attribution, weight adjustments, radar chart
6. **Historical Performance**: Daily P&L (7 days), weekly summary (4 weeks), P&L bar chart

## Iteration Goals
- v1: Core report with all sections and charts
- v2: Add strategy-specific deep dives, trade-by-trade log
- v3: Add comparison to backtest expectations, drift detection
- v4: Add position-level attribution, execution quality metrics
