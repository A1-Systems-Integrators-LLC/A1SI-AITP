"""PDF report generator — orchestrates data collection, charts, and rendering."""

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
        logger.info("Collecting report data (portfolio=%d, lookback=%dd)", portfolio_id, lookback_days)
        data = PDFReportDataCollector.collect(portfolio_id, lookback_days)

        # 2. Render charts
        logger.info("Rendering charts")
        charts = {}
        try:
            charts["chart_equity_curve"] = ReportChartRenderer.equity_curve(
                data.get("equity_history", [])
            )
        except Exception as e:
            logger.warning("Equity curve chart failed: %s", e)
            charts["chart_equity_curve"] = ""

        try:
            charts["chart_drawdown"] = ReportChartRenderer.drawdown_chart(
                data.get("equity_history", [])
            )
        except Exception as e:
            logger.warning("Drawdown chart failed: %s", e)
            charts["chart_drawdown"] = ""

        try:
            charts["chart_daily_pnl"] = ReportChartRenderer.daily_pnl_bars(
                data.get("daily_pnl_history", [])
            )
        except Exception as e:
            logger.warning("Daily P&L chart failed: %s", e)
            charts["chart_daily_pnl"] = ""

        try:
            charts["chart_strategy_comparison"] = ReportChartRenderer.strategy_comparison(
                data.get("strategy_breakdown", [])
            )
        except Exception as e:
            logger.warning("Strategy comparison chart failed: %s", e)
            charts["chart_strategy_comparison"] = ""

        try:
            charts["chart_regime_timeline"] = ReportChartRenderer.regime_timeline(
                data.get("regime_history", [])
            )
        except Exception as e:
            logger.warning("Regime timeline chart failed: %s", e)
            charts["chart_regime_timeline"] = ""

        try:
            attribution = data.get("attribution", {})
            sources = attribution.get("sources", {})
            charts["chart_signal_radar"] = ReportChartRenderer.signal_source_radar(sources)
        except Exception as e:
            logger.warning("Signal radar chart failed: %s", e)
            charts["chart_signal_radar"] = ""

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
