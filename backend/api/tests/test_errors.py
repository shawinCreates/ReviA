"""
The error envelope contract.

api.md says every error response is `{"error": {"code", "message"}}`. That holds
for errors raised inside a view, because the DRF exception handler rewrites
them. It does not hold for errors raised *before* a view exists — an unmatched
path, or an unhandled crash — which is what these cover.

The subtlety is `DEBUG`. Django serves its own HTML debug page for an unmatched
path when DEBUG is on and never consults `handler404`, so the real behaviour is
only observable with it off, which is also how it runs in production.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from api.models import Profile

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(jwks_server):
    return APIClient()


@pytest.fixture
def authed(client, make_token):
    def _authed(profile: Profile) -> APIClient:
        token = make_token(subject=str(profile.id), email=profile.email)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return client

    return _authed


@pytest.fixture
def profile(db):
    return Profile.objects.create(id=uuid.uuid4(), email="errors@example.com")


@pytest.fixture(autouse=True)
def production_debug():
    """
    Run with DEBUG off, which is both production and the only way Django
    consults handler404 at all.
    """
    with override_settings(DEBUG=False):
        yield


class TestUnmatchedPaths:
    def test_unknown_api_path_returns_the_envelope(self, authed, profile):
        response = authed(profile).get("/api/no-such-endpoint")
        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "not_found", "message": "No such endpoint."}
        }

    def test_the_body_is_json_not_html(self, authed, profile):
        """The frontend parses every error body as JSON. An HTML 404 here
        silently degrades into a generic 'something went wrong'."""
        response = authed(profile).get("/api/no-such-endpoint")
        assert response["Content-Type"].startswith("application/json")

    def test_a_typo_in_a_real_path_is_also_an_envelope(self, authed, profile):
        # The route is `documents`, not `document`.
        response = authed(profile).get("/api/document")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_a_non_api_path_is_rejected_by_auth_before_routing(self, client):
        """
        Auth runs on every path, not just /api/. So a non-API path never
        reaches handler404 either — it is 401 like everything else. The HTML
        branch in the handler is therefore unreachable in this deployment; it
        exists so that relaxing the middleware later does not start serving an
        HTML page where the frontend expects the envelope.
        """
        response = client.get("/not-an-api-page")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"


class TestAuthPrecedesRouting:
    def test_an_unknown_path_without_a_token_is_401_not_404(self, client):
        """
        Auth runs in middleware, before routing. So the response for an unknown
        path depends on the token: 401 without one, 404 with one. Reporting 404
        first would leak which endpoints exist to unauthenticated callers.
        """
        response = client.get("/api/no-such-endpoint")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"
