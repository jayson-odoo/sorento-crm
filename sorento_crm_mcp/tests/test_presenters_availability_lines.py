"""Dealer stock verdict - S2, the MCP presenter's per-item verdict lines and the
noted/missing question (AC-1755 to AC-1758).

PLAN `documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md` "The presenter (S2)".
UAC `documentation/plans/chatbot/chatbot-dealer-stock-verdict-acceptance-criteria.md`
AC-1755 to AC-1758, rulings D3 (purchase ETA = "ETA in N days"), D10 (incoming ETA earliest
or "ETA to be confirmed"), D14 (no verdict shown while any asked product still needs a
quantity), D15 (a `proceed_anyway`/drop reply names what it did not check - out of scope
here, S3), D17 (no quantity of OURS ever reaches the reply - only the dealer's own asked
quantity, the ETA date, and "in N days").

`_stock_availability` / `_availability_intro` today only read `needs_quantity` and
`available` off each `stock_availability` entry (`presenters.py:1387-1424`) and render
nothing but a whole-reply yes/no/ask/mixed line - there is no per-item verdict text, no
`running_low` handling, no `disclaimer` handling at all. Every test below is red for that
reason: the exact sentence the AC names is simply not anywhere in the rendered envelope
yet, not a fixture bug.

The entry shape matches S1's contract (`tests/test_stock_availability_block.py`,
`sorento_crm_backend/tests/test_stock_availability_block.py`):

    {product_id, product_code, product_name, needs_quantity, requested_qty, available,
     verdict, running_low, disclaimer: None | {sources, limited, incoming_eta, purchase_eta_days}}

Assertions go through the SAME public render entry point
`tests/test_presenters_stock.py` uses (`present_response`/`env()`), on payload dicts - no
implementation has been written, so where exactly the coder lands the per-item sentence
(item title, a field, or elsewhere) is not pinned down here; `_rendered_text` sweeps every
customer-facing string in the envelope (`intro` + each item's `title` + each item's field
labels/values) so the test traces to the AC's wording ("the item line reads ...") without
over-specifying the JSON path.
"""
from __future__ import annotations

import json
import re

import pytest

from sorento_crm_mcp.presenters import present_response

TOOL = "crm_inventory_stock_balance_list"


def env(data):
    return json.loads(present_response(TOOL, json.dumps(data)))


def _visibility(mode, codes=None, source="contact"):
    return {"mode": mode, "warehouse_codes": codes, "source": source}


def _availability_payload(entries):
    return {
        "data": [],
        "pagination": {"total": len(entries), "page": 1, "limit": 50},
        "empty": False,
        "stock_visibility": _visibility("availability", ["BRW", "MWH", "DC1"], "access_type"),
        "stock_availability": entries,
        "last_updated_at": "2026-09-22T18:00:00",
    }


def _entry(
    code,
    *,
    needs_quantity=False,
    requested_qty=None,
    available=None,
    verdict=None,
    running_low=None,
    disclaimer=None,
    product_id="33333333-3333-4333-8333-333333333333",
):
    return {
        "product_id": product_id,
        "product_code": code,
        "product_name": code,
        "needs_quantity": needs_quantity,
        "requested_qty": requested_qty,
        "available": available,
        "verdict": verdict,
        "running_low": running_low,
        "disclaimer": disclaimer,
    }


def _rendered_text(out: dict) -> str:
    """Every customer-facing string in the envelope: `intro` plus each item's
    `title` and its fields' labels/values. Deliberately excludes envelope
    metadata (`last_updated_at`, `stock_visibility`, `flags`) - those are not
    read out to a dealer."""
    parts = [str(out.get("intro") or "")]
    for item in out.get("items") or []:
        if item.get("title") is not None:
            parts.append(str(item["title"]))
        for f in item.get("fields") or []:
            if f.get("label") is not None:
                parts.append(str(f["label"]))
            if f.get("value") is not None:
                parts.append(str(f["value"]))
    return "\n".join(parts)


# ============================================================ AC-1755, AC-1756


def test_item_line_available_not_running_low():
    """AC-1755. One product, `verdict = available`, `running_low = false`."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "MWT5727SS-CR",
                    requested_qty=5,
                    available=True,
                    verdict="available",
                    running_low=False,
                )
            ]
        )
    )

    assert "MWT5727SS-CR x 5: Yes, available." in _rendered_text(out)


def test_item_line_available_running_low():
    """AC-1756, case 1. `running_low = true`."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "MHS1028",
                    requested_qty=60,
                    available=True,
                    verdict="available",
                    running_low=True,
                )
            ]
        )
    )

    assert "MHS1028 x 60: Yes, available, but running low." in _rendered_text(out)


def test_item_line_not_available_no_sources():
    """AC-1756, case 2. `not_available`, no disclaimer at all."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "MHS9999",
                    requested_qty=20,
                    available=False,
                    verdict="not_available",
                    running_low=False,
                    disclaimer=None,
                )
            ]
        )
    )

    assert "MHS9999 x 20: Not available." in _rendered_text(out)


def test_item_line_not_available_incoming_limited():
    """AC-1756, case 3. Sources incoming only, limited."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "MSK11A-QT",
                    requested_qty=110,
                    available=False,
                    verdict="not_available",
                    running_low=False,
                    disclaimer={
                        "sources": ["incoming"],
                        "limited": True,
                        "incoming_eta": "2026-10-12",
                        "purchase_eta_days": 90,
                    },
                )
            ]
        )
    )

    assert (
        "MSK11A-QT x 110: Not available, but there is limited incoming, ETA 12/10/2026."
        in _rendered_text(out)
    )


def test_item_line_not_available_incoming_and_purchase_both_limited():
    """AC-1756, case 4. Both sources named, both limited - the PLAN's own worked
    example, verbatim."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "MSK11A-QT",
                    requested_qty=110,
                    available=False,
                    verdict="not_available",
                    running_low=False,
                    disclaimer={
                        "sources": ["incoming", "purchase"],
                        "limited": True,
                        "incoming_eta": "2026-10-12",
                        "purchase_eta_days": 90,
                    },
                )
            ]
        )
    )

    assert (
        "MSK11A-QT x 110: Not available, but there is limited incoming, ETA 12/10/2026 "
        "and limited purchase, ETA in 90 days." in _rendered_text(out)
    )


def test_item_line_not_available_purchase_only_not_limited():
    """AC-1756, case 5. Purchase only, not limited - no "limited" adjective."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "MPO2001",
                    requested_qty=40,
                    available=False,
                    verdict="not_available",
                    running_low=False,
                    disclaimer={
                        "sources": ["purchase"],
                        "limited": False,
                        "incoming_eta": None,
                        "purchase_eta_days": 90,
                    },
                )
            ]
        )
    )

    assert (
        "MPO2001 x 40: Not available, but there is purchase, ETA in 90 days."
        in _rendered_text(out)
    )


def test_item_line_incoming_null_eta_renders_to_be_confirmed():
    """AC-1756, case 6 (D10). No dated allocation counted - "ETA to be confirmed",
    never a blank or a raised exception."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "METANULL",
                    requested_qty=15,
                    available=False,
                    verdict="not_available",
                    running_low=False,
                    disclaimer={
                        "sources": ["incoming"],
                        "limited": True,
                        "incoming_eta": None,
                        "purchase_eta_days": 90,
                    },
                )
            ]
        )
    )

    rendered = _rendered_text(out)
    assert "ETA to be confirmed" in rendered
    assert (
        "METANULL x 15: Not available, but there is limited incoming, ETA to be confirmed."
        in rendered
    )


# ============================================================ Review round 2, SEC-N3


def test_item_line_falls_back_to_product_name_when_code_is_null():
    """Review round 2. A row the resolver only matched by name carries no
    `product_code` - the item line falls back to `product_name` rather than
    printing the Python `None`."""
    entry = _entry(
        None,
        requested_qty=5,
        available=True,
        verdict="available",
        running_low=False,
    )
    entry["product_name"] = "Basin Mixer"
    out = env(_availability_payload([entry]))

    rendered = _rendered_text(out)
    assert "Basin Mixer x 5: Yes, available." in rendered
    assert "None" not in rendered


def test_item_with_neither_code_nor_name_is_dropped_not_rendered_as_none():
    """Review round 2. A row with NEITHER `product_code` nor `product_name` cannot
    be named to a person at all - it is dropped from the reply entirely, never
    rendered as the string `None`. A second, nameable row still renders."""
    nameless = _entry(None, requested_qty=5, available=True, verdict="available", running_low=False)
    nameless["product_name"] = None
    named = _entry("MWT5727SS-CR", requested_qty=5, available=True, verdict="available", running_low=False)
    out = env(_availability_payload([nameless, named]))

    assert len(out["items"]) == 1
    rendered = _rendered_text(out)
    assert "None" not in rendered
    assert "MWT5727SS-CR x 5: Yes, available." in rendered


def test_noted_and_missing_question_falls_back_to_name_and_drops_nameless():
    """Review round 2, the AC-1757 question half. A `missing` row with no code
    falls back to its name; a row with neither is dropped from the "how many for
    ..." list and from the "Noted: ..." clause, never printed as `None`."""
    noted_nameless = _entry(None, requested_qty=5, needs_quantity=False, available=True, verdict="available")
    noted_nameless["product_name"] = None
    noted_named = _entry(None, requested_qty=60, needs_quantity=False, available=True, verdict="available")
    noted_named["product_name"] = "Shower Mixer"
    missing_named = _entry(None, needs_quantity=True)
    missing_named["product_name"] = "Basin Mixer"
    missing_nameless = _entry(None, needs_quantity=True)
    missing_nameless["product_name"] = None

    out = env(
        _availability_payload([noted_nameless, noted_named, missing_named, missing_nameless])
    )

    assert "None" not in out["intro"]
    assert "Noted: Shower Mixer x 60" in out["intro"]
    assert "How many units do you need for Basin Mixer?" in out["intro"]


# ============================================================ AC-1757


def test_intro_notes_answered_and_asks_for_missing_no_verdict_shown():
    """AC-1757 (D14). Two products already carry a quantity (A, B); two more (C, D)
    still need one. The WHOLE reply is a question: the intro notes A and B by their
    quantities, asks for C and D by code, and NO verdict phrasing appears anywhere
    in the envelope for ANY product - not even for A and B, which already have a
    verdict computed server-side."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "A",
                    requested_qty=5,
                    needs_quantity=False,
                    available=True,
                    verdict="available",
                    running_low=False,
                ),
                _entry(
                    "B",
                    requested_qty=60,
                    needs_quantity=False,
                    available=True,
                    verdict="available",
                    running_low=True,
                ),
                _entry("C", needs_quantity=True),
                _entry("D", needs_quantity=True),
            ]
        )
    )

    assert "Noted: A x 5, B x 60" in out["intro"]
    assert "How many units do you need for C and D?" in out["intro"]

    rendered = _rendered_text(out)
    assert "Yes, available" not in rendered
    assert "Not available" not in rendered
    assert "running low" not in rendered


# ============================================================ AC-1758


_ALLOWED_INTEGERS = {
    5, 60,  # the dealer's own asked quantities
    12, 10, 2026,  # the ETA date parts (12/10/2026)
    90,  # the lead-time days
}


def test_rendered_envelope_regex_sweep_no_stray_integers():
    """AC-1758. The rendered envelope (intro + item titles/fields) contains no
    integer other than the asked quantities, the ETA date parts and the
    lead-time days (D17) - not the on-hand figure, not a percentage, nothing of
    ours. Regex sweep over the customer-facing text only (envelope metadata like
    `last_updated_at` is excluded by `_rendered_text`, same as the old
    `test_render_availability_carries_no_quantity_anywhere` pattern). Product codes here
    are deliberately digit-free (`PRODALPHA`/`PRODBETA`) - a real code like
    "MWT5727SS-CR" legitimately carries digits of its own, and the sweep must isolate
    numbers the PRESENTER put there from numbers that were already part of the code."""
    out = env(
        _availability_payload(
            [
                _entry(
                    "PRODALPHA",
                    requested_qty=5,
                    available=True,
                    verdict="available",
                    running_low=False,
                ),
                _entry(
                    "PRODBETA",
                    requested_qty=110,
                    available=False,
                    verdict="not_available",
                    running_low=False,
                    disclaimer={
                        "sources": ["incoming", "purchase"],
                        "limited": True,
                        "incoming_eta": "2026-10-12",
                        "purchase_eta_days": 90,
                    },
                ),
            ]
        )
    )

    rendered = _rendered_text(out)
    found = {int(n) for n in re.findall(r"\d+", rendered)}
    # 110 is the dealer's own ask on the second product - allow it explicitly
    # here rather than folding it into the module-level set, which is shared
    # with the other (5/60-only) tests above.
    allowed = _ALLOWED_INTEGERS | {110}
    assert found <= allowed, f"unexpected integers leaked into the reply: {found - allowed}"
