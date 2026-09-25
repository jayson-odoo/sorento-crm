"""Chatbot stock ask v2 S3 fix round 1, Blocking 1 (R6 B1, R14) and AC-SA312.

Reviewer pass, PR #1247 S3 at e01ef5c2: AC-SA312's regex guard ran only over the MCP
presenter's item TITLE (`sorento_crm_mcp/tests/test_presenters_availability_lines.py`),
never over the actual WhatsApp text `output_structurer` builds - so `_availability_intro`'s
shared intro and `_item_line`'s position number (`f"{position}. "`) both reached the
dealer unguarded. `_availability_intro`'s old `_AVAILABILITY_NO` line ("Sorry, we do not
have enough stock for that quantity.") is a statement about OUR stock, which R6 B1
forbids, and is false for a `too_big` entry with plenty on hand. This file guards the
RENDERED reply `output_structurer` produces, not the presenter's item title alone.
"""
from __future__ import annotations

import re

from app.services.chatbot.lanes.business import fetch


def _entry(code: str, qty: int, branch: str, tail: str) -> dict:
    return {
        "title": f"{code} x {qty}: {tail}",
        "fields": [],
        "flags": {"needs_quantity": False, "branch": branch},
    }


def _availability_envelope(items: list) -> dict:
    return {
        "result_type": "stock_availability",
        "intro": "",
        "items": items,
        "has_result": True,
    }


def test_answered_reply_carries_no_intro_and_no_numbering():
    """A too_big entry with stock on hand elsewhere must never be preceded by a
    sentence claiming OUR stock is short, and no line is prefixed with a position
    number - the item title alone (product, quantity, R6 sentence) is the whole
    answer, plan sample (g)."""
    entries = [
        _entry(
            "SRT-TOOBIG",
            250,
            "too_big",
            "the quantity is more than what I can confirm here, please refer to "
            "your salesman.",
        ),
        _entry(
            "SRT-INSTOCK",
            5,
            "in_stock",
            "yes, we have stock, please refer to your salesman to proceed.",
        ),
    ]
    out = fetch.output_structurer(_availability_envelope(entries), {"semantic_input": {}})

    assert "Sorry, we do not have enough stock" not in out["response"]
    assert "enough stock" not in out["response"]
    assert not out["response"].startswith("1.")
    assert "1. SRT-TOOBIG" not in out["response"]
    assert "2. SRT-INSTOCK" not in out["response"]
    assert out["response"] == (
        "SRT-TOOBIG x 250: the quantity is more than what I can confirm here, "
        "please refer to your salesman.\n\n"
        "SRT-INSTOCK x 5: yes, we have stock, please refer to your salesman to "
        "proceed."
    )


def test_ac_sa312_rendered_reply_has_no_digit_of_ours():
    """AC-SA312, over the RENDERED reply: the only digits anywhere in the message are
    the dealer's own asked quantities and the ETA date, never a position number or a
    stock figure of ours."""
    entries = [
        _entry(
            "SRT-BIG",
            42,
            "too_big",
            "the quantity is more than what I can confirm here, please refer to "
            "your salesman.",
        ),
        _entry("SRT-ETA", 7, "incoming", "no stock at the moment, ETA 19/10/2026."),
    ]
    out = fetch.output_structurer(_availability_envelope(entries), {"semantic_input": {}})

    assert re.findall(r"\d+", out["response"]) == ["42", "7", "19", "10", "2026"]
