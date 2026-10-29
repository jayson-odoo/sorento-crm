"""AGENTIC-P1 card sections 2 and 3: the tool registry and its dispatch permission layer.

No database and no MCP: `dispatch` is handed a fake `call`, and the linked user's
permission check is monkeypatched at `UserPermissionService.check_user_has_permission`
(the same check `require_permission` uses). The check must run at DISPATCH time, so a
test revokes the slug between exposure and dispatch.
"""
from __future__ import annotations

import json

import pytest

from app.services.chatbot.lanes.business import fetch
from app.services.chatbot.lanes.business.fetch import ToolNotAllowed
from app.services.user_service import UserPermissionService

EXPECTED = {
    "crm_report_ask": "order_management.orders.view",
    "crm_inventory_stock_balance_list": "inventory.stock.view",
    "crm_incoming_stock_by_product": "procurement.packing_lists.view",
    "crm_incoming_stock_shipments": "procurement.packing_lists.view",
    "crm_procurement_grn_summary": "procurement.grn.view",
    "crm_procurement_po_last_cost_list": "scm.purchase_orders.view",
    "crm_procurement_po_placed_list": "scm.purchase_orders.view",
    "crm_procurement_spo_allocations_last_receipt_list": "procurement.spo_allocations.view",
    "crm_order_management_orders_by_product_list": "order_management.orders.view",
    # Round 5: the local resolver; each kind it searches has its own slug (tools.KIND_SLUGS).
    "crm_resolve": "",
}

STOCK = "crm_inventory_stock_balance_list"
SUPPLIER_GRANT = "purchase_orders.supplier"
# Round 3: the PO tools are behind the contact's placed reveal, as in today's bot.
PLACED_GRANT = "purchase_orders.placed"

CATALOG = {
    name: {
        "description": f"{name} description",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "space_id": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["contact_id", "space_id", "query"],
        },
    }
    for name in EXPECTED
}

_HELD: set[str] = set()


@pytest.fixture(autouse=True)
def _user_holds(monkeypatch):
    _HELD.clear()
    _HELD.update(EXPECTED.values())
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in _HELD
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _HELD.clear()


def _ctx(grants=frozenset()):
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(
        contact_pk="pk-1",
        contact_respond_id="ZZT-RESPOND-1",
        space_id="364817",
        user_id="user-1",
        user_name="ZZT User",
        grants=frozenset(grants),
    )


class Recorder:
    """A fake `call(name, args)` that records every invocation."""

    def __init__(self, result=None, exc=None):
        # Round 5: an envelope with no rows is the typed `empty`, so the default carries a row.
        self.result = {"items": [{"qty": 1}]} if result is None else result
        self.exc = exc
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        if self.exc is not None:
            raise self.exc
        return self.result


def _dispatch(name, args, rec, ctx=None):
    from app.services.chatbot.agent import tools

    return tools.dispatch(None, ctx or _ctx(), name, args, call=rec, catalog=CATALOG, timeout=5.0)


# ------------------------------------------------------------------ registry


def test_registry_holds_exactly_the_ten_tools_with_their_slugs():
    from app.services.chatbot.agent.tools import REGISTRY

    assert {name: d.user_permission for name, d in REGISTRY.items()} == EXPECTED
    assert all(d.name == name for name, d in REGISTRY.items())


def test_tool_schemas_strip_contact_and_space_from_properties_and_required():
    from app.services.chatbot.agent.tools import REGISTRY, tool_schemas

    schemas = tool_schemas([REGISTRY[STOCK]], CATALOG)

    assert len(schemas) == 1
    fn = schemas[0]["function"]
    assert schemas[0]["type"] == "function"
    assert fn["name"] == STOCK
    params = fn["parameters"]
    assert "contact_id" not in params["properties"]
    assert "space_id" not in params["properties"]
    assert params["properties"]["query"] == {"type": "string"}
    assert params["required"] == ["query"]


# ------------------------------------------------------------------ dispatch rules


def test_unknown_name_is_denied_and_the_call_never_happens():
    rec = Recorder()
    out = _dispatch("crm_delete_everything", {}, rec)
    assert out.status == "denied"
    assert rec.calls == []


def test_a_name_outside_the_registry_but_in_the_catalogue_is_denied():
    rec = Recorder()
    catalog = dict(CATALOG, crm_other_tool=CATALOG[STOCK])
    from app.services.chatbot.agent import tools

    out = tools.dispatch(None, _ctx(), "crm_other_tool", {}, call=rec, catalog=catalog, timeout=5.0)
    assert out.status == "denied"
    assert rec.calls == []


def test_a_slug_lost_between_exposure_and_dispatch_is_denied():
    from app.services.chatbot.agent.tools import REGISTRY

    rec = Recorder()
    exposed = [REGISTRY[STOCK]]  # the model was shown the tool while the user held the slug
    assert exposed
    _HELD.discard("inventory.stock.view")  # revoked before the call comes back

    out = _dispatch(STOCK, {"query": "x"}, rec)

    assert out.status == "denied"
    assert rec.calls == []


@pytest.mark.parametrize("bad", [None, "query=x", ["query"], 7])
def test_args_that_are_not_a_dict_are_invalid(bad):
    rec = Recorder()
    out = _dispatch(STOCK, bad, rec)
    assert out.status == "invalid"
    assert rec.calls == []


def test_an_unknown_argument_key_is_invalid():
    rec = Recorder()
    out = _dispatch(STOCK, {"query": "x", "drop_table": "y"}, rec)
    assert out.status == "invalid"
    assert rec.calls == []


def test_model_supplied_contact_and_space_are_replaced_by_the_contexts():
    rec = Recorder()
    out = _dispatch(STOCK, {"query": "x", "contact_id": "EVIL", "space_id": "EVIL-SPACE"}, rec)

    assert out.status == "ok"
    assert rec.calls == [
        (STOCK, {"query": "x", "contact_id": "ZZT-RESPOND-1", "space_id": "364817", "view": "render"})
    ]


def test_contact_and_space_are_injected_when_the_model_sent_none():
    rec = Recorder()
    _dispatch(STOCK, {"query": "x"}, rec)
    assert rec.calls[0][1]["contact_id"] == "ZZT-RESPOND-1"
    assert rec.calls[0][1]["space_id"] == "364817"


def test_tool_not_allowed_is_denied():
    rec = Recorder(exc=ToolNotAllowed("not allowed for a brand-scoped contact"))
    out = _dispatch(STOCK, {"query": "x"}, rec)
    assert out.status == "denied"
    assert out.message


def test_a_timeout_is_a_timeout_result():
    rec = Recorder(exc=TimeoutError("slow"))
    out = _dispatch(STOCK, {"query": "x"}, rec)
    assert out.status == "timeout"


def test_any_other_exception_is_an_error_result_and_never_raises():
    rec = Recorder(exc=RuntimeError("mcp exploded"))
    out = _dispatch(STOCK, {"query": "x"}, rec)
    assert out.status == "error"
    assert out.message


# ------------------------------------------------------------------ field scope


def _po_envelope():
    return {
        "items": [
            {
                "fields": [
                    {"key": "product_code", "label": "Code", "value": "SRTWT7445"},
                    {"key": "supplier", "label": "Supplier", "value": "ZZT SUPPLIER SECRET"},
                ]
            }
        ],
        "restricted_fields": {"supplier": SUPPLIER_GRANT},
        "has_result": True,
    }


def _keys(out):
    return [f["key"] for f in out.data["items"][0]["fields"]]


def test_a_restricted_field_is_dropped_when_the_contact_lacks_the_grant():
    rec = Recorder(result=_po_envelope())
    out = _dispatch("crm_procurement_po_placed_list", {"query": "x"}, rec, ctx=_ctx(grants={PLACED_GRANT}))
    assert out.status == "ok"
    assert _keys(out) == ["product_code"]
    assert "ZZT SUPPLIER SECRET" not in json.dumps(out.data)


def test_a_restricted_field_is_kept_when_the_contact_holds_the_grant():
    rec = Recorder(result=_po_envelope())
    out = _dispatch(
        "crm_procurement_po_placed_list", {"query": "x"}, rec, ctx=_ctx(grants={SUPPLIER_GRANT, PLACED_GRANT})
    )
    assert out.status == "ok"
    assert _keys(out) == ["product_code", "supplier"]


# ------------------------------------------------------------------ size cap


def test_the_twelve_thousand_char_cap_cuts_list_items_whole_and_counts_more():
    items = [{"row": i, "text": "x" * 500} for i in range(100)]
    rec = Recorder(result={"items": items, "has_result": True})
    out = _dispatch(STOCK, {"query": "x"}, rec)

    assert out.status == "ok"
    shown = out.data["items"]
    assert 0 < len(shown) < 100
    assert out.more == 100 - len(shown)
    assert len(json.dumps(out.data)) <= 12_000
    # whole items only, from the front, never a row cut mid-way
    assert shown == items[: len(shown)]


def test_a_small_result_is_returned_whole_with_no_more():
    rec = Recorder(result={"items": [{"a": 1}, {"a": 2}], "has_result": True})
    out = _dispatch(STOCK, {"query": "x"}, rec)
    assert out.data["items"] == [{"a": 1}, {"a": 2}]
    assert out.more == 0


# ------------------------------------------------------------------ fetch extraction


def test_fetch_exposes_drop_restricted_fields_and_drops_in_place():
    assert callable(fetch.drop_restricted_fields)
    env = _po_envelope()
    fetch.drop_restricted_fields(env, set())
    assert [f["key"] for f in env["items"][0]["fields"]] == ["product_code"]

    env = _po_envelope()
    fetch.drop_restricted_fields(env, {SUPPLIER_GRANT})
    assert [f["key"] for f in env["items"][0]["fields"]] == ["product_code", "supplier"]


def test_output_structurer_still_drops_the_same_field():
    out = fetch.output_structurer(
        _po_envelope(),
        {"tool": "crm_procurement_po_placed_list", "access": {"attributes": []}},
    )
    assert "ZZT SUPPLIER SECRET" not in json.dumps(out, default=str)

    kept = fetch.output_structurer(
        _po_envelope(),
        {"tool": "crm_procurement_po_placed_list", "access": {"attributes": [SUPPLIER_GRANT]}},
    )
    assert "ZZT SUPPLIER SECRET" in json.dumps(kept, default=str)
