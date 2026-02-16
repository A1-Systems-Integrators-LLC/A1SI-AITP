import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, django_user_model):
    django_user_model.objects.create_user(
        username="testuser", password="testpass123!"
    )
    api_client.login(username="testuser", password="testpass123!")
    return api_client


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="admin", password="adminpass123!"
    )
