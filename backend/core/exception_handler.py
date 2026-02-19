"""Custom DRF exception handler — structured JSON errors, no stack traces in production."""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Handle DRF exceptions with structured JSON responses.

    Falls through to DRF's default handler first, then catches any
    unhandled exceptions that would otherwise return raw 500 HTML.
    """
    response = drf_exception_handler(exc, context)

    if response is not None:
        # DRF already handled it — normalize the shape
        response.data = _normalize(response.data, response.status_code)
        return response

    # Unhandled exception — log and return safe 500
    view = context.get("view")
    view_name = view.__class__.__name__ if view else "unknown"
    logger.exception("Unhandled exception in %s: %s", view_name, exc)

    detail = str(exc) if settings.DEBUG else "Internal server error"
    return Response(
        {"error": detail, "status_code": 500},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _normalize(data, status_code: int) -> dict:
    """Ensure every error response has a consistent {error, status_code} shape."""
    if isinstance(data, dict) and "error" in data:
        data.setdefault("status_code", status_code)
        return data

    # DRF often returns {"detail": "..."} or {"field": ["error"]}
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return {"error": str(detail), "status_code": status_code}
        # Field-level validation errors — keep as-is but wrap
        return {"error": "Validation failed", "fields": data, "status_code": status_code}

    return {"error": str(data), "status_code": status_code}
