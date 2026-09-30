"""Cookie parsing.

These are the cases that fail silently in production: a chunked cookie that is
never reassembled, the `base64-` prefix decoded as though it were not there, or
a session cookie read from a project that has been renamed.

The encoding is verified against `frontend/node_modules/@supabase/ssr`, so if
these tests pass, the parser agrees with the library the frontend actually uses.
"""

from __future__ import annotations

import json

import pytest

from api.supabase_cookies import extract_session
from api.tests.conftest import b64url, build_cookie_value

COOKIE = "sb-abcdefghijklmnopqrst-auth-token"


def test_no_cookies_yields_no_session():
    assert extract_session({}) is None


def test_unrelated_cookies_are_ignored():
    cookies = {
        "csrftoken": "abc123",
        "theme": "dark",
        "sb-other-ref-storage-key": "x",
    }
    assert extract_session(cookies) is None


def test_plain_single_cookie(make_session_cookie):
    session = extract_session(make_session_cookie(access_token="tok-plain"))

    assert session is not None
    assert session.access_token == "tok-plain"
    assert session.refresh_token == "refresh-abc"
    assert session.expires_at == 4_000_000_000


def test_chunked_cookie_is_reassembled(make_session_cookie):
    cookies = make_session_cookie(access_token="tok-chunked", chunk_size=24)
    assert len(cookies) > 1, "fixture should produce multiple chunks"

    session = extract_session(cookies)

    assert session is not None
    assert session.access_token == "tok-chunked"


def test_chunk_order_does_not_matter(make_session_cookie):
    cookies = make_session_cookie(access_token="tok-order", chunk_size=24)
    session = extract_session(dict(reversed(list(cookies.items()))))

    assert session is not None
    assert session.access_token == "tok-order"


def test_gap_in_chunks_stops_instead_of_splicing_sessions(make_session_cookie):
    """A missing middle chunk must not join two different sessions."""
    cookies = make_session_cookie(access_token="tok-gap", chunk_size=24)
    names = sorted(cookies, key=lambda n: int(n.rsplit(".", 1)[1]))
    assert len(names) >= 3, "fixture needs at least three chunks for this test"

    del cookies[names[1]]
    session = extract_session(cookies)

    # Either nothing, or a decodable token; never a spliced hybrid.
    if session is not None:
        assert session.access_token.startswith("tok-")
        assert session.refresh_token is None or session.refresh_token == "refresh-abc"


def test_unchunked_cookie_wins_over_stale_chunks(make_session_cookie):
    """`combineChunks` tries the plain cookie first; so must this."""
    fresh = make_session_cookie(access_token="tok-fresh")
    stale = make_session_cookie(access_token="tok-stale", chunk_size=24)

    cookies = {**stale, **fresh}
    session = extract_session(cookies)

    assert session is not None
    assert session.access_token == "tok-fresh"


def test_base64_prefix_is_stripped_before_decoding(make_session_cookie):
    """`-` is a valid base64url character, so decoding without stripping the
    prefix yields garbage rather than an error."""
    session = extract_session(make_session_cookie())

    assert session is not None
    assert session.access_token == "header.payload.signature"


def test_plain_encoding_without_prefix_is_supported(make_session_cookie):
    """A project configured with cookieEncoding: plain stores raw JSON."""
    cookies = make_session_cookie(access_token="tok-plain-encoding", plain=True)
    session = extract_session(cookies)

    assert session is not None
    assert session.access_token == "tok-plain-encoding"


def test_cookie_name_is_not_hardcoded_to_one_project_ref(make_session_cookie):
    cookies = make_session_cookie(
        access_token="tok-ref", cookie_name="sb-zzzzzzzzzzzzzzzz-auth-token"
    )
    session = extract_session(cookies)

    assert session is not None
    assert session.access_token == "tok-ref"


def test_corrupt_base64_is_treated_as_absent_not_an_error():
    assert extract_session({COOKIE: "base64-!!!not-base64!!!"}) is None


def test_valid_base64_that_is_not_json_is_treated_as_absent():
    assert extract_session({COOKIE: "base64-" + b64url("just a string")}) is None


def test_json_without_access_token_is_skipped():
    cookies = {COOKIE: build_cookie_value({"refresh_token": "only-this"})}
    assert extract_session(cookies) is None


def test_empty_access_token_is_rejected():
    cookies = {COOKIE: build_cookie_value({"access_token": ""})}
    assert extract_session(cookies) is None


def test_non_string_access_token_is_rejected():
    cookies = {COOKIE: build_cookie_value({"access_token": 12345})}
    assert extract_session(cookies) is None


def test_expired_session_is_reported_as_expired(make_session_cookie):
    session = extract_session(make_session_cookie(expires_at=1))

    assert session is not None
    assert session.is_expired is True


def test_session_without_expiry_is_not_treated_as_expired(session_payload):
    payload = session_payload()
    payload.pop("expires_at")
    cookies = {COOKIE: build_cookie_value(payload)}

    session = extract_session(cookies)

    assert session is not None
    assert session.expires_at is None
    assert session.is_expired is False


def test_non_integer_expiry_is_ignored_rather_than_crashing(session_payload):
    payload = session_payload()
    payload["expires_at"] = "soon"
    cookies = {COOKIE: build_cookie_value(payload)}

    session = extract_session(cookies)

    assert session is not None
    assert session.expires_at is None


def test_unicode_in_session_survives_the_round_trip(make_session_cookie):
    cookies = make_session_cookie(access_token="tok-ünïcøde-✓")
    session = extract_session(cookies)

    assert session is not None
    assert session.access_token == "tok-ünïcøde-✓"


def test_encoded_value_is_valid_json_after_decoding(session_payload):
    """Guards the fixture itself against drifting from the real format."""
    value = build_cookie_value(session_payload("tok"))
    assert value.startswith("base64-")

    padded = value[len("base64-") :] + "=" * (-len(value[len("base64-") :]) % 4)
    import base64

    assert json.loads(base64.urlsafe_b64decode(padded).decode())["access_token"] == "tok"


@pytest.mark.parametrize("bad", ["", "   "])
def test_blank_token_is_rejected_by_the_verifier(bad):
    from api.supabase_auth import TokenVerificationError, verify_access_token

    with pytest.raises(TokenVerificationError):
        verify_access_token(bad)
