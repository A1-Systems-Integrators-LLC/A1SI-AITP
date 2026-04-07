"""Tests for PostgreSQL database configuration."""

import pytest
from django.conf import settings


class TestDatabaseConfig:
    def test_default_engine_is_postgresql(self):
        """Database engine must be PostgreSQL."""
        assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"

    def test_conn_max_age_zero_in_tests(self):
        """CONN_MAX_AGE should be 0 in tests to avoid connection leaks."""
        assert settings.DATABASES["default"]["CONN_MAX_AGE"] == 0

    def test_conn_health_checks_enabled(self):
        """Connection health checks should be enabled."""
        assert settings.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True

    def test_postgres_deps_in_pyproject(self):
        """pyproject.toml should have postgres deps."""
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        assert "psycopg" in content

    @pytest.mark.django_db
    def test_database_connection_is_postgresql(self):
        """Live database connection must be PostgreSQL."""
        from django.db import connection

        assert connection.vendor == "postgresql"
