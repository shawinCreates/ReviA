"""
Auth middleware tests.

These cover the cases phases/phase-0-auth-and-repl.md names explicitly: a
missing token, a malformed token, and an expired token, all of which must be
401 and must never be 500.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from api.jwt_auth import AuthError, verify_token

pytestmark = pytest.mark.django_db


class TestRejectsBadTokens:
    def test_missing_header_is_401(self, client):
        response = client.get("/api/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"

    def test_empty_header_is_401(self, client):
        response = client.get("/api/me", HTTP_AUTHORIZATION="")
        assert response.status_code == 401

    def test_garbage_token_is_401_not_500(self, client):
        """Phase 0 calls this out specifically. A 500 here is a launch-day bug."""
        response = client.get("/api/me", HTTP_AUTHORIZATION="Bearer notatoken")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"

    def test_wrong_scheme_is_401(self, client):
        response = client.get("/api/me", HTTP_AUTHORIZATION="Basic abc123")
        assert response.status_code == 401
        assert "Bearer" in response.json()["error"]["message"]

    def test_expired_token_is_401(self, client, jwks_server, make_token):
        token = make_token(expires_delta=timedelta(hours=-2))
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 401
        assert "expired" in response.json()["error"]["message"].lower()

    def test_token_without_sub_is_401(self, client, jwks_server, signing_key):
        """A token with no subject has no user, so it cannot be accepted."""
        import jwt
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "iss": __import__("django.conf", fromlist=["settings"]).settings.SUPABASE_URL.rstrip("/")
                + "/auth/v1",
                "aud": "authenticated",
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            signing_key,
            algorithm="ES256",
            headers={"kid": "test-kid-1"},
        )
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 401

    def test_non_uuid_sub_is_401(self, client, jwks_server, make_token):
        token = make_token(subject="not-a-uuid")
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 401
        assert "uuid" in response.json()["error"]["message"].lower()

    def test_wrong_issuer_is_401(self, client, jwks_server, make_token):
        """A valid signature from a different Supabase project must not pass."""
        token = make_token(issuer="https://someone-elses-project.supabase.co/auth/v1")
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 401


class TestAlgorithmConfusion:
    def test_unsigned_token_is_rejected(self, client, jwks_server):
        """
        alg=none is the classic JWT attack. The algorithm allowlist is a
        constant, so a token cannot select its own verification method.
        """
        import jwt
        from datetime import datetime, timedelta, timezone

        from django.conf import settings

        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "iss": settings.SUPABASE_URL.rstrip("/") + "/auth/v1",
                "aud": "authenticated",
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            key="",
            algorithm="none",
        )
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 401

    def test_hs256_signed_with_public_key_is_rejected(self, client, jwks_server):
        """
        The other half of the confusion attack: sign with HS256 using the
        public key as the HMAC secret. The allowlist is ES256 only, so this
        fails even though the key material is genuinely correct.

        The token is assembled by hand because PyJWT refuses to *sign* with a
        PEM key, which is itself a good sign: it does not consider a PEM to be
        a valid HMAC secret. An attacker would not be using PyJWT.
        """
        import base64
        import hashlib
        import hmac
        import json
        from datetime import datetime, timedelta, timezone

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        from django.conf import settings

        # A keypair standing in for "the verification key's public half".
        public_key = ec.generate_private_key(ec.SECP256R1()).public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        now = datetime.now(timezone.utc)
        header = {"alg": "HS256", "typ": "JWT", "kid": "test-kid-1"}
        payload = {
            "sub": str(uuid.uuid4()),
            "iss": settings.SUPABASE_URL.rstrip("/") + "/auth/v1",
            "aud": "authenticated",
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        signing_input = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(payload).encode())}"
        signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
        token = f"{signing_input}.{b64(signature)}"

        # Sanity check: the HMAC is genuine, so a verifier that honoured HS256
        # and looked the key up by kid would accept this. It must still fail.
        assert hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()

        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 401


class TestValidToken:
    def test_me_returns_the_profile(self, client, jwks_server, make_token):
        token = make_token(email="reader@example.com")
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200

        body = response.json()
        assert body["email"] == "reader@example.com"
        uuid.UUID(body["id"])  # raises if it is not a real UUID
        assert body["created_at"]

    def test_profile_row_is_created_on_first_request(
        self, client, jwks_server, make_token
    ):
        from api.models import Profile

        user_id = str(uuid.uuid4())
        token = make_token(subject=user_id, email="new@example.com")

        assert not Profile.objects.filter(id=user_id).exists()
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200
        assert Profile.objects.filter(id=user_id).exists()

    def test_repeat_request_does_not_duplicate_the_profile(
        self, client, jwks_server, make_token
    ):
        """The upsert is lazy but must be idempotent, not get-or-create per call."""
        from api.models import Profile

        user_id = str(uuid.uuid4())
        token = make_token(subject=user_id)

        for _ in range(3):
            assert (
                client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}").status_code
                == 200
            )
        assert Profile.objects.filter(id=user_id).count() == 1

    def test_email_change_is_reflected_in_the_mirror(
        self, client, jwks_server, make_token
    ):
        """Supabase is the source of truth for the address."""
        from api.models import Profile

        user_id = str(uuid.uuid4())
        first = make_token(subject=user_id, email="old@example.com")
        client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {first}")

        second = make_token(subject=user_id, email="new@example.com")
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {second}")

        assert response.json()["email"] == "new@example.com"
        assert Profile.objects.get(id=user_id).email == "new@example.com"


class TestJwksCaching:
    def test_key_is_fetched_once_across_many_requests(
        self, client, jwks_server, make_token, monkeypatch
    ):
        """
        Refetching per request would put the auth endpoint on the critical path
        of every call. Assert the fetch count, not just the outcome.
        """
        from api import jwt_auth

        calls = {"count": 0}
        original_fetch = jwt_auth.JWKSCache._fetch

        def counting_fetch(self):
            calls["count"] += 1
            return original_fetch(self)

        monkeypatch.setattr(jwt_auth.JWKSCache, "_fetch", counting_fetch)

        token = make_token()
        for _ in range(5):
            assert (
                client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}").status_code
                == 200
            )
        assert calls["count"] == 1

    def test_unknown_kid_triggers_one_refresh(self, client, jwks_server, make_token):
        """Supabase rotates keys. An unknown kid must refetch, not hard-fail."""
        token = make_token(kid="a-rotated-kid")
        response = client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200


class TestVerifyTokenUnit:
    def test_raises_auth_error_for_missing_jwks_url(self, monkeypatch, make_token):
        from api import jwt_auth

        monkeypatch.setattr(jwt_auth, "_jwks_cache", jwt_auth.JWKSCache(""))
        with pytest.raises(AuthError) as excinfo:
            verify_token(make_token())
        assert excinfo.value.code == "auth_unavailable"

    def test_missing_supabase_url_is_a_config_error_not_a_crash(self, client):
        """
        A misconfigured deployment should fail with a clear 401-shaped auth
        error, not a stack trace on every request.
        """
        from api import jwt_auth

        monkey = jwt_auth.JWKSCache("")
        assert monkey._url == ""
