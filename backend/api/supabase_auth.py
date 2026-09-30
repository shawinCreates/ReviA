"""Turning a Supabase access token into a verified user.

The token is verified by asking Supabase Auth to resolve it rather than by
checking a signature locally. That costs one small HTTP request and buys two
things worth more than the latency:

  * the answer is authoritative regardless of whether the project signs with a
    legacy shared secret or the newer asymmetric keys, so there is no local
    verification path that can drift from the project's actual configuration;
  * a token signed by anyone else is rejected by construction.

Results are cached by token hash. A verified access token is immutable, so a
cache hit cannot go stale. The TTL bounds memory; it is not a correctness
mechanism. Failures are never cached, since a transport blip must not log
everyone out.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from threading import Lock

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_MAX_CACHE_ENTRIES = 1024


class TokenVerificationError(Exception):
    """The access token could not be verified."""


@dataclass(frozen=True)
class SupabaseUser:
    id: str
    email: str | None = None
    claims: dict | None = None


def _token_fingerprint(token: str) -> str:
    """A hash suitable as a cache key.

    The raw token is never a cache key, so it cannot leak through a cache dump.
    A full sha256 rather than a prefix, because truncated hashes collide.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_jwt_claims(token: str) -> dict:
    """Read a JWT payload without verifying it.

    Only used to enrich an identity that has already been verified against the
    Auth API. Nothing here can grant access on its own, so a malformed payload
    degrades to no extra claims rather than raising.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError, TypeError:
        return {}
    return claims if isinstance(claims, dict) else {}


class _VerifiedUserCache:
    """Small TTL cache of verified users, keyed by token fingerprint."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, dict]] = {}
        self._lock = Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, payload = entry
            if expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            return payload

    def put(self, key: str, payload: dict) -> None:
        ttl = settings.SUPABASE_AUTH_CACHE_SECONDS
        if ttl <= 0:
            return
        with self._lock:
            if len(self._entries) >= _MAX_CACHE_ENTRIES:
                # Cheapest correct eviction: drop the oldest expiry we can see.
                oldest = min(self._entries, key=lambda k: self._entries[k][0])
                self._entries.pop(oldest, None)
            self._entries[key] = (time.monotonic() + ttl, payload)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_cache = _VerifiedUserCache()


def _fetch_verified_user(token: str) -> dict:
    """Ask Supabase Auth to resolve the token to a user."""
    url = f"{settings.SUPABASE_URL}/auth/v1/user"
    headers = {
        "apikey": settings.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
    }

    try:
        with httpx.Client(timeout=settings.SUPABASE_AUTH_TIMEOUT_SECONDS) as client:
            response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        # A transport failure is not a rejected token. Say so distinctly, so the
        # caller can return 503 rather than pretending the user is unauthenticated.
        raise TokenVerificationError(f"supabase_auth_unavailable: {exc}") from exc

    if response.status_code in (401, 403):
        raise TokenVerificationError("invalid_token")
    if response.status_code >= 500:
        raise TokenVerificationError(f"supabase_auth_unavailable: {response.status_code}")
    if response.status_code != 200:
        raise TokenVerificationError(f"supabase_auth_unexpected: {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise TokenVerificationError("supabase_auth_unexpected: malformed json") from exc

    if not isinstance(payload, dict) or not payload.get("id"):
        raise TokenVerificationError("supabase_auth_unexpected: no user id in payload")

    return payload


def verify_access_token(token: str) -> SupabaseUser:
    """Verify a Supabase access token and return the authenticated user.

    Raises TokenVerificationError for both a rejected token and an unreachable
    Auth API; the message distinguishes them.
    """
    if not token or not token.strip():
        raise TokenVerificationError("missing_token")

    fingerprint = _token_fingerprint(token)

    payload = _cache.get(fingerprint)
    if payload is None:
        payload = _fetch_verified_user(token)
        _cache.put(fingerprint, payload)

    claims = _decode_jwt_claims(token)
    email = payload.get("email") or claims.get("email")

    return SupabaseUser(id=str(payload["id"]), email=email, claims=payload)


def clear_cache() -> None:
    """Drop all cached verifications. Intended for tests."""
    _cache.clear()
