"""Shared test setup.

Cookies here are built the way `@supabase/ssr` builds them, because a fixture
that invented its own format is worse than no fixture: it agrees with whatever
the parser happens to do. The shape is taken from `dist/main/cookies.js` in
`frontend/node_modules/@supabase/ssr`:

    "base64-" + base64url(json.dumps(session))

optionally split into ``<name>.0``, ``<name>.1`` chunks.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest


def b64url(raw: str) -> str:
    """Mirror @supabase/ssr's base64url encoding: no padding, url alphabet."""
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def build_cookie_value(session: dict[str, Any], *, plain: bool = False) -> str:
    """Encode a session dict the way the SSR cookie adapter does."""
    raw = json.dumps(session, separators=(",", ":"))
    if plain:
        return raw
    return "base64-" + b64url(raw)


@pytest.fixture(autouse=True)
def _isolate():
    """Keep cached token verifications from leaking between tests."""
    from api.supabase_auth import clear_cache

    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def session_payload():
    """A minimal but realistic Supabase session."""

    def _make(
        access_token: str = "header.payload.signature",
        *,
        expires_at: int = 4_000_000_000,
        refresh_token: str = "refresh-abc",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": expires_at,
        }
        if refresh_token is not None:
            payload["refresh_token"] = refresh_token
        return payload

    return _make


@pytest.fixture
def make_session_cookie(session_payload):
    """Build request cookies in each shape the SSR adapter can produce."""

    def _make(
        access_token: str = "header.payload.signature",
        *,
        expires_at: int = 4_000_000_000,
        refresh_token: str = "refresh-abc",
        cookie_name: str = "sb-abcdefghijklmnopqrst-auth-token",
        plain: bool = False,
        chunk_size: int | None = None,
    ) -> dict[str, str]:
        session = session_payload(access_token, expires_at=expires_at, refresh_token=refresh_token)
        value = build_cookie_value(session, plain=plain)

        if chunk_size is None:
            return {cookie_name: value}

        chunks = [value[i : i + chunk_size] for i in range(0, len(value), chunk_size)]
        return {f"{cookie_name}.{index}": chunk for index, chunk in enumerate(chunks)}

    return _make
