"""Consistent JSON error response helper."""

from rest_framework.response import Response


def error_response(message: str, status_code: int = 400) -> Response:
    """Return a JSON error response with a standard body."""
    return Response({"error": message}, status=status_code)
