"""CHAT-GROUPED-ORDER-STATUS: a grouped delivery order list crashed the chat turn.

Prod turn 9465ad23 (26 Oct 2026): a delivery order check grouped by customer failed at the
"Looked up" step with `TypeError: unhashable type: 'dict'` and the contact read the generic
"Sorry, I ran into a problem". The orders route buckets its RAW rows into `groups[i].rows`
(`app/api/v1/order_management/orders.py`), the MCP sanitizer slimmed only the flat `data`
rows (`sorento_crm_mcp/server.py::_slim_orders_list_response`), so each group row kept the
`order_status` object `{id, status_code, status_name}`; the presenter printed it as the Status
value and `turn/compose.py` deduped the answer rows in a set keyed by `_row_key`, a tuple that
held the dict.

`documentation/plans/chatbot/PLAN-chat-grouped-order-status-26oct.md`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
from app.services.chatbot.turn import compose
from tests.chatbot._turn_helpers import do_window
from tests.chatbot.conftest import validating_resolve_entity
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_samantha_26sep_r3_brand_carry import _Chat

ORDERS_LIST = "crm_order_management_orders_list"
CUSTOMER = "ZZT Customer A"
CUSTOMER_UUID = "66666666-6666-6666-6666-666666666666"
GROUP_LABEL = "ZZT CUSTOMER A SDN BHD"
SORRY = "ran into a problem"

#: Every DO field is a per-contact reveal (DO-ASK-SIMPLIFY rule 2); Status is the one this is about.
_DO_REVEALS = [
    "delivery_orders.status",
    "delivery_orders.order_number",
    "delivery_orders.customer",
    "delivery_orders.order_date",
    "delivery_orders.delivery_date",
    "delivery_orders.warehouse",
    "delivery_orders.products",
]


def _route_row(order_number: str, status_code: str, status_name: str) -> dict[str, Any]:
    """One DO row the way the orders route's `jsonable_encoder` emits it: `order_status`
    is the status object, ids included."""
    return {
        "id": f"77777777-7777-7777-7777-77777777777{order_number[-1]}",
        "order_number": order_number,
        "debtor_name": GROUP_LABEL,
        "order_date": "2026-09-20",
        "actual_delivery_date": "2026-09-21",
        "company_id": "88888888-8888-8888-8888-888888888888",
        "order_status": {
            "id": "99999999-9999-9999-9999-999999999999",
            "status_code": status_code,
            "status_name": status_name,
        },
        "lines": [{"product_code": "ZZT5733", "quantity": 4, "warehouse": {"warehouse_code": "ZZW"}}],
    }


def _grouped_route_body() -> dict[str, Any]:
    """`GET /order-management/orders?group_by=customer`: the flat rows plus the same raw
    rows bucketed by `debtor_name` (`orders.py`, `order_service.group_rows`)."""
    rows = [_route_row("DO-ZZT-1", "delivered", "Delivered"), _route_row("DO-ZZT-2", "in_transit", "In Transit")]
    return {
        "data": rows,
        "groups": [{"key": GROUP_LABEL, "label": GROUP_LABEL, "rows": rows}],
        "pagination": {"total": len(rows), "page": 1, "limit": 20},
    }


def _mcp_root() -> None:
    """THIS checkout's `sorento_crm_mcp` first on `sys.path`, an already-imported copy from
    elsewhere dropped: the backend venv's editable install points at the primary checkout."""
    root = Path(__file__).resolve().parents[3] / "sorento_crm_mcp"
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
    loaded = sys.modules.get("sorento_crm_mcp")
    if loaded is not None and not str(getattr(loaded, "__file__", "")).startswith(str(root)):
        for name in [n for n in sys.modules if n == "sorento_crm_mcp" or n.startswith("sorento_crm_mcp.")]:
            del sys.modules[name]


def _presenter_only():
    """The presenter alone: the payload the chat received before this fix, a group row that
    still carries the raw status object."""
    _mcp_root()
    try:
        from sorento_crm_mcp.presenters import present_response
    except ImportError:  # pragma: no cover - the backend container carries no MCP package
        pytest.skip("sorento_crm_mcp is not importable in this environment")
    return present_response


def _sanitize_then_present():
    """The production chain (`server.py`): sanitize the route body, then present it. Needs
    the `mcp` SDK `server.py` imports, absent from the backend CI job (the MCP job runs the
    sanitizer's own test)."""
    _mcp_root()
    pytest.importorskip("mcp")
    from sorento_crm_mcp.presenters import present_response
    from sorento_crm_mcp.server import _sanitize_tool_response

    return lambda name, raw: present_response(name, _sanitize_tool_response(name, raw))


class _GroupedChat(_Chat):
    """`_Chat` (real `engine.run_turn`, parser, access and resolver faked) whose orders list
    answers with the grouped route body through `render`."""

    def __init__(self, session_factory, monkeypatch, render) -> None:
        super().__init__(session_factory, monkeypatch, attributes=list(_DO_REVEALS), tool_body={})
        from app.services.chatbot import engine as engine_mod

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            tokens = list(body.get("tokens") or [])
            return {
                "tokens": tokens,
                "resolutions": [
                    {
                        "token": t,
                        "resolved": True,
                        "matches": [
                            {"uuid": CUSTOMER_UUID, "entity_type": "customer", "canonical_code": t, "match_tier": "exact"}
                        ],
                    }
                    for t in tokens
                    if t == CUSTOMER
                ],
                "unresolved_tokens": [t for t in tokens if t != CUSTOMER],
            }

        services = ResolveGateServices(
            access_types=lambda **_: [{"name": "Sorento Dealer"}],
            resolve_entity=validating_resolve_entity(resolve_entity),
            probe=lambda **_: None,
        )

        def mcp_call(name: str, args: dict) -> str:
            self.captured.append((name, dict(args)))
            if name == ORDERS_LIST:
                return render(name, json.dumps(_grouped_route_body()))
            return json.dumps({"has_result": False, "items": []})

        monkeypatch.setattr(
            engine_mod.business_services, "production_services", lambda db, *, space_id=None: services
        )
        monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=mcp_call))


def _grouped_do_check() -> dict[str, Any]:
    """The parser's reading of a delivery order check for one customer, grouped by customer."""
    return _parser_output(
        domain_hint="order",
        intent_hint="check_order",
        domain_in_message=True,
        entities=[{"raw": CUSTOMER, "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
        document=["DO"],
        group_by="customer",
        **do_window(),
    )


def _ask(chat: _GroupedChat) -> str:
    reply = chat.say(f"DO for {CUSTOMER} by customer", _grouped_do_check())
    calls = [args for name, args in chat.captured if name == ORDERS_LIST]
    assert calls and calls[-1].get("group_by") == "customer", (chat.captured, reply)
    return reply


def test_a_grouped_do_list_whose_rows_carry_the_status_object_still_answers(session_factory, monkeypatch) -> None:
    """Whatever shape an answer row arrives in, the turn answers: the composer's dedupe key
    must not need every field value to be hashable."""
    reply = _ask(_GroupedChat(session_factory, monkeypatch, _presenter_only()))
    assert SORRY not in reply, reply
    assert GROUP_LABEL in reply, reply
    assert "DO-ZZT-1" in reply and "DO-ZZT-2" in reply, reply


def test_the_grouped_do_list_prints_status_as_text_like_the_flat_list(session_factory, monkeypatch) -> None:
    """Through the production chain (sanitizer, then presenter) a grouped row reads the same
    as a flat one: Status is the status name, never the object or its id."""
    reply = _ask(_GroupedChat(session_factory, monkeypatch, _sanitize_then_present()))
    assert SORRY not in reply, reply
    assert GROUP_LABEL in reply, reply
    assert "*Status:* Delivered" in reply and "*Status:* In Transit" in reply, reply
    assert "status_code" not in reply and "9999" not in reply, reply


def _fig(*fields: tuple[str, Any]) -> dict[str, Any]:
    return {"fields": [{"label": label, "value": value} for label, value in fields]}


def test_row_key_hashes_object_and_list_values_and_keeps_the_dedupe() -> None:
    status = {"status_name": "Delivered", "id": "x"}
    a = _fig(("Order Number", "DO-1"), ("Status", status), ("Lines", ["ZZT5733"]))
    same = _fig(("Order Number", "DO-1"), ("Status", {"id": "x", "status_name": "Delivered"}), ("Lines", ["ZZT5733"]))
    other = _fig(("Order Number", "DO-1"), ("Status", {"status_name": "In Transit", "id": "x"}), ("Lines", ["ZZT5733"]))
    keys = {compose._row_key(a), compose._row_key(same), compose._row_key(other)}
    assert len(keys) == 2, keys
    flat = _fig(("Order Number", "DO-1"), ("Status", "Delivered"))
    assert compose._row_key(flat) == (("Order Number", "DO-1"), ("Status", "Delivered"))
