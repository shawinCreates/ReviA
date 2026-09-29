"""
Phase 0 endpoints.

Two views. `health` is the only unauthenticated endpoint and confirms the
database is reachable. `me` is the first endpoint behind the auth middleware,
and returning a real row from it is the phase 0 gate: a logged-in browser call
reaching Django with a verified `sub` claim.

`/api/chat/stream` arrives in phase 3, when there is something to retrieve. The
streaming path is proved in phase 0 by the REPL instead, because proving SSE
works through the ASGI stack does not require a retrieval pipeline.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import error_payload

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """
    Unauthenticated. Used by Render's health check, so it must be cheap and
    must not require a token. It does open a database connection on purpose:
    a process that is up but cannot reach Postgres is not healthy, and finding
    that out from the health check beats finding it out from a user.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            logger.error("Health check database probe failed: %s", type(exc).__name__)
            return Response(
                error_payload("database_unavailable", "Database is unreachable."),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "ok",
                "database": "ok",
                # Reported so a stale deploy is obvious from the outside.
                "debug": settings.DEBUG,
            }
        )


class MeView(APIView):
    """
    Returns the caller's Profile. Reached only after the middleware has
    verified the JWT and upserted the row, so reaching this view at all is the
    auth gate. `request.profile` is set by the middleware.
    """

    def get(self, request):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover - middleware guarantees this
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "id": str(profile.id),
                "email": profile.email,
                "created_at": profile.created_at.isoformat(),
            }
        )
