"""Phase 11: 100% coverage for backend/config/ and manage.py."""

import importlib
import os
import sys
import warnings
from unittest import mock

import pytest


# ── config/urls.py ───────────────────────────────────────────────
class TestConfigUrls:
    """urls.py is loaded by Django — verify urlpatterns exist."""

    def test_urlpatterns_loaded(self):
        from config import urls

        assert hasattr(urls, "urlpatterns")
        assert len(urls.urlpatterns) > 0

    def test_api_routes_present(self):
        from config import urls

        paths = [str(p.pattern) for p in urls.urlpatterns]
        assert "api/" in paths
        assert "metrics/" in paths


# ── config/asgi.py ───────────────────────────────────────────────
class TestConfigAsgi:
    """ASGI application object is created with ProtocolTypeRouter."""

    def test_asgi_application_exists(self):
        from config import asgi

        assert hasattr(asgi, "application")

    def test_asgi_application_is_protocol_router(self):
        from config.asgi import application

        # ProtocolTypeRouter wraps http + websocket
        assert application is not None


# ── config/wsgi.py ───────────────────────────────────────────────
class TestConfigWsgi:
    """WSGI application object."""

    def test_wsgi_application_exists(self):
        from config import wsgi

        assert hasattr(wsgi, "application")
        assert wsgi.application is not None


# ── config/settings.py — production guards ───────────────────────
class TestSettingsProductionGuards:
    """Lines 29, 31: ValueError when DEBUG=False and secrets not set."""

    def test_secret_key_required_in_production(self):
        """Line 29: raises ValueError when DEBUG=False and default SECRET_KEY."""
        env = {
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "insecure-dev-key-change-me",
            "DJANGO_ENCRYPTION_KEY": "some-key",
        }
        with (
            mock.patch.dict(os.environ, env, clear=False),
            pytest.raises(ValueError, match="DJANGO_SECRET_KEY must be set"),
        ):
            importlib.reload(importlib.import_module("config.settings"))

    def test_encryption_key_required_in_production(self):
        """Line 31: raises ValueError when DEBUG=False and no ENCRYPTION_KEY."""
        env = {
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "a-real-secret-key-for-testing-1234",
            "DJANGO_ENCRYPTION_KEY": "",
        }
        with (
            mock.patch.dict(os.environ, env, clear=False),
            pytest.raises(ValueError, match="DJANGO_ENCRYPTION_KEY must be set"),
        ):
            importlib.reload(importlib.import_module("config.settings"))

    def test_hsts_settings_when_not_debug(self):
        """Lines 167-170: HSTS/SSL settings are set when DEBUG=False."""
        env = {
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "a-real-secret-key-for-testing-1234",
            "DJANGO_ENCRYPTION_KEY": "a-real-encryption-key-1234",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            mod = importlib.reload(importlib.import_module("config.settings"))
            assert mod.SECURE_HSTS_SECONDS == 31536000
            assert mod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
            assert mod.SECURE_HSTS_PRELOAD is True
            assert isinstance(mod.SECURE_SSL_REDIRECT, bool)

    def test_exchange_api_key_deprecation_warning(self):
        """Lines 264-266: warns when EXCHANGE_API_KEY is set (non-test)."""
        env = {
            "DJANGO_DEBUG": "true",
            "EXCHANGE_API_KEY": "test-api-key-abc123",
        }
        # Temporarily remove 'pytest' from sys.modules so TESTING=False
        pytest_mod = sys.modules.pop("pytest", None)
        original_argv = sys.argv
        sys.argv = ["manage.py", "runserver"]
        try:
            with (
                mock.patch.dict(os.environ, env, clear=False),
                warnings.catch_warnings(record=True) as w,
            ):
                warnings.simplefilter("always")
                importlib.reload(importlib.import_module("config.settings"))
                deprecation_warnings = [
                    x for x in w if issubclass(x.category, DeprecationWarning)
                ]
                assert len(deprecation_warnings) >= 1
                assert "EXCHANGE_API_KEY" in str(deprecation_warnings[0].message)
        finally:
            sys.argv = original_argv
            if pytest_mod is not None:
                sys.modules["pytest"] = pytest_mod
            # Reload settings back to test mode
            importlib.reload(importlib.import_module("config.settings"))


# ── manage.py ────────────────────────────────────────────────────
class TestManagePy:
    """manage.py main() function."""

    def test_main_calls_execute(self):
        """manage.py main() delegates to execute_from_command_line."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        try:
            import manage

            with mock.patch("django.core.management.execute_from_command_line") as mock_exec:
                manage.main()
                mock_exec.assert_called_once()
        finally:
            sys.path.pop(0)

    def test_main_sets_settings_module(self):
        """manage.py main() sets DJANGO_SETTINGS_MODULE."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        old_val = os.environ.pop("DJANGO_SETTINGS_MODULE", None)
        try:
            import manage

            with mock.patch("django.core.management.execute_from_command_line"):
                manage.main()
                assert os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings"
        finally:
            sys.path.pop(0)
            if old_val is not None:
                os.environ["DJANGO_SETTINGS_MODULE"] = old_val
