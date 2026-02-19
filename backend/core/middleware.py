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

        if not self._allow(ip, limit):
            logger.warning(f"Rate limit exceeded: ip={ip} path={path}")
            response = JsonResponse(
                {"error": "Rate limit exceeded. Try again later."},
                status=429,
            )
            response["Retry-After"] = "60"
            return response

        return self.get_response(request)

    def _get_ip(self, request) -> str:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def _allow(self, key: str, limit: int) -> bool:
        now = time.time()
        with self._lock:
            timestamps = self._requests[key]
            # Remove entries older than 60 seconds
            self._requests[key] = [t for t in timestamps if now - t < 60]
            if len(self._requests[key]) >= limit:
                return False
            self._requests[key].append(now)
            return True


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
            except Exception as e:
                logger.debug(f"Audit log write failed: {e}")

        thread = threading.Thread(target=_write, daemon=True)
        thread.start()
