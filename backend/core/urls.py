from django.urls import path

from core.auth import AuthStatusView, LoginView, LogoutView
from core.views import HealthView, PlatformConfigView, PlatformStatusView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/status/", AuthStatusView.as_view(), name="auth-status"),
    path("platform/status/", PlatformStatusView.as_view(), name="platform-status"),
    path("platform/config/", PlatformConfigView.as_view(), name="platform-config"),
]
