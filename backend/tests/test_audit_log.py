"""Audit log API tests."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import AuditLog


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="auditor", password="pass")


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestAuditLogAPI:
    def test_list_empty(self, auth_client):
        AuditLog.objects.all().delete()
        resp = auth_client.get("/api/audit-log/")
        assert resp.status_code == 200
        data = resp.json()
        # The GET itself may be logged by AuditMiddleware; just check structure
        assert "results" in data
        assert "total" in data

    def test_list_with_data(self, auth_client):
        AuditLog.objects.all().delete()
        AuditLog.objects.create(user="admin", action="GET /api/health/", status_code=200)
        AuditLog.objects.create(user="admin", action="POST /api/trading/orders/", status_code=201)
        resp = auth_client.get("/api/audit-log/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_filter_by_user(self, auth_client):
        AuditLog.objects.create(user="admin", action="GET /", status_code=200)
        AuditLog.objects.create(user="trader", action="GET /", status_code=200)
        resp = auth_client.get("/api/audit-log/?user=admin")
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["user"] == "admin"

    def test_filter_by_status_code(self, auth_client):
        AuditLog.objects.create(user="admin", action="GET /ok", status_code=200)
        AuditLog.objects.create(user="admin", action="GET /fail", status_code=500)
        resp = auth_client.get("/api/audit-log/?status_code=500")
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["status_code"] == 500

    def test_filter_by_date_range(self, auth_client):
        AuditLog.objects.all().delete()
        now = timezone.now()
        old = AuditLog.objects.create(user="admin", action="old", status_code=200)
        old.created_at = now - timedelta(days=7)
        old.save(update_fields=["created_at"])

        AuditLog.objects.create(user="admin", action="new", status_code=200)

        after = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = auth_client.get(f"/api/audit-log/?created_after={after}")
        data = resp.json()
        # The GET itself is also recent, so we check the old entry is excluded
        actions = [r["action"] for r in data["results"]]
        assert "old" not in actions
        assert "new" in actions

    def test_auth_required(self, client):
        resp = client.get("/api/audit-log/")
        assert resp.status_code in (401, 403)
