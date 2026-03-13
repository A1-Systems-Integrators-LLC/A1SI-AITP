"""Comprehensive tests for Exchange Service and Circuit Breaker.

Covers: cache TTL, cache thread safety, circuit breaker state transitions,
recovery timing, state-change logging, exchange config loading, key rotation,
exchange health endpoint, and ccxt error mapping.
"""

import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    get_all_breakers,
    get_breaker,
    reset_breaker,
)
from market.services.exchange import ExchangeService, _load_db_config

# ── Cache TTL expiry ─────────────────────────────────────────


class TestCacheTTLExpiry:
    """Test the module-level exchange connectivity cache with 30s TTL."""

    @pytest.mark.django_db
    def test_cached_exchange_status_reuses_within_ttl(self):
        """Within TTL window, cached result is returned without re-checking."""
        from trading.views import _exchange_check_cache

        # Save original state
        orig = dict(_exchange_check_cache)
        try:
            # Prime the cache
            _exchange_check_cache["ok"] = True
            _exchange_check_cache["error"] = ""
            _exchange_check_cache["checked_at"] = time.monotonic()

            from trading.views import _get_cached_exchange_status

            ok, error = _get_cached_exchange_status()
            assert ok is True
            assert error == ""
        finally:
            _exchange_check_cache.update(orig)

    @pytest.mark.django_db
    def test_cached_exchange_status_refreshes_after_ttl(self):
        """After TTL expires, the cache is refreshed by calling the exchange."""
        from trading.views import _exchange_check_cache, _exchange_check_ttl

        orig = dict(_exchange_check_cache)
        try:
            # Set checked_at far in the past so TTL is expired
            _exchange_check_cache["ok"] = True
            _exchange_check_cache["error"] = ""
            _exchange_check_cache["checked_at"] = time.monotonic() - _exchange_check_ttl - 10

            mock_exchange = AsyncMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()

            with (
                patch(
                    "market.services.exchange.ExchangeService._get_exchange",
                    new_callable=AsyncMock,
                    return_value=mock_exchange,
                ),
                patch(
                    "market.services.exchange.ExchangeService.close",
                    new_callable=AsyncMock,
                ),
            ):
                from trading.views import _get_cached_exchange_status

                ok, error = _get_cached_exchange_status()
                assert ok is True
        finally:
            _exchange_check_cache.update(orig)

    @pytest.mark.django_db
    def test_cached_exchange_status_records_failure(self):
        """When exchange check fails, the error is cached."""
        from trading.views import _exchange_check_cache, _exchange_check_ttl

        orig = dict(_exchange_check_cache)
        try:
            _exchange_check_cache["checked_at"] = time.monotonic() - _exchange_check_ttl - 10

            mock_exchange = AsyncMock()
            mock_exchange.load_markets = AsyncMock(
                side_effect=Exception("Connection refused"),
            )
            mock_exchange.close = AsyncMock()

            with (
                patch(
                    "market.services.exchange.ExchangeService._get_exchange",
                    new_callable=AsyncMock,
                    return_value=mock_exchange,
                ),
                patch(
                    "market.services.exchange.ExchangeService.close",
                    new_callable=AsyncMock,
                ),
            ):
                from trading.views import _get_cached_exchange_status

                ok, error = _get_cached_exchange_status()
                assert ok is False
                assert "Connection refused" in error
        finally:
            _exchange_check_cache.update(orig)


# ── Cache thread safety ──────────────────────────────────────


class TestCacheThreadSafety:
    """Verify concurrent cache reads/writes do not corrupt state."""

    @pytest.mark.django_db
    def test_concurrent_cache_reads_are_safe(self):
        """Multiple threads reading cache simultaneously should not raise."""
        from trading.views import _exchange_check_cache

        orig = dict(_exchange_check_cache)
        try:
            _exchange_check_cache["ok"] = True
            _exchange_check_cache["error"] = ""
            _exchange_check_cache["checked_at"] = time.monotonic()

            results = []
            errors = []

            def read_cache():
                try:
                    from trading.views import _get_cached_exchange_status

                    ok, error = _get_cached_exchange_status()
                    results.append(ok)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=read_cache) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len(errors) == 0
            assert all(r is True for r in results)
        finally:
            _exchange_check_cache.update(orig)


# ── Circuit breaker state transitions ────────────────────────


class TestCircuitBreakerStateTransitions:
    """Full CLOSED -> OPEN -> HALF_OPEN -> CLOSED cycle."""

    def test_closed_to_open_after_threshold_failures(self):
        """Circuit transitions from CLOSED to OPEN after failure_threshold failures."""
        cb = CircuitBreaker("test-transitions", failure_threshold=3, reset_timeout_seconds=60)

        assert cb._state == CircuitState.CLOSED
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.CLOSED  # still below threshold
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

    def test_open_to_half_open_after_timeout(self):
        """OPEN transitions to HALF_OPEN once reset_timeout_seconds has elapsed."""
        cb = CircuitBreaker("test-open-halfopen", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()
        assert cb._state == CircuitState.OPEN
        assert cb.can_execute() is False

        time.sleep(0.1)
        assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """A success in HALF_OPEN transitions back to CLOSED."""
        cb = CircuitBreaker("test-ho-closed", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()
        time.sleep(0.1)
        cb.can_execute()  # triggers OPEN -> HALF_OPEN
        assert cb._state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_to_open_on_failure(self):
        """A failure in HALF_OPEN transitions back to OPEN."""
        cb = CircuitBreaker("test-ho-open", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()
        time.sleep(0.1)
        cb.can_execute()  # triggers OPEN -> HALF_OPEN

        cb.record_failure()
        assert cb._state == CircuitState.OPEN

    def test_full_recovery_cycle(self):
        """Complete cycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
        cb = CircuitBreaker("test-full-cycle", failure_threshold=2, reset_timeout_seconds=0.05)

        # CLOSED
        assert cb._state == CircuitState.CLOSED
        assert cb.can_execute() is True

        # Trip to OPEN
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.OPEN
        assert cb.can_execute() is False

        # Wait for timeout -> HALF_OPEN
        time.sleep(0.1)
        assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

        # Success -> CLOSED
        cb.record_success()
        assert cb._state == CircuitState.CLOSED
        assert cb.can_execute() is True


# ── Circuit breaker recovery timing ──────────────────────────


class TestCircuitBreakerRecoveryTiming:
    """Verify open-state duration before transitioning to half-open."""

    def test_stays_open_before_timeout(self):
        """Circuit remains OPEN if reset_timeout has not elapsed."""
        cb = CircuitBreaker("test-timing", failure_threshold=1, reset_timeout_seconds=1.0)
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # Immediately check — should still be OPEN
        assert cb.can_execute() is False
        assert cb._state == CircuitState.OPEN

    def test_transitions_after_exact_timeout(self):
        """Circuit transitions to HALF_OPEN once timeout elapses."""
        cb = CircuitBreaker("test-exact-timeout", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()

        time.sleep(0.1)  # well past timeout
        assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

    def test_half_open_limits_concurrent_calls(self):
        """In HALF_OPEN, only half_open_max_calls are allowed."""
        cb = CircuitBreaker(
            "test-ho-limit",
            failure_threshold=1,
            reset_timeout_seconds=0.05,
            half_open_max_calls=1,
        )
        cb.record_failure()
        time.sleep(0.1)

        # First call allowed (transitions to HALF_OPEN)
        assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

        # Increment half_open_calls to simulate an in-flight call
        cb._half_open_calls = 1

        # Second call should be rejected
        assert cb.can_execute() is False


# ── Circuit breaker state-change alerts/logging ──────────────


class TestCircuitBreakerStateAlerts:
    """Verify that state changes produce log messages."""

    def test_closed_to_open_logs_warning(self):
        """CLOSED->OPEN transition should log a WARNING."""
        cb = CircuitBreaker("test-log-open", failure_threshold=2)
        with patch("market.services.circuit_breaker.logger") as mock_logger:
            cb.record_failure()
            cb.record_failure()
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "CLOSED -> OPEN" in call_args[0][0]

    def test_open_to_half_open_logs_info(self):
        """OPEN->HALF_OPEN transition should log an INFO message."""
        cb = CircuitBreaker("test-log-ho", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()
        time.sleep(0.1)
        with patch("market.services.circuit_breaker.logger") as mock_logger:
            cb.can_execute()
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "OPEN -> HALF_OPEN" in call_args[0][0]

    def test_half_open_to_closed_logs_info(self):
        """HALF_OPEN->CLOSED transition should log an INFO message."""
        cb = CircuitBreaker("test-log-close", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()
        time.sleep(0.1)
        cb.can_execute()  # OPEN -> HALF_OPEN
        with patch("market.services.circuit_breaker.logger") as mock_logger:
            cb.record_success()
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "HALF_OPEN -> CLOSED" in call_args[0][0]

    def test_half_open_to_open_logs_warning(self):
        """HALF_OPEN->OPEN transition should log a WARNING."""
        cb = CircuitBreaker("test-log-reopen", failure_threshold=1, reset_timeout_seconds=0.05)
        cb.record_failure()
        time.sleep(0.1)
        cb.can_execute()
        with patch("market.services.circuit_breaker.logger") as mock_logger:
            cb.record_failure()
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "HALF_OPEN -> OPEN" in call_args[0][0]

    def test_manual_reset_logs_info(self):
        """Manual reset should log an INFO message."""
        cb = CircuitBreaker("test-log-reset", failure_threshold=1)
        cb.record_failure()
        with patch("market.services.circuit_breaker.logger") as mock_logger:
            cb.reset()
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "manually reset to CLOSED" in call_args[0][0]


# ── Exchange config loading ──────────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigLoading:
    """Test _load_db_config: DB config, fallback on ImportError, DoesNotExist."""

    def test_returns_none_when_no_default_config(self):
        """With no default config in DB, returns None."""
        result = _load_db_config()
        assert result is None

    def test_returns_default_active_config(self):
        """Returns the default+active config when one exists."""
        from market.models import ExchangeConfig

        config = ExchangeConfig.objects.create(
            name="Default",
            exchange_id="kraken",
            is_default=True,
            is_active=True,
        )
        result = _load_db_config()
        assert result is not None
        assert result.pk == config.pk

    def test_returns_none_for_inactive_default(self):
        """An inactive default config should not be returned."""
        from market.models import ExchangeConfig

        ExchangeConfig.objects.create(
            name="Inactive",
            exchange_id="kraken",
            is_default=True,
            is_active=False,
        )
        result = _load_db_config()
        assert result is None

    def test_returns_specific_config_by_id(self):
        """Loading by config_id returns the specific config."""
        from market.models import ExchangeConfig

        config = ExchangeConfig.objects.create(
            name="Specific",
            exchange_id="binance",
            is_active=True,
        )
        result = _load_db_config(config_id=config.pk)
        assert result is not None
        assert result.exchange_id == "binance"

    def test_returns_none_for_nonexistent_config_id(self):
        """Non-existent config_id returns None."""
        result = _load_db_config(config_id=99999)
        assert result is None

    def test_returns_none_on_import_error(self):
        """When market.models cannot be imported, returns None gracefully."""
        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def failing_import(name, *args, **kwargs):
            if name == "market.models":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=failing_import):
            result = _load_db_config()
            assert result is None

    def test_exchange_service_uses_db_config(self):
        """ExchangeService picks exchange_id from DB config when available."""
        from market.models import ExchangeConfig

        ExchangeConfig.objects.create(
            name="Primary",
            exchange_id="coinbase",
            is_default=True,
            is_active=True,
        )
        service = ExchangeService()
        assert service._exchange_id == "coinbase"

    def test_exchange_service_falls_back_to_settings(self):
        """Without a DB config, ExchangeService uses settings.EXCHANGE_ID."""
        with patch("market.services.exchange.settings") as mock_settings:
            mock_settings.EXCHANGE_ID = "bybit"
            mock_settings.EXCHANGE_API_KEY = ""
            mock_settings.EXCHANGE_API_SECRET = ""
            service = ExchangeService()
            assert service._exchange_id == "bybit"


# ── Key rotation (test-before-apply) ─────────────────────────


@pytest.mark.django_db
class TestKeyRotationLogic:
    """Test the rotate endpoint's test-before-apply pattern."""

    def test_rotate_does_not_apply_on_validation_failure(self, authenticated_client):
        """When new keys fail validation, old keys are preserved."""
        from market.models import ExchangeConfig

        config = ExchangeConfig.objects.create(
            name="Rotate Test",
            exchange_id="binance",
            api_key="old-key-1234567890",
            api_secret="old-secret-1234567890",
            is_active=True,
        )

        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(side_effect=Exception("Bad credentials"))
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            resp = authenticated_client.post(
                f"/api/exchange-configs/{config.pk}/rotate/",
                data={"api_key": "bad-new-key", "api_secret": "bad-new-secret"},
                content_type="application/json",
            )

        assert resp.status_code == 400
        config.refresh_from_db()
        assert config.api_key == "old-key-1234567890"
        assert config.api_secret == "old-secret-1234567890"

    def test_rotate_applies_on_validation_success(self, authenticated_client):
        """When new keys pass validation, they replace the old keys."""
        from market.models import ExchangeConfig

        config = ExchangeConfig.objects.create(
            name="Rotate Apply",
            exchange_id="binance",
            api_key="old-key-abcdefghij",
            api_secret="old-secret-abcdefghij",
            is_active=True,
        )

        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}, "ETH/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            resp = authenticated_client.post(
                f"/api/exchange-configs/{config.pk}/rotate/",
                data={"api_key": "new-key-zyxwvutsrq", "api_secret": "new-secret-zyxwvutsrq"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        config.refresh_from_db()
        assert config.api_key == "new-key-zyxwvutsrq"
        assert config.api_secret == "new-secret-zyxwvutsrq"
        assert config.key_rotated_at is not None


# ── Exchange health endpoint ─────────────────────────────────


@pytest.mark.django_db
class TestExchangeHealthEndpoint:
    """Test GET /api/trading/exchange-health/ latency and state."""

    def test_health_connected(self, authenticated_client):
        """Successful connection returns connected=True with latency."""
        mock_exchange = AsyncMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.close = AsyncMock()

        with (
            patch(
                "market.services.exchange.ExchangeService._get_exchange",
                new_callable=AsyncMock,
                return_value=mock_exchange,
            ),
            patch(
                "market.services.exchange.ExchangeService.close",
                new_callable=AsyncMock,
            ),
        ):
            resp = authenticated_client.get("/api/trading/exchange-health/?exchange_id=kraken")

        assert resp.status_code == 200
        data = resp.json()
        assert data["exchange"] == "kraken"
        assert data["connected"] is True
        assert "latency_ms" in data
        assert data["latency_ms"] >= 0
        assert data["error"] is None

    def test_health_disconnected(self, authenticated_client):
        """Failed connection returns connected=False with error message."""
        mock_exchange = AsyncMock()
        mock_exchange.load_markets = AsyncMock(side_effect=Exception("Timeout connecting"))
        mock_exchange.close = AsyncMock()

        with (
            patch(
                "market.services.exchange.ExchangeService._get_exchange",
                new_callable=AsyncMock,
                return_value=mock_exchange,
            ),
            patch(
                "market.services.exchange.ExchangeService.close",
                new_callable=AsyncMock,
            ),
        ):
            resp = authenticated_client.get("/api/trading/exchange-health/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert "Timeout" in data["error"]

    def test_health_requires_auth(self, api_client):
        """Exchange health endpoint requires authentication."""
        resp = api_client.get("/api/trading/exchange-health/")
        assert resp.status_code in (401, 403)

    def test_health_includes_timestamp(self, authenticated_client):
        """Response includes last_checked ISO timestamp."""
        mock_exchange = AsyncMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.close = AsyncMock()

        with (
            patch(
                "market.services.exchange.ExchangeService._get_exchange",
                new_callable=AsyncMock,
                return_value=mock_exchange,
            ),
            patch(
                "market.services.exchange.ExchangeService.close",
                new_callable=AsyncMock,
            ),
        ):
            resp = authenticated_client.get("/api/trading/exchange-health/")

        data = resp.json()
        assert "last_checked" in data
        assert "T" in data["last_checked"]  # ISO format


# ── ccxt error handling / mapping ────────────────────────────


@pytest.mark.django_db
class TestCcxtErrorMapping:
    """Verify ccxt exceptions are mapped to correct HTTP status codes."""

    def test_request_timeout_returns_408(self, authenticated_client):
        """ccxt.RequestTimeout should return HTTP 408."""
        from ccxt.base.errors import RequestTimeout

        with patch(
            "market.services.data_router.DataServiceRouter.fetch_ticker",
            new_callable=AsyncMock,
            side_effect=RequestTimeout("Timed out"),
        ):
            resp = authenticated_client.get("/api/market/ticker/BTC/USDT/")
        assert resp.status_code == 408

    def test_exchange_not_available_returns_503(self, authenticated_client):
        """ccxt.ExchangeNotAvailable should return HTTP 503."""
        from ccxt.base.errors import ExchangeNotAvailable

        with patch(
            "market.services.data_router.DataServiceRouter.fetch_ticker",
            new_callable=AsyncMock,
            side_effect=ExchangeNotAvailable("Exchange down"),
        ):
            resp = authenticated_client.get("/api/market/ticker/BTC/USDT/")
        assert resp.status_code == 503

    def test_network_error_returns_503(self, authenticated_client):
        """ccxt.NetworkError should return HTTP 503."""
        from ccxt.base.errors import NetworkError

        with patch(
            "market.services.data_router.DataServiceRouter.fetch_ticker",
            new_callable=AsyncMock,
            side_effect=NetworkError("DNS failure"),
        ):
            resp = authenticated_client.get("/api/market/ticker/BTC/USDT/")
        assert resp.status_code == 503

    def test_generic_exception_returns_500(self, authenticated_client):
        """Generic exceptions should return HTTP 500."""
        with patch(
            "market.services.data_router.DataServiceRouter.fetch_ticker",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        ):
            resp = authenticated_client.get("/api/market/ticker/BTC/USDT/")
        assert resp.status_code == 500


# ── Circuit breaker integration with ExchangeService ─────────


class TestCircuitBreakerWithExchangeService:
    """Test circuit breaker behavior when used through ExchangeService."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_ticker_raises_on_open_breaker(self):
        """fetch_ticker raises CircuitBreakerOpenError when breaker is open."""
        service = ExchangeService(exchange_id="test-breaker-svc")

        with patch("market.services.circuit_breaker.get_breaker") as mock_get:
            breaker = MagicMock()
            breaker.can_execute.return_value = False
            breaker.reset_timeout_seconds = 60
            mock_get.return_value = breaker

            with pytest.raises(CircuitBreakerOpenError) as exc_info:
                await service.fetch_ticker("BTC/USDT")
            assert exc_info.value.exchange_id == "test-breaker-svc"
            assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_ohlcv_records_success(self):
        """Successful fetch_ohlcv records success on the breaker."""
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(
            return_value=[
                [1700000000000, 50000.0, 51000.0, 49000.0, 50500.0, 100.0],
            ]
        )

        service = ExchangeService(exchange_id="test-ohlcv-svc")
        service._exchange = mock_exchange

        with patch("market.services.circuit_breaker.get_breaker") as mock_get:
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_get.return_value = breaker

            result = await service.fetch_ohlcv("BTC/USDT", "1h", 100)
            assert len(result) == 1
            breaker.record_success.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_tickers_records_failure_on_exception(self):
        """When fetch_tickers raises, failure is recorded on the breaker."""
        mock_exchange = AsyncMock()
        mock_exchange.fetch_tickers = AsyncMock(side_effect=Exception("API error"))

        service = ExchangeService(exchange_id="test-tickers-fail")
        service._exchange = mock_exchange

        with patch("market.services.circuit_breaker.get_breaker") as mock_get:
            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_get.return_value = breaker

            with pytest.raises(Exception, match="API error"):
                await service.fetch_tickers(["BTC/USDT"])
            breaker.record_failure.assert_called_once()


# ── Circuit breaker registry ─────────────────────────────────


class TestCircuitBreakerRegistry:
    """Test the module-level breaker registry functions."""

    def test_get_breaker_creates_new_instance(self):
        """get_breaker creates a new CircuitBreaker for unknown exchange_id."""
        from market.services import circuit_breaker

        orig = circuit_breaker._breakers.copy()
        circuit_breaker._breakers.clear()
        try:
            breaker = get_breaker("registry-new-test")
            assert isinstance(breaker, CircuitBreaker)
            assert breaker.exchange_id == "registry-new-test"
        finally:
            circuit_breaker._breakers.clear()
            circuit_breaker._breakers.update(orig)

    def test_get_breaker_returns_same_instance(self):
        """Repeated calls to get_breaker return the same instance."""
        from market.services import circuit_breaker

        orig = circuit_breaker._breakers.copy()
        circuit_breaker._breakers.clear()
        try:
            b1 = get_breaker("registry-same-test")
            b2 = get_breaker("registry-same-test")
            assert b1 is b2
        finally:
            circuit_breaker._breakers.clear()
            circuit_breaker._breakers.update(orig)

    def test_reset_breaker_returns_false_for_unknown(self):
        """reset_breaker returns False for an unknown exchange."""
        assert reset_breaker("totally-unknown-exchange-xyz") is False

    def test_reset_breaker_resets_existing(self):
        """reset_breaker resets a known breaker and returns True."""
        from market.services import circuit_breaker

        orig = circuit_breaker._breakers.copy()
        circuit_breaker._breakers.clear()
        try:
            breaker = get_breaker("registry-reset-test")
            breaker.record_failure()
            breaker.record_failure()
            breaker.record_failure()
            breaker.record_failure()
            breaker.record_failure()
            assert breaker._state == CircuitState.OPEN

            result = reset_breaker("registry-reset-test")
            assert result is True
            assert breaker._state == CircuitState.CLOSED
        finally:
            circuit_breaker._breakers.clear()
            circuit_breaker._breakers.update(orig)

    def test_get_all_breakers_returns_states(self):
        """get_all_breakers returns state dicts for all registered breakers."""
        from market.services import circuit_breaker

        orig = circuit_breaker._breakers.copy()
        circuit_breaker._breakers.clear()
        try:
            get_breaker("all-test-a")
            get_breaker("all-test-b")

            states = get_all_breakers()
            assert len(states) == 2
            ids = {s["exchange_id"] for s in states}
            assert "all-test-a" in ids
            assert "all-test-b" in ids
        finally:
            circuit_breaker._breakers.clear()
            circuit_breaker._breakers.update(orig)


# ── CircuitBreakerOpenError ──────────────────────────────────


class TestCircuitBreakerOpenError:
    """Test the custom exception class."""

    def test_error_contains_exchange_id(self):
        """Error message includes the exchange_id."""
        err = CircuitBreakerOpenError("kraken", 60.0)
        assert err.exchange_id == "kraken"
        assert err.retry_after == 60.0
        assert "kraken" in str(err)

    def test_error_contains_retry_after(self):
        """Error message includes the retry-after duration."""
        err = CircuitBreakerOpenError("binance", 120.0)
        assert "120" in str(err)


# ── Circuit breaker thread safety ────────────────────────────


class TestCircuitBreakerThreadSafety:
    """Verify circuit breaker is safe under concurrent access."""

    def test_concurrent_failures_trip_breaker(self):
        """Multiple threads recording failures should safely trip the breaker."""
        cb = CircuitBreaker("thread-safe-test", failure_threshold=10, reset_timeout_seconds=60)
        errors = []

        def record_failures():
            try:
                for _ in range(5):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        # 4 threads x 5 failures = 20, threshold is 10 -> should be OPEN
        assert cb._state == CircuitState.OPEN
        assert cb._failure_count >= 10
