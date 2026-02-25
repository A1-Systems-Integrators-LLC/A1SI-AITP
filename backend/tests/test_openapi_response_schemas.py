"""P14-2: Tests for OpenAPI response schema annotations."""

import pytest


@pytest.mark.django_db
class TestOpenAPISchemaGeneration:
    """Verify schema generation succeeds and key endpoints have response definitions."""

    @pytest.fixture(autouse=True)
    def _generate_schema(self):
        from drf_spectacular.generators import SchemaGenerator

        generator = SchemaGenerator(patterns=None)
        self.schema = generator.get_schema(request=None, public=True)

    def test_schema_generates_successfully(self):
        assert self.schema is not None
        assert "paths" in self.schema
        assert "components" in self.schema

    def test_health_endpoint_has_response(self):
        path = self.schema["paths"].get("/api/health/")
        assert path is not None
        get = path.get("get", {})
        assert "200" in get.get("responses", {})

    def test_dashboard_kpi_has_response(self):
        path = self.schema["paths"].get("/api/dashboard/kpis/")
        assert path is not None
        get = path.get("get", {})
        responses = get.get("responses", {})
        assert "200" in responses

    def test_workflow_trigger_has_response(self):
        # Check any workflow trigger path exists with response
        found = False
        for path_key, path_val in self.schema["paths"].items():
            if "trigger" in path_key and "workflows" in path_key:
                post = path_val.get("post", {})
                if "200" in post.get("responses", {}) or "202" in post.get("responses", {}):
                    found = True
                    break
        assert found, "No workflow trigger endpoint found with response schema"
