"""
Custom middleware — request tracing, rate limiting, audit logging, security event logging.
"""

import logging
import threading
import time
import uuid
from collections import defaultdict

from django.conf import settings
from django.http import JsonResponse

from core.logging import request_id_var

logger = logging.getLogger("security")
request_logger = logging.getLogger("requests")


class RequestIDMiddleware:
    """Assign a unique request ID to every request for end-to-end tracing.

    - Reads X-Request-ID from incoming header (trusted proxy), or generates one.
    - Sets it in contextvars for structured log enrichment.
    - Logs request start/end with method, path, status, duration, user.
    - Returns X-Request-ID in response header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)

        start = time.time()
        response = self.get_response(request)
        duration_ms = round((time.time() - start) * 1000, 1)

        response["X-Request-ID"] = rid

        # Log completed request
        has_user = hasattr(request, "user") and request.user.is_authenticated
        user = request.user.username if has_user else "-"
        request_logger.info(
            "%s %s %s %sms",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user": user,
            },
        )

        request_id_var.reset(token)
        return response


class CSPMiddleware:
    """Add Content-Security-Policy header from settings."""

    def __init__(self, get_response):
        self.get_response = get_response
        directives = []
        for directive, setting in [
            ("default-src", "CSP_DEFAULT_SRC"),
            ("script-src", "CSP_SCRIPT_SRC"),
            ("style-src", "CSP_STYLE_SRC"),
            ("img-src", "CSP_IMG_SRC"),
            ("connect-src", "CSP_CONNECT_SRC"),
            ("object-src", "CSP_OBJECT_SRC"),
            ("base-uri", "CSP_BASE_URI"),
            ("form-action", "CSP_FORM_ACTION"),
            ("frame-ancestors", "CSP_FRAME_ANCESTORS"),
        ]:
            value = getattr(settings, setting, None)
            if value:
                directives.append(f"{directive} {value}")
        self._header = "; ".join(directives) if directives else ""

    def __call__(self, request):
        response = self.get_response(request)
        if self._header:
            response["Content-Security-Policy"] = self._header
        perms_policy = getattr(settings, "PERMISSIONS_POLICY", None)
        if perms_policy:
            response["Permissions-Policy"] = perms_policy
        return response


class RateLimitMiddleware:
    """In-memory sliding window rate limiter."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def __call__(self, request):
        ip = self._get_ip(request)
        path = request.path

        # Determine rate limit
        if path.startswith("/api/auth/login"):
            limit = getattr(settings, "RATE_LIMIT_LOGIN", 5)
        else:
            limit = getattr(settings, "RATE_LIMIT_GENERAL", 60)

        allowed, remaining, reset_time = self._allow(ip, limit)

        if not allowed:
            logger.warning(f"Rate limit exceeded: ip={ip} path={path}")
            response = JsonResponse(
                {"error": "Rate limit exceeded. Try again later."},
                status=429,
            )
            response["Retry-After"] = "60"
            response["X-RateLimit-Limit"] = str(limit)
            response["X-RateLimit-Remaining"] = "0"
            response["X-RateLimit-Reset"] = str(int(reset_time))
            return response

        response = self.get_response(request)
        response["X-RateLimit-Limit"] = str(limit)
        response["X-RateLimit-Remaining"] = str(remaining)
        response["X-RateLimit-Reset"] = str(int(reset_time))
        return response

    _TRUSTED_PROXIES = {"127.0.0.1", "::1", "172.17.0.1"}

    def _get_ip(self, request) -> str:
        remote_addr = request.META.get("REMOTE_ADDR", "unknown")
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff and (remote_addr in self._TRUSTED_PROXIES or remote_addr.startswith("172.")):
            return xff.split(",")[0].strip()
        return remote_addr

    def _allow(self, key: str, limit: int) -> tuple[bool, int, float]:
        """Check if request is allowed under rate limit.

        Returns:
            Tuple of (allowed, remaining, reset_time) where reset_time is a
            Unix timestamp when the oldest request in the window expires.
        """
        now = time.time()
        with self._lock:
            timestamps = self._requests[key]
            # Remove entries older than 60 seconds
            self._requests[key] = [t for t in timestamps if now - t < 60]
            if len(self._requests[key]) >= limit:
                oldest = min(self._requests[key]) if self._requests[key] else now
                reset_time = oldest + 60.0
                return False, 0, reset_time
            self._requests[key].append(now)
            remaining = max(0, limit - len(self._requests[key]))
            oldest = min(self._requests[key]) if self._requests[key] else now
            reset_time = oldest + 60.0
            return True, remaining, reset_time


class MetricsMiddleware:
    """Count HTTP requests and record response time."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration = time.time() - start

        # Skip metrics endpoint itself to avoid recursion
        if request.path != "/metrics/":
            from core.services.metrics import metrics

            labels = {
                "method": request.method,
                "path": request.path,
                "status": str(response.status_code),
            }
            metrics.counter_inc("http_requests_total", labels)
            metrics.histogram_observe(
                "http_request_duration_seconds",
                duration,
                {"method": request.method, "path": request.path},
            )

        return response


class AuditMiddleware:
    """Log state-changing requests to AuditLog (background thread)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only audit state-changing methods on API endpoints
        if request.method in ("POST", "PUT", "DELETE") and request.path.startswith("/api/"):
            self._log_async(request, response)

        return response

    def _log_async(self, request, response):
        """Fire-and-forget audit log entry via thread."""
        user = request.user.username if request.user.is_authenticated else "anonymous"
        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
        method = request.method
        path = request.path
        status_code = response.status_code

        def _write():
            try:
                from core.models import AuditLog

                AuditLog.objects.create(
                    user=user,
                    action=f"{method} {path}",
                    ip_address=ip.split(",")[0].strip() if ip else "",
                    status_code=status_code,
                )
            except (ImportError, RuntimeError) as e:
                logger.debug("Audit log write failed (app not ready): %s", e)
            except Exception as e:
                logger.warning("Audit log write failed: %s", e)

        thread = threading.Thread(target=_write, daemon=True)
        thread.start()
