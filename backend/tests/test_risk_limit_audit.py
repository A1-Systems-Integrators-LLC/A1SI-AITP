"""Tests for P5-3: Risk Limit Audit Trail."""

import pytest
from django.contrib.auth.models import User

from risk.models import RiskLimitChange, RiskLimits
from risk.services.risk import RiskManagementService


@pytest.fixture
def portfolio_id():
    return 99


@pytest.fixture
def limits(portfolio_id):
    return RiskLimits.objects.create(
        portfolio_id=portfolio_id,
        max_portfolio_drawdown=0.15,
        max_daily_loss=0.05,
        max_open_positions=10,
    )


@pytest.fixture
def user():
    return User.objects.create_user("testtrader", password="pass")


# ── Service tests ────────────────────────────────────────────


@pytest.mark.django_db
class TestRiskLimitAuditService:
    def test_creates_change_records(self, portfolio_id, limits):
        RiskManagementService.update_limits(
            portfolio_id,
            {"max_daily_loss": 0.10},
            changed_by="admin",
        )
        assert RiskLimitChange.objects.filter(portfolio_id=portfolio_id).count() == 1

    def test_no_change_no_record(self, portfolio_id, limits):
        RiskManagementService.update_limits(
            portfolio_id,
            {"max_daily_loss": 0.05},  # same as current
        )
        assert RiskLimitChange.objects.filter(portfolio_id=portfolio_id).count() == 0

    def test_old_new_values_correct(self, portfolio_id, limits):
        RiskManagementService.update_limits(
            portfolio_id,
            {"max_daily_loss": 0.10},
        )
        change = RiskLimitChange.objects.filter(portfolio_id=portfolio_id).first()
        assert change.old_value == "0.05"
        assert change.new_value == "0.1"

    def test_changed_by_captured(self, portfolio_id, limits):
        RiskManagementService.update_limits(
            portfolio_id,
            {"max_daily_loss": 0.10},
            changed_by="trader_joe",
        )
        change = RiskLimitChange.objects.filter(portfolio_id=portfolio_id).first()
        assert change.changed_by == "trader_joe"

    def test_reason_captured(self, portfolio_id, limits):
        RiskManagementService.update_limits(
            portfolio_id,
            {"max_daily_loss": 0.10},
            reason="Increased risk tolerance",
        )
        change = RiskLimitChange.objects.filter(portfolio_id=portfolio_id).first()
        assert change.reason == "Increased risk tolerance"

    def test_partial_update_only_logs_changed(self, portfolio_id, limits):
        RiskManagementService.update_limits(
            portfolio_id,
            {"max_daily_loss": 0.10, "max_portfolio_drawdown": 0.15},  # drawdown same
        )
        changes = RiskLimitChange.objects.filter(portfolio_id=portfolio_id)
        assert changes.count() == 1
        assert changes.first().field_name == "max_daily_loss"


# ── API tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestRiskLimitHistoryAPI:
    def test_history_endpoint_returns_200(self, client, user, portfolio_id, limits):
        client.force_login(user)
        resp = client.get(f"/api/risk/{portfolio_id}/limit-history/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_history_after_update(self, client, user, portfolio_id, limits):
        client.force_login(user)
        client.put(
            f"/api/risk/{portfolio_id}/limits/",
            {"max_daily_loss": 0.08},
            content_type="application/json",
        )
        resp = client.get(f"/api/risk/{portfolio_id}/limit-history/")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["field_name"] == "max_daily_loss"

    def test_filter_by_field(self, client, user, portfolio_id, limits):
        client.force_login(user)
        # Create two different changes
        RiskManagementService.update_limits(portfolio_id, {"max_daily_loss": 0.10})
        RiskManagementService.update_limits(portfolio_id, {"max_open_positions": 20})

        resp = client.get(
            f"/api/risk/{portfolio_id}/limit-history/?field=max_daily_loss",
        )
        data = resp.json()
        assert len(data) == 1
        assert data[0]["field_name"] == "max_daily_loss"

    def test_portfolio_isolation(self, client, user, portfolio_id, limits):
        client.force_login(user)
        # Create change on a different portfolio
        RiskLimits.objects.create(portfolio_id=200, max_daily_loss=0.05)
        RiskManagementService.update_limits(200, {"max_daily_loss": 0.10})

        resp = client.get(f"/api/risk/{portfolio_id}/limit-history/")
        assert len(resp.json()) == 0

    def test_auth_required(self, client, portfolio_id):
        resp = client.get(f"/api/risk/{portfolio_id}/limit-history/")
        assert resp.status_code in (401, 403)

    def test_reason_from_request(self, client, user, portfolio_id, limits):
        client.force_login(user)
        client.put(
            f"/api/risk/{portfolio_id}/limits/",
            {"max_daily_loss": 0.08, "reason": "Tightening limits"},
            content_type="application/json",
        )
        resp = client.get(f"/api/risk/{portfolio_id}/limit-history/")
        data = resp.json()
        assert data[0]["reason"] == "Tightening limits"

    def test_changed_by_from_user(self, client, user, portfolio_id, limits):
        client.force_login(user)
        client.put(
            f"/api/risk/{portfolio_id}/limits/",
            {"max_daily_loss": 0.08},
            content_type="application/json",
        )
        resp = client.get(f"/api/risk/{portfolio_id}/limit-history/")
        data = resp.json()
        assert data[0]["changed_by"] == "testtrader"


# ── Model tests ──────────────────────────────────────────────


@pytest.mark.django_db
class TestRiskLimitChangeModel:
    def test_ordering(self, portfolio_id):
        RiskLimitChange.objects.create(
            portfolio_id=portfolio_id,
            field_name="max_daily_loss",
            old_value="0.05",
            new_value="0.10",
        )
        RiskLimitChange.objects.create(
            portfolio_id=portfolio_id,
            field_name="max_open_positions",
            old_value="10",
            new_value="20",
        )
        changes = list(RiskLimitChange.objects.filter(portfolio_id=portfolio_id))
        # Most recent first
        assert changes[0].field_name == "max_open_positions"

    def test_str_representation(self, portfolio_id):
        change = RiskLimitChange.objects.create(
            portfolio_id=portfolio_id,
            field_name="max_daily_loss",
            old_value="0.05",
            new_value="0.10",
        )
        assert "max_daily_loss" in str(change)
        assert "0.05" in str(change)
        assert "0.10" in str(change)

    def test_index_exists(self):
        names = {idx.name for idx in RiskLimitChange._meta.indexes}
        assert "idx_risklimitchange_port_time" in names
