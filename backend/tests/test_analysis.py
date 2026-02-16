"""Analysis API tests — jobs, backtest strategies."""

import pytest


@pytest.mark.django_db
class TestAnalysis:
    def test_list_jobs_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/jobs/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_job_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/jobs/nonexistent-id/")
        assert resp.status_code == 404

    def test_list_backtest_results_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/backtest/results/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_screening_results_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/screening/results/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_screening_strategies(self, authenticated_client):
        resp = authenticated_client.get("/api/screening/strategies/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 4

    def test_list_data_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/data/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
