"""Step executor registry for workflow pipelines.

Re-exports existing task executors + workflow-specific step executors.
Each step has signature: (params: dict, progress_cb: Callable) -> dict
"""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("workflow")

ProgressCallback = Callable[[float, str], None]
StepExecutor = Callable[[dict, ProgressCallback], dict[str, Any]]


# ── Re-exports from task_registry ────────────────────────────

def _step_data_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    from core.services.task_registry import _run_data_refresh
    return _run_data_refresh(params, progress_cb)


def _step_regime_detection(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    from core.services.task_registry import _run_regime_detection
    return _run_regime_detection(params, progress_cb)


def _step_news_fetch(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    from core.services.task_registry import _run_news_fetch
    return _run_news_fetch(params, progress_cb)


def _step_data_quality(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    from core.services.task_registry import _run_data_quality
    return _run_data_quality(params, progress_cb)


def _step_order_sync(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    from core.services.task_registry import _run_order_sync
    return _run_order_sync(params, progress_cb)


# ── Workflow-specific steps ──────────────────────────────────

def _step_vbt_screen(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run VectorBT screen on specified or default symbols."""
    progress_cb(0.1, "Running VectorBT screen")
    try:
        from analysis.services.screening import ScreenerService

        screen_params = {
            "symbol": params.get("symbol", "BTC/USDT"),
            "timeframe": params.get("timeframe", "1h"),
            "exchange": params.get("exchange", "kraken"),
            "fees": params.get("fees", 0.001),
            "asset_class": params.get("asset_class", "crypto"),
        }
        result = ScreenerService.run_full_screen(screen_params, progress_cb)
        return {"status": "completed", "screen_result": result}
    except Exception as e:
        logger.warning("VBT screen step failed: %s", e)
        return {"status": "error", "error": str(e)}


def _step_sentiment_aggregate(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Aggregate sentiment scores for asset class."""
    progress_cb(0.1, "Aggregating sentiment")
    try:
        from market.services.news import NewsService

        asset_class = params.get("asset_class", "crypto")
        service = NewsService()
        signal = service.get_sentiment_signal(asset_class)
        summary = service.get_sentiment_summary(asset_class)
        return {
            "status": "completed",
            "signal": signal,
            "summary": summary,
        }
    except Exception as e:
        logger.warning("Sentiment aggregation failed: %s", e)
        return {"status": "error", "error": str(e)}


def _step_composite_score(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Combine regime + sentiment into weighted composite score."""
    progress_cb(0.1, "Computing composite score")
    try:
        prev_result = params.get("_prev_result", {})
        signal_data = prev_result.get("signal", {})
        sentiment_signal = signal_data.get("signal", 0.0)
        sentiment_conviction = signal_data.get("conviction", 0.0)

        # Get regime data
        from market.services.regime import RegimeService

        service = RegimeService()
        regimes = service.get_all_current_regimes()

        # Composite: 60% regime, 40% sentiment
        regime_score = 0.0
        if regimes:
            # Map regime confidence to a score
            scores = []
            for r in regimes:
                conf = r.get("confidence", 0.0)
                regime_name = r.get("regime", "unknown")
                # Positive for bullish regimes, negative for bearish
                if "up" in regime_name:
                    scores.append(conf)
                elif "down" in regime_name:
                    scores.append(-conf)
                else:
                    scores.append(0.0)
            regime_score = sum(scores) / len(scores) if scores else 0.0

        composite = regime_score * 0.6 + sentiment_signal * 0.4
        composite = max(-1.0, min(1.0, composite))

        return {
            "status": "completed",
            "composite_score": round(composite, 4),
            "regime_component": round(regime_score, 4),
            "sentiment_component": round(sentiment_signal, 4),
            "sentiment_conviction": round(sentiment_conviction, 4),
            "regime_count": len(regimes),
        }
    except Exception as e:
        logger.warning("Composite score step failed: %s", e)
        return {"status": "error", "error": str(e)}


def _step_alert_evaluate(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Evaluate thresholds and send notifications if crossed."""
    progress_cb(0.1, "Evaluating alerts")
    try:
        prev_result = params.get("_prev_result", {})
        alert_threshold = params.get("alert_threshold", 0.5)
        alerts_triggered = []

        # Check composite score
        composite = prev_result.get("composite_score")
        if composite is not None and abs(composite) >= alert_threshold:
            direction = "bullish" if composite > 0 else "bearish"
            alerts_triggered.append({
                "type": "composite_signal",
                "direction": direction,
                "score": composite,
                "message": f"Strong {direction} composite signal: {composite:.3f}",
            })

        # Check sentiment conviction
        conviction = prev_result.get("sentiment_conviction", prev_result.get("conviction", 0.0))
        signal_val = prev_result.get("sentiment_component", prev_result.get("signal", 0.0))
        if conviction > 0.8 and abs(signal_val) > 0.3:
            alerts_triggered.append({
                "type": "high_conviction_sentiment",
                "signal": signal_val,
                "conviction": conviction,
                "message": f"High conviction sentiment: {signal_val:.3f} ({conviction:.0%})",
            })

        # Send notifications for any triggered alerts
        if alerts_triggered:
            try:
                from core.services.notification import send_notification

                for alert in alerts_triggered:
                    send_notification(alert["message"])
            except Exception:
                logger.debug("Alert notification failed", exc_info=True)

        return {
            "status": "completed",
            "alerts_triggered": len(alerts_triggered),
            "alerts": alerts_triggered,
        }
    except Exception as e:
        logger.warning("Alert evaluation failed: %s", e)
        return {"status": "error", "error": str(e)}


def _step_strategy_recommend(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Get strategy routing recommendations for watchlist symbols."""
    progress_cb(0.1, "Getting strategy recommendations")
    try:
        from market.services.regime import RegimeService

        service = RegimeService()
        recommendations = service.get_all_recommendations()
        return {
            "status": "completed",
            "recommendations": recommendations,
            "count": len(recommendations),
        }
    except Exception as e:
        logger.warning("Strategy recommend step failed: %s", e)
        return {"status": "error", "error": str(e)}


def _step_ml_training(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Train ML model within workflow."""
    from core.services.task_registry import _run_ml_training
    return _run_ml_training(params, progress_cb)


# ── Registry ────────────────────────────────────────────────

STEP_REGISTRY: dict[str, StepExecutor] = {
    # Re-exports
    "data_refresh": _step_data_refresh,
    "regime_detection": _step_regime_detection,
    "news_fetch": _step_news_fetch,
    "data_quality": _step_data_quality,
    "order_sync": _step_order_sync,
    # Workflow-specific
    "vbt_screen": _step_vbt_screen,
    "sentiment_aggregate": _step_sentiment_aggregate,
    "composite_score": _step_composite_score,
    "alert_evaluate": _step_alert_evaluate,
    "strategy_recommend": _step_strategy_recommend,
    "ml_training": _step_ml_training,
}


def get_step_types() -> list[dict[str, str]]:
    """Return list of available step types with descriptions."""
    descriptions = {
        "data_refresh": "Refresh OHLCV data for asset class watchlist",
        "regime_detection": "Run regime detection for watchlist symbols",
        "news_fetch": "Fetch latest news for all asset classes",
        "data_quality": "Check for stale data across asset classes",
        "order_sync": "Sync open live orders with exchange",
        "vbt_screen": "Run VectorBT strategy screen",
        "sentiment_aggregate": "Aggregate sentiment scores for asset class",
        "composite_score": "Combine regime + sentiment into composite score",
        "alert_evaluate": "Evaluate thresholds and send notifications",
        "strategy_recommend": "Get strategy routing recommendations",
        "ml_training": "Train LightGBM model on OHLCV data",
    }
    return [
        {"step_type": k, "description": descriptions.get(k, "")}
        for k in STEP_REGISTRY
    ]
