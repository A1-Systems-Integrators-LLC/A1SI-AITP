"""Registry mapping task_type strings to executor functions.

Each executor has signature: (params: dict, progress_cb: Callable) -> dict
"""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("scheduler")

ProgressCallback = Callable[[float, str], None]
TaskExecutor = Callable[[dict, ProgressCallback], dict[str, Any]]


def _run_data_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Refresh OHLCV data for an asset class watchlist."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    from common.data_pipeline.pipeline import download_watchlist

    asset_class = params.get("asset_class", "crypto")
    config = get_platform_config()
    data_cfg = config.get("data", {})

    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist configured"}

    # Download all watchlist symbols (no cap — scheduler handles rate limiting)
    timeframe = params.get("timeframe")
    timeframes = [timeframe] if timeframe else None
    tf_label = f" ({timeframe})" if timeframe else ""
    progress_cb(0.1, f"Refreshing {len(symbols)} {asset_class} symbols{tf_label}")
    results = download_watchlist(
        symbols=symbols,
        timeframes=timeframes,
        asset_class=asset_class,
    )
    progress_cb(0.9, "Data refresh complete")

    succeeded = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "ok")
    failed = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "error")
    if failed:
        logger.error(
            "Data refresh: %d/%d symbols failed to download",
            failed,
            len(results),
        )
    return {
        "status": "completed" if succeeded > 0 else "error",
        "symbols": len(symbols),
        "saved": succeeded,
        "failed": failed,
    }


# Track last known regimes for transition detection
_last_known_regimes: dict[str, str] = {}


def _run_regime_detection(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run regime detection for all crypto watchlist symbols."""
    progress_cb(0.1, "Detecting regimes")
    try:
        from market.services.regime import RegimeService

        service = RegimeService()
        regimes = service.get_all_current_regimes()

        # Detect regime transitions and broadcast changes
        try:
            from core.services.ws_broadcast import broadcast_regime_change

            for regime_data in regimes:
                symbol = regime_data.get("symbol", "")
                new_regime = regime_data.get("regime", "unknown")
                prev_regime = _last_known_regimes.get(symbol)
                if prev_regime is not None and prev_regime != new_regime:
                    broadcast_regime_change(
                        symbol=symbol,
                        previous_regime=prev_regime,
                        new_regime=new_regime,
                        confidence=regime_data.get("confidence", 0.0),
                    )
                _last_known_regimes[symbol] = new_regime
        except Exception:
            logger.debug("Regime broadcast failed", exc_info=True)

        return {"status": "completed", "regimes_detected": len(regimes)}
    except Exception as e:
        logger.error("Regime detection failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_order_sync(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Sync open live orders with exchange."""
    from datetime import timedelta

    from asgiref.sync import async_to_sync
    from django.conf import settings
    from django.utils import timezone

    from trading.models import Order, OrderStatus, TradingMode
    from trading.services.live_trading import LiveTradingService

    timeout_hours = getattr(settings, "ORDER_SYNC_TIMEOUT_HOURS", 24)
    cutoff = timezone.now() - timedelta(hours=timeout_hours)

    pending = Order.objects.filter(
        mode=TradingMode.LIVE,
        status__in=[OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL],
    )
    total = pending.count()
    progress_cb(0.0, f"Syncing {total} pending orders")

    if total == 0:
        return {"status": "completed", "synced": 0, "timed_out": 0, "errors": 0, "total": 0}

    synced = 0
    timed_out = 0
    errors = 0

    for i, order in enumerate(pending):
        # Timeout stuck SUBMITTED orders
        if order.status == OrderStatus.SUBMITTED and order.created_at < cutoff:
            try:
                order.transition_to(
                    OrderStatus.ERROR,
                    error_message="Order sync timeout: no exchange confirmation",
                )
            except (ValueError, Exception) as e:
                logger.warning("Transition failed for stuck order %s: %s", order.id, e)
                order.status = OrderStatus.ERROR
                order.error_message = "Order sync timeout: no exchange confirmation"
                order.save(update_fields=["status", "error_message"])
            timed_out += 1
            continue

        try:
            async_to_sync(LiveTradingService.sync_order)(order)
            synced += 1
        except Exception as exc:
            logger.error("Order sync failed for %s: %s", order.id, exc)
            errors += 1

        progress_cb((i + 1) / max(total, 1), f"Synced {i + 1}/{total}")

    return {
        "status": "completed",
        "total": total,
        "synced": synced,
        "timed_out": timed_out,
        "errors": errors,
    }


def _run_data_quality(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run full data quality validation and auto-remediate stale data."""
    from core.platform_bridge import ensure_platform_imports

    ensure_platform_imports()
    progress_cb(0.1, "Checking data quality")
    try:
        from common.data_pipeline.pipeline import validate_all_data

        reports = validate_all_data()
        passed = sum(1 for r in reports if r.passed)
        failed = len(reports) - passed

        summary = {
            "total": len(reports),
            "passed": passed,
            "failed": failed,
            "issues": [],
        }
        for r in reports:
            if not r.passed:
                summary["issues"].append(
                    f"{r.symbol}/{r.timeframe}: {', '.join(r.issues_summary)}",
                )

        # Auto-remediation: refresh stale symbols (capped at 20)
        stale_symbols = []
        for r in reports:
            if r.is_stale and r.symbol:
                stale_symbols.append({
                    "symbol": r.symbol,
                    "timeframe": r.timeframe,
                    "exchange": r.exchange,
                })

        remediated = 0
        if stale_symbols:
            progress_cb(0.5, f"Auto-remediating {min(len(stale_symbols), 20)} stale symbols")
            from common.data_pipeline.pipeline import download_watchlist

            # Group by asset class for efficient download
            stale_by_class: dict[str, list[str]] = {}
            for item in stale_symbols[:20]:  # Cap at 20
                # Infer asset class from exchange
                ac = _infer_asset_class(item["symbol"], item.get("exchange", ""))
                stale_by_class.setdefault(ac, []).append(item["symbol"])

            for ac, symbols in stale_by_class.items():
                try:
                    results = download_watchlist(
                        symbols=symbols,
                        timeframes=None,
                        asset_class=ac,
                    )
                    remediated += sum(
                        1 for v in results.values()
                        if isinstance(v, dict) and v.get("status") == "ok"
                    )
                except Exception as e:
                    logger.warning("Auto-remediation failed for %s: %s", ac, e)

        summary["remediated"] = remediated
        progress_cb(0.9, f"Validated {len(reports)} files, remediated {remediated}")
        return {"status": "completed", "quality_summary": summary}
    except Exception as e:
        logger.error("Data quality check failed: %s", e)
        return {"status": "error", "error": str(e)}


def _infer_asset_class(symbol: str, exchange: str = "") -> str:
    """Infer asset class from symbol format and exchange."""
    if exchange == "yfinance":
        # Forex pairs have / and are currency pairs
        if "/" in symbol and len(symbol.split("/")[0]) == 3 and len(symbol.split("/")[1]) == 3:
            return "forex"
        return "equity"
    if "USDT" in symbol or "USD" in symbol.split("/")[-1:][0] if "/" in symbol else "":
        return "crypto"
    # Default based on symbol format
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
        if base in ("EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF") or quote in (
            "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF",
        ):
            return "forex"
        return "crypto"
    return "equity"


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


def _run_workflow(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Execute a workflow pipeline."""
    from analysis.services.workflow_engine import execute_workflow

    return execute_workflow(params, progress_cb)


def _sync_freqtrade_equity() -> dict[str, Any]:
    """Read Freqtrade profit API and update RiskState equity.

    SAFETY: If no Freqtrade instances respond, we skip the equity update entirely
    to avoid corrupting RiskState with fabricated values (which previously caused
    false drawdown halts).
    """
    import requests
    from django.conf import settings

    ft_urls = [
        getattr(settings, "FREQTRADE_API_URL", ""),
        getattr(settings, "FREQTRADE_BMR_API_URL", ""),
        getattr(settings, "FREQTRADE_VB_API_URL", ""),
    ]
    # Fall back to instance configs if top-level settings not set
    if not any(ft_urls):
        for inst in getattr(settings, "FREQTRADE_INSTANCES", []):
            if not inst.get("enabled", True):
                continue  # Skip disabled (not deployed) instances
            url = inst.get("url", "")
            if url:
                ft_urls.append(url)

    ft_user = getattr(settings, "FREQTRADE_USERNAME", "freqtrader")
    ft_pass = getattr(settings, "FREQTRADE_PASSWORD", "freqtrader")

    total_pnl = 0.0
    instance_results = []
    for url in ft_urls:
        if not url:
            continue
        try:
            resp = requests.get(
                f"{url}/api/v1/profit",
                auth=(ft_user, ft_pass),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            pnl = data.get("profit_all_coin", 0.0)
            total_pnl += pnl
            instance_results.append({"url": url, "pnl": pnl, "status": "ok"})
        except Exception as e:
            logger.warning("Freqtrade equity sync failed for %s: %s", url, e)
            instance_results.append({"url": url, "status": "error", "error": str(e)})

    # Include forex paper trading P&L
    forex_pnl = 0.0
    forex_initial = 0.0
    try:
        from trading.services.forex_paper_trading import ForexPaperTradingService

        forex_profit = ForexPaperTradingService().get_profit()
        forex_pnl = forex_profit.get("profit_all_coin", 0.0) or 0.0
        from trading.models import Order, OrderStatus, TradingMode
        forex_buys = Order.objects.filter(
            asset_class="forex", mode=TradingMode.PAPER, status=OrderStatus.FILLED, side="buy",
        ).values("symbol").distinct().count()
        forex_initial = forex_buys * 1000.0
    except Exception:
        pass

    # ── SAFETY: Count how many Freqtrade instances actually responded ──
    from django.conf import settings as django_settings

    ft_instances = getattr(django_settings, "FREQTRADE_INSTANCES", [])
    url_to_wallet: dict[str, float] = {}
    for inst in ft_instances:
        inst_url = inst.get("url", "")
        if inst_url:
            url_to_wallet[inst_url] = inst.get("dry_run_wallet", 0)

    successful = [r for r in instance_results if r.get("status") == "ok"]
    total_urls = len([u for u in ft_urls if u])

    # If NO Freqtrade instances responded, skip equity update entirely.
    # This prevents fabricating equity from zero wallets and triggering false halts.
    if not successful and total_urls > 0 and forex_initial <= 0:
        logger.warning(
            "Freqtrade equity sync: 0/%d instances responded, no forex capital — "
            "SKIPPING equity update to prevent corruption",
            total_urls,
        )
        return {
            "total_pnl": 0.0,
            "forex_pnl": forex_pnl,
            "equity_updated": False,
            "skipped_reason": "no_instances_responding",
            "instances": instance_results,
            "open_positions_count": 0,
        }

    live_wallet_total = sum(
        url_to_wallet.get(r["url"], 0) for r in successful
    )
    initial_capital = live_wallet_total + forex_initial

    # If computed initial capital is zero (no wallets matched, no forex),
    # skip update to avoid division-by-zero and false drawdown calculations.
    if initial_capital <= 0:
        logger.error(
            "Freqtrade equity sync: initial_capital=%.2f (wallet=%.2f, forex=%.2f) — "
            "skipping update to prevent corruption",
            initial_capital, live_wallet_total, forex_initial,
        )
        return {
            "total_pnl": total_pnl,
            "forex_pnl": forex_pnl,
            "equity_updated": False,
            "skipped_reason": "zero_initial_capital",
            "instances": instance_results,
            "open_positions_count": 0,
        }

    current_equity = initial_capital + total_pnl + forex_pnl

    from portfolio.models import Portfolio
    from risk.models import RiskState
    from risk.services.risk import RiskManagementService

    # Sync open positions from Freqtrade instances
    open_positions: dict[str, dict] = {}
    for url in ft_urls:
        if not url:
            continue
        try:
            resp = requests.get(
                f"{url}/api/v1/status",
                auth=(ft_user, ft_pass),
                timeout=10,
            )
            if resp.status_code == 200:
                trades = resp.json()
                for trade in trades:
                    pair = trade.get("pair", "")
                    if pair:
                        open_positions[pair] = {
                            "side": "buy",
                            "size": trade.get("amount", 0),
                            "entry_price": trade.get("open_rate", 0),
                            "value": trade.get("stake_amount", 0),
                        }
        except Exception as e:
            logger.debug("Failed to fetch open trades from %s: %s", url, e)

    # Only update the first crypto portfolio — equity/forex have separate tracking.
    # Previously iterated all portfolios, applying the same equity to each,
    # which would corrupt drawdown calculations in multi-portfolio scenarios.
    portfolios = Portfolio.objects.filter(asset_class="crypto")
    if not portfolios.exists():
        portfolios = Portfolio.objects.all()

    portfolio = portfolios.first()
    equity_updated = False

    if portfolio is not None:
        # ── EQUITY SWING GUARD: reject updates that change equity by >50% ──
        # This catches data errors (e.g. partial instance responses) before they
        # corrupt the risk state and trigger false halts.
        swing_blocked = False
        try:
            state = RiskState.objects.get(portfolio_id=portfolio.id)
            if state.total_equity > 0:
                delta_pct = abs(current_equity - state.total_equity) / state.total_equity
                if delta_pct > 0.50:
                    logger.error(
                        "Equity swing guard: new=$%.2f, current=$%.2f, delta=%.0f%% — "
                        "skipping update for portfolio %s",
                        current_equity, state.total_equity, delta_pct * 100, portfolio.id,
                    )
                    swing_blocked = True
        except RiskState.DoesNotExist:
            pass

        if not swing_blocked:
            RiskManagementService.update_equity(portfolio.id, current_equity)
            equity_updated = True
            # Also update daily_pnl and open_positions
            try:
                state = RiskState.objects.get(portfolio_id=portfolio.id)
                state.daily_pnl = current_equity - state.daily_start_equity
                state.open_positions = open_positions
                state.save(update_fields=["daily_pnl", "open_positions"])
            except RiskState.DoesNotExist:
                pass

    # Feed open position prices into the singleton ReturnTracker for VaR/correlation
    if open_positions:
        prices = {
            sym: pos.get("entry_price", 0)
            for sym, pos in open_positions.items()
            if pos.get("entry_price")
        }
        if prices:
            RiskManagementService.record_prices(prices)

    return {
        "total_pnl": total_pnl,
        "forex_pnl": forex_pnl,
        "equity_updated": equity_updated,
        "current_equity": current_equity,
        "initial_capital": initial_capital,
        "instances": instance_results,
        "open_positions_count": len(open_positions),
    }


def _run_daily_risk_reset(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Reset daily P&L counters for all portfolios.

    Should run once per day (midnight UTC) to prevent stale daily_pnl accumulation.
    """
    from portfolio.models import Portfolio
    from risk.services.risk import RiskManagementService

    progress_cb(0.1, "Resetting daily risk counters")
    portfolios = list(Portfolio.objects.values_list("id", flat=True))

    if not portfolios:
        return {"status": "completed", "message": "No portfolios", "reset_count": 0}

    reset_count = 0
    for i, pid in enumerate(portfolios):
        try:
            RiskManagementService.reset_daily(pid)
            reset_count += 1
            logger.info("Daily risk reset completed for portfolio %s", pid)
        except Exception as e:
            logger.error("Daily risk reset failed for portfolio %s: %s", pid, e)
        progress_cb(0.1 + 0.8 * (i + 1) / len(portfolios), f"Reset {i + 1}/{len(portfolios)}")

    progress_cb(0.9, f"Reset {reset_count} portfolios")
    return {"status": "completed", "reset_count": reset_count, "total_portfolios": len(portfolios)}


def _run_risk_monitoring(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run periodic risk monitoring across all portfolios."""
    # Sync Freqtrade equity before risk checks
    progress_cb(0.1, "Syncing Freqtrade equity")
    sync_result = None
    try:
        sync_result = _sync_freqtrade_equity()
        logger.info("Equity synced: total_pnl=$%.2f", sync_result.get("total_pnl", 0))
    except Exception as e:
        logger.error("Freqtrade equity sync failed: %s", e)

    progress_cb(0.3, "Checking portfolio risk")
    try:
        from portfolio.models import Portfolio
        from risk.services.risk import RiskManagementService

        portfolios = list(Portfolio.objects.values_list("id", flat=True))
        if not portfolios:
            return {"status": "completed", "message": "No portfolios", "equity_sync": sync_result}

        results = []
        for i, pid in enumerate(portfolios):
            try:
                result = RiskManagementService.periodic_risk_check(pid)
                results.append(result)
            except Exception as e:
                logger.error("Risk check failed for portfolio %s: %s", pid, e)
                results.append({"portfolio_id": pid, "status": "error", "error": str(e)})
            progress_cb(0.3 + 0.6 * (i + 1) / len(portfolios), f"Checked portfolio {pid}")

        return {
            "status": "completed",
            "portfolios_checked": len(portfolios),
            "results": results,
            "equity_sync": sync_result,
        }
    except Exception as e:
        logger.error("Risk monitoring failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_db_maintenance(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run SQLite maintenance: integrity check and optimize.

    No WAL checkpoint needed — using DELETE journal mode (not WAL)
    because WAL is incompatible with Docker virtiofs bind mounts.
    """
    from django.db import connection

    progress_cb(0.1, "Running integrity check")
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
    progress_cb(0.9, "Maintenance complete")
    return {"status": "completed", "integrity": result, "journal_mode": mode}


def _run_vbt_screen(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run VectorBT strategy screen on watchlist symbols."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    asset_class = params.get("asset_class", "crypto")
    timeframe = params.get("timeframe", "1h")
    config = get_platform_config()
    data_cfg = config.get("data", {})

    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist configured"}

    progress_cb(0.1, f"Screening {len(symbols)} {asset_class} symbols")
    results = []
    for i, symbol in enumerate(symbols):
        try:
            from analysis.services.screening import ScreenerService

            default_exchange = "yfinance" if asset_class in ("equity", "forex") else "kraken"
            screen_params = {
                "symbol": symbol,
                "timeframe": "1d" if asset_class in ("equity", "forex") else timeframe,
                "exchange": params.get("exchange", default_exchange),
                "asset_class": asset_class,
            }
            result = ScreenerService.run_full_screen(
                screen_params,
                lambda p, m, _i=i: progress_cb(0.1 + 0.8 * (_i + p) / len(symbols), m),
            )
            results.append({"symbol": symbol, "status": "completed", "result": result})
        except Exception as e:
            logger.warning("VBT screen failed for %s: %s", symbol, e)
            results.append({"symbol": symbol, "status": "error", "error": str(e)})
        progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Screened {i + 1}/{len(symbols)}")

    return {"status": "completed", "symbols_screened": len(results), "results": results}


def _run_ml_training(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Train ML models on OHLCV data for specified symbols."""
    progress_cb(0.1, "Starting ML training")
    symbols = params.get("symbols", [params.get("symbol", "BTC/USDT")])
    if isinstance(symbols, str):
        symbols = [symbols]
    timeframe = params.get("timeframe", "1h")

    results = []
    for i, symbol in enumerate(symbols):
        try:
            from analysis.services.ml import MLService

            train_params = {
                "symbol": symbol,
                "timeframe": timeframe,
                "exchange": params.get("exchange", "kraken"),
                "test_ratio": params.get("test_ratio", 0.2),
            }
            result = MLService.train(
                train_params,
                lambda p, m, _i=i: progress_cb(0.1 + 0.8 * (_i + p) / len(symbols), m),
            )
            results.append({"symbol": symbol, **result})
        except Exception as e:
            logger.warning("ML training failed for %s: %s", symbol, e)
            results.append({"symbol": symbol, "status": "error", "error": str(e)})
        progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Trained {i + 1}/{len(symbols)}")

    return {"status": "completed", "models_trained": len(results), "results": results}


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


def _run_forex_paper_trading(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run forex paper trading cycle — entries and exits from scanner signals."""
    progress_cb(0.1, "Running forex paper trading cycle")
    try:
        from trading.services.forex_paper_trading import ForexPaperTradingService

        service = ForexPaperTradingService()
        result = service.run_cycle()
        progress_cb(0.9, "Forex paper trading cycle complete")
        return result
    except Exception as e:
        logger.error("Forex paper trading cycle failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_nautilus_backtest(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run NautilusTrader backtests across configured strategies for an asset class."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    asset_class = params.get("asset_class", "crypto")
    timeframe = params.get("timeframe", "1h")
    exchange = params.get("exchange", "kraken")
    initial_balance = params.get("initial_balance", 10000.0)

    try:
        from nautilus.nautilus_runner import list_nautilus_strategies, run_nautilus_backtest
    except ImportError as e:
        return {"status": "error", "error": f"NautilusTrader not available: {e}"}

    # Map asset class to strategy subset
    strategy_map = {
        "crypto": ["NautilusTrendFollowing", "NautilusMeanReversion", "NautilusVolatilityBreakout"],
        "equity": ["EquityMomentum", "EquityMeanReversion"],
        "forex": ["ForexTrend", "ForexRange"],
    }
    strategies = params.get("strategies") or strategy_map.get(asset_class, [])
    available = list_nautilus_strategies()
    strategies = [s for s in strategies if s in available]

    if not strategies:
        return {"status": "skipped", "reason": f"No Nautilus strategies for {asset_class}"}

    # Get symbols from watchlist
    config = get_platform_config()
    data_cfg = config.get("data", {})
    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])[:3]  # Top 3 symbols per run

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist configured"}

    progress_cb(
        0.1,
        f"Running {len(strategies)} Nautilus strategies on {len(symbols)} {asset_class} symbols",
    )
    results = []
    total_steps = len(strategies) * len(symbols)
    step = 0

    for strategy in strategies:
        for symbol in symbols:
            step += 1
            try:
                result = run_nautilus_backtest(
                    strategy,
                    symbol,
                    timeframe,
                    exchange,
                    initial_balance,
                    asset_class=asset_class,
                )
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "completed",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.warning("Nautilus backtest failed %s/%s: %s", strategy, symbol, e)
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "error",
                        "error": str(e),
                    }
                )
            progress_cb(0.1 + 0.8 * step / total_steps, f"{strategy} on {symbol}")

    completed = sum(1 for r in results if r["status"] == "completed")
    progress_cb(0.95, f"Nautilus backtests done: {completed}/{len(results)}")
    return {
        "status": "completed",
        "framework": "nautilus",
        "asset_class": asset_class,
        "strategies_run": len(strategies),
        "symbols_tested": len(symbols),
        "total_backtests": len(results),
        "completed": completed,
        "results": results,
    }


def _run_hft_backtest(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run HFT backtests across configured strategies."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    exchange = params.get("exchange", "kraken")
    initial_balance = params.get("initial_balance", 10000.0)
    latency_ns = params.get("latency_ns", 1_000_000)

    try:
        from hftbacktest.hft_runner import list_hft_strategies, run_hft_backtest
    except ImportError as e:
        return {"status": "error", "error": f"hftbacktest not available: {e}"}

    strategies = params.get("strategies") or list_hft_strategies()
    if not strategies:
        return {"status": "skipped", "reason": "No HFT strategies available"}

    # HFT is crypto-only, use top crypto symbols
    config = get_platform_config()
    symbols = config.get("data", {}).get("watchlist", [])[:3]
    timeframe = params.get("timeframe", "1h")

    if not symbols:
        return {"status": "skipped", "reason": "No crypto watchlist configured"}

    progress_cb(0.1, f"Running {len(strategies)} HFT strategies on {len(symbols)} symbols")
    results = []
    total_steps = len(strategies) * len(symbols)
    step = 0

    for strategy in strategies:
        for symbol in symbols:
            step += 1
            try:
                result = run_hft_backtest(
                    strategy,
                    symbol,
                    timeframe,
                    exchange,
                    latency_ns,
                    initial_balance,
                )
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "completed",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.warning("HFT backtest failed %s/%s: %s", strategy, symbol, e)
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "error",
                        "error": str(e),
                    }
                )
            progress_cb(0.1 + 0.8 * step / total_steps, f"{strategy} on {symbol}")

    completed = sum(1 for r in results if r["status"] == "completed")
    progress_cb(0.95, f"HFT backtests done: {completed}/{len(results)}")
    return {
        "status": "completed",
        "framework": "hftbacktest",
        "strategies_run": len(strategies),
        "symbols_tested": len(symbols),
        "total_backtests": len(results),
        "completed": completed,
        "results": results,
    }


def _run_ml_predict(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Batch ML predictions for watchlist symbols, store MLPrediction records."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    progress_cb(0.1, "Starting ML predictions")
    asset_class = params.get("asset_class", "crypto")

    ensure_platform_imports()
    config = get_platform_config()
    data_cfg = config.get("data", {})
    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])[:20]

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist"}

    results = []
    for i, symbol in enumerate(symbols):
        try:
            from analysis.services.signal_service import SignalService

            ml_prob, ml_conf = SignalService._get_ml_prediction(symbol, asset_class)
            if ml_prob is not None:
                from analysis.models import MLPrediction

                direction = "up" if ml_prob >= 0.5 else "down"
                regime_state = SignalService._get_regime_state(symbol, asset_class)
                regime_name = regime_state.regime.value if regime_state else ""

                MLPrediction.objects.create(
                    model_id=params.get("model_id", "auto"),
                    symbol=symbol,
                    asset_class=asset_class,
                    probability=ml_prob,
                    confidence=ml_conf or 0.0,
                    direction=direction,
                    regime=regime_name,
                )
                results.append({"symbol": symbol, "status": "predicted", "probability": ml_prob})
            else:
                results.append({"symbol": symbol, "status": "no_model"})
        except Exception as e:
            logger.warning("ML predict failed for %s: %s", symbol, e)
            results.append({"symbol": symbol, "status": "error", "error": str(e)})
        progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Predicted {i + 1}/{len(symbols)}")

    predicted = sum(1 for r in results if r["status"] == "predicted")
    return {
        "status": "completed",
        "predicted": predicted,
        "total": len(results),
        "results": results,
    }


def _run_ml_feedback(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Backfill prediction outcomes and update model performance metrics."""
    from django.utils import timezone as tz

    progress_cb(0.1, "Backfilling ML prediction outcomes")

    # Find predictions without outcomes (up to 24h old)
    from datetime import timedelta

    from analysis.models import MLModelPerformance, MLPrediction

    cutoff = tz.now() - timedelta(hours=24)
    unresolved = MLPrediction.objects.filter(
        correct__isnull=True,
        predicted_at__gte=cutoff,
    )[:200]

    filled = 0
    for pred in unresolved:
        try:
            from core.platform_bridge import ensure_platform_imports

            ensure_platform_imports()
            from common.data_pipeline.pipeline import load_ohlcv

            exchange_id = {
                "equity": "yfinance",
                "forex": "yfinance",
            }.get(pred.asset_class, "kraken")
            df = load_ohlcv(pred.symbol, "1h", exchange_id=exchange_id)
            if df is not None and len(df) >= 4:
                last_close = float(df["close"].iloc[-1])
                prev_close = float(df["close"].iloc[-4])
                actual = "up" if last_close >= prev_close else "down"
                pred.actual_direction = actual
                pred.correct = pred.direction == actual
                pred.save(update_fields=["actual_direction", "correct"])
                filled += 1
        except Exception as e:
            logger.warning("Feedback backfill failed for %s: %s", pred.symbol, e)

    progress_cb(0.5, f"Backfilled {filled} outcomes")

    # Update model performance aggregates
    model_ids = (
        MLPrediction.objects.filter(
            correct__isnull=False,
        )
        .values_list("model_id", flat=True)
        .distinct()[:50]
    )

    updated = 0
    for model_id in model_ids:
        preds = MLPrediction.objects.filter(model_id=model_id, correct__isnull=False)
        total = preds.count()
        correct = preds.filter(correct=True).count()
        accuracy = correct / total if total > 0 else 0.0

        # Accuracy by regime
        regime_acc = {}
        for regime_name in preds.values_list("regime", flat=True).distinct():
            if not regime_name:
                continue
            r_preds = preds.filter(regime=regime_name)
            r_total = r_preds.count()
            r_correct = r_preds.filter(correct=True).count()
            regime_acc[regime_name] = round(r_correct / r_total, 3) if r_total > 0 else 0.0

        perf, _ = MLModelPerformance.objects.update_or_create(
            model_id=model_id,
            defaults={
                "total_predictions": total,
                "correct_predictions": correct,
                "rolling_accuracy": round(accuracy, 4),
                "accuracy_by_regime": regime_acc,
                "retrain_recommended": total >= 50 and accuracy < 0.52,
            },
        )
        updated += 1

    progress_cb(0.9, f"Updated {updated} model performance records")
    return {"status": "completed", "outcomes_filled": filled, "models_updated": updated}


def _run_ml_retrain(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Retrain ML models flagged by the feedback loop."""
    from analysis.models import MLModelPerformance

    progress_cb(0.1, "Checking for models needing retraining")
    flagged = list(
        MLModelPerformance.objects.filter(
            retrain_recommended=True,
        ).values_list("model_id", flat=True),
    )

    if not flagged:
        return {"status": "completed", "retrained": 0, "reason": "No models flagged for retraining"}

    retrained = 0
    for i, model_id in enumerate(flagged[:5]):  # Max 5 retrains per run
        try:
            from analysis.services.ml import MLService

            # Extract symbol from model_id pattern (symbol_timeframe_exchange_timestamp)
            parts = model_id.split("_")
            symbol = parts[0] if parts else "BTC/USDT"
            timeframe = parts[1] if len(parts) > 1 else "1h"
            exchange = parts[2] if len(parts) > 2 else "kraken"

            train_params = {
                "symbol": symbol,
                "timeframe": timeframe,
                "exchange": exchange,
                "test_ratio": 0.2,
            }
            MLService.train(
                train_params,
                lambda p, m, _i=i: progress_cb(
                    0.1 + 0.8 * (_i + p) / len(flagged),
                    m,
                ),
            )
            # Clear retrain flag
            MLModelPerformance.objects.filter(model_id=model_id).update(
                retrain_recommended=False,
            )
            retrained += 1
        except Exception as e:
            logger.warning("ML retrain failed for %s: %s", model_id, e)
        progress_cb(0.1 + 0.8 * (i + 1) / len(flagged), f"Retrained {i + 1}/{len(flagged)}")

    return {"status": "completed", "retrained": retrained, "flagged": len(flagged)}


def _run_conviction_audit(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Log conviction scores and compute rolling accuracy for audit."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    progress_cb(0.1, "Running conviction audit")
    asset_class = params.get("asset_class", "crypto")

    ensure_platform_imports()
    config = get_platform_config()
    data_cfg = config.get("data", {})
    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])[:10]

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist"}

    audit_results = []
    for i, symbol in enumerate(symbols):
        try:
            from analysis.services.signal_service import SignalService

            signal = SignalService.get_signal(symbol, asset_class)
            audit_results.append(
                {
                    "symbol": symbol,
                    "score": signal["composite_score"],
                    "label": signal["signal_label"],
                    "approved": signal["entry_approved"],
                    "sources": signal["sources_available"],
                }
            )
        except Exception as e:
            logger.warning("Conviction audit failed for %s: %s", symbol, e)
            audit_results.append({"symbol": symbol, "error": str(e)})
        progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Audited {i + 1}/{len(symbols)}")

    avg_score = 0.0
    scored = [r for r in audit_results if "score" in r]
    if scored:
        avg_score = sum(r["score"] for r in scored) / len(scored)

    return {
        "status": "completed",
        "asset_class": asset_class,
        "symbols_audited": len(audit_results),
        "average_score": round(avg_score, 1),
        "results": audit_results,
    }


def _run_strategy_orchestration(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Check regime alignment for all strategies and set pause/active flags.

    Delegates to StrategyOrchestrator service which persists state,
    logs transitions to AlertLog, broadcasts via WS, and notifies Telegram.
    """
    from trading.services.strategy_orchestrator import StrategyOrchestrator

    progress_cb(0.1, "Evaluating strategy-regime alignment")

    asset_classes = params.get("asset_classes", ["crypto", "equity", "forex"])
    orchestrator = StrategyOrchestrator.get_instance()
    all_results = orchestrator.evaluate(asset_classes=asset_classes)

    progress_cb(0.9, "Evaluation complete")

    paused = sum(1 for r in all_results if r["action"] == "pause")
    transitioned = sum(1 for r in all_results if r.get("transitioned", False))
    return {
        "status": "completed",
        "strategies_evaluated": len(all_results),
        "paused": paused,
        "transitioned": transitioned,
        "results": all_results,
    }


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
        logger.warning("Freqtrade backfill failed: %s", e)

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


def _run_adaptive_weighting(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Compute and log adaptive weight recommendations."""
    progress_cb(0.1, "Computing adaptive weight recommendations")

    from analysis.services.signal_feedback import SignalFeedbackService

    asset_class = params.get("asset_class")
    strategy = params.get("strategy")
    window_days = params.get("window_days", 30)

    result = SignalFeedbackService.get_weight_recommendations(
        asset_class=asset_class,
        strategy=strategy,
        window_days=window_days,
    )

    progress_cb(0.9, "Weight recommendations computed")

    if "error" in result:
        return {"status": "failed", "error": result["error"]}

    logger.info(
        "Adaptive weights: win_rate=%.2f threshold_adj=%d recommended=%s",
        result.get("win_rate", 0),
        result.get("threshold_adjustment", 0),
        result.get("recommended_weights", {}),
    )

    # Apply recommended weights to DEFAULT_WEIGHTS so they take effect
    recommended = result.get("recommended_weights", {})
    if recommended and result.get("total_trades", 0) >= 10:
        try:
            from core.platform_bridge import ensure_platform_imports
            ensure_platform_imports()
            from common.signals.constants import DEFAULT_WEIGHTS

            for source, weight in recommended.items():
                if source in DEFAULT_WEIGHTS:
                    DEFAULT_WEIGHTS[source] = weight
            logger.info("Applied adaptive weights to DEFAULT_WEIGHTS: %s", recommended)
        except Exception as e:
            logger.warning("Failed to apply adaptive weights: %s", e)

    return {
        "status": "completed",
        "win_rate": result.get("win_rate"),
        "threshold_adjustment": result.get("threshold_adjustment"),
        "recommended_weights": result.get("recommended_weights"),
        "reasoning": result.get("reasoning"),
        "applied": bool(recommended and result.get("total_trades", 0) >= 10),
    }


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
    """Fetch and store funding rates for crypto watchlist."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    progress_cb(0.1, "Fetching funding rates")

    try:
        from common.data_pipeline.pipeline import fetch_funding_rates, save_funding_rates

        config = get_platform_config()
        symbols = config.get("data", {}).get("watchlist", [])[:20]

        if not symbols:
            return {"status": "skipped", "reason": "No crypto watchlist"}

        fetched = 0
        for i, symbol in enumerate(symbols):
            try:
                rates = fetch_funding_rates(symbol)
                if rates is not None and not rates.empty:
                    save_funding_rates(rates, symbol)
                    fetched += 1
            except Exception as e:
                logger.warning("Funding rate fetch failed for %s: %s", symbol, e)
            progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Fetched {i + 1}/{len(symbols)}")

        return {"status": "completed", "fetched": fetched, "total": len(symbols)}
    except Exception as e:
        logger.error("Funding rate refresh failed: %s", e)
        return {"status": "error", "error": str(e)}


TASK_REGISTRY: dict[str, TaskExecutor] = {
    "data_refresh": _run_data_refresh,
    "regime_detection": _run_regime_detection,
    "order_sync": _run_order_sync,
    "data_quality": _run_data_quality,
    "news_fetch": _run_news_fetch,
    "workflow": _run_workflow,
    "risk_monitoring": _run_risk_monitoring,
    "db_maintenance": _run_db_maintenance,
    "vbt_screen": _run_vbt_screen,
    "ml_training": _run_ml_training,
    "market_scan": _run_market_scan,
    "daily_report": _run_daily_report,
    "forex_paper_trading": _run_forex_paper_trading,
    "nautilus_backtest": _run_nautilus_backtest,
    "hft_backtest": _run_hft_backtest,
    "ml_predict": _run_ml_predict,
    "ml_feedback": _run_ml_feedback,
    "ml_retrain": _run_ml_retrain,
    "conviction_audit": _run_conviction_audit,
    "strategy_orchestration": _run_strategy_orchestration,
    "signal_feedback": _run_signal_feedback,
    "adaptive_weighting": _run_adaptive_weighting,
    "economic_calendar": _run_economic_calendar,
    "funding_rate_refresh": _run_funding_rate_refresh,
    "fear_greed_refresh": _run_fear_greed_refresh,
    "reddit_sentiment_refresh": _run_reddit_sentiment_refresh,
    "coingecko_trending_refresh": _run_coingecko_trending_refresh,
    "macro_data_refresh": _run_macro_data_refresh,
    "daily_risk_reset": _run_daily_risk_reset,
}
