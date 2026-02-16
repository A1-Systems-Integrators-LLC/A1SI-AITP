from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/", include("portfolio.urls")),
    path("api/", include("trading.urls")),
    path("api/", include("market.urls")),
    path("api/", include("risk.urls")),
    path("api/", include("analysis.urls")),
]
