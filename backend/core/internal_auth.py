"""Internal API authentication for Freqtrade/NautilusTrader endpoints.

Provides HMAC signature verification + IP allowlist for endpoints that
must be callable without Django session auth (e.g., risk check, entry check,
signal recording).

Usage:
    class TradeCheckView(InternalAPIView):
        def post(self, request, portfolio_id):
            ...

Or as a standalone permission class:
    class MyView(APIView):
        permission_classes = [InternalEndpointPermission]
"""

import hashlib
import hmac
import logging
import time

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _get_client_ip(request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def verify_hmac_signature(request) -> bool:
    """Verify HMAC-SHA256 signature on internal API request.

    Expected header: X-Internal-Signature: <timestamp>:<hex_signature>
    Signature = HMAC-SHA256(secret, timestamp + request.body)
    Timestamp must be within 5 minutes of server time.
    """
    secret = getattr(settings, "INTERNAL_API_SECRET", "")
    if not secret:
        return False  # HMAC not configured

    sig_header = request.META.get("HTTP_X_INTERNAL_SIGNATURE", "")
    if not sig_header or ":" not in sig_header:
        return False

    try:
        timestamp_str, signature = sig_header.split(":", 1)
        timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        return False

    # Reject stale signatures (>5 minute window)
    if abs(time.time() - timestamp) > 300:
        logger.warning("Internal API signature expired (age=%ds)", abs(time.time() - timestamp))
        return False

    # Compute expected signature
    body = request.body if hasattr(request, "body") else b""
    message = f"{timestamp}".encode() + body
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    if hmac.compare_digest(signature, expected):
        return True

    logger.warning("Internal API HMAC signature mismatch")
    return False


class InternalEndpointPermission(BasePermission):
    """Permission class for internal-only endpoints.

    Grants access if ANY of:
    1. Valid HMAC signature in X-Internal-Signature header
    2. Client IP is in INTERNAL_API_ALLOWED_IPS
    3. User is authenticated via Django session (for dashboard/admin use)
    """

    def has_permission(self, request, view) -> bool:
        # 1. Check HMAC signature
        if verify_hmac_signature(request):
            return True

        # 2. Check IP allowlist
        client_ip = _get_client_ip(request)
        allowed_ips = getattr(settings, "INTERNAL_API_ALLOWED_IPS", [])
        if client_ip in allowed_ips:
            return True

        # 3. Fall back to session auth (allows dashboard/admin to call these endpoints)
        if request.user and request.user.is_authenticated:
            return True

        logger.warning(
            "Internal endpoint access denied: ip=%s, hmac=%s, authenticated=%s",
            client_ip,
            bool(request.META.get("HTTP_X_INTERNAL_SIGNATURE")),
            request.user.is_authenticated if request.user else False,
        )
        return False


class InternalAPIView(APIView):
    """Base view for internal-only endpoints (Freqtrade, NautilusTrader).

    Replaces permission_classes = [AllowAny] or permission_classes = [].
    """

    authentication_classes = []  # Don't require session/CSRF
    permission_classes = [InternalEndpointPermission]
