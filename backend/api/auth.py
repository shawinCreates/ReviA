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

from django.middleware.csrf import CsrfViewMiddleware
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
    def pk(self) -> str:
        """The same value as `id`.

        DRF's throttles key on `request.user.pk` for an authenticated caller, and
        raise `AttributeError` without it. Every view with a `throttle_scope` —
        which is every one that costs money or storage — would fail on every
        request rather than merely not throttle. Aliasing it here is cheaper and
        clearer than replacing DRF's throttles.
        """
        return self.id

    @property
    def display_name(self) -> str:
        return self.email or self.id[:8]


class CookieSessionAuthentication(BaseAuthentication):
    """Authenticate a request from the Supabase SSR session cookie."""

    def authenticate(self, request: Request) -> tuple[SupabasePrincipal, str] | None:
        session = extract_session(request.COOKIES)
        if session is None or not session.access_token:
            return None

        # Django's CSRF protection is tied to its session middleware, which is not
        # installed here, and DRF only enforces CSRF for its own
        # `SessionAuthentication`. So a state-changing request arrives carrying
        # the session cookie with nothing else proving the user meant to send
        # it, which is exactly the shape a cross-site request forgery takes.
        #
        # Enforced only for unsafe methods: a GET cannot change anything, and
        # requiring a token on it would break the frontend's plain fetches.
        if request.method in _UNSAFE_METHODS:
            self.enforce_csrf(request)

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

    def enforce_csrf(self, request: Request) -> None:
        """Reject a state-changing request that did not come from our frontend.

        **The origin check below is what actually protects this endpoint.** The
        token check is run first and will catch a client that sends a *wrong*
        token, but it cannot catch a client that sends none: with
        `CSRF_COOKIE_NAME` set to an empty string there is no cookie to compare
        against, and Django's masked-token comparison treats two empty strings as
        equal. So a request with no token at all passes the token check and is
        judged entirely by its `Origin`/`Referer`.

        That is a deliberate trade rather than an oversight. The browser holds
        the Supabase session cookie and the service writes no CSRF cookie of its
        own, so there is nothing for a double-submit pattern to work with. A
        cross-origin state-changing request, which is the attack this guards
        against, cannot forge `Origin` — browsers set it and forbid scripts from
        writing it. Requiring a token instead would mean inventing a cookie for
        one endpoint, and a frontend that has to fetch it before every write.
        """
        from rest_framework.exceptions import PermissionDenied

        reason = _CsrfCheck(lambda req: None).process_view(request, None, (), {})
        if reason is not None:
            logger.info("Rejected a state-changing request: CSRF check failed")
            raise PermissionDenied("CSRF verification failed.")

        if not _origin_is_trusted(request):
            logger.warning(
                "Rejected a state-changing request from untrusted origin %r",
                request.META.get("HTTP_ORIGIN"),
            )
            raise PermissionDenied("Request origin is not allowed.")


class _CsrfCheck(CsrfViewMiddleware):
    """Runs Django's CSRF check and reports the reason instead of returning 403."""

    def _reject(self, request: Request, reason: str) -> str:
        return reason


#: Methods that can change state, and so need CSRF protection.
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_is_trusted(request: Request) -> bool:
    """Whether the request's Origin (or Referer) is one we serve.

    A cross-origin form post sends no `Origin` header on older browsers but
    always sends a `Referer`, so both are considered. An absent Origin on a
    same-origin request is normal and not a reason to refuse.
    """
    from django.conf import settings

    allowed = {origin.rstrip("/") for origin in settings.CORS_ALLOWED_ORIGINS}
    if not allowed:
        # No configured origins means no browser client is expected, so there is
        # nothing to check against. Refusing everything would make a curl-based
        # workflow impossible for no security gain.
        return True

    origin = request.META.get("HTTP_ORIGIN", "").rstrip("/")
    if origin:
        return origin in allowed

    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        return referer.rstrip("/").startswith(tuple(f"{item}/" for item in allowed))

    # Neither header present. A browser always sends at least one for a
    # cross-origin request, so this is a non-browser client.
    return True
