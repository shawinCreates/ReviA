from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import httpx
import pytest


def b64url(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def build_cookie_value(session: dict[str, Any], *, plain: bool = False) -> str:
    raw = json.dumps(session, separators=(",", ":"))
    if plain:
        return raw
    return "base64-" + b64url(raw)


@pytest.fixture(autouse=True)
def _isolate():
    from api.supabase_auth import clear_cache

    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def session_payload():
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

AUTH_COOKIE = "sb-abcdefghijklmnopqrst-auth-token"


def auth_cookie(access_token: str = "header.payload.signature") -> str:
    return build_cookie_value(
        {"access_token": access_token, "expires_at": 4_000_000_000, "refresh_token": "r"}
    )


@pytest.fixture
def mock_auth_api(monkeypatch):
    calls: list[str] = []

    def _install(status_code: int, payload: dict, *, raise_exc: Exception | None = None):
        def _handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.headers.get("authorization", ""))
            if raise_exc is not None:
                raise raise_exc
            return httpx.Response(status_code, json=payload)

        transport = httpx.MockTransport(_handler)
        original = httpx.Client

        def _patched(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", _patched)
        return calls

    return _install


@pytest.fixture
def token_auth(monkeypatch):
    def _handler(request: httpx.Request) -> httpx.Response:
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        user_id = token.removeprefix("token-for-")
        if not user_id or user_id == token:
            return httpx.Response(401, json={"message": "invalid token"})
        return httpx.Response(200, json={"id": user_id, "email": f"{user_id[:8]}@example.com"})

    transport = httpx.MockTransport(_handler)
    original = httpx.Client

    def _patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _patched)


@pytest.fixture
def auth_client(token_auth):
    from rest_framework.test import APIClient

    def _make(user_id: str | None = None, email: str | None = None):
        resolved = user_id or str(uuid.uuid4())
        client = APIClient()
        client.cookies[AUTH_COOKIE] = auth_cookie(f"token-for-{resolved}")
        client.owner_id = resolved
        client.email = email
        return client

    return _make
