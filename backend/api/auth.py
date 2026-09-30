"""DRF authentication backed by the Supabase SSR session cookie.

The browser never sends a bearer token from the frontend: `@supabase/ssr` holds
the session in cookies, and the browser attaches those to the API. This class
reads that cookie, verifies the token with Supabase Auth, and exposes a
principal that carries the Supabase user id.

Anonymous access is allowed only where a view opts in. `/api/v1/me` requires a
user, but the demo library and demo chat need to work for signed-out visitors,
so those views will list `AllowAny` and read `request.user` defensively.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from api.supabase_auth import TokenVerificationError, verify_access_token
from api.supabase_cookies import extract_session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupabasePrincipal:
    """The authenticated caller.

    Named rather than modelled as a Django user: this service has no local
    identity, and pretending otherwise invites code that expects
    `is_authenticated` on a real user model.
    """

    id: str
    email: str | None = None
    is_authenticated: bool = True

    @property
    def display_name(self) -> str:
        return self.email or self.id[:8]


class CookieSessionAuthentication(BaseAuthentication):
    """Authenticate a request from the Supabase SSR session cookie."""

    def authenticate(self, request: Request) -> tuple[SupabasePrincipal, str] | None:
        session = extract_session(request.COOKIES)
        if session is None or not session.access_token:
            return None

        try:
            user = verify_access_token(session.access_token)
        except TokenVerificationError as exc:
            message = str(exc)
            if message.startswith("supabase_auth_unavailable"):
                # Our dependency is down, not the caller. 503 keeps that
                # distinction visible to the frontend instead of showing a
                # spurious "please sign in again".
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
        return principal, session.access_token

    def authenticate_header(self, request: Request) -> str:
        # Deliberately not "Bearer": this API is cookie-authenticated, and
        # advertising a bearer scheme would invite clients to try one.
        return "Cookie"
