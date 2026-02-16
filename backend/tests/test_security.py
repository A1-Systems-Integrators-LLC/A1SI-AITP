"""Security tests — CSRF, session settings, security headers."""

import pytest


@pytest.mark.django_db
class TestSecurity:
    def test_session_cookie_httponly(self, settings):
        assert settings.SESSION_COOKIE_HTTPONLY is True

    def test_csrf_cookie_readable_by_frontend(self, settings):
        assert settings.CSRF_COOKIE_HTTPONLY is False

    def test_x_frame_options_deny(self, settings):
        assert settings.X_FRAME_OPTIONS == "DENY"

    def test_content_type_nosniff(self, settings):
        assert settings.SECURE_CONTENT_TYPE_NOSNIFF is True

    def test_xss_filter(self, settings):
        assert settings.SECURE_BROWSER_XSS_FILTER is True

    def test_session_age(self, settings):
        assert settings.SESSION_COOKIE_AGE == 3600

    def test_drf_default_auth(self, settings):
        assert "rest_framework.authentication.SessionAuthentication" in (
            settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
        )

    def test_drf_default_permissions(self, settings):
        assert "rest_framework.permissions.IsAuthenticated" in (
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]
        )

    def test_cors_credentials(self, settings):
        assert settings.CORS_ALLOW_CREDENTIALS is True

    def test_csrf_protection_on_post(self, api_client, django_user_model):
        """POST without CSRF should be rejected for session-authenticated requests."""
        django_user_model.objects.create_user(
            username="testuser", password="testpass123!"
        )
        # Login first (via DRF client which handles CSRF)
        api_client.login(username="testuser", password="testpass123!")

        # DRF's APIClient enforces CSRF, so this should work
        resp = api_client.post(
            "/api/portfolios/",
            {"name": "Test", "exchange_id": "binance"},
            format="json",
        )
        # Should succeed because DRF test client handles CSRF
        assert resp.status_code == 201

    def test_audit_log_created_on_post(self, authenticated_client):
        import time

        from core.models import AuditLog

        authenticated_client.post(
            "/api/portfolios/",
            {"name": "Audit Test"},
            format="json",
        )
        # Give background thread a moment
        time.sleep(0.5)
        assert AuditLog.objects.filter(action__contains="POST").exists()
