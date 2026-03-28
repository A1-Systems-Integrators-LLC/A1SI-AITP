"""Data-related task executors: data refresh, data quality, incremental download."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


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
