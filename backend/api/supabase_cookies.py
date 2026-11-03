from __future__ import annotations

import base64
import binascii
import json
import re
import time
from dataclasses import dataclass

AUTH_COOKIE_MARKER = "auth-token"
BASE64_PREFIX = "base64-"

# @supabase/ssr chunk naming: suffix, then "." and a no-leading-zero index.
_CHUNK_SUFFIX = re.compile(r"^(?P<base>.+)\.(?P<index>0|[1-9][0-9]*)$")


@dataclass(frozen=True)
class SupabaseSession:
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= time.time()


def _b64url_decode(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def _candidate_names(cookies: dict[str, str]) -> list[str]:
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
    if name in cookies:
        return cookies[name]

    parts: list[str] = []
    index = 0
    while True:
        chunk = cookies.get(f"{name}.{index}")
        if chunk is None:
            # Like combineChunks: stop at the first gap rather than mixing sessions.
            break
        parts.append(chunk)
        index += 1

    return "".join(parts) if parts else None


def _decode_value(encoded: str) -> str | None:
    if not encoded.startswith(BASE64_PREFIX):
        # cookieEncoding: "plain", or a project predating base64url encoding.
        return encoded
    try:
        return _b64url_decode(encoded[len(BASE64_PREFIX) :])
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _parse_session(raw: str) -> SupabaseSession | None:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
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
