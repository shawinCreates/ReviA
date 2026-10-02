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
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
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
        # `enforce_csrf` decides that, by origin rather than by token: see the
        # trade recorded there before adding a token back.
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

        This is an `Origin`/`Referer` check and nothing else.

        Django's own token check used to run here first, and it could never
        pass. `CsrfViewMiddleware.process_view` does not short-circuit on a
        verified origin: it rejects an *untrusted* origin early, then falls
        through to `_check_token`, which insists on a CSRF cookie. This service
        writes none (`CSRF_COOKIE_NAME` is the empty string, so there is no
        cookie for the frontend to echo), so every unsafe method was refused
        with "CSRF cookie not set" — including this frontend's own uploads,
        questions and deletes. The double-submit pattern needs a cookie to
        work with; inventing one for a single endpoint, and making the
        frontend fetch it before every write, buys nothing over the origin
        check that already exists below.

        Origin on its own is sufficient for the attack this guards against. A
        browser sets `Origin` on every cross-origin non-GET request and forbids
        scripts from writing it, so a forged cross-origin write cannot present
        an allowed origin — it arrives as the attacker's own. `Referer` covers
        the browsers that omit `Origin`, and a request carrying neither is not
        from a browser, where an attacker has no cookie to ride anyway.
        """
        if not _origin_is_trusted(request):
            logger.warning(
                "Rejected a state-changing request from untrusted origin %r",
                request.META.get("HTTP_ORIGIN"),
            )
            raise PermissionDenied("Request origin is not allowed.")


#: Methods that can change state, and so need the origin check above.
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
