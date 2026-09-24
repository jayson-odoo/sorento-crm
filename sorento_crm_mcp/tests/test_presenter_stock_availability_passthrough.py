"""Dealer stock verdict - review round 6, the root cause behind findings A, E and F.

Live evidence (`sorento_crm_backend/tests/chatbot/journeys/dealer-stock-verdict.EVIDENCE.md`,
Run 3): every turn of every case went into the next turn with `focus.tasks: []`, so the
open stock task never survived a single turn in production - "make MHS1028 80" answered
MHS1028 alone because there was no task holding MSK11A-QT, not because the task dropped it.

Measured on the live database (`chatbot.turns`, turn `d18b2e6f`, the `looked_up` trace):
the engine's own envelope carried `"stock_availability": []`, which is
`turn_runtime.py`'s default for "the lane did not carry one". The lane copies the block
only when the MCP envelope has it (`lanes/business/fetch.py`, the `isinstance(e.get(
"stock_availability"), list)` guard) - and `present_response` builds the render envelope
from a fixed key list plus `_PASSTHROUGH_KEYS`, which did not include it. The dealer's
reply was right (the presenter reads the block before discarding it), but the one fact
`turn/task.py::tasks_after_reply` opens the task from never left this process.

`_PASSTHROUGH_KEYS` is the mechanism for exactly this - "keys preserved from the raw
response into the envelope ... kept so render mode loses nothing".
"""
from __future__ import annotations

import json

from sorento_crm_mcp.presenters import present_response

TOOL = "crm_inventory_stock_balance_list"


def _entry(code, *, needs_quantity, requested_qty=None, verdict=None):
    return {
        "product_id": f"00000000-0000-4000-8000-0000000000{len(code):02d}",
        "product_code": code,
        "product_name": code,
        "needs_quantity": needs_quantity,
        "requested_qty": requested_qty,
        "available": None if verdict is None else verdict == "available",
        "verdict": verdict,
        "running_low": None if verdict is None else False,
        "disclaimer": None,
    }


def _payload(entries):
    return {
        "data": [],
        "pagination": {"total": len(entries), "page": 1, "limit": 50},
        "empty": False,
        "stock_visibility": {
            "mode": "availability",
            "source": "contact",
            "hide_zero_locations": False,
        },
        "stock_availability": entries,
        "last_updated_at": "2026-09-22T18:00:00",
    }


def test_render_envelope_carries_the_availability_block_through():
    """The block is what the ENGINE reads (D25): one entry per product, each with the
    `needs_quantity` the backend decided. Without it in the envelope no stock task is
    ever opened, so every later turn - a restated quantity, a resume, a "just proceed" -
    has nothing to be about."""
    entries = [
        _entry("MHS1028", needs_quantity=False, requested_qty=60, verdict="available"),
        _entry("MSK11A-QT", needs_quantity=True),
    ]

    out = json.loads(present_response(TOOL, json.dumps(_payload(entries))))

    assert out["stock_availability"] == entries


def test_a_detailed_reply_carries_no_availability_block():
    """Only the dealer mode has one - a detailed/staff reply's envelope stays
    byte-identical, which is what `_filled` already guarantees for every other
    passthrough key."""
    payload = {
        "data": [],
        "pagination": {"total": 0, "page": 1, "limit": 50},
        "empty": True,
    }

    out = json.loads(present_response(TOOL, json.dumps(payload)))

    assert "stock_availability" not in out
