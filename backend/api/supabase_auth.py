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
    pass


@dataclass(frozen=True)
class SupabaseUser:
    id: str
    email: str | None = None
    claims: dict | None = None


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        return {}
    return claims if isinstance(claims, dict) else {}


class _VerifiedUserCache:
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
    _cache.clear()
