"""Authentication behaviour.

Token verification is the security boundary, so these tests cover the split
between "your token is bad" (401) and "our dependency is down" (503). Collapsing
those two is how a Supabase outage turns into every user appearing logged out.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from rest_framework.test import APIClient

from api.supabase_auth import (
    TokenVerificationError,
    _decode_jwt_claims,
    _token_fingerprint,
    verify_access_token,
)
from api.tests.conftest import AUTH_COOKIE, auth_cookie

COOKIE = AUTH_COOKIE


def _cookie_for(access_token: str) -> str:
    return auth_cookie(access_token)


def _user_payload(user_id: str, email: str = "reader@example.com") -> dict:
    return {"id": user_id, "email": email}


def test_valid_token_returns_user(mock_auth_api):
    user_id = str(uuid.uuid4())
    mock_auth_api(200, _user_payload(user_id))

    user = verify_access_token("valid-token")

    assert user.id == user_id
    assert user.email == "reader@example.com"


def test_rejected_token_raises_invalid_token(mock_auth_api):
    mock_auth_api(401, {"message": "invalid"})

    with pytest.raises(TokenVerificationError, match="invalid_token"):
        verify_access_token("bad-token")


def test_forbidden_is_treated_as_rejection(mock_auth_api):
    mock_auth_api(403, {"message": "forbidden"})

    with pytest.raises(TokenVerificationError, match="invalid_token"):
        verify_access_token("bad-token")


def test_server_error_is_reported_as_unavailable(mock_auth_api):
    mock_auth_api(503, {"message": "down"})

    with pytest.raises(TokenVerificationError, match="supabase_auth_unavailable"):
        verify_access_token("some-token")


def test_transport_failure_is_reported_as_unavailable(mock_auth_api):
    mock_auth_api(0, {}, raise_exc=httpx.ConnectError("no route to host"))

    with pytest.raises(TokenVerificationError, match="supabase_auth_unavailable"):
        verify_access_token("some-token")


def test_payload_without_id_is_not_trusted(mock_auth_api):
    mock_auth_api(200, {"email": "nobody@example.com"})

    with pytest.raises(TokenVerificationError, match="no user id"):
        verify_access_token("weird-token")


def test_verified_token_is_cached_and_not_reverified(mock_auth_api):
    user_id = str(uuid.uuid4())
    calls = mock_auth_api(200, _user_payload(user_id))

    first = verify_access_token("cache-me")
    second = verify_access_token("cache-me")

    assert first.id == second.id == user_id
    assert len(calls) == 1, "a verified token is immutable, so it should be cached"


def test_rejected_token_is_not_cached(mock_auth_api):
    calls = mock_auth_api(401, {"message": "invalid"})

    for _ in range(2):
        with pytest.raises(TokenVerificationError):
            verify_access_token("never-good")

    assert len(calls) == 2, "a rejection must not be remembered as a result"


def test_fingerprint_is_stable_and_hides_the_token():
    token = "super-secret-token-value"
    fingerprint = _token_fingerprint(token)

    assert fingerprint == _token_fingerprint(token)
    assert token not in fingerprint
    assert _token_fingerprint("other") != fingerprint


def test_malformed_jwt_yields_no_claims():
    assert _decode_jwt_claims("not-a-jwt") == {}
    assert _decode_jwt_claims("a.b") == {}


def test_jwt_claims_are_readable():
    import base64
    import json

    payload = (
        base64.urlsafe_b64encode(json.dumps({"email": "c@example.com"}).encode())
        .decode()
        .rstrip("=")
    )
    assert _decode_jwt_claims(f"header.{payload}.sig")["email"] == "c@example.com"


@pytest.mark.django_db
def test_me_requires_authentication():
    response = APIClient().get("/api/v1/me")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_me_creates_profile_on_first_request(mock_auth_api):
    user_id = str(uuid.uuid4())
    mock_auth_api(200, _user_payload(user_id, "owner@example.com"))

    client = APIClient()
    client.cookies[COOKIE] = _cookie_for("real-token")
    response = client.get("/api/v1/me")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["user"]["id"] == user_id
    assert body["profile"]["email"] == "owner@example.com"
    assert body["profile"]["id"] == user_id


@pytest.mark.django_db
def test_me_is_idempotent(mock_auth_api):
    user_id = str(uuid.uuid4())
    mock_auth_api(200, _user_payload(user_id))

    client = APIClient()
    client.cookies[COOKIE] = _cookie_for("real-token")

    first = client.get("/api/v1/me").json()
    second = client.get("/api/v1/me").json()

    assert first["profile"]["created_at"] == second["profile"]["created_at"]


@pytest.mark.django_db
def test_rejected_token_returns_401(mock_auth_api):
    mock_auth_api(401, {"message": "invalid"})

    client = APIClient()
    client.cookies[COOKIE] = _cookie_for("stale-token")
    response = client.get("/api/v1/me")

    assert response.status_code == 401


@pytest.mark.django_db
def test_auth_outage_returns_503_not_401(mock_auth_api):
    mock_auth_api(500, {"message": "boom"})

    client = APIClient()
    client.cookies[COOKIE] = _cookie_for("good-token")
    response = client.get("/api/v1/me")

    assert response.status_code == 503


@pytest.mark.django_db
def test_session_endpoint_reports_signed_out_without_cookies():
    response = APIClient().get("/api/v1/session")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user_id": None}


@pytest.mark.django_db
def test_session_endpoint_reports_signed_in(mock_auth_api):
    user_id = str(uuid.uuid4())
    mock_auth_api(200, _user_payload(user_id))

    client = APIClient()
    client.cookies[COOKIE] = _cookie_for("real-token")
    body = client.get("/api/v1/session").json()

    assert body == {"authenticated": True, "user_id": user_id}
