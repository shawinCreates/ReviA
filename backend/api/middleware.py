"""
Request middleware.

Runs before routing so that every endpoint inherits one auth path. Auth is
resolved here rather than in a DRF authentication class because it must apply
to plain Django views too, and because `request.profile` needs to be available
to the Profile upsert regardless of how the view is written.

`/api/health` is the only unauthenticated endpoint, and it is excluded here
rather than in the view so there is exactly one place that decides what is
public.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .errors import error_payload
from .jwt_auth import AuthError, extract_bearer_token, verify_token

logger = logging.getLogger(__name__)

# Paths served without a token. Kept short on purpose: every entry here is a
# decision to expose an endpoint to the internet.
PUBLIC_PATHS = {"/api/health", "/api/health/"}


class JWTAuthMiddleware(MiddlewareMixin):
    """
    Deliberately synchronous.

    An async process_request returns a coroutine, which Django's sync middleware
    adapter does not await before handing the response on — the coroutine then
    reaches the view layer and blows up on `response.status_code`. Verification
    is a network call to a cached key and one indexed upsert, so it is held on
    Django's sync-to-async thread pool rather than the event loop, which stays
    free for the SSE streams that do need it.
    """

    def process_request(self, request):
        if request.path in PUBLIC_PATHS:
            return None

        try:
            token = extract_bearer_token(request.headers.get("Authorization"))
            verified = verify_token(token)
        except AuthError as exc:
            # A failed token is a normal outcome, not a server error. Returning
            # 401 here rather than raising keeps a garbage token from surfacing
            # as a 500, which is the case phase 0 explicitly tests for.
            logger.info("Rejected request to %s: %s", request.path, exc.code)
            return JsonResponse(
                error_payload(exc.code, exc.message),
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.verified_token = verified

        # Lazy Profile upsert on first authenticated request. A local mirror
        # avoids querying Supabase's auth schema on every request, which is not
        # designed for application-level joins. See architecture.md.
        try:
            from .models import Profile

            profile, _ = Profile.objects.get_or_create(
                id=verified.user_id, defaults={"email": verified.email}
            )
            # Supabase is the source of truth for the address; keep the mirror
            # current without an extra write when nothing changed.
            if verified.email and profile.email != verified.email:
                profile.email = verified.email
                profile.save(update_fields=["email"])
            request.profile = profile
        except Exception:
            # The database being unreachable is a server fault, not an auth
            # failure. Do not mask it as 401: that would send the user to log
            # in again when the real problem is the database.
            logger.exception("Profile upsert failed for user %s", verified.user_id)
            return JsonResponse(
                error_payload("internal_error", "Could not load the user profile."),
                status=503,
            )

        return None
