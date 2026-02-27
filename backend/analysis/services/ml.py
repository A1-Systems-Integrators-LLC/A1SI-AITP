"""ML service — training, prediction, and model listing for the backend API."""

import logging
from collections.abc import Callable

from core.platform_bridge import ensure_platform_imports

logger = logging.getLogger("ml_service")


class MLService:
    @staticmethod
    def train(params: dict, progress_cb: Callable) -> dict:
        """Train an ML model on OHLCV data.

        Params:
            symbol: Trading pair (e.g. "BTC/USDT")
            timeframe: Candle timeframe (e.g. "1h")
            exchange: Exchange id (e.g. "kraken")
            test_ratio: Fraction for time-series test split (default 0.2)
        """
        ensure_platform_imports()

        symbol = params.get("symbol", "BTC/USDT")
        timeframe = params.get("timeframe", "1h")
        exchange = params.get("exchange", "kraken")
        test_ratio = params.get("test_ratio", 0.2)

        progress_cb(0.1, "Loading data...")
        try:
            from common.data_pipeline.pipeline import load_ohlcv
        except ImportError as e:
            return {"error": f"Data pipeline not available: {e}"}

        df = load_ohlcv(symbol, timeframe, exchange)
        if df.empty:
            return {"error": f"No data for {symbol} {timeframe} on {exchange}"}

        progress_cb(0.3, "Building feature matrix...")
        try:
            from common.ml.features import build_feature_matrix
            from common.ml.registry import ModelRegistry
            from common.ml.trainer import train_model
        except ImportError as e:
            return {"error": f"ML modules not available: {e}"}

        x_feat, y_target, feature_names = build_feature_matrix(df)
        if len(x_feat) < 100:
            return {"error": f"Insufficient data: {len(x_feat)} rows (need >= 100)"}

        progress_cb(0.5, "Training model...")
        result = train_model(x_feat, y_target, feature_names, test_ratio=test_ratio)

        progress_cb(0.8, "Saving model...")
        registry = ModelRegistry()
        model_id = registry.save_model(
            model=result["model"],
            metrics=result["metrics"],
            metadata=result["metadata"],
            feature_importance=result["feature_importance"],
            symbol=symbol,
            timeframe=timeframe,
        )

        progress_cb(1.0, "Complete")
        return {
            "model_id": model_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "metrics": result["metrics"],
        }

    @staticmethod
    def predict(params: dict) -> dict:
        """Generate predictions from a trained model.

        Params:
            model_id: Model identifier
            symbol: Trading pair
            timeframe: Candle timeframe
            exchange: Exchange id
            bars: Number of recent bars to predict on (default 50)
        """
        ensure_platform_imports()

        model_id = params.get("model_id", "")
        symbol = params.get("symbol", "BTC/USDT")
        timeframe = params.get("timeframe", "1h")
        exchange = params.get("exchange", "kraken")
        n_bars = params.get("bars", 50)

        if not model_id:
            return {"error": "model_id is required"}

        try:
            from common.data_pipeline.pipeline import load_ohlcv
            from common.ml.features import build_feature_matrix
            from common.ml.registry import ModelRegistry
            from common.ml.trainer import predict
        except ImportError as e:
            return {"error": f"ML modules not available: {e}"}

        # Load model
        registry = ModelRegistry()
        try:
            model, manifest = registry.load_model(model_id)
        except FileNotFoundError:
            return {"error": f"Model not found: {model_id}"}

        # Load data and build features
        df = load_ohlcv(symbol, timeframe, exchange)
        if df.empty:
            return {"error": f"No data for {symbol} {timeframe}"}

        x_feat, _y, _names = build_feature_matrix(df, config={"drop_na": True})
        if len(x_feat) == 0:
            return {"error": "No valid feature rows after NaN removal"}

        # Use last N bars
        x_recent = x_feat.tail(n_bars)

        result = predict(model, x_recent)
        result["model_id"] = model_id
        result["symbol"] = symbol
        result["timeframe"] = timeframe
        return result

    @staticmethod
    def list_models() -> list[dict]:
        """List all saved models."""
        ensure_platform_imports()
        try:
            from common.ml.registry import ModelRegistry
        except ImportError:
            return []
        return ModelRegistry().list_models()

    @staticmethod
    def get_model_detail(model_id: str) -> dict | None:
        """Get full metadata for a model."""
        ensure_platform_imports()
        try:
            from common.ml.registry import ModelRegistry
        except ImportError:
            return None
        return ModelRegistry().get_model_detail(model_id)
