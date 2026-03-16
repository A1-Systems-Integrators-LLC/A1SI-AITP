from unittest.mock import patch

import pytest
from django.conf import settings
from rest_framework.test import APIClient

# Ensure a test encryption key is always available
if not settings.ENCRYPTION_KEY:
    settings.ENCRYPTION_KEY = "TepMz4I9BrtjZvZ7sH6fVVB2iuW568_UVGBFg189xls="


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, django_user_model):
    django_user_model.objects.create_user(username="testuser", password="testpass123!")
    api_client.login(username="testuser", password="testpass123!")
    return api_client


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(username="admin", password="adminpass123!")


@pytest.fixture(autouse=True)
def _mock_btc_dominance():
    """Prevent live CoinGecko API calls in all tests — return neutral (no score modifier)."""
    neutral = {"dominance": 50.0, "regime_label": "neutral", "modifier": 0}
    with (
        patch("common.market_data.coingecko.fetch_btc_dominance", return_value=50.0),
        patch("common.market_data.coingecko.get_dominance_signal", return_value=neutral),
    ):
        yield
