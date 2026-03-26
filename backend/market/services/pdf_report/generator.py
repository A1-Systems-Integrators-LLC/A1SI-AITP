"""PDF report generator — orchestrates data collection, charts, and rendering.

Enhanced version: produces a comprehensive daily intelligence report with
team assessments, decision logs, market intelligence, lessons learned,
and improvement recommendations. Light/print-friendly theme.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Output directory for generated reports
REPORTS_DIR = Path(__file__).resolve().parents[3] / "data" / "reports"
MAX_REPORTS_KEPT = 30


class PDFReportGenerator:
    """Orchestrate data collection, chart rendering, and PDF generation."""

    @staticmethod
    def generate(
        portfolio_id: int = 1,
        output_dir: str | None = None,
        lookback_days: int = 30,
    ) -> Path:
        """Generate the daily PDF report.

        Returns the Path to the generated PDF file.
        """
        from market.services.pdf_report.chart_renderer import ReportChartRenderer
        from market.services.pdf_report.data_collector import PDFReportDataCollector

        out = Path(output_dir) if output_dir else REPORTS_DIR
        out.mkdir(parents=True, exist_ok=True)

        # 1. Collect data
        logger.info(
            "Collecting report data (portfolio=%d, lookback=%dd)",
            portfolio_id, lookback_days,
        )
        data = PDFReportDataCollector.collect(portfolio_id, lookback_days)

        # 2. Render charts
        logger.info("Rendering charts")
        charts = {}

        # Existing charts
        charts["chart_equity_curve"] = _render_chart(
            ReportChartRenderer.equity_curve, data.get("equity_history", []),
        )
        charts["chart_drawdown"] = _render_chart(
            ReportChartRenderer.drawdown_chart, data.get("equity_history", []),
        )
        charts["chart_daily_pnl"] = _render_chart(
            ReportChartRenderer.daily_pnl_bars, data.get("daily_pnl_history", []),
        )
        charts["chart_strategy_comparison"] = _render_chart(
            ReportChartRenderer.strategy_comparison, data.get("strategy_breakdown", []),
        )
        charts["chart_regime_timeline"] = _render_chart(
            ReportChartRenderer.regime_timeline, data.get("regime_history", []),
        )

        # Signal radar
        try:
            attribution = data.get("attribution", {})
            sources = attribution.get("sources", {})
            charts["chart_signal_radar"] = ReportChartRenderer.signal_source_radar(sources)
        except Exception as e:
            logger.warning("Signal radar chart failed: %s", e)
            charts["chart_signal_radar"] = ""

        # NEW: Sentiment trend chart
        charts["chart_sentiment_trend"] = _render_chart(
            ReportChartRenderer.sentiment_trend, data.get("sentiment_history", []),
        )

        # NEW: Team assessment summary chart
        charts["chart_team_assessment"] = _render_chart(
            ReportChartRenderer.team_assessment_summary, data.get("team_assessments", {}),
        )

        # NEW: Weight comparison chart
        charts["chart_weight_comparison"] = _render_chart(
            ReportChartRenderer.weight_comparison, data.get("weights", {}),
        )

        # 3. Render HTML template
        logger.info("Rendering HTML template")
        now = datetime.now(timezone.utc)
        report_date = now.strftime("%B %d, %Y")

        template_vars = {
            **data,
            **charts,
            "report_date": report_date,
            "generated_at": now.isoformat(),
        }

        html_content = _render_template(template_vars)

        # 4. Convert to PDF
        logger.info("Converting HTML to PDF via WeasyPrint")
        filename = f"daily_report_{now.strftime('%Y-%m-%d')}.pdf"
        pdf_path = out / filename

        import weasyprint

        doc = weasyprint.HTML(string=html_content)
        doc.write_pdf(str(pdf_path))

        size_kb = pdf_path.stat().st_size / 1024
        logger.info("PDF report generated: %s (%.1f KB)", pdf_path, size_kb)

        # 5. Cleanup old reports
        _cleanup_old_reports(out, MAX_REPORTS_KEPT)

        return pdf_path


def _render_chart(renderer_fn: callable, data: object) -> str:
    """Safely render a chart, returning empty string on failure."""
    try:
        return renderer_fn(data)
    except Exception as e:
        logger.warning("Chart render failed (%s): %s", renderer_fn.__name__, e)
        return ""


def _render_template(context: dict) -> str:
    """Render the Jinja2 HTML template with the given context."""
    from jinja2 import Environment, FileSystemLoader

    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("daily_report.html")
    return template.render(**context)


def _cleanup_old_reports(directory: Path, keep: int) -> None:
    """Remove old PDF reports beyond the retention limit."""
    pdfs = sorted(directory.glob("daily_report_*.pdf"), key=lambda p: p.stat().st_mtime)
    to_delete = pdfs[:-keep] if len(pdfs) > keep else []
    for old_pdf in to_delete:
        try:
            old_pdf.unlink()
            logger.debug("Deleted old report: %s", old_pdf.name)
        except OSError:
            pass
