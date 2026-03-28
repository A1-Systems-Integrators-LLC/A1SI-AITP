"""ML-related task executors: training, prediction, feedback, retrain, conviction audit, adaptive weighting."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


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

    trained = sum(1 for r in results if r.get("status") != "error")
    errors = sum(1 for r in results if r.get("status") == "error")
    if errors > 0:
        logger.error("ML training: %d/%d symbols failed", errors, len(results))
    return {
        "status": "completed" if trained > 0 else "error",
        "models_trained": trained,
        "errors": errors,
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
    no_model = sum(1 for r in results if r["status"] == "no_model")
    errors = sum(1 for r in results if r["status"] == "error")

    if predicted == 0 and len(results) > 0:
        logger.error(
            "ML predict completed with 0 predictions (%d no_model, %d errors) — "
            "ML pipeline may be dead. Check ml_training task.",
            no_model, errors,
        )

    return {
        "status": "completed" if predicted > 0 else "error",
        "predicted": predicted,
        "no_model": no_model,
        "errors": errors,
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
