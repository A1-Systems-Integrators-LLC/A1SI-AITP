"""Tests for Alpha Phase 4 — ML Upgrade.

Covers: LSTM model/trainer, cross-asset features, on-chain data,
RL position sizer, multi-model ensemble updates, registry LSTM support.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/rredmer/Dev/Portfolio/A1SI-AITP")

import numpy as np
import pandas as pd

# ── LSTM Model ────────────────────────────────────────────────────────────────


class TestLSTMModel:
    """Tests for LSTM predictor model."""

    def test_is_available(self):
        from common.ml.lstm_model import is_available

        assert isinstance(is_available(), bool)

    def test_lstm_config_defaults(self):
        from common.ml.lstm_model import DEFAULT_HIDDEN_SIZE, DEFAULT_SEQ_LEN, LSTMConfig

        cfg = LSTMConfig(input_size=15)
        assert cfg.input_size == 15
        assert cfg.hidden_size == DEFAULT_HIDDEN_SIZE
        assert cfg.seq_len == DEFAULT_SEQ_LEN

    def test_lstm_forward_pass(self):
        from common.ml.lstm_model import LSTMConfig, LSTMPredictor, is_available

        if not is_available():
            return  # skip on systems without torch
        import torch

        cfg = LSTMConfig(input_size=10, hidden_size=32, num_layers=2, seq_len=20)
        model = LSTMPredictor(cfg)
        x = torch.randn(2, 20, 10)  # batch=2, seq=20, features=10
        out = model(x)
        assert out.shape == (2, 1)
        assert 0.0 <= out.min().item() <= out.max().item() <= 1.0

    def test_lstm_predict_proba(self):
        from common.ml.lstm_model import LSTMConfig, LSTMPredictor, is_available

        if not is_available():
            return
        import torch

        cfg = LSTMConfig(input_size=5, hidden_size=16, num_layers=1, seq_len=10)
        model = LSTMPredictor(cfg)
        x = torch.randn(1, 10, 5)
        prob = model.predict_proba(x)
        assert 0.0 <= prob <= 1.0

    def test_lstm_save_load(self):
        from common.ml.lstm_model import LSTMConfig, LSTMPredictor, is_available

        if not is_available():
            return
        import torch

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_model.pt"
            cfg = LSTMConfig(input_size=5, hidden_size=16, num_layers=1, seq_len=10)
            model = LSTMPredictor(cfg)

            # Save
            model.save(path)
            assert path.exists()

            # Load
            loaded = LSTMPredictor.load(path)
            assert loaded.config.input_size == 5
            assert loaded.config.hidden_size == 16

            # Verify predictions match
            x = torch.randn(1, 10, 5)
            p1 = model.predict_proba(x)
            p2 = loaded.predict_proba(x)
            assert abs(p1 - p2) < 1e-5

    def test_prepare_sequences(self):
        from common.ml.lstm_model import is_available, prepare_sequences

        if not is_available():
            return

        n_rows = 100
        n_features = 10
        seq_len = 20
        features = np.random.randn(n_rows, n_features)
        target = np.random.randint(0, 2, n_rows).astype(np.float32)

        x, y = prepare_sequences(features, target, seq_len)
        assert x.shape == (n_rows - seq_len, seq_len, n_features)
        assert y.shape == (n_rows - seq_len, 1)

    def test_prepare_sequences_too_short(self):
        from common.ml.lstm_model import is_available, prepare_sequences

        if not is_available():
            return
        import pytest

        features = np.random.randn(10, 5)
        target = np.random.randint(0, 2, 10).astype(np.float32)
        with pytest.raises(ValueError, match="Need more than"):
            prepare_sequences(features, target, seq_len=20)


# ── LSTM Trainer ──────────────────────────────────────────────────────────────


class TestLSTMTrainer:
    """Tests for LSTM training pipeline."""

    def test_train_lstm_basic(self):
        from common.ml.lstm_model import is_available

        if not is_available():
            return
        from common.ml.lstm_trainer import train_lstm

        n_rows = 200
        n_features = 10
        features = np.random.randn(n_rows, n_features).astype(np.float32)
        target = np.random.randint(0, 2, n_rows).astype(np.float32)

        result = train_lstm(
            features, target,
            epochs=3, batch_size=16, seq_len=20, patience=2,
        )
        assert result.metrics["accuracy"] >= 0.0
        assert result.metrics["n_features"] == n_features
        assert result.metadata["model_type"] == "LSTM"
        assert result.elapsed_seconds > 0

    def test_train_lstm_with_save(self):
        from common.ml.lstm_model import is_available

        if not is_available():
            return
        from common.ml.lstm_trainer import train_lstm

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "trained.pt"
            features = np.random.randn(150, 8).astype(np.float32)
            target = np.random.randint(0, 2, 150).astype(np.float32)

            result = train_lstm(
                features, target,
                epochs=2, batch_size=16, seq_len=15,
                save_path=save_path,
            )
            assert save_path.exists()
            assert result.metrics["train_rows"] > 0
            assert result.metrics["test_rows"] > 0

    def test_train_result_has_metrics(self):
        from common.ml.lstm_model import is_available

        if not is_available():
            return
        from common.ml.lstm_trainer import train_lstm

        features = np.random.randn(120, 5).astype(np.float32)
        target = np.random.randint(0, 2, 120).astype(np.float32)

        result = train_lstm(features, target, epochs=2, seq_len=10, patience=2)
        for key in ["accuracy", "precision", "recall", "f1", "test_loss", "epochs_trained"]:
            assert key in result.metrics


# ── Cross-Asset Features ──────────────────────────────────────────────────────


class TestCrossAssetFeatures:
    """Tests for cross-asset correlation features."""

    def _make_ohlcv(self, n=100, base_price=100.0):
        """Create synthetic OHLCV DataFrame."""
        dates = pd.date_range("2024-01-01", periods=n, freq="h")
        close = base_price + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "open": close + np.random.randn(n) * 0.1,
            "high": close + abs(np.random.randn(n) * 0.3),
            "low": close - abs(np.random.randn(n) * 0.3),
            "close": close,
            "volume": np.random.randint(100, 10000, n).astype(float),
        }, index=dates)

    def test_no_reference_returns_neutral(self):
        from common.ml.features import add_cross_asset_features

        df = self._make_ohlcv()
        result = add_cross_asset_features(df, reference_df=None)
        assert "cross_corr" in result.columns
        assert "cross_lead1_return" in result.columns
        assert "relative_strength" in result.columns
        assert (result["cross_corr"] == 0.0).all()

    def test_with_reference_data(self):
        from common.ml.features import add_cross_asset_features

        df = self._make_ohlcv(100, 50000)
        ref = self._make_ohlcv(100, 60000)
        result = add_cross_asset_features(df, reference_df=ref)
        assert "cross_corr" in result.columns
        assert "cross_lead1_return" in result.columns
        assert "cross_lead2_return" in result.columns
        assert "relative_strength" in result.columns
        # Should have some non-zero values after warmup
        assert not result["cross_corr"].iloc[25:].isna().all()

    def test_empty_reference(self):
        from common.ml.features import add_cross_asset_features

        df = self._make_ohlcv()
        result = add_cross_asset_features(df, reference_df=pd.DataFrame())
        assert (result["cross_corr"] == 0.0).all()

    def test_build_feature_matrix_with_cross_asset(self):
        from common.ml.features import build_feature_matrix

        df = self._make_ohlcv(200, 100)
        ref = self._make_ohlcv(200, 50000)
        x_feat, y, names = build_feature_matrix(
            df, include_cross_asset=True, reference_df=ref,
        )
        # May be filtered out by _reduce_features if correlated, but should exist before
        assert len(x_feat) > 0


# ── On-Chain Data ─────────────────────────────────────────────────────────────


class TestOnChainData:
    """Tests for on-chain data adapter."""

    def test_clear_cache(self):
        from common.market_data.onchain import _cache, clear_cache

        _cache["test"] = (0, {"test": True})
        clear_cache()
        assert len(_cache) == 0

    @patch("common.market_data.onchain.httpx.get")
    def test_fetch_hash_rate(self, mock_get):
        from common.market_data.onchain import clear_cache, fetch_hash_rate

        clear_cache()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "values": [
                {"x": 1, "y": 500_000_000},
                {"x": 2, "y": 520_000_000},
            ],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_hash_rate()
        assert result is not None
        assert result["hash_rate"] == 520_000_000
        assert result["change_pct"] > 0

    @patch("common.market_data.onchain.httpx.get")
    def test_fetch_hash_rate_failure(self, mock_get):
        from common.market_data.onchain import clear_cache, fetch_hash_rate

        clear_cache()
        mock_get.side_effect = Exception("Network error")
        result = fetch_hash_rate()
        assert result is None

    @patch("common.market_data.onchain.httpx.get")
    def test_fetch_transaction_count(self, mock_get):
        from common.market_data.onchain import clear_cache, fetch_transaction_count

        clear_cache()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "values": [{"x": 1, "y": 300000}, {"x": 2, "y": 330000}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_transaction_count()
        assert result is not None
        assert result["tx_count"] == 330000
        assert result["change_pct"] == 10.0

    @patch("common.market_data.onchain.httpx.get")
    def test_fetch_mempool_size(self, mock_get):
        from common.market_data.onchain import clear_cache, fetch_mempool_size

        clear_cache()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"values": [{"x": 1, "y": 5000}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_mempool_size()
        assert result is not None
        assert result["mempool_count"] == 5000

    @patch("common.market_data.onchain.fetch_transaction_count")
    @patch("common.market_data.onchain.fetch_hash_rate")
    def test_get_onchain_signal_bullish(self, mock_hr, mock_tx):
        from common.market_data.onchain import get_onchain_signal

        mock_hr.return_value = {"change_pct": 10.0}
        mock_tx.return_value = {"change_pct": 15.0}
        result = get_onchain_signal()
        assert result["modifier"] == 5  # +3 (HR) + +2 (TX)
        assert "bullish" in result["reasoning"].lower() or "rising" in result["reasoning"].lower()

    @patch("common.market_data.onchain.fetch_transaction_count")
    @patch("common.market_data.onchain.fetch_hash_rate")
    def test_get_onchain_signal_bearish(self, mock_hr, mock_tx):
        from common.market_data.onchain import get_onchain_signal

        mock_hr.return_value = {"change_pct": -10.0}
        mock_tx.return_value = {"change_pct": -15.0}
        result = get_onchain_signal()
        assert result["modifier"] == -5  # -3 (HR) + -2 (TX)

    @patch("common.market_data.onchain.fetch_transaction_count")
    @patch("common.market_data.onchain.fetch_hash_rate")
    def test_get_onchain_signal_neutral(self, mock_hr, mock_tx):
        from common.market_data.onchain import get_onchain_signal

        mock_hr.return_value = {"change_pct": 1.0}
        mock_tx.return_value = {"change_pct": 2.0}
        result = get_onchain_signal()
        assert result["modifier"] == 0

    @patch("common.market_data.onchain.fetch_transaction_count")
    @patch("common.market_data.onchain.fetch_hash_rate")
    def test_get_onchain_signal_no_data(self, mock_hr, mock_tx):
        from common.market_data.onchain import get_onchain_signal

        mock_hr.return_value = None
        mock_tx.return_value = None
        result = get_onchain_signal()
        assert result["modifier"] == 0
        assert result["reasoning"] == "On-chain neutral"

    def test_cache_hit(self):

        from common.market_data.onchain import _get_cached, _set_cached, clear_cache

        clear_cache()
        _set_cached("test_key", {"value": 42})
        assert _get_cached("test_key") == {"value": 42}

    def test_cache_expired(self):
        from common.market_data.onchain import CACHE_TTL, _cache, _get_cached, clear_cache

        clear_cache()
        import time

        _cache["expired"] = (time.monotonic() - CACHE_TTL - 1, {"old": True})
        assert _get_cached("expired") is None


# ── RL Position Sizer ─────────────────────────────────────────────────────────


class TestRLPositionSizer:
    """Tests for RL-based position sizing."""

    def test_is_available(self):
        from common.ml.rl_position_sizer import is_available

        assert isinstance(is_available(), bool)

    def test_untrained_returns_one(self):
        from common.ml.rl_position_sizer import RLPositionSizer

        sizer = RLPositionSizer()
        mult = sizer.get_multiplier(
            composite_score=70, regime_ordinal=0, drawdown=-0.05,
            daily_pnl=0.01, fear_greed=50, win_rate=0.6,
        )
        assert mult == 1.0

    def test_is_trained_initially_false(self):
        from common.ml.rl_position_sizer import RLPositionSizer

        sizer = RLPositionSizer()
        assert sizer.is_trained is False

    def test_trade_experience_dataclass(self):
        from common.ml.rl_position_sizer import TradeExperience

        exp = TradeExperience(
            composite_score=75, regime_ordinal=1, drawdown=-0.03,
            daily_pnl=0.02, fear_greed=45, win_rate=0.55,
            position_multiplier=1.0, pnl_result=0.03,
        )
        assert exp.composite_score == 75
        assert exp.pnl_result == 0.03

    def test_train_insufficient_data(self):
        from common.ml.rl_position_sizer import RLPositionSizer, TradeExperience, is_available

        if not is_available():
            return
        sizer = RLPositionSizer()
        experiences = [
            TradeExperience(70, 1, -0.02, 0.01, 50, 0.6, 1.0, 0.02)
            for _ in range(10)
        ]
        result = sizer.train(experiences)
        assert result["status"] == "insufficient_data"

    def test_train_with_enough_data(self):
        from common.ml.rl_position_sizer import RLPositionSizer, TradeExperience, is_available

        if not is_available():
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "rl_model.zip"
            sizer = RLPositionSizer(model_path=model_path)
            experiences = [
                TradeExperience(
                    composite_score=np.random.uniform(30, 90),
                    regime_ordinal=np.random.randint(0, 7),
                    drawdown=np.random.uniform(-0.2, 0),
                    daily_pnl=np.random.uniform(-0.05, 0.05),
                    fear_greed=np.random.uniform(10, 90),
                    win_rate=np.random.uniform(0.3, 0.7),
                    position_multiplier=1.0,
                    pnl_result=np.random.uniform(-0.05, 0.05),
                )
                for _ in range(120)
            ]
            result = sizer.train(experiences, total_timesteps=100)
            assert result["status"] == "trained"
            assert sizer.is_trained
            assert model_path.exists()

            # Test prediction after training
            mult = sizer.get_multiplier(70, 1, -0.05, 0.01, 50, 0.6)
            assert 0.2 <= mult <= 1.5

    def test_load_nonexistent(self):
        from common.ml.rl_position_sizer import RLPositionSizer

        sizer = RLPositionSizer(model_path="/tmp/nonexistent_rl.zip")
        assert sizer.load() is False

    def test_trading_env_basics(self):
        from common.ml.rl_position_sizer import TradeExperience, TradingEnv, is_available

        if not is_available():
            return
        experiences = [
            TradeExperience(70, 1, -0.02, 0.01, 50, 0.6, 1.0, 0.03),
            TradeExperience(50, 3, -0.05, -0.01, 30, 0.5, 0.8, -0.02),
        ]
        env = TradingEnv(experiences)
        obs, info = env.reset()
        assert obs.shape == (6,)
        assert obs[0] == 70.0  # composite_score

        # Step
        action = np.array([0.5], dtype=np.float32)
        obs2, reward, terminated, truncated, info = env.step(action)
        assert not terminated  # still have one more experience
        assert "multiplier" in info

        # Final step
        obs3, reward, terminated, truncated, info = env.step(action)
        assert terminated


# ── Registry LSTM Support ─────────────────────────────────────────────────────


class TestRegistryLSTM:
    """Tests for registry LSTM model support."""

    def test_save_load_lstm(self):
        from common.ml.lstm_model import LSTMConfig, LSTMPredictor, is_available

        if not is_available():
            return
        from common.ml.registry import ModelRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(models_dir=Path(tmpdir))
            cfg = LSTMConfig(input_size=5, hidden_size=16, num_layers=1, seq_len=10)
            model = LSTMPredictor(cfg)

            model_id = registry.save_model(
                model=model,
                metrics={"accuracy": 0.65, "f1": 0.60},
                metadata={"model_type": "LSTM", "seq_len": 10},
                feature_importance={},
                symbol="BTC/USDT",
                timeframe="1h",
                label="lstm_test",
            )
            assert model_id

            # Load
            loaded, manifest = registry.load_model(model_id)
            assert manifest["model_format"] == "lstm"
            assert isinstance(loaded, LSTMPredictor)

            # List
            models = registry.list_models()
            assert len(models) == 1
            assert models[0]["model_id"] == model_id


# ── Ensemble LSTM Integration ─────────────────────────────────────────────────


class TestEnsembleLSTM:
    """Tests for ensemble with LSTM models."""

    def test_ensemble_with_lstm_model(self):
        from common.ml.lstm_model import LSTMConfig, LSTMPredictor, is_available

        if not is_available():
            return
        from common.ml.ensemble import ModelEnsemble
        from common.ml.registry import ModelRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(models_dir=Path(tmpdir))
            cfg = LSTMConfig(input_size=5, hidden_size=16, num_layers=1, seq_len=10)
            model = LSTMPredictor(cfg)

            model_id = registry.save_model(
                model=model,
                metrics={"accuracy": 0.65},
                metadata={"model_type": "LSTM", "seq_len": 10},
                feature_importance={},
                symbol="BTC/USDT",
                timeframe="1h",
            )

            ensemble = ModelEnsemble(registry=registry)
            added = ensemble.add_model(model_id)
            assert added

            # Predict with features matching (seq_len, n_features)
            features = pd.DataFrame(np.random.randn(10, 5))
            result = ensemble.predict(features)
            assert result is not None
            assert 0.0 <= result.probability <= 1.0
            assert result.model_count == 1


# ── Docstring/Import Checks ──────────────────────────────────────────────────


class TestPhase4Imports:
    """Verify all new modules are importable."""

    def test_import_lstm_model(self):
        from common.ml.lstm_model import (
            DEFAULT_SEQ_LEN,
        )

        assert DEFAULT_SEQ_LEN == 60

    def test_import_lstm_trainer(self):
        from common.ml.lstm_trainer import TrainResult

        assert TrainResult is not None

    def test_import_onchain(self):
        from common.market_data.onchain import (
            get_onchain_signal,
        )

        assert callable(get_onchain_signal)

    def test_import_rl_position_sizer(self):
        from common.ml.rl_position_sizer import (
            MAX_MULTIPLIER,
            MIN_MULTIPLIER,
        )

        assert MIN_MULTIPLIER == 0.2
        assert MAX_MULTIPLIER == 1.5

    def test_import_cross_asset_features(self):
        from common.ml.features import add_cross_asset_features

        assert callable(add_cross_asset_features)
