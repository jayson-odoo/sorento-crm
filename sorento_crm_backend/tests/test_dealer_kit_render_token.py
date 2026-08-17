"""Render tokens: the only thing standing between a download id and its prices.

Headless Chromium has no session, so the print URL cannot be behind normal auth.
A bare download id would mean anyone who guesses a UUID gets a rendered page
that may carry prices they are not entitled to, so the URL is signed.
"""
from __future__ import annotations

import pytest

from app.services.dealer_kit import render_token

_ID = "11111111-2222-4333-8444-555555555555"
_OTHER = "99999999-2222-4333-8444-555555555555"
_NOW = 1_800_000_000


def test_a_freshly_issued_token_verifies():
    token = render_token.issue(_ID, now=_NOW)
    assert render_token.verify(_ID, token, now=_NOW) is True


def test_a_token_is_bound_to_its_download():
    # Otherwise one legitimate export URL would unlock every other one.
    token = render_token.issue(_ID, now=_NOW)
    assert render_token.verify(_OTHER, token, now=_NOW) is False


def test_a_token_expires():
    token = render_token.issue(_ID, ttl_seconds=60, now=_NOW)
    assert render_token.verify(_ID, token, now=_NOW + 59) is True
    assert render_token.verify(_ID, token, now=_NOW + 61) is False


@pytest.mark.parametrize(
    "bad",
    ["", None, "nonsense", "abc.def", "9999999999.deadbeef", ".", "9999999999."],
)
def test_a_malformed_or_forged_token_is_refused(bad):
    assert render_token.verify(_ID, bad, now=_NOW) is False


def test_a_tampered_expiry_does_not_extend_the_token():
    # The expiry is part of the signed payload, so pushing it out invalidates
    # the signature rather than buying more time.
    token = render_token.issue(_ID, ttl_seconds=60, now=_NOW)
    _expiry, _, signature = token.partition(".")
    forged = f"{_NOW + 99_999}.{signature}"
    assert render_token.verify(_ID, forged, now=_NOW) is False


def test_two_tokens_for_the_same_download_at_the_same_moment_match():
    # Deterministic: the worker can re-issue rather than having to store one.
    assert render_token.issue(_ID, now=_NOW) == render_token.issue(_ID, now=_NOW)
