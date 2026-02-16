"""Authentication tests — login, logout, lockout, session management."""

import pytest


@pytest.mark.django_db
class TestAuth:
    def test_health_unauthenticated(self, api_client):
        resp = api_client.get("/api/health/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_auth_status_unauthenticated(self, api_client):
        resp = api_client.get("/api/auth/status/")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False

    def test_login_success(self, api_client, django_user_model):
        django_user_model.objects.create_user(username="testuser", password="testpass123!")
        resp = api_client.post(
            "/api/auth/login/",
            {"username": "testuser", "password": "testpass123!"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"
        assert resp.json()["status"] == "authenticated"

    def test_login_failure(self, api_client, django_user_model):
        django_user_model.objects.create_user(username="testuser", password="testpass123!")
        resp = api_client.post(
            "/api/auth/login/",
            {"username": "testuser", "password": "wrongpassword"},
            format="json",
        )
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_logout(self, authenticated_client):
        resp = authenticated_client.post("/api/auth/logout/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged_out"

    def test_auth_status_authenticated(self, authenticated_client):
        resp = authenticated_client.get("/api/auth/status/")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True
        assert resp.json()["username"] == "testuser"

    def test_protected_endpoint_unauthenticated(self, api_client):
        resp = api_client.get("/api/portfolios/")
        assert resp.status_code == 403

    def test_protected_endpoint_authenticated(self, authenticated_client):
        resp = authenticated_client.get("/api/portfolios/")
        assert resp.status_code == 200

    def test_login_lockout(self, api_client, django_user_model, settings):
        django_user_model.objects.create_user(username="testuser", password="testpass123!")
        settings.LOGIN_MAX_ATTEMPTS = 3
        settings.LOGIN_LOCKOUT_WINDOW = 900

        # Clear any existing lockout state
        from core.auth import _failed_logins
        _failed_logins.clear()

        for _ in range(3):
            api_client.post(
                "/api/auth/login/",
                {"username": "testuser", "password": "wrong"},
                format="json",
            )

        resp = api_client.post(
            "/api/auth/login/",
            {"username": "testuser", "password": "testpass123!"},
            format="json",
        )
        assert resp.status_code == 429
