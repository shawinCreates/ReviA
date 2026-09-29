"""
Error envelope.

Every error response has the same shape, so the frontend has one code path:

    {"error": {"code": "...", "message": "...", "retry_after": "..."}}

`retry_after` is present only for quota errors. The codes are part of the API
contract in api.md; the frontend switches on `code`, never on `message`.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404, JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .jwt_auth import AuthError


def error_payload(
    code: str, message: str, retry_after: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if retry_after is not None:
        payload["retry_after"] = retry_after
    return {"error": payload}


def error_response(
    code: str,
    message: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    retry_after: str | None = None,
) -> JsonResponse:
    return JsonResponse(
        error_payload(code, message, retry_after), status=status_code
    )


def envelope_exception_handler(exc: Exception, context: dict) -> Response | None:
    """DRF exception handler that emits the envelope above."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(response.data, dict) and "error" in response.data:
        return response

    code = {
        status.HTTP_401_UNAUTHORIZED: "unauthenticated",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_429_TOO_MANY_REQUESTS: "quota_exhausted",
    }.get(response.status_code, "bad_request")

    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    message = str(detail) if detail else "The request could not be processed."
    response.data = error_payload(code, message)
    return response


def not_found_response(message: str = "Not found.") -> JsonResponse:
    return error_response("not_found", message, status.HTTP_404_NOT_FOUND)


__all__ = [
    "AuthError",
    "Http404",
    "envelope_exception_handler",
    "error_payload",
    "error_response",
    "not_found_response",
]
