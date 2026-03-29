from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from core.views import MetricsView

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/", include("portfolio.urls")),
    path("api/", include("trading.urls")),
    path("api/", include("market.urls")),
    path("api/", include("risk.urls")),
    path("api/", include("analysis.urls")),
    path("metrics/", MetricsView.as_view(), name="metrics"),
    # OpenAPI schema (machine-readable, always available for CI schema freshness check)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]

# Django admin and interactive API docs only available in debug mode
if settings.DEBUG:
    urlpatterns += [
        path("admin/", admin.site.urls),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]
