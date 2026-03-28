"""Market-related task executors: scan, news, daily report, sentiment, calendar, funding rates."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


def _run_market_scan(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Scan pairs for trading opportunities."""
    asset_class = params.get("asset_class", "crypto")
    progress_cb(0.1, f"Scanning {asset_class} market for opportunities")
    try:
        from market.services.market_scanner import MarketScannerService

        scanner = MarketScannerService()
        timeframe = params.get("timeframe", "1h")
        result = scanner.scan_all(timeframe=timeframe, asset_class=asset_class)
        progress_cb(0.9, "Market scan complete")
        return result
    except Exception as e:
        logger.error("Market scan failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_news_fetch(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Fetch latest news for all asset classes."""
    progress_cb(0.1, "Fetching news")
    try:
        from market.services.news import NewsService

        service = NewsService()
        total = 0
        for ac in ("crypto", "equity", "forex"):
            count = service.fetch_and_store(ac)
            total += count

            # Broadcast news + sentiment updates per asset class
            try:
                from core.services.ws_broadcast import (
                    broadcast_news_update,
                    broadcast_sentiment_update,
                )

                summary = service.get_sentiment_summary(ac)
                broadcast_news_update(ac, count, summary)
                broadcast_sentiment_update(
                    asset_class=ac,
                    avg_score=summary.get("avg_score", 0.0),
                    overall_label=summary.get("overall_label", "neutral"),
                    total_articles=summary.get("total_articles", 0),
                )
            except Exception:
                logger.debug("News broadcast failed for %s", ac, exc_info=True)

        return {"status": "completed", "articles_fetched": total}
    except Exception as e:
        logger.warning("News fetch failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_daily_report(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Generate daily intelligence report and send Telegram summary."""
    progress_cb(0.1, "Generating daily report")
    try:
        from market.services.daily_report import DailyReportService

        service = DailyReportService()
        report = service.generate()
        progress_cb(0.9, "Daily report complete")

        # Send Telegram summary
        try:
            from core.services.notification import NotificationService

            regime = report.get("regime", {})
            perf = report.get("strategy_performance", {})
            sys_status = report.get("system_status", {})
            lines = [
                "<b>Daily Intelligence Report</b>",
                f"Regime: {regime.get('dominant_regime', 'unknown')} "
                f"(conf {regime.get('avg_confidence', 0):.0%})",
                f"Orders: {perf.get('total_orders', 0)} | "
                f"Win rate: {perf.get('win_rate', 0):.1f}% | "
                f"P&L: ${perf.get('total_pnl', 0):.2f}",
                f"Paper trading day {sys_status.get('days_paper_trading', 0)}"
                f"/{sys_status.get('min_days_required', 14)}",
            ]
            NotificationService.send_telegram_sync("\n".join(lines))
        except Exception:
            logger.debug("Daily report Telegram send failed", exc_info=True)

        return {"status": "completed", "report": report}
    except Exception as e:
        logger.error("Daily report generation failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_fear_greed_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Refresh Fear & Greed Index data."""
    progress_cb(0.1, "Fetching Fear & Greed Index")
    try:
        from core.platform_bridge import ensure_platform_imports
        ensure_platform_imports()
        from common.market_data.fear_greed import get_fear_greed_signal
        signal = get_fear_greed_signal()
        progress_cb(0.9, f"Fear & Greed: {signal.get('label', 'unknown')}")
        return {"status": "completed", "signal": signal}
    except Exception as e:
        logger.warning("Fear & Greed refresh failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_reddit_sentiment_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Refresh Reddit crypto sentiment data."""
    progress_cb(0.1, "Fetching Reddit sentiment")
    try:
        from core.platform_bridge import ensure_platform_imports
        ensure_platform_imports()
        from common.data_pipeline.reddit_adapter import fetch_reddit_sentiment
        result = fetch_reddit_sentiment()
        progress_cb(0.9, f"Reddit: {result.get('post_count', 0)} posts scored")
        return {"status": "completed", "sentiment": result}
    except Exception as e:
        logger.warning("Reddit sentiment refresh failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_coingecko_trending_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Refresh CoinGecko trending coins + DeFi data."""
    progress_cb(0.1, "Fetching CoinGecko trending + DeFi data")
    try:
        from core.platform_bridge import ensure_platform_imports
        ensure_platform_imports()
        from common.market_data.coingecko import fetch_global_defi_data, fetch_trending_coins
        trending = fetch_trending_coins()
        defi = fetch_global_defi_data()
        progress_cb(0.9, f"Trending: {len(trending or [])} coins")
        return {
            "status": "completed",
            "trending_count": len(trending or []),
            "defi_data": defi,
        }
    except Exception as e:
        logger.warning("CoinGecko trending refresh failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_sentiment_aggregation(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Aggregate sentiment from all sources (Fear & Greed, Reddit, News)."""
    progress_cb(0.1, "Aggregating sentiment sources")
    try:
        from core.platform_bridge import ensure_platform_imports
        ensure_platform_imports()

        results = {}

        # Fear & Greed
        try:
            from common.market_data.fear_greed import get_fear_greed_signal
            results["fear_greed"] = get_fear_greed_signal()
        except Exception as e:
            logger.warning("Fear & Greed aggregation failed: %s", e)
            results["fear_greed"] = {"status": "error", "error": str(e)}

        # Reddit
        try:
            from common.data_pipeline.reddit_adapter import fetch_reddit_sentiment
            results["reddit"] = fetch_reddit_sentiment()
        except Exception as e:
            logger.warning("Reddit aggregation failed: %s", e)
            results["reddit"] = {"status": "error", "error": str(e)}

        progress_cb(0.9, "Sentiment aggregation complete")
        return {"status": "completed", "sources": results}
    except Exception as e:
        logger.error("Sentiment aggregation failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_macro_data_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Refresh FRED macro economic data."""
    progress_cb(0.1, "Fetching FRED macro data")
    try:
        from core.platform_bridge import ensure_platform_imports
        ensure_platform_imports()
        from common.market_data.fred_adapter import fetch_macro_snapshot
        snapshot = fetch_macro_snapshot()
        progress_cb(0.9, f"Macro score: {snapshot.get('macro_score', 'N/A')}")
        return {"status": "completed", "snapshot": snapshot}
    except Exception as e:
        logger.warning("FRED macro data refresh failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_economic_calendar(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Check for upcoming high-impact economic events."""
    progress_cb(0.1, "Checking economic calendar")
    try:
        from core.platform_bridge import ensure_platform_imports
        ensure_platform_imports()
        from common.calendar.economic_events import get_upcoming_events
        events = get_upcoming_events(hours=24)
        progress_cb(0.9, f"Found {len(events)} upcoming events")
        return {"status": "completed", "events": events, "count": len(events)}
    except Exception as e:
        logger.warning("Economic calendar check failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_funding_rate_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Fetch and store funding rates for crypto watchlist.

    Funding rates are only available on exchanges that support perpetual
    swaps (e.g. Bybit, Kraken Futures).  The pipeline will try multiple
    exchanges automatically and log clear warnings when an exchange does
    not support ``fetchFundingRateHistory``.
    """
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    progress_cb(0.1, "Fetching funding rates")

    try:
        from common.data_pipeline.pipeline import (
            PROCESSED_DIR,
            fetch_funding_rates,
            save_funding_rates,
        )

        # Ensure output directory exists before we try to save anything
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

        config = get_platform_config()
        symbols = config.get("data", {}).get("watchlist", [])[:20]

        if not symbols:
            return {"status": "skipped", "reason": "No crypto watchlist configured"}

        fetched = 0
        failed_symbols: list[str] = []
        for i, symbol in enumerate(symbols):
            try:
                rates = fetch_funding_rates(symbol)
                if rates is not None and not rates.empty:
                    save_funding_rates(rates, symbol)
                    fetched += 1
                else:
                    failed_symbols.append(symbol)
            except Exception as e:
                logger.warning("Funding rate fetch failed for %s: %s", symbol, e)
                failed_symbols.append(symbol)
            progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Fetched {i + 1}/{len(symbols)}")

        result: dict[str, Any] = {
            "status": "completed",
            "fetched": fetched,
            "total": len(symbols),
        }
        if fetched == 0:
            result["warning"] = (
                "No funding rate data collected. This is expected if no exchange "
                "in the fallback list has perpetual contracts for the watchlist "
                "symbols. Check logs for per-exchange details."
            )
            logger.warning(
                "Funding rate refresh: 0/%d symbols fetched — verify exchange "
                "support and symbol availability",
                len(symbols),
            )
        if failed_symbols:
            result["failed_symbols"] = failed_symbols[:10]  # cap for readability

        return result
    except Exception as e:
        logger.error("Funding rate refresh failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_signal_feedback(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Backfill signal attribution outcomes and compute source accuracy."""
    progress_cb(0.1, "Backfilling signal attribution outcomes")

    from analysis.services.signal_feedback import SignalFeedbackService

    window_hours = params.get("window_hours", 24)
    backfill_result = SignalFeedbackService.backfill_outcomes(window_hours=window_hours)
    progress_cb(0.5, f"Backfilled {backfill_result.get('resolved', 0)} outcomes")

    # Also backfill from Freqtrade paper trades
    ft_backfill = {"matched": 0, "errors": 0}
    try:
        ft_backfill = SignalFeedbackService.backfill_from_freqtrade(
            window_hours=window_hours,
        )
    except Exception as e:
        logger.error(
            "Freqtrade backfill failed: %s — signal weights will not update from paper trades",
            e,
        )

    accuracy = SignalFeedbackService.get_source_accuracy(
        asset_class=params.get("asset_class"),
        window_days=params.get("window_days", 30),
    )
    progress_cb(0.8, "Computed source accuracy")

    return {
        "status": "completed",
        "backfill": backfill_result,
        "freqtrade_backfill": ft_backfill,
        "accuracy": accuracy,
    }
