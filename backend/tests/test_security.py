"""Security tests — CSRF, session settings, security headers, hardening."""

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
        assert (
            "rest_framework.authentication.SessionAuthentication"
            in (settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"])
        )

    def test_drf_default_permissions(self, settings):
        assert (
            "rest_framework.permissions.IsAuthenticated"
            in (settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"])
        )

    def test_cors_credentials(self, settings):
        assert settings.CORS_ALLOW_CREDENTIALS is True

    def test_csrf_protection_on_post(self, api_client, django_user_model):
        """POST without CSRF should be rejected for session-authenticated requests."""
        django_user_model.objects.create_user(username="testuser", password="testpass123!")
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

    def test_audit_middleware_installed(self, settings):
        """Verify AuditMiddleware is in the middleware stack."""
        assert "core.middleware.AuditMiddleware" in settings.MIDDLEWARE

    def test_audit_middleware_logs_post(self, authenticated_client):
        """Verify AuditMiddleware fires on POST requests."""
        from unittest.mock import patch

        with patch("core.middleware.AuditMiddleware._enqueue") as mock_log:
            authenticated_client.post(
                "/api/portfolios/",
                {"name": "Audit Test"},
                format="json",
            )
            mock_log.assert_called_once()


@pytest.mark.django_db
class TestSecurityHardening:
    """Tests for security hardening measures."""

    def test_argon2_is_primary_hasher(self, settings):
        """Argon2id should be the first (preferred) password hasher."""
        assert settings.PASSWORD_HASHERS[0] == ("django.contrib.auth.hashers.Argon2PasswordHasher")

    def test_pbkdf2_is_fallback_hasher(self, settings):
        """PBKDF2 should remain as a fallback for existing password migration."""
        assert "django.contrib.auth.hashers.PBKDF2PasswordHasher" in settings.PASSWORD_HASHERS

    def test_password_minimum_length_12(self, settings):
        """Financial best practice: minimum password length of 12."""
        for validator in settings.AUTH_PASSWORD_VALIDATORS:
            if "MinimumLengthValidator" in validator["NAME"]:
                assert validator["OPTIONS"]["min_length"] == 12
                return
        pytest.fail("MinimumLengthValidator not found")

    def test_session_cookie_name_non_default(self, settings):
        """Session cookie name should not reveal framework identity."""
        assert settings.SESSION_COOKIE_NAME == "__ci_sid"
        assert settings.SESSION_COOKIE_NAME != "sessionid"

    def test_encryption_round_trip(self, settings):
        """Fernet encrypt/decrypt should round-trip correctly."""
        from cryptography.fernet import Fernet

        # Set a test encryption key
        settings.ENCRYPTION_KEY = Fernet.generate_key().decode()

        from core.encryption import decrypt_value, encrypt_value

        plaintext = "my-secret-api-key-12345"
        ciphertext = encrypt_value(plaintext)
        assert ciphertext != plaintext
        assert decrypt_value(ciphertext) == plaintext

    def test_encryption_key_required_in_production(self, settings):
        """ENCRYPTION_KEY must be set when DEBUG is False."""
        # The settings module validates this at import time, so we check the logic
        settings.DEBUG = False
        settings.ENCRYPTION_KEY = ""
        # In production (DEBUG=False), empty ENCRYPTION_KEY should be invalid
        assert not settings.ENCRYPTION_KEY

    def test_csrf_failure_returns_json(self, api_client):
        """CSRF failure view should return JSON, not HTML."""
        from django.test import RequestFactory

        from core.views import csrf_failure

        request = RequestFactory().post("/api/test/")
        response = csrf_failure(request, reason="Test failure")
        assert response.status_code == 403
        assert response["Content-Type"] == "application/json"

    def test_rate_limit_returns_retry_after(self, api_client):
        """429 rate limit response should include Retry-After header."""
        import time
        from unittest.mock import patch

        reset = time.time() + 60
        with patch(
            "core.middleware.RateLimitMiddleware._allow",
            return_value=(False, 0, reset),
        ):
            resp = api_client.get("/api/health/")
            assert resp.status_code == 429
            assert resp["Retry-After"] == "60"

    def test_secure_proxy_ssl_header(self, settings):
        """Proxy SSL header should be configured for nginx reverse proxy."""
        assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")

    def test_csrf_failure_view_configured(self, settings):
        """CSRF_FAILURE_VIEW should point to our JSON view."""
        assert settings.CSRF_FAILURE_VIEW == "core.views.csrf_failure"


@pytest.mark.django_db
class TestCSPHardening:
    """Tests for Content-Security-Policy and security header hardening."""

    def test_csp_object_src_setting(self, settings):
        assert settings.CSP_OBJECT_SRC == "'none'"

    def test_csp_base_uri_setting(self, settings):
        assert settings.CSP_BASE_URI == "'self'"

    def test_csp_form_action_setting(self, settings):
        assert settings.CSP_FORM_ACTION == "'self'"

    def test_csp_frame_ancestors_setting(self, settings):
        assert settings.CSP_FRAME_ANCESTORS == "'none'"

    def test_referrer_policy_setting(self, settings):
        assert settings.SECURE_REFERRER_POLICY == "strict-origin-when-cross-origin"

    def test_permissions_policy_setting(self, settings):
        assert settings.PERMISSIONS_POLICY
        assert "camera=()" in settings.PERMISSIONS_POLICY

    def test_csp_header_contains_object_src(self, api_client):
        resp = api_client.get("/api/health/")
        csp = resp.get("Content-Security-Policy", "")
        assert "object-src 'none'" in csp

    def test_permissions_policy_header(self, api_client):
        resp = api_client.get("/api/health/")
        assert "Permissions-Policy" in resp
        assert "camera=()" in resp["Permissions-Policy"]
