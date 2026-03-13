"""Alert filtering and order CSV export tests."""

from datetime import datetime, timedelta, timezone

import pytest

from risk.models import AlertLog
from trading.models import Order, OrderStatus


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="alert_user", password="pass")


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


def _create_alert(portfolio_id=1, severity="info", event_type="test", message="test alert"):
    return AlertLog.objects.create(
        portfolio_id=portfolio_id,
        severity=severity,
        event_type=event_type,
        message=message,
        channel="log",
        delivered=True,
        error="",
    )


@pytest.mark.django_db
class TestAlertFiltering:
    def test_filter_by_severity(self, auth_client):
        _create_alert(severity="info")
        _create_alert(severity="warning")
        _create_alert(severity="critical")
        resp = auth_client.get("/api/risk/1/alerts/?severity=warning")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["severity"] == "warning"

    def test_filter_by_event_type(self, auth_client):
        _create_alert(event_type="kill_switch_halt")
        _create_alert(event_type="trade_rejected")
        resp = auth_client.get("/api/risk/1/alerts/?event_type=kill_switch")
        data = resp.json()
        assert len(data) == 1
        assert "kill_switch" in data[0]["event_type"]

    def test_filter_by_date_range(self, auth_client):
        old = _create_alert(event_type="old_alert")
        old.created_at = datetime.now(timezone.utc) - timedelta(days=7)
        old.save(update_fields=["created_at"])

        _create_alert(event_type="new_alert")

        after = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = auth_client.get(f"/api/risk/1/alerts/?created_after={after}")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "new_alert"

    def test_combined_filters(self, auth_client):
        _create_alert(severity="critical", event_type="halt")
        _create_alert(severity="info", event_type="halt")
        _create_alert(severity="critical", event_type="other")
        resp = auth_client.get("/api/risk/1/alerts/?severity=critical&event_type=halt")
        data = resp.json()
        assert len(data) == 1


@pytest.mark.django_db
class TestOrderExport:
    def test_csv_export_with_data(self, auth_client):
        Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=1.0,
            price=100.0,
            status=OrderStatus.FILLED,
            mode="paper",
            portfolio_id=1,
            timestamp=datetime.now(timezone.utc),
        )
        resp = auth_client.get("/api/trading/orders/export/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/csv"
        assert "orders_export.csv" in resp["Content-Disposition"]
        content = resp.content.decode()
        lines = content.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        assert "BTC/USDT" in lines[1]

    def test_csv_export_empty(self, auth_client):
        resp = auth_client.get("/api/trading/orders/export/")
        assert resp.status_code == 200
        content = resp.content.decode()
        lines = content.strip().split("\n")
        assert len(lines) == 1  # header only
