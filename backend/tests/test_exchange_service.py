"""Tests for ExchangeService — wraps ccxt for async market data access."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market.services.exchange import SUPPORTED_EXCHANGES, ExchangeService, _load_db_config


class TestLoadDbConfig:
    def test_returns_none_on_import_error(self):
        """When market.models can't be imported, _load_db_config returns None."""
        with patch.dict("sys.modules", {"market.models": None}):
            # Force re-import failure by making the lazy import raise

            # Temporarily break the import
            original_import = (
                __builtins__.__import__
                if hasattr(__builtins__, "__import__")
                else __import__
            )
            def failing_import(name, *args, **kwargs):
                if name == "market.models":
                    raise ImportError("mocked")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=failing_import):
                result = _load_db_config()
                assert result is None

    @pytest.mark.django_db
    def test_returns_none_when_no_config(self):
        result = _load_db_config()
        assert result is None

    @pytest.mark.django_db
    def test_returns_none_for_nonexistent_config_id(self):
        result = _load_db_config(config_id=9999)
        assert result is None


class TestExchangeServiceInit:
    @pytest.mark.django_db
    def test_defaults_to_settings_exchange_id(self):
        with patch("market.services.exchange.settings") as mock_settings:
            mock_settings.EXCHANGE_ID = "binance"
            mock_settings.EXCHANGE_API_KEY = ""
            mock_settings.EXCHANGE_API_SECRET = ""
            service = ExchangeService()
            assert service._exchange_id == "binance"

    @pytest.mark.django_db
    def test_uses_explicit_exchange_id(self):
        service = ExchangeService(exchange_id="kraken")
        assert service._exchange_id == "kraken"


class TestExchangeServiceListExchanges:
    @pytest.mark.django_db
    def test_list_exchanges_returns_supported(self):
        service = ExchangeService(exchange_id="binance")
        result = service.list_exchanges()
        assert isinstance(result, list)
        assert len(result) == len(SUPPORTED_EXCHANGES)
        ids = [e["id"] for e in result]
        for eid in SUPPORTED_EXCHANGES:
            assert eid in ids

    @pytest.mark.django_db
    def test_list_exchanges_has_expected_keys(self):
        service = ExchangeService(exchange_id="binance")
        result = service.list_exchanges()
        for entry in result:
            assert "id" in entry
            assert "name" in entry
            assert "countries" in entry
            assert "has_fetch_tickers" in entry
            assert "has_fetch_ohlcv" in entry


class TestExchangeServiceFetchTicker:
    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_ticker_success(self):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ticker = AsyncMock(return_value={
            "symbol": "BTC/USDT",
            "last": 50000.0,
            "quoteVolume": 1_000_000.0,
            "percentage": 2.5,
            "high": 51000.0,
            "low": 49000.0,
            "timestamp": 1700000000000,
        })

        service = ExchangeService(exchange_id="binance")
        service._exchange = mock_exchange

        with patch("market.services.circuit_breaker.get_breaker") as mock_get_breaker:
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_get_breaker.return_value = breaker

            result = await service.fetch_ticker("BTC/USDT")
            assert result["symbol"] == "BTC/USDT"
            assert result["price"] == 50000.0
            assert result["volume_24h"] == 1_000_000.0
            assert result["change_24h"] == 2.5
            breaker.record_success.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_ticker_circuit_breaker_open(self):
        from market.services.circuit_breaker import CircuitBreakerOpenError

        service = ExchangeService(exchange_id="binance")

        with patch("market.services.circuit_breaker.get_breaker") as mock_get_breaker:
            breaker = MagicMock()
            breaker.can_execute.return_value = False
            breaker.reset_timeout_seconds = 60
            mock_get_breaker.return_value = breaker

            with pytest.raises(CircuitBreakerOpenError):
                await service.fetch_ticker("BTC/USDT")

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_ticker_records_failure_on_exception(self):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ticker = AsyncMock(side_effect=Exception("Network error"))

        service = ExchangeService(exchange_id="binance")
        service._exchange = mock_exchange

        with patch("market.services.circuit_breaker.get_breaker") as mock_get_breaker:
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_get_breaker.return_value = breaker

            with pytest.raises(Exception, match="Network error"):
                await service.fetch_ticker("BTC/USDT")
            breaker.record_failure.assert_called_once()


class TestExchangeServiceFetchTickers:
    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_tickers_returns_list(self):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_tickers = AsyncMock(return_value={
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "last": 50000.0,
                "quoteVolume": 1_000_000.0,
                "percentage": 2.5,
                "high": 51000.0,
                "low": 49000.0,
                "timestamp": 1700000000000,
            },
        })

        service = ExchangeService(exchange_id="binance")
        service._exchange = mock_exchange

        with patch("market.services.circuit_breaker.get_breaker") as mock_get_breaker:
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_get_breaker.return_value = breaker

            result = await service.fetch_tickers(["BTC/USDT"])
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["symbol"] == "BTC/USDT"


class TestExchangeServiceFetchOHLCV:
    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_ohlcv_returns_candles(self):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=[
            [1700000000000, 50000.0, 51000.0, 49000.0, 50500.0, 100.0],
            [1700003600000, 50500.0, 51500.0, 50000.0, 51000.0, 150.0],
        ])

        service = ExchangeService(exchange_id="binance")
        service._exchange = mock_exchange

        with patch("market.services.circuit_breaker.get_breaker") as mock_get_breaker:
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_get_breaker.return_value = breaker

            result = await service.fetch_ohlcv("BTC/USDT", "1h", 100)
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["timestamp"] == 1700000000000
            assert result[0]["open"] == 50000.0
            assert result[0]["close"] == 50500.0
            assert result[0]["volume"] == 100.0


class TestExchangeServiceClose:
    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_close_calls_exchange_close(self):
        mock_exchange = AsyncMock()
        service = ExchangeService(exchange_id="binance")
        service._exchange = mock_exchange

        await service.close()
        mock_exchange.close.assert_called_once()
        assert service._exchange is None

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_close_noop_when_no_exchange(self):
        service = ExchangeService(exchange_id="binance")
        # Should not raise
        await service.close()
        assert service._exchange is None
