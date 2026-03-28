"""Regime detection and strategy orchestration executors."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")

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
