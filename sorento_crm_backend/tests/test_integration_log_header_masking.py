"""`integration_logs.request_headers` must never store a credential.

Every external endpoint that logs its own call copied the same two lines:
`dict(request.headers)` and then `if "x-api-key" in headers: headers["x-api-key"]
= "***"`. Exactly one key was masked, so `authorization`, `cookie`,
`x-chatbot-retry-key` and `proxy-authorization` landed in the table in plaintext,
readable by anyone who can read integration logs - once per customer message,
forever, because `chatbot.turns` and its logs are never pruned. `X-API-Key` and
`Authorization: Bearer` are BOTH accepted by `get_current_user_or_api_key`, so
which one an n8n HTTP node is configured with decided whether the secret was
kept.

There is now one helper and five callers, and this file is its guardrail: the
denylist test, the case-insensitivity test (HTTP header names are
case-insensitive and Starlette lowercases them, but a caller may pass a plain
dict), the substring rule that catches a header nobody has invented yet, and a
scan asserting no endpoint has gone back to hand-rolling it.

Pure functions and a source scan: no database, no HTTP, CI-safe.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services.integration_service import (
    MASKED_HEADER_VALUE,
    sanitize_request_headers,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_every_named_credential_header_is_masked() -> None:
    masked = sanitize_request_headers(
        {
            "x-api-key": "sk-live-1",
            "authorization": "Bearer eyJhb.secret",
            "proxy-authorization": "Basic abc",
            "cookie": "session=zzt",
            "set-cookie": "session=zzt",
            "x-chatbot-retry-key": "retry-secret",
        }
    )

    assert set(masked.values()) == {MASKED_HEADER_VALUE}


def test_a_header_that_merely_looks_like_a_credential_is_masked_too() -> None:
    """The denylist cannot name a header that does not exist yet, so the rule is
    also "the NAME says it is one"."""
    masked = sanitize_request_headers(
        {
            "x-webhook-secret": "s",
            "x-some-token": "t",
            "x-vendor-api-key": "k",
            "x-signing-Key": "k",
        }
    )

    assert set(masked.values()) == {MASKED_HEADER_VALUE}


def test_ordinary_headers_survive_unchanged() -> None:
    headers = {
        "content-type": "application/json",
        "content-length": "1234",
        "user-agent": "n8n",
        "x-request-id": "req-1",
        "host": "fe-sorento.foundryx.my",
    }

    assert sanitize_request_headers(headers) == headers


def test_the_match_is_case_insensitive_and_keeps_the_original_name() -> None:
    masked = sanitize_request_headers({"X-API-Key": "sk", "Authorization": "Bearer x"})

    assert masked == {"X-API-Key": MASKED_HEADER_VALUE, "Authorization": MASKED_HEADER_VALUE}


def test_a_missing_credential_header_adds_nothing() -> None:
    """Masking must not INVENT a key: an absent header stays absent, or every log
    row would claim a credential was sent."""
    assert sanitize_request_headers({"content-type": "application/json"}) == {
        "content-type": "application/json"
    }
    assert sanitize_request_headers({}) == {}


def test_no_endpoint_hand_rolls_the_mask_any_more() -> None:
    """The copy-paste this replaces, as a pattern: assigning a literal mask to a
    header key. A new external endpoint that reinvents it fails here rather than
    in a table nobody reads."""
    offenders: list[str] = []
    pattern = re.compile(r"""\[["']x-api-key["']\]\s*=""", re.IGNORECASE)
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        if pattern.search(path.read_text()):
            offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == [], (
        "these files mask headers by hand instead of calling "
        f"sanitize_request_headers: {offenders}"
    )
