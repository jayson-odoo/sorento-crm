"""Stock render envelopes under the visibility policy (UAC section D).

PLAN `documentation/plans/inventory/PLAN-stock-visibility-policy.md`, UAC
`documentation/plans/inventory/stock-visibility-policy-acceptance-criteria.md`.

The backend decides WHAT a contact may be told (`stock_visibility.mode`); this
layer decides only how that answer is shaped for the consumer. Three modes, and
the split matters:

* `detailed` - the envelope every contact gets today. It must stay byte-identical
  (AC-D2 / AC-F5): a deploy that changes one field label changes the outbound
  WhatsApp text for everyone.
* `compact` - one item per product, `Total` first, then the allowed locations.
* `availability` - the dealer answer. `fields` is EMPTY on purpose: a dealer may
  be told yes or no and nothing else, so there is no field for a number to hide
  in, and the whole reply lives in `intro` + `flags`.

The sanitizer tests are here rather than with the other stock-sanitizer coverage
because they are about THIS feature's blocks: `_STOCK_HIDDEN_FIELDS` contains
`available`, which is the entire availability answer, so a sanitizer that walks
the policy blocks deletes the reply it was meant to protect.
"""
import json

import pytest

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import present_response
from sorento_crm_mcp.server import _compile_tool, _is_uuid_param, _sanitize_tool_response

TOOL = "crm_inventory_stock_balance_list"


def env(data):
    return json.loads(present_response(TOOL, json.dumps(data)))


def sanitized(data):
    """What the presenter actually receives: the response AFTER server sanitize."""
    return json.loads(_sanitize_tool_response(TOOL, json.dumps(data)))


def spec():
    return next(s for s in CATALOG if s.name == TOOL)


def _visibility(mode, codes=None, source="contact"):
    return {"mode": mode, "warehouse_codes": codes, "source": source}


# ------------------------------------------------------------------ D1 catalog


class _FakeSettings:
    crm_base_url = "http://crm.local"
    external_api_key = "test-key"


class _FakeClient:
    def __init__(self):
        self.query = None

    async def request(
        self, method, path, path_params=None, query=None, body=None, tool_name=None
    ):
        self.query = dict(query or {})
        return json.dumps({"data": [], "pagination": {"total": 0, "page": 1, "limit": 50}})

    async def get(self, path, path_params=None, query=None, tool_name=None):
        return await self.request("GET", path, path_params, query, None, tool_name)

    async def post(self, path, path_params=None, query=None, body=None, tool_name=None):
        return await self.request("POST", path, path_params, query, body, tool_name)


class _FakeCtx:
    def __init__(self, client):
        self.request_context = type(
            "_RC", (), {"lifespan_context": {"client": client, "settings": _FakeSettings()}}
        )()


def test_catalog_requested_qty():
    """D1. The param exists AND the docstring tells the planner to fill it -
    without the instruction the model has the slot and never uses it, and every
    dealer answer stalls on "how many units do you need?" forever."""
    assert "requested_qty" in spec().query_params
    assert "requested_qty" in spec().description
    assert "how many" in spec().description.lower()


def test_catalog_pairs_the_contact_with_its_space():
    """The backend fails closed on `contact_id` alone - company scope needs both
    params, so one without the other would answer a contact with every company's
    stock. The planner has to be told, or it sends the id it has and reads the
    empty result as "there is none"."""
    assert "Pass BOTH or NEITHER" in spec().description


@pytest.mark.asyncio
async def test_catalog_requested_qty_reaches_the_backend():
    """D1. A number, not a UUID: the compiler validates any `*_id` / `*_ids`
    param as canonical UUIDs, so a numeric param sharing that suffix would be
    rejected before the call. `requested_qty` must pass straight through."""
    assert _is_uuid_param("requested_qty") is False

    client = _FakeClient()
    fn = _compile_tool(spec())
    await fn(_FakeCtx(client), requested_qty=50)

    assert client.query["requested_qty"] == "50"


# ------------------------------------------------------------- D2 detailed


#: The envelope this tool produced BEFORE the visibility policy existed, captured
#: verbatim. n8n prints it field by field into a WhatsApp message, so any drift
#: here is drift in what a live contact reads (AC-F5).
_DETAILED_GOLDEN = {
    "result_type": "stock",
    "intro": "Stock details found for the requested products.",
    "items": [
        {
            "title": "SRTBF11201-NEW",
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": "SRTBF11201-NEW"},
                {"key": "warehouse", "label": "Warehouse", "value": "BUKIT RAJA"},
                {"key": "system_location", "label": "System Location", "value": "BRW"},
                {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": 500},
            ],
            "flags": {
                "discontinued": False,
                "expired": False,
                "expiring_soon": False,
                "unallocated": False,
                "partially_allocated": False,
            },
        }
    ],
    "attachments": [],
    "action_links": [],
    "last_updated_at": "2026-08-24T18:00:00",
    "has_result": True,
}


def _detailed_row():
    return {
        "product": {"product_code": "SRTBF11201-NEW", "product_name": "SRTBF11201-NEW"},
        "system_location": {"system_location": "BRW", "warehouse": "BUKIT RAJA"},
        "quantity_on_hand": 500,
        "updated_at": "2026-08-24T18:00:00",
    }


def test_render_detailed_unchanged():
    """D2. No policy block at all (the legacy caller) - byte-identical."""
    out = env({"data": [_detailed_row()], "pagination": {"total": 1, "page": 1, "limit": 50}})

    assert out == _DETAILED_GOLDEN


def test_render_detailed_with_policy_block_unchanged():
    """D2. A `detailed` policy answers the same envelope plus the passthrough -
    a contact explicitly set to Detailed reads exactly what they read before."""
    out = env(
        {
            "data": [_detailed_row()],
            "pagination": {"total": 1, "page": 1, "limit": 50},
            "stock_visibility": _visibility("detailed", ["BRW", "BRW-BB"]),
        }
    )

    assert {k: v for k, v in out.items() if k != "stock_visibility"} == _DETAILED_GOLDEN
    assert out["stock_visibility"] == _visibility("detailed", ["BRW", "BRW-BB"])


# ------------------------------------------------------------- D3 compact


def _compact_payload():
    return {
        "data": [],
        # `total` counts the PRODUCTS answered for and `empty` is False: the
        # summary modes clear `data` while still carrying an answer (B15 / the
        # escalation-hint fix).
        "pagination": {"total": 2, "page": 1, "limit": 50},
        "empty": False,
        "stock_visibility": _visibility("compact", ["BRW", "BRW-BB"]),
        "stock_summary": [
            {
                "product_id": "11111111-1111-4111-8111-111111111111",
                "product_code": "SRTBF11201-NEW",
                "product_name": "SRTBF11201-NEW",
                "total_on_hand": 700,
                "locations": [
                    {"warehouse_code": "BRW", "quantity_on_hand": 500},
                    {"warehouse_code": "BRW-BB", "quantity_on_hand": 200},
                ],
                "flags": {"discontinued": False},
            },
            {
                "product_id": "22222222-2222-4222-8222-222222222222",
                "product_code": "SRTWB7109",
                "product_name": "SRTWB7109",
                "total_on_hand": 0,
                "locations": [],
                "flags": {"discontinued": True},
            },
        ],
        "last_updated_at": "2026-08-24T18:00:00",
    }


def test_render_compact():
    """D3. One item per product, `Total` first, then the locations in the order
    the backend put them (it already sorted by code, and re-sorting here would
    make the two answers disagree). No product id anywhere - it is a UUID."""
    out = env(_compact_payload())

    assert out["result_type"] == "stock_compact"
    assert out["intro"] == "Stock summary for the requested products."
    assert [i["title"] for i in out["items"]] == ["SRTBF11201-NEW", "SRTWB7109"]
    assert out["items"][0]["fields"] == [
        {"label": "Total", "value": 700},
        {"label": "BRW", "value": 500},
        {"label": "BRW-BB", "value": 200},
    ]
    assert out["has_result"] is True
    assert "11111111-1111-4111-8111-111111111111" not in json.dumps(out["items"])


def test_render_compact_values_are_plain_integers():
    """D3. n8n prints `Total: ${value}`. A Decimal-shaped string ("500.0000")
    would render as-is in the WhatsApp message."""
    payload = _compact_payload()
    payload["stock_summary"][0]["total_on_hand"] = "700.0000"
    payload["stock_summary"][0]["locations"][0]["quantity_on_hand"] = "500.0000"

    fields = env(payload)["items"][0]["fields"]

    assert fields[0]["value"] == 700
    assert fields[1]["value"] == 500


def test_render_compact_zero_stock_still_an_item():
    """D3 + B13. A product with nothing left still renders, as `Total: 0`.
    Dropping it answers an out-of-stock question with silence."""
    out = env(_compact_payload())

    assert out["items"][1]["fields"] == [{"label": "Total", "value": 0}]


def test_render_compact_reads_a_relabelled_location_key():
    """The exemption that keeps `warehouse_code` intact lives in server.py, one
    file away. If it is ever dropped, the label must still be the location code
    and not disappear, leaving a bare `Total` line."""
    payload = _compact_payload()
    payload["stock_summary"][0]["locations"] = [
        {"system_location": "BRW", "quantity_on_hand": 500}
    ]

    fields = env(payload)["items"][0]["fields"]

    assert fields[1] == {"label": "BRW", "value": 500}


def test_render_compact_passes_the_backend_flags_through():
    """D3. `discontinued` is decided by the backend from the product row; the
    presenter re-states it rather than inventing the standard five-flag block."""
    out = env(_compact_payload())

    assert out["items"][0]["flags"] == {"discontinued": False}
    assert out["items"][1]["flags"] == {"discontinued": True}


# ---------------------------------------------------------- D4/D5 availability


def _availability_payload(entries):
    return {
        "data": [],
        "pagination": {"total": 0, "page": 1, "limit": 50},
        "empty": True,
        "stock_visibility": _visibility("availability", ["BRW", "MWH", "DC1"], "access_type"),
        "stock_availability": entries,
        "last_updated_at": "2026-08-24T18:00:00",
    }


def _entry(code, *, needs_quantity=False, requested_qty=50, available=True):
    return {
        "product_id": "33333333-3333-4333-8333-333333333333",
        "product_code": code,
        "product_name": code,
        "needs_quantity": needs_quantity,
        "requested_qty": requested_qty,
        "available": available,
    }


def test_render_availability_ask():
    """D4. No number yet: the whole reply is the question. `fields` is empty and
    stays empty - a dealer is told yes or no, never a quantity, so there is no
    field for one to leak through."""
    out = env(
        _availability_payload(
            [_entry("SRTBF11201-NEW", needs_quantity=True, requested_qty=None, available=None)]
        )
    )

    assert out["result_type"] == "stock_availability"
    assert out["intro"] == "How many units do you need?"
    assert out["items"] == [
        {
            "title": "SRTBF11201-NEW",
            "fields": [],
            "flags": {"needs_quantity": True, "available": None},
        }
    ]
    assert out["has_result"] is True


def test_render_availability_answer():
    """D5. The two answers, in the exact words the dealer reads."""
    yes = env(_availability_payload([_entry("SRTBF11201-NEW", available=True)]))
    no = env(_availability_payload([_entry("SRTBF11201-NEW", available=False)]))

    assert yes["intro"] == "Yes, we have stock."
    assert yes["items"][0]["flags"] == {"needs_quantity": False, "available": True}
    assert no["intro"] == "Sorry, we do not have enough stock for that quantity."
    assert no["items"][0]["flags"] == {"needs_quantity": False, "available": False}


def test_render_availability_several_products_that_disagree():
    """D5. Two products, one in stock and one not: a single yes or no would be a
    lie about one of them, so the intro stops answering and the items carry
    their own flags."""
    out = env(
        _availability_payload(
            [_entry("SRTBF11201-NEW", available=True), _entry("SRTWB7109", available=False)]
        )
    )

    assert out["intro"] == "Here is the stock availability for the requested products."
    assert [i["flags"]["available"] for i in out["items"]] == [True, False]


def test_render_availability_ask_wins_over_a_mixed_answer():
    """D5. One product still missing its quantity means the turn is not an
    answer yet - ask, and say nothing about the other product."""
    out = env(
        _availability_payload(
            [
                _entry("SRTBF11201-NEW", available=True),
                _entry("SRTWB7109", needs_quantity=True, requested_qty=None, available=None),
            ]
        )
    )

    assert out["intro"] == "How many units do you need?"


def test_render_availability_carries_no_quantity_anywhere():
    """D4. The point of the mode: walk the whole envelope and prove no number
    from the stock table can be read out of it."""
    out = env(_availability_payload([_entry("SRTBF11201-NEW", available=True)]))

    dumped = json.dumps(out)
    for item in out["items"]:
        assert item["fields"] == []
    # `needs_quantity` is a boolean and stays; nothing counted in units does.
    assert "on_hand" not in dumped
    assert "requested_qty" not in dumped
    assert "50" not in dumped


def test_render_availability_no_products_says_nothing_found():
    """An availability policy with no resolved product falls back to the shared
    empty answer rather than asking "how many" about nothing."""
    out = env(_availability_payload([]))

    assert out["items"] == []
    assert out["has_result"] is False
    assert out["intro"] == "No matching results found."


# ------------------------------------------------------------ D6 passthrough


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [_detailed_row()], "stock_visibility": _visibility("detailed")},
        _compact_payload(),
        _availability_payload([_entry("SRTBF11201-NEW")]),
    ],
    ids=["detailed", "compact", "availability"],
)
def test_envelope_passthrough(payload):
    """D6. n8n branches on the mode (which format to print, whether to write the
    pending-quantity turn). Re-deriving it from the block that happens to be
    present would break the moment a mode carries no block."""
    out = env(payload)

    assert out["stock_visibility"]["mode"] == payload["stock_visibility"]["mode"]
    assert "source" in out["stock_visibility"]


def test_last_updated_at_survives_the_summary_modes():
    """n8n's `_Data last updated_` footer reads the envelope. The summary modes
    have no rows to walk it out of, so it comes off the payload itself."""
    assert env(_compact_payload())["last_updated_at"] == "2026-08-24T18:00:00"
    assert (
        env(_availability_payload([_entry("SRTBF11201-NEW")]))["last_updated_at"]
        == "2026-08-24T18:00:00"
    )


# --------------------------------------------------- sanitizer, before render


def test_sanitizer_keeps_the_availability_answer():
    """`available` is in `_STOCK_HIDDEN_FIELDS` - it is a quantity-shaped word on
    a stock ROW, where it means quantity_available and must never be shown. On
    the availability block it is the entire answer, so the recursive strip would
    delete the reply and every dealer would be told "no matching results"."""
    out = sanitized(_availability_payload([_entry("SRTBF11201-NEW", available=True)]))

    assert out["stock_availability"][0]["available"] is True
    assert out["stock_availability"][0]["needs_quantity"] is False


def test_sanitizer_keeps_the_compact_location_codes():
    """The Sage vocabulary relabel renames `warehouse_code` to `system_location`
    everywhere it walks. Inside a summary location that key IS the label the
    presenter prints, so the block is held out of the rewrite and reaches the
    presenter as the backend declared it."""
    out = sanitized(_compact_payload())

    assert out["stock_summary"][0]["locations"][0] == {
        "warehouse_code": "BRW",
        "quantity_on_hand": 500,
    }
    assert out["stock_visibility"]["warehouse_codes"] == ["BRW", "BRW-BB"]


def test_sanitizer_still_relabels_the_detailed_rows():
    """The exemption is the three policy blocks and nothing else: a stock ROW
    keeps every sanitizer it has today."""
    out = sanitized(
        {
            "data": [
                {
                    "warehouse_code": "BRW",
                    "quantity_on_hand": 12,
                    "quantity_available": 10,
                    "status": "normal",
                }
            ],
            "stock_visibility": _visibility("detailed"),
        }
    )

    row = out["data"][0]
    assert row["system_location"] == "BRW"
    assert "warehouse_code" not in row
    assert "quantity_available" not in row
    assert "status" not in row


def test_sanitizer_puts_last_updated_at_in_malaysia_time():
    """Rows get their `updated_at` moved to Malaysia time, and the footer reads
    whichever is latest. The summary modes have no rows, so the payload's own
    `last_updated_at` is the footer - untouched, it would read 8 hours early."""
    out = sanitized(_compact_payload())

    assert out["last_updated_at"] == "2026-08-25T02:00:00"


def test_sanitized_compact_renders_end_to_end():
    """Sanitize then present, in the order the server runs them."""
    out = json.loads(
        present_response(TOOL, json.dumps(sanitized(_compact_payload())))
    )

    assert out["result_type"] == "stock_compact"
    assert out["items"][0]["fields"] == [
        {"label": "Total", "value": 700},
        {"label": "BRW", "value": 500},
        {"label": "BRW-BB", "value": 200},
    ]
    assert out["last_updated_at"] == "2026-08-25T02:00:00"


def test_sanitized_availability_renders_end_to_end():
    out = json.loads(
        present_response(
            TOOL,
            json.dumps(sanitized(_availability_payload([_entry("SRTBF11201-NEW", available=False)]))),
        )
    )

    assert out["intro"] == "Sorry, we do not have enough stock for that quantity."
    assert out["items"][0]["flags"] == {"needs_quantity": False, "available": False}


# ------------------------------------- the escalation hint, before the render


_ROUTING_HINT = {
    "team": "warehouse",
    "team_name": "warehouse",
    "message": (
        "We don't have that information available. Would you like me to route "
        "you to our warehouse team?"
    ),
    "alternatives": [],
}


async def _attach(payload, monkeypatch):
    from sorento_crm_mcp import escalation_hint

    async def _routing(tool_name, *, api_url, api_key, timeout=5.0):
        return dict(_ROUTING_HINT)

    monkeypatch.setattr(escalation_hint, "_fetch_routing", _routing)
    return json.loads(
        await escalation_hint.attach_suggested_escalation(
            TOOL, json.dumps(payload), api_url="http://crm.local", api_key="k"
        )
    )


@pytest.mark.asyncio
async def test_a_summary_answer_is_not_treated_as_nothing_found(monkeypatch):
    """The hint runs on the raw response, BEFORE the render, and reads `data`.

    `compact` and `availability` clear `data` by design, so a reply carrying 700
    units in BRW - or a plain "yes, we have stock" - came back with "We don't
    have that information available. Would you like me to route you to our
    warehouse team?" stapled to it. The two summary blocks ARE the answer, so a
    payload holding one is not empty.
    """
    compact = await _attach(_compact_payload(), monkeypatch)
    availability = await _attach(
        _availability_payload([_entry("SRTBF11201-NEW", available=True)]), monkeypatch
    )

    assert "suggested_escalation" not in compact
    assert "suggested_escalation" not in availability


@pytest.mark.asyncio
async def test_a_summary_with_no_entries_still_escalates(monkeypatch):
    """The other side: nothing was found, and the routing offer is the useful
    reply. Suppressing it there would make the dealer modes unescalatable."""
    payload = _compact_payload()
    payload["stock_summary"] = []
    payload["empty"] = True

    out = await _attach(payload, monkeypatch)

    assert out["suggested_escalation"]["team"] == "warehouse"


@pytest.mark.asyncio
async def test_a_detailed_miss_still_escalates(monkeypatch):
    """And the mode every contact is on today is untouched."""
    out = await _attach(
        {"data": [], "stock_visibility": _visibility("detailed")}, monkeypatch
    )

    assert out["suggested_escalation"]["team"] == "warehouse"
