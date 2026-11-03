from __future__ import annotations

import logging
from dataclasses import dataclass

from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request

from api.supabase_auth import TokenVerificationError, verify_access_token
from api.supabase_cookies import extract_session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupabasePrincipal:
    id: str
    email: str | None = None
    is_authenticated: bool = True

    @property
    def pk(self) -> str:
        return self.id

    @property
    def display_name(self) -> str:
        return self.email or self.id[:8]


class CookieSessionAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[SupabasePrincipal, str] | None:
        bearer = request.META.get("HTTP_AUTHORIZATION", "")
        if bearer.startswith("Bearer "):
            access_token = bearer.removeprefix("Bearer ")
            return self._verify(access_token)

        session = extract_session(request.COOKIES)
        if session is None or not session.access_token:
            return None

        if request.method in _UNSAFE_METHODS:
            self.enforce_csrf(request)

        return self._verify(session.access_token)

    def _verify(self, access_token: str) -> tuple[SupabasePrincipal, str]:
        try:
            user = verify_access_token(access_token)
        except TokenVerificationError as exc:
            message = str(exc)
            if message.startswith("supabase_auth_unavailable"):
                logger.warning("Supabase Auth unavailable: %s", message)
                unavailable = AuthenticationFailed(
                    "Authentication service is temporarily unavailable.",
                    code="auth_unavailable",
                )
                # APIException takes no status argument, so it is set directly.
                unavailable.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                raise unavailable from exc

            logger.info("Rejected access token: %s", message)
            raise AuthenticationFailed("Invalid or expired session.", code="invalid_token") from exc

        principal = SupabasePrincipal(id=user.id, email=user.email)
        return principal, access_token

    def authenticate_header(self, request: Request) -> str:
        # Not "Bearer": this API is cookie-authenticated.
        return "Cookie"

    def enforce_csrf(self, request: Request) -> None:
        if not _origin_is_trusted(request):
            logger.warning(
                "Rejected a state-changing request from untrusted origin %r",
                request.META.get("HTTP_ORIGIN"),
            )
            raise PermissionDenied("Request origin is not allowed.")

#: Methods that can change state, and so need the origin check above.
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_is_trusted(request: Request) -> bool:
    from django.conf import settings

    allowed = {origin.rstrip("/") for origin in settings.CORS_ALLOWED_ORIGINS}
    if not allowed:
        return True

    origin = request.META.get("HTTP_ORIGIN", "").rstrip("/")
    if origin:
        return origin in allowed

    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        return referer.rstrip("/").startswith(tuple(f"{item}/" for item in allowed))

    return True
