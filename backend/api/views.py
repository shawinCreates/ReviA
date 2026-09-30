"""API views.

Scope so far is deliberately thin: a health probe that does not touch the
database, and `/me` which proves the cookie-to-Profile path end to end. The
library, upload and chat endpoints build on these once they exist.
"""

from __future__ import annotations

import logging

from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.auth import SupabasePrincipal
from api.profiles import get_or_create_profile
from api.serializers import ProfileSerializer

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Liveness and readiness in one probe.

    Reports database reachability separately from serving status: an API that
    cannot reach Postgres is running but not ready, and conflating the two makes
    a bad deploy look like a crash.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        database_ok = True
        database_error: str | None = None

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            database_ok = False
            database_error = type(exc).__name__
            logger.warning("Health check could not reach the database: %s", exc)

        body = {
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "unreachable",
        }
        if database_error:
            body["database_error"] = database_error

        return Response(body, status=status.HTTP_200_OK)


class MeView(APIView):
    """The caller's own profile.

    Doubles as the end-to-end check that cookie parsing, token verification and
    profile provisioning all work against the real Supabase project.
    """

    def get(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user
        profile = get_or_create_profile(principal)

        return Response(
            {
                "user": {
                    "id": str(principal.id),
                    "email": principal.email,
                },
                "profile": ProfileSerializer(profile).data,
            }
        )


class DemoPrincipalView(APIView):
    """Confirms whether the caller is signed in, without requiring it.

    The frontend needs to know which of two states to render, and a 403 is a
    clumsy way to say "signed out". This is that signal.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        user = request.user
        authenticated = bool(user and getattr(user, "is_authenticated", False))
        return Response(
            {
                "authenticated": authenticated,
                "user_id": str(user.id) if authenticated else None,
            }
        )
