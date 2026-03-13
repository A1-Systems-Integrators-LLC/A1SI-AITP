"""Tests for ExchangeConfig and DataSourceConfig — encryption, API security, CRUD."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.db import connection

from market.fields import EncryptedTextField
from market.models import DataSourceConfig, ExchangeConfig

# ── EncryptedTextField ───────────────────────────────────────


@pytest.mark.django_db
class TestEncryptedTextField:
    def test_round_trip(self):
        """Value is decrypted when read back from DB."""
        config = ExchangeConfig.objects.create(
            name="Test", exchange_id="binance", api_key="my-secret-key-12345",
        )
        config.refresh_from_db()
        assert config.api_key == "my-secret-key-12345"

    def test_raw_db_value_is_ciphertext(self):
        """Raw database value should be encrypted, not plaintext."""
        config = ExchangeConfig.objects.create(
            name="Test", exchange_id="binance", api_key="plaintext-secret",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT api_key FROM market_exchangeconfig WHERE id = %s",
                [config.pk],
            )
            raw_value = cursor.fetchone()[0]
        assert raw_value != "plaintext-secret"
        assert raw_value != ""
        # Fernet tokens start with gAAAAA
        assert raw_value.startswith("gAAAAA")

    def test_empty_string_not_encrypted(self):
        """Empty strings should pass through unchanged."""
        config = ExchangeConfig.objects.create(name="Test", exchange_id="binance", api_key="")
        config.refresh_from_db()
        assert config.api_key == ""

    def test_none_not_encrypted(self):
        """None should pass through unchanged."""
        field = EncryptedTextField()
        assert field.get_prep_value(None) is None


# ── API Security ─────────────────────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigAPISecurity:
    def test_credentials_not_in_response(self, authenticated_client):
        """API response must never contain raw credentials."""
        ExchangeConfig.objects.create(
            name="Test",
            exchange_id="binance",
            api_key="super-secret-key-abc123",
            api_secret="super-secret-secret-xyz",
            passphrase="my-passphrase",
        )
        resp = authenticated_client.get("/api/exchange-configs/")
        assert resp.status_code == 200
        data = resp.json()[0]
        assert "api_key" not in data
        assert "api_secret" not in data
        assert "passphrase" not in data

    def test_masked_key_format(self, authenticated_client):
        """Masked key should show first4****last4."""
        ExchangeConfig.objects.create(
            name="Test",
            exchange_id="binance",
            api_key="abcdefghijklmnop",
        )
        resp = authenticated_client.get("/api/exchange-configs/")
        data = resp.json()[0]
        assert data["api_key_masked"] == "abcd****mnop"

    def test_short_key_masked_as_stars(self, authenticated_client):
        """Keys 8 chars or fewer are masked as ****."""
        ExchangeConfig.objects.create(name="Test", exchange_id="binance", api_key="short")
        resp = authenticated_client.get("/api/exchange-configs/")
        data = resp.json()[0]
        assert data["api_key_masked"] == "****"

    def test_has_credential_booleans(self, authenticated_client):
        """has_api_key, has_api_secret, has_passphrase booleans exposed."""
        ExchangeConfig.objects.create(
            name="Test",
            exchange_id="binance",
            api_key="key123456789",
            api_secret="secret123",
        )
        resp = authenticated_client.get("/api/exchange-configs/")
        data = resp.json()[0]
        assert data["has_api_key"] is True
        assert data["has_api_secret"] is True
        assert data["has_passphrase"] is False

    def test_unauthenticated_returns_401(self, api_client):
        """Unauthenticated requests should return 401 or 403."""
        resp = api_client.get("/api/exchange-configs/")
        assert resp.status_code in (401, 403)


# ── CRUD ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigCRUD:
    def test_create(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/exchange-configs/",
            {"name": "My Binance", "exchange_id": "binance", "api_key": "key123456789"},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Binance"
        assert data["exchange_id"] == "binance"
        assert data["is_sandbox"] is True  # safe default
        assert "api_key" not in data

    def test_list(self, authenticated_client):
        ExchangeConfig.objects.create(name="A", exchange_id="binance")
        ExchangeConfig.objects.create(name="B", exchange_id="kraken")
        resp = authenticated_client.get("/api/exchange-configs/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_detail(self, authenticated_client):
        config = ExchangeConfig.objects.create(name="A", exchange_id="binance")
        resp = authenticated_client.get(f"/api/exchange-configs/{config.pk}/")
        assert resp.status_code == 200
        assert resp.json()["name"] == "A"

    def test_update(self, authenticated_client):
        config = ExchangeConfig.objects.create(
            name="Old", exchange_id="binance", api_key="original-key-1234",
        )
        resp = authenticated_client.put(
            f"/api/exchange-configs/{config.pk}/",
            {"name": "New Name"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_partial_update_preserves_credentials(self, authenticated_client):
        """Updating name without sending credentials should keep them."""
        config = ExchangeConfig.objects.create(
            name="Old",
            exchange_id="binance",
            api_key="keep-this-key-123",
            api_secret="keep-this-secret",
        )
        authenticated_client.put(
            f"/api/exchange-configs/{config.pk}/",
            {"name": "New Name"},
            format="json",
        )
        config.refresh_from_db()
        assert config.api_key == "keep-this-key-123"
        assert config.api_secret == "keep-this-secret"

    def test_delete(self, authenticated_client):
        config = ExchangeConfig.objects.create(name="Delete Me", exchange_id="binance")
        resp = authenticated_client.delete(f"/api/exchange-configs/{config.pk}/")
        assert resp.status_code == 204
        assert not ExchangeConfig.objects.filter(pk=config.pk).exists()

    def test_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/exchange-configs/9999/")
        assert resp.status_code == 404


# ── Default uniqueness ───────────────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigDefault:
    def test_only_one_default(self):
        """Setting a new default should unset the previous one."""
        a = ExchangeConfig.objects.create(name="A", exchange_id="binance", is_default=True)
        b = ExchangeConfig.objects.create(name="B", exchange_id="kraken", is_default=True)
        a.refresh_from_db()
        assert a.is_default is False
        assert b.is_default is True


# ── Connectivity test ────────────────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigTest:
    def test_test_endpoint(self, authenticated_client):
        config = ExchangeConfig.objects.create(
            name="Test", exchange_id="binance", api_key="key123456789",
        )

        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}, "ETH/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            resp = authenticated_client.post(f"/api/exchange-configs/{config.pk}/test/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["markets_count"] == 2

    def test_test_endpoint_not_found(self, authenticated_client):
        resp = authenticated_client.post("/api/exchange-configs/9999/test/")
        assert resp.status_code == 404


# ── Data Sources ─────────────────────────────────────────────


@pytest.mark.django_db
class TestDataSourceConfig:
    def test_create(self, authenticated_client):
        config = ExchangeConfig.objects.create(name="Binance", exchange_id="binance")
        resp = authenticated_client.post(
            "/api/data-sources/",
            {
                "exchange_config": config.pk,
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "timeframes": ["1h", "4h"],
                "fetch_interval_minutes": 30,
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbols"] == ["BTC/USDT", "ETH/USDT"]
        assert data["timeframes"] == ["1h", "4h"]
        assert data["exchange_name"] == "Binance"

    def test_list(self, authenticated_client):
        config = ExchangeConfig.objects.create(name="Binance", exchange_id="binance")
        DataSourceConfig.objects.create(
            exchange_config=config, symbols=["BTC/USDT"], timeframes=["1h"],
        )
        resp = authenticated_client.get("/api/data-sources/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_cascade_delete(self):
        """Deleting an exchange config should delete its data sources."""
        config = ExchangeConfig.objects.create(name="Binance", exchange_id="binance")
        DataSourceConfig.objects.create(
            exchange_config=config, symbols=["BTC/USDT"], timeframes=["1h"],
        )
        config.delete()
        assert DataSourceConfig.objects.count() == 0

    def test_delete(self, authenticated_client):
        config = ExchangeConfig.objects.create(name="Binance", exchange_id="binance")
        ds = DataSourceConfig.objects.create(
            exchange_config=config, symbols=["BTC/USDT"], timeframes=["1h"],
        )
        resp = authenticated_client.delete(f"/api/data-sources/{ds.pk}/")
        assert resp.status_code == 204


# ── Key Rotation ────────────────────────────────────────────


@pytest.fixture
def exchange_config_for_rotation(db):
    return ExchangeConfig.objects.create(
        name="Test Exchange",
        exchange_id="binance",
        api_key="old-api-key-12345678",
        api_secret="old-api-secret-12345678",
        passphrase="",
        is_sandbox=True,
        is_default=True,
        is_active=True,
    )


@pytest.mark.django_db
class TestExchangeConfigRotation:
    def test_rotate_requires_auth(self, api_client, exchange_config_for_rotation):
        resp = api_client.post(
            f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
            data={"api_key": "new-key", "api_secret": "new-secret"},
            content_type="application/json",
        )
        assert resp.status_code in (401, 403)

    def test_rotate_404_for_missing_config(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/exchange-configs/99999/rotate/",
            data={"api_key": "new-key", "api_secret": "new-secret"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_rotate_validates_new_keys_first(
        self, authenticated_client, exchange_config_for_rotation,
    ):
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            resp = authenticated_client.post(
                f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
                data={"api_key": "new-key", "api_secret": "new-secret"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_rotate_fails_if_new_keys_invalid(
        self, authenticated_client, exchange_config_for_rotation,
    ):
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(side_effect=Exception("Invalid API key"))
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            resp = authenticated_client.post(
                f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
                data={"api_key": "bad-key", "api_secret": "bad-secret"},
                content_type="application/json",
            )
        assert resp.status_code == 400
        assert "validation failed" in resp.json()["error"].lower()

    def test_rotate_updates_keys_on_success(
        self, authenticated_client, exchange_config_for_rotation,
    ):
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            authenticated_client.post(
                f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
                data={"api_key": "new-key-123-abcde", "api_secret": "new-secret-456-abcde"},
                content_type="application/json",
            )

        exchange_config_for_rotation.refresh_from_db()
        assert exchange_config_for_rotation.api_key == "new-key-123-abcde"
        assert exchange_config_for_rotation.api_secret == "new-secret-456-abcde"

    def test_rotate_sets_rotated_at_timestamp(
        self, authenticated_client, exchange_config_for_rotation,
    ):
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        assert exchange_config_for_rotation.key_rotated_at is None

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            authenticated_client.post(
                f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
                data={"api_key": "new-key", "api_secret": "new-secret"},
                content_type="application/json",
            )

        exchange_config_for_rotation.refresh_from_db()
        assert exchange_config_for_rotation.key_rotated_at is not None

    def test_rotate_creates_audit_log_entry(
        self, authenticated_client, exchange_config_for_rotation,
    ):
        from risk.models import AlertLog

        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        initial_count = AlertLog.objects.filter(event_type="key_rotation").count()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            authenticated_client.post(
                f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
                data={"api_key": "new-key", "api_secret": "new-secret"},
                content_type="application/json",
            )

        assert AlertLog.objects.filter(event_type="key_rotation").count() == initial_count + 1

    def test_rotate_preserves_old_keys_on_failure(
        self, authenticated_client, exchange_config_for_rotation,
    ):
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(side_effect=Exception("Connection failed"))
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        old_key = exchange_config_for_rotation.api_key
        old_secret = exchange_config_for_rotation.api_secret

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            authenticated_client.post(
                f"/api/exchange-configs/{exchange_config_for_rotation.pk}/rotate/",
                data={"api_key": "bad-key", "api_secret": "bad-secret"},
                content_type="application/json",
            )

        exchange_config_for_rotation.refresh_from_db()
        assert exchange_config_for_rotation.api_key == old_key
        assert exchange_config_for_rotation.api_secret == old_secret


# ── Connection test (failure) ───────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigTestFailure:
    def test_test_connection_ccxt_error(self, authenticated_client):
        """When ccxt raises during load_markets, test returns 400 with error."""
        config = ExchangeConfig.objects.create(
            name="Fail Test", exchange_id="binance", api_key="key123456789",
        )

        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(
            side_effect=Exception("AuthenticationError: invalid key"),
        )
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            resp = authenticated_client.post(f"/api/exchange-configs/{config.pk}/test/")

        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "AuthenticationError" in data["message"]

    def test_test_connection_updates_db_fields(self, authenticated_client):
        """Test endpoint should update last_tested_at and last_test_success fields."""
        config = ExchangeConfig.objects.create(
            name="DB Update", exchange_id="binance", api_key="key123456789",
        )
        assert config.last_tested_at is None

        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.close = AsyncMock()
        mock_exchange.set_sandbox_mode = MagicMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            authenticated_client.post(f"/api/exchange-configs/{config.pk}/test/")

        config.refresh_from_db()
        assert config.last_tested_at is not None
        assert config.last_test_success is True
        assert config.last_test_error == ""


# ── Additional CRUD edge cases ──────────────────────────────


@pytest.mark.django_db
class TestExchangeConfigCRUDExtra:
    def test_create_default_is_sandbox(self, authenticated_client):
        """New configs should default to sandbox=True for safety."""
        resp = authenticated_client.post(
            "/api/exchange-configs/",
            {"name": "Safe Config", "exchange_id": "kraken"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["is_sandbox"] is True

    def test_list_empty(self, authenticated_client):
        """Empty exchange config list returns empty array."""
        resp = authenticated_client.get("/api/exchange-configs/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_update_name_only(self, authenticated_client):
        """Updating just the name should preserve everything else."""
        config = ExchangeConfig.objects.create(
            name="Before", exchange_id="binance", is_sandbox=True, is_active=True,
        )
        resp = authenticated_client.put(
            f"/api/exchange-configs/{config.pk}/",
            {"name": "After"},
            format="json",
        )
        assert resp.status_code == 200
        config.refresh_from_db()
        assert config.name == "After"
        assert config.is_sandbox is True
        assert config.is_active is True

    def test_delete_nonexistent_returns_404(self, authenticated_client):
        """Deleting a non-existent config returns 404."""
        resp = authenticated_client.delete("/api/exchange-configs/99999/")
        assert resp.status_code == 404

    def test_update_nonexistent_returns_404(self, authenticated_client):
        """Updating a non-existent config returns 404."""
        resp = authenticated_client.put(
            "/api/exchange-configs/99999/",
            {"name": "Nope"},
            format="json",
        )
        assert resp.status_code == 404

    def test_multiple_defaults_only_last_wins(self, authenticated_client):
        """Creating multiple default configs — only the last should be default."""
        a = ExchangeConfig.objects.create(name="A", exchange_id="binance", is_default=True)
        b = ExchangeConfig.objects.create(name="B", exchange_id="kraken", is_default=True)
        c = ExchangeConfig.objects.create(name="C", exchange_id="coinbase", is_default=True)
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.is_default is False
        assert b.is_default is False
        assert c.is_default is True

    def test_test_requires_auth(self, api_client):
        """Test endpoint requires authentication."""
        config = ExchangeConfig.objects.create(name="Auth Test", exchange_id="binance")
        resp = api_client.post(f"/api/exchange-configs/{config.pk}/test/")
        assert resp.status_code in (401, 403)

    def test_create_with_credentials_masked_in_response(self, authenticated_client):
        """Created config response should not include raw credentials."""
        resp = authenticated_client.post(
            "/api/exchange-configs/",
            {
                "name": "Masked",
                "exchange_id": "binance",
                "api_key": "super-secret-key-12345",
                "api_secret": "super-secret-secret-67890",
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        # Raw credentials should not be in the response
        assert "super-secret-key-12345" not in str(data)
        assert "super-secret-secret-67890" not in str(data)
