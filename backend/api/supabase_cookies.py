"""Reading a Supabase SSR session out of request cookies.

This mirrors what `@supabase/ssr` actually writes, verified against the copy in
`frontend/node_modules/@supabase/ssr`. The relevant code is `combineChunks` and
the read path of the server storage adapter in `dist/main/cookies.js`:

  1. the session is serialised to JSON, then encoded as
     ``"base64-" + base64url(json)``;
  2. that encoded string is split into chunks of at most 3180 characters named
     ``<name>.0``, ``<name>.1``, ... only when it does not fit one cookie;
  3. reading tries the unchunked cookie first and only falls back to joining
     ``.0``, ``.1``, ... in order, stopping at the first gap.

Two details are easy to get wrong and both fail silently. The `base64-` prefix
is stripped *before* decoding, and because `-` is itself a valid base64url
character, decoding without stripping it yields plausible-looking garbage
rather than an error. And a project may set `cookieEncoding: "plain"`, in which
case the value is raw JSON with no prefix at all.

Cookie names are matched on the `auth-token` marker rather than a specific
project ref, so pointing the backend at a different Supabase project stays a
configuration change.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
from dataclasses import dataclass

AUTH_COOKIE_MARKER = "auth-token"
BASE64_PREFIX = "base64-"

# Matches the chunk naming used by @supabase/ssr: any suffix, then `.` and a
# chunk index with no leading zeros.
_CHUNK_SUFFIX = re.compile(r"^(?P<base>.+)\.(?P<index>0|[1-9][0-9]*)$")


@dataclass(frozen=True)
class SupabaseSession:
    """The parts of the stored Supabase session this backend needs."""

    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None

    @property
    def is_expired(self) -> bool:
        """Whether `expires_at` has passed.

        `expires_at` is a Unix timestamp in seconds, so this compares against
        the clock. It is a hint for deciding whether to prompt a refresh; the
        Auth API remains the authority on whether a token is still good.
        """
        if self.expires_at is None:
            return False
        return self.expires_at <= time.time()


def _b64url_decode(value: str) -> str:
    """Decode base64url, tolerating missing padding."""
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def _candidate_names(cookies: dict[str, str]) -> list[str]:
    """Every cookie name that could hold a Supabase session.

    A name qualifies either by being an unchunked auth cookie, or by being a
    chunk of one. Ordered so the unchunked form is tried first, matching
    `combineChunks`.
    """
    plain: list[str] = []
    chunked: list[str] = []

    for name in cookies:
        if AUTH_COOKIE_MARKER not in name:
            continue
        match = _CHUNK_SUFFIX.match(name)
        if match:
            chunked.append(match.group("base"))
        else:
            plain.append(name)

    # Deduplicate while keeping the plain cookies ahead of the chunked ones.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in [*plain, *chunked]:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _combine(name: str, cookies: dict[str, str]) -> str | None:
    """Reassemble one cookie's value, preferring the unchunked form."""
    if name in cookies:
        return cookies[name]

    parts: list[str] = []
    index = 0
    while True:
        chunk = cookies.get(f"{name}.{index}")
        if chunk is None:
            # Matches `combineChunks`, which stops at the first gap. A missing
            # middle chunk means the value is unrecoverable, so stop rather
            # than silently concatenating two halves of different sessions.
            break
        parts.append(chunk)
        index += 1

    return "".join(parts) if parts else None


def _decode_value(encoded: str) -> str | None:
    """Undo the `base64-` prefix and base64url encoding, if present."""
    if not encoded.startswith(BASE64_PREFIX):
        # cookieEncoding: "plain", or a project predating base64url encoding.
        return encoded
    try:
        return _b64url_decode(encoded[len(BASE64_PREFIX) :])
    except binascii.Error, UnicodeDecodeError, ValueError:
        return None


def _parse_session(raw: str) -> SupabaseSession | None:
    """Read a serialised Supabase session out of the decoded cookie value."""
    try:
        payload = json.loads(raw)
    except TypeError, ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None

    refresh_token = payload.get("refresh_token")
    expires_at = payload.get("expires_at")

    return SupabaseSession(
        access_token=access_token,
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        expires_at=expires_at if isinstance(expires_at, int) else None,
    )


def extract_session(cookies: dict[str, str]) -> SupabaseSession | None:
    """Recover the Supabase session from a request's cookies.

    Returns None when there is no session, and also when a session cookie exists
    but cannot be decoded. A corrupt cookie should log the user out, not
    produce a 500.
    """
    for name in _candidate_names(cookies):
        combined = _combine(name, cookies)
        if combined is None:
            continue

        decoded = _decode_value(combined)
        if decoded is None:
            continue

        session = _parse_session(decoded)
        if session is not None:
            return session

    return None
