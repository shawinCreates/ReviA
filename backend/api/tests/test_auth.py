"""Authentication behaviour.

Token verification is the security boundary, so these tests cover the split
between "your token is bad" (401) and "our dependency is down" (503). Collapsing
those two is how a Supabase outage turns into every user appearing logged out.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from api.auth import CookieSessionAuthentication
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


# --- cross-origin writes --------------------------------------------------------
#
# The origin check is the whole of this project's CSRF defence, and it replaced
# a Django token check that could never pass. That shipped broken for a reason
# no test would have caught: every unsafe method returned 403 "CSRF cookie not
# set", so upload, ask and delete were all dead in development, while the GET
# tests kept passing.
#
# These drive the authentication class directly rather than going through a
# view. The guard sits between parsing the cookie and verifying the token, so
# exercising it there keeps a trusted origin distinguishable from a refused one
# by the *outcome* — a principal, versus a PermissionDenied — without standing
# up storage, a quota, or an upload to assert on something unrelated.


def _authenticate(method: str, *, origin: str | None = None, referer: str | None = None):
    """Run the auth class over one synthetic request.

    No database and no network: `mock_auth_api` resolves the token, so a request
    that gets past the origin check returns a real principal rather than a 401.
    """
    factory = APIRequestFactory()
    handler = getattr(factory, method.lower())
    environ = {}
    if origin is not None:
        environ["HTTP_ORIGIN"] = origin
    if referer is not None:
        environ["HTTP_REFERER"] = referer

    django_request = handler("/api/v1/documents/upload", **environ)
    django_request.COOKIES[COOKIE] = _cookie_for("token-for-origin-check")
    # Django's test factory sets `_dont_enforce_csrf_checks = True` on every
    # request it builds (django/test/client.py:183), which makes
    # `CsrfViewMiddleware.process_view` accept immediately. Left in place, these
    # tests pass against code that rejects every write in production — they
    # assert nothing about CSRF at all. A real request arrives through
    # `WSGIHandler`, which never sets this flag, so clear it and test what
    # actually runs.
    django_request._dont_enforce_csrf_checks = False
    return CookieSessionAuthentication().authenticate(Request(django_request))


def test_a_write_from_an_allowed_origin_authenticates(mock_auth_api):
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    result = _authenticate("post", origin="http://localhost:3000")

    assert result is not None
    principal, _token = result
    assert principal.is_authenticated


def test_the_second_allowed_origin_is_also_accepted(mock_auth_api):
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    assert _authenticate("post", origin="http://127.0.0.1:3000") is not None


def test_a_write_from_an_untrusted_origin_is_refused(mock_auth_api):
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    with pytest.raises(PermissionDenied):
        _authenticate("post", origin="https://evil.example")


def test_an_origin_that_merely_looks_allowed_is_refused(mock_auth_api):
    """A prefix match would accept `http://localhost:3000.evil.example`."""

    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    with pytest.raises(PermissionDenied):
        _authenticate("post", origin="http://localhost:3000.evil.example")


def test_an_untrusted_origin_is_refused_before_the_token_is_verified(mock_auth_api):
    """The order matters: a refused request must not cost a call to Supabase.

    `calls` is empty because nothing was sent to Auth — the origin refused it
    first. Were this reversed, every forgery attempt would be a live request
    against a third-party rate limit.
    """
    calls = mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    with pytest.raises(PermissionDenied):
        _authenticate("post", origin="https://evil.example")

    assert calls == []


def test_a_referer_within_an_allowed_origin_is_accepted(mock_auth_api):
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    result = _authenticate("post", referer="http://localhost:3000/chat")

    assert result is not None


def test_a_referer_outside_every_allowed_origin_is_refused(mock_auth_api):
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    with pytest.raises(PermissionDenied):
        _authenticate("post", referer="https://evil.example/attack")


def test_a_write_carrying_neither_header_is_not_refused(mock_auth_api):
    """A client with no Origin and no Referer is not a browser.

    It cannot be ridden by a cross-site forgery, because an attacker has no
    cookie to attach on its behalf, so refusing it would only break curl and
    the pipeline worker's own calls.
    """
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    assert _authenticate("post") is not None


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_every_unsafe_method_is_refused_from_an_untrusted_origin(mock_auth_api, method):
    """The guard is keyed on the method, not on the endpoint.

    DELETE is the case that matters most: the frontend's delete call goes
    through this same class, so a guard written only for POST would leave
    document removal wide open.
    """
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    with pytest.raises(PermissionDenied):
        _authenticate(method, origin="https://evil.example")


@pytest.mark.parametrize("method", ["post", "delete"])
def test_unsafe_methods_are_accepted_from_an_allowed_origin(mock_auth_api, method):
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    assert _authenticate(method, origin="http://localhost:3000") is not None


def test_a_get_is_never_checked_for_origin(mock_auth_api):
    """Safe methods carry the session cookie without any Origin check.

    This is what keeps the frontend's plain `fetch` calls working, and it is why
    the guard on unsafe methods must not spill over onto reads.
    """
    mock_auth_api(200, _user_payload(str(uuid.uuid4())))

    assert _authenticate("get", origin="https://evil.example") is not None
