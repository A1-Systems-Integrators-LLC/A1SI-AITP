"""
Authentication views — login, logout, status, lockout logic.
"""

import logging
import time

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("auth")

# In-memory failed login tracker: {ip: [(timestamp, username), ...]}
_failed_logins: dict[str, list[tuple[float, str]]] = {}


def _get_client_ip(request: Request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _is_locked_out(ip: str) -> bool:
    """Check if an IP is locked out due to too many failed attempts."""
    now = time.time()
    window = settings.LOGIN_LOCKOUT_WINDOW
    max_attempts = settings.LOGIN_MAX_ATTEMPTS

    attempts = _failed_logins.get(ip, [])
    recent = [t for t, _ in attempts if now - t < window]
    if len(recent) >= max_attempts:
        # Check if lockout has expired
        oldest_recent = min(recent)
        if now - oldest_recent < settings.LOGIN_LOCKOUT_DURATION:
            return True
        # Lockout expired, clear
        _failed_logins[ip] = []
    return False


def _record_failure(ip: str, username: str) -> int:
    """Record a failed login attempt. Returns total recent failures."""
    now = time.time()
    window = settings.LOGIN_LOCKOUT_WINDOW

    if ip not in _failed_logins:
        _failed_logins[ip] = []

    _failed_logins[ip].append((now, username))
    # Prune old entries
    _failed_logins[ip] = [(t, u) for t, u in _failed_logins[ip] if now - t < window]
    return len(_failed_logins[ip])


def _clear_failures(ip: str) -> None:
    _failed_logins.pop(ip, None)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        ip = _get_client_ip(request)

        if _is_locked_out(ip):
            logger.warning(f"Login blocked (lockout): ip={ip}")
            return Response(
                {"error": "Account locked due to too many failed attempts. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=ser.validated_data["username"],
            password=ser.validated_data["password"],
        )

        if user is None:
            failures = _record_failure(ip, ser.validated_data["username"])
            remaining = settings.LOGIN_MAX_ATTEMPTS - failures
            logger.warning(
                f"Login failed: user={ser.validated_data['username']} ip={ip} "
                f"remaining={max(remaining, 0)}"
            )
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        _clear_failures(ip)
        logger.info(f"Login success: user={user.username} ip={ip}")
        return Response({"username": user.username, "status": "authenticated"})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logger.info(f"Logout: user={request.user.username}")
        logout(request)
        return Response({"status": "logged_out"})


class AuthStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        if request.user.is_authenticated:
            return Response({
                "authenticated": True,
                "username": request.user.username,
            })
        return Response({"authenticated": False})
