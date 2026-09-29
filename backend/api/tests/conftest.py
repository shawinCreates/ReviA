"""
Shared test fixtures.

The auth tests need a real ES256 keypair, because the thing being tested is
whether a genuinely signed Supabase-shaped token verifies. Mocking the
signature check would mean the ES256 path, which differs from RS256, was never
exercised at all. So these tests generate a real key, serve a real JWKS, and
sign real tokens.

The `sub` is a real Profile upsert against the real database, which also proves
the middleware writes a row.
"""

from __future__ import annotations

import json
import time
import types
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

# Settings are loaded before anything else so that SUPABASE_URL is populated
# when the issuer is checked.
from django.conf import settings  # noqa: E402


@pytest.fixture(scope="session")
def signing_key():
    """A real P-256 key, the curve Supabase signs with."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def jwks_document(signing_key):
    """
    A JWKS in Supabase's exact shape, including ES256 and P-256. If this
    fixture ever drifts to RS256 the tests stop covering the real case.
    """
    numbers = signing_key.public_key().public_numbers()

    def b64(value: int) -> str:
        import base64

        length = (value.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()

    return {
        "keys": [
            {
                "kty": "EC",
                "crv": "P-256",
                "x": b64(numbers.x),
                "y": b64(numbers.y),
                "alg": "ES256",
                "use": "sig",
                "ext": True,
                "key_ops": ["verify"],
                "kid": "test-kid-1",
            }
        ]
    }


@pytest.fixture
def jwks_server(jwks_document, monkeypatch):
    """
    Point the JWKS cache at an in-process keyset. The cache is module-level and
    session-lived, so it is reset explicitly rather than left to leak a test
    key into later tests.
    """
    from api import jwt_auth

    document = json.dumps(jwks_document).encode()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return json.loads(document)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            return FakeResponse()

    # Patch a shim inside jwt_auth's namespace, NOT `httpx.Client` itself.
    # `jwt_auth.httpx` is the shared httpx module object, so patching its
    # `Client` attribute also breaks huggingface_hub, which uses the same
    # module. That surfaced as an AttributeError deep inside a model download
    # during the upload tests, in a completely unrelated code path.
    fake_httpx = types.SimpleNamespace(Client=FakeClient)
    monkeypatch.setattr(jwt_auth, "httpx", fake_httpx)

    cache = jwt_auth.JWKSCache("https://test.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setattr(jwt_auth, "_jwks_cache", cache)
    return cache


@pytest.fixture(scope="session", autouse=True)
def warm_embedding_model():
    """
    Load the local ONNX model once, before any test can interfere with HTTP.

    `api.embeddings` caches the session in a module global on first use, so
    doing this here means the download never happens again mid-test — and
    `hf_hub_download` revalidates its cache over the network on every call,
    which is not something a test should be doing.
    """
    from api.embeddings import embed_texts

    try:
        embed_texts(["warmup"])
    except Exception as exc:  # pragma: no cover - reported by the tests that need it
        pytest.exit(f"Embedding model could not be loaded: {exc}", returncode=1)


@pytest.fixture
def make_token(signing_key):
    """Mint a token shaped exactly like a Supabase one."""

    def _make(
        *,
        subject: str | None = None,
        email: str = "student@example.com",
        issuer: str | None = None,
        expires_delta: timedelta = timedelta(hours=1),
        algorithm: str = "ES256",
        kid: str = "test-kid-1",
        key=None,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": subject or str(uuid.uuid4()),
            "email": email,
            "iss": issuer or (settings.SUPABASE_URL.rstrip("/") + "/auth/v1"),
            "aud": "authenticated",
            "role": "authenticated",
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
        }
        return jwt.encode(
            payload, key or signing_key, algorithm=algorithm, headers={"kid": kid}
        )

    return _make


@pytest.fixture
def auth_client(client, make_token):
    """A DRF test client carrying a valid Bearer token."""

    def _make(**kwargs):
        token = make_token(**kwargs)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return client

    return _make
