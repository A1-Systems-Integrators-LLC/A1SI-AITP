"""Regime Service — wraps RegimeDetector + StrategyRouter for dashboard API."""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Ensure project root is on path for common.* imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.regime.regime_detector import RegimeDetector, RegimeState
from common.regime.strategy_router import RoutingDecision, StrategyRouter
from common.risk.risk_manager import RiskManager

logger = logging.getLogger("regime_service")

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


class RegimeService:
    def __init__(
        self,
        detector: RegimeDetector | None = None,
        router: StrategyRouter | None = None,
        symbols: list[str] | None = None,
    ) -> None:
        self.detector = detector or RegimeDetector()
        self.router = router or StrategyRouter()
        self.symbols = symbols or list(DEFAULT_SYMBOLS)
        self._cache: dict[str, tuple[RegimeState, datetime]] = {}
        self._history: dict[str, list[tuple[RegimeState, datetime]]] = {}

    def get_current_regime(self, symbol: str) -> dict | None:
        df = self._load_data(symbol)
        if df is None or df.empty:
            if symbol in self._cache:
                state, ts = self._cache[symbol]
                return self._state_to_dict(symbol, state, ts)
            return None

        state = self.detector.detect(df)
        now = datetime.now(timezone.utc)
        self._cache[symbol] = (state, now)

        if symbol not in self._history:
            self._history[symbol] = []
        self._history[symbol].append((state, now))
        if len(self._history[symbol]) > 1000:
            self._history[symbol] = self._history[symbol][-500:]

        return self._state_to_dict(symbol, state, now)

    def get_all_current_regimes(self) -> list[dict]:
        results = []
        for symbol in self.symbols:
            regime = self.get_current_regime(symbol)
            if regime is not None:
                results.append(regime)
        return results

    def get_regime_history(self, symbol: str, limit: int = 100) -> list[dict]:
        history = self._history.get(symbol, [])
        entries = history[-limit:]
        return [
            {
                "timestamp": ts.isoformat(),
                "regime": state.regime.value,
                "confidence": round(state.confidence, 3),
                "adx_value": round(state.adx_value, 2),
                "bb_width_percentile": round(state.bb_width_percentile, 2),
            }
            for state, ts in entries
        ]

    def get_recommendation(
        self,
        symbol: str,
        include_sentiment: bool = True,
    ) -> dict | None:
        df = self._load_data(symbol)
        if df is None or df.empty:
            if symbol in self._cache:
                state, _ = self._cache[symbol]
            else:
                return None
        else:
            state = self.detector.detect(df)

        # Fetch sentiment modifier if enabled
        sentiment_modifier = None
        if include_sentiment:
            try:
                from market.services.news import NewsService

                service = NewsService()
                # Determine asset class from symbol pattern
                asset_class = self._guess_asset_class(symbol)
                sig = service.get_sentiment_signal(asset_class)
                sentiment_modifier = sig.get("position_modifier")
            except Exception as e:
                logger.debug("Sentiment signal unavailable for %s: %s", symbol, e)

        decision = self.router.route(state, sentiment_modifier=sentiment_modifier)
        return self._decision_to_dict(symbol, decision)

    def get_all_recommendations(self) -> list[dict]:
        results = []
        for symbol in self.symbols:
            rec = self.get_recommendation(symbol)
            if rec is not None:
                results.append(rec)
        return results

    def get_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        risk_manager: RiskManager,
    ) -> dict | None:
        df = self._load_data(symbol)
        if df is None or df.empty:
            if symbol in self._cache:
                state, _ = self._cache[symbol]
            else:
                return None
        else:
            state = self.detector.detect(df)

        decision = self.router.route(state)
        regime_modifier = decision.position_size_modifier
        size = risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            regime_modifier=regime_modifier,
        )
        return {
            "symbol": symbol,
            "regime": state.regime.value,
            "regime_modifier": regime_modifier,
            "position_size": round(size, 8),
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "primary_strategy": decision.primary_strategy,
        }

    @staticmethod
    def _guess_asset_class(symbol: str) -> str:
        """Guess asset class from symbol format."""
        s = symbol.upper()
        # Forex pairs: EUR/USD, GBP/JPY etc.
        forex_currencies = {"EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD"}
        parts = s.split("/")
        if len(parts) == 2 and parts[0] in forex_currencies and parts[1] in forex_currencies:
            return "forex"
        # Common crypto quote currencies
        crypto_quotes = {"USDT", "USDC", "BTC", "ETH", "BUSD", "BNB"}
        if len(parts) == 2 and parts[1] in crypto_quotes:
            return "crypto"
        # Default: equity for stock-like symbols, crypto otherwise
        if "/" not in symbol:
            return "equity"
        return "crypto"

    def _load_data(self, symbol: str) -> pd.DataFrame | None:
        try:
            from common.data_pipeline.pipeline import load_ohlcv

            df = load_ohlcv(symbol, "1h", "kraken")
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.debug(f"Failed to load data for {symbol}: {e}")
        return None

    @staticmethod
    def _state_to_dict(symbol: str, state: RegimeState, ts: datetime) -> dict:
        return {
            "symbol": symbol,
            "regime": state.regime.value,
            "confidence": round(state.confidence, 3),
            "adx_value": round(state.adx_value, 2),
            "bb_width_percentile": round(state.bb_width_percentile, 2),
            "ema_slope": round(state.ema_slope, 6),
            "trend_alignment": round(state.trend_alignment, 3),
            "price_structure_score": round(state.price_structure_score, 3),
            "transition_probabilities": state.transition_probabilities,
            "timestamp": ts.isoformat(),
        }

    @staticmethod
    def _decision_to_dict(symbol: str, decision: RoutingDecision) -> dict:
        result = {
            "symbol": symbol,
            "regime": decision.regime.value,
            "confidence": round(decision.confidence, 3),
            "primary_strategy": decision.primary_strategy,
            "weights": [
                {
                    "strategy_name": w.strategy_name,
                    "weight": w.weight,
                    "position_size_factor": w.position_size_factor,
                }
                for w in decision.weights
            ],
            "position_size_modifier": decision.position_size_modifier,
            "reasoning": decision.reasoning,
        }
        if decision.sentiment_modifier is not None:
            result["sentiment_modifier"] = decision.sentiment_modifier
        return result
