"""
Supabase JWT verification.

Supabase owns auth; Django verifies and mirrors. There is no login endpoint
here and no password ever touches this service. See decisions.md D-004.

Two details are load-bearing and were confirmed against the live project
rather than assumed:

1. Supabase signs with **ES256** (ECDSA P-256), not RS256. The JWKS at
   /auth/v1/.well-known/jwks.json returns `{"alg":"ES256","crv":"P-256",...}`.
   architecture.md said RS256; that is wrong, and it matters because it decides
   the allowed algorithms. `algorithms` below is a fixed allowlist, never read
   from the token, so a token cannot select its own verification algorithm.
2. The JWKS is cached in-process and refreshed at most once per hour, or on an
   unknown `kid` when Supabase rotates keys. Refetching per request would add a
   network round trip to every API call and put availability of the auth
   endpoint on the critical path of every endpoint.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

# Supabase signs ES256. This allowlist is a constant, not configuration: it must
# not be possible for a token to name the algorithm it wants to be verified
# with. `none` and HS256 are the classic JWT confusion attacks.
ALLOWED_ALGORITHMS = ["ES256"]

# Refresh at most this often even when a kid is unknown, so a stream of
# requests with garbage tokens cannot turn into a stream of JWKS fetches.
JWKS_MIN_REFRESH_INTERVAL_SECONDS = 3600
JWKS_FETCH_TIMEOUT_SECONDS = 5.0


class AuthError(Exception):
    """Authentication failed. Carries the code that goes in the error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VerifiedToken:
    user_id: uuid.UUID
    email: str
    claims: dict[str, Any]


class JWKSCache:
    """
    Process-local JWKS cache with a rate-limited refresh.

    Thread-safe because a Django ASGI worker handles concurrent requests and
    several may miss the cache at once. The lock is only held around the
    refetch, never around verification, so a cache hit does not serialise.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._signing_key: jwt.PyJWK | None = None
        self._loaded_at: float = 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> None:
        if not self._url:
            raise AuthError(
                "auth_unavailable",
                "SUPABASE_URL is not configured, so tokens cannot be verified.",
            )
        try:
            with httpx.Client(timeout=JWKS_FETCH_TIMEOUT_SECONDS) as client:
                response = client.get(self._url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            # The cache is a dependency, not a nicety: without it no request
            # can be authenticated. Log the cause, but never the response body,
            # which can contain key material.
            logger.error("JWKS fetch failed from %s: %s", self._url, type(exc).__name__)
            raise AuthError("auth_unavailable", "Could not fetch the signing keys.") from exc

        keys = payload.get("keys") or []
        if not keys:
            logger.error("JWKS response from %s contained no keys", self._url)
            raise AuthError("auth_unavailable", "The signing key set was empty.")

        key = jwt.PyJWK.from_dict(keys[0])
        if key.algorithm_name not in ALLOWED_ALGORITHMS:
            # Refuse rather than widen the allowlist at runtime.
            logger.error("JWKS offered algorithm %s, which is not allowed", key.algorithm_name)
            raise AuthError("auth_unavailable", "The signing key algorithm is not supported.")

        self._signing_key = key
        self._loaded_at = time.monotonic()
        logger.info("Loaded Supabase JWKS, kid=%s alg=%s", key.key_id, key.algorithm_name)

    def get_key(self, kid: str | None) -> jwt.PyJWK:
        now = time.monotonic()
        stale = now - self._loaded_at > JWKS_MIN_REFRESH_INTERVAL_SECONDS

        if self._signing_key is not None and not stale:
            if kid is None or self._signing_key.key_id == kid:
                return self._signing_key
        elif self._signing_key is not None and kid == self._signing_key.key_id:
            # Cached key matches the token's kid but is stale: keep using it.
            # Expiry is still checked, so a stale key cannot extend a session.
            return self._signing_key

        with self._lock:
            # Re-check: another thread may have refreshed while we waited.
            now = time.monotonic()
            if (
                self._signing_key is not None
                and not now - self._loaded_at > JWKS_MIN_REFRESH_INTERVAL_SECONDS
                and (kid is None or self._signing_key.key_id == kid)
            ):
                return self._signing_key
            self._fetch()
            assert self._signing_key is not None
            return self._signing_key


_jwks_cache: JWKSCache | None = None
_jwks_lock = threading.Lock()


def get_jwks_cache() -> JWKSCache:
    global _jwks_cache
    if _jwks_cache is None:
        with _jwks_lock:
            if _jwks_cache is None:
                _jwks_cache = JWKSCache(settings.SUPABASE_JWKS_URL)
    return _jwks_cache


def extract_bearer_token(header_value: str | None) -> str:
    """Return the token from an Authorization header, or raise AuthError."""
    if not header_value:
        raise AuthError("unauthenticated", "Missing Authorization header.")
    parts = header_value.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("unauthenticated", "Authorization header must be 'Bearer <token>'.")
    return parts[1]


def _expected_issuer() -> str:
    """The `iss` claim of a token minted by this project's Supabase Auth."""
    return settings.SUPABASE_URL.rstrip("/") + "/auth/v1"


def verify_token(token: str) -> VerifiedToken:
    """
    Verify signature, expiry, and issuer. Raises AuthError on any failure.

    The cross-project binding is the issuer, not the audience. Supabase user
    tokens all carry `aud: "authenticated"` regardless of project, but `iss`
    is `https://<project-ref>.supabase.co/auth/v1` and therefore unique per
    project. Verifying `iss` is what stops a token minted for a different
    Supabase project from being accepted here.
    """
    # Decode the header only, to learn the kid. Signature is not yet checked,
    # so nothing from the token body is trusted at this point.
    try:
        unverified = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("unauthenticated", "Malformed token.") from exc

    key = get_jwks_cache().get_key(unverified.get("kid"))

    options = {
        "require": ["exp", "sub", "iss"],
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": False,
        "verify_iss": True,
    }

    expected_issuer = _expected_issuer()

    try:
        claims = jwt.decode(
            token,
            key.key,
            algorithms=ALLOWED_ALGORITHMS,
            issuer=expected_issuer,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("unauthenticated", "Token has expired.") from exc
    except jwt.InvalidIssuerError as exc:
        # A valid signature from a different project (or a foreign actor
        # using our project's name). Logged distinctly because it means a
        # misconfiguration or a cross-project token, not a user error.
        logger.warning("Token issuer did not match %r", expected_issuer)
        raise AuthError("unauthenticated", "Token issuer is not valid here.") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("unauthenticated", "Token could not be verified.") from exc

    subject = claims.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (TypeError, ValueError) as exc:
        raise AuthError("unauthenticated", "Token subject is not a UUID.") from exc

    return VerifiedToken(
        user_id=user_id, email=str(claims.get("email") or ""), claims=claims
    )
