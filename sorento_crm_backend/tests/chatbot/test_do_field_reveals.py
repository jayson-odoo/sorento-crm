"""DO-ASK-SIMPLIFY rule 2: five DO fields are per-contact field reveals, hidden by default.

`documentation/plans/chatbot/PLAN-do-ask-simplify-2oct.md`, rule 2. Status, Pickup Time,
Transporter, Driver and Lorry Plate on a delivery order list carry a `contact_field_reveals`
key under `delivery_orders.*`; a contact without the grant never reads them. Every other DO
field (Order Number, Customer, dates, Products, Company, Warehouse) is always shown.

The real MCP presenter renders the row, then the chatbot's `output_structurer` gates it, so
this pins the whole chain the WhatsApp reply goes through.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.services.chatbot.lanes.business import fetch
from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

# The MCP package sits next to this checkout's backend and is not installed in the backend
# image CI runs; put it on the path first, the way
# `test_field_reveal_keys_pinned_to_catalog.py` and `test_dealer_eta_stock_routing.py` do.
_MCP_ROOT = Path(__file__).resolve().parents[3] / "sorento_crm_mcp"
if str(_MCP_ROOT) not in sys.path:
    sys.path.append(str(_MCP_ROOT))

from sorento_crm_mcp.catalog import CATALOG  # noqa: E402
from sorento_crm_mcp.presenters import present_response  # noqa: E402

DO_KEYS = {
    "delivery_orders.status": "Status",
    "delivery_orders.pickup_time": "Pickup Time",
    "delivery_orders.transporter": "Transporter",
    "delivery_orders.driver": "Driver",
    "delivery_orders.lorry_plate": "Lorry Plate",
}

_ROW = {
    "order_number": "202609-0916",
    "debtor_name": "HANLIM TRADING SDN BHD [A/C I]",
    "order_date": "2026-09-07",
    "actual_delivery_date": "2026-09-07",
    "order_status": "Picked Up / In Transit",
    "pickup_time": "09:18:00",
    "transporter": "SORENTO",
    "driver_name": "AZHAR",
    "lorry_plate": "VQP1678",
    "warehouse": "BRW",
    "lines": [{"product_code": "SRT320-CR", "quantity": 200}],
}


def _reply(granted: list[str] | None) -> str:
    envelope = json.loads(present_response("crm_order_management_orders_list", json.dumps({"data": [_ROW]})))
    ctx = {"semantic_input": {}, "access": {"allowed": True, "attributes": granted}}
    return fetch.output_structurer(envelope, ctx)["response"]


def test_a_contact_with_no_grant_reads_no_logistics_field() -> None:
    said = _reply(None)
    for label in DO_KEYS.values():
        assert f"*{label}:*" not in said, f"{label} must be hidden without its grant: {said!r}"
    for value in ("AZHAR", "VQP1678", "Picked Up / In Transit", "09:18:00"):
        assert value not in said, said


def test_a_contact_with_no_grant_still_reads_the_always_shown_fields() -> None:
    said = _reply(None)
    for value in ("202609-0916", "HANLIM TRADING SDN BHD [A/C I]", "BRW", "SRT320-CR (200)"):
        assert value in said, said


def test_a_contact_with_every_grant_reads_today_s_reply() -> None:
    said = _reply(list(DO_KEYS))
    for value in ("Picked Up / In Transit", "09:18:00", "SORENTO", "AZHAR", "VQP1678"):
        assert value in said, said


def test_each_key_unlocks_only_its_own_field() -> None:
    said = _reply(["delivery_orders.status"])
    assert "Picked Up / In Transit" in said, said
    for value in ("AZHAR", "VQP1678", "09:18:00"):
        assert value not in said, said


def test_the_five_keys_are_on_the_field_reveals_checklist() -> None:
    listed = dict(FIELD_REVEAL_KEYS)
    for key in DO_KEYS:
        assert key in listed, f"{key} missing from FIELD_REVEAL_KEYS"


def test_the_orders_list_tool_declares_the_five_keys() -> None:
    """Only the orders list shows the five fields; the by-product list shows none of them."""
    specs = {spec.name: spec for spec in CATALOG}
    declared = {key for key, _label in specs["crm_order_management_orders_list"].restricted_fields}
    assert set(DO_KEYS) <= declared, declared


# --- security B1: the "not delivered yet" miss line names the status only with the grant --- #


def _delivered_miss(**kwargs) -> str:
    from app.services.chatbot.lanes.business.answer import not_found_error_message

    order_uuid = "33333333-3333-4333-9333-333333333333"
    match = {
        "entity_type": "order",
        "uuid": order_uuid,
        "canonical_code": "202609-0916",
        "display": {"customer_name": "HANLIM TRADING SDN BHD [A/C I]", "status": "Picked Up / In Transit"},
    }
    resolved = {
        "tokens": ["202609-0916"],
        "unresolved_tokens": [],
        "resolutions": [{"token": "202609-0916", "matches": [match]}],
        "intersection": [match],
        "by_entity_type": {"order": [match]},
    }
    parser = {
        "domain_hint": "order",
        "order_status": "delivered",
        "entities": [{"hint": "order", "raw": "202609-0916"}],
        "routing": {"suggested_team": "customer_service"},
        "access_levels": [],
    }
    gate = {
        "gate_passed": True,
        "compatible_entities": [{"uuid": order_uuid, "entity_type": "order", "code": "202609-0916"}],
    }
    out = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate, **kwargs)
    return out.get("escalate_message") or ""


def test_the_not_delivered_line_hides_the_status_without_the_grant() -> None:
    message = _delivered_miss(granted_keys=[])
    assert "hasn't been delivered yet." in message, message
    assert "Picked Up" not in message and "current status" not in message, message


def test_the_not_delivered_line_hides_the_status_when_no_grants_are_passed() -> None:
    message = _delivered_miss()
    assert "Picked Up" not in message, message


def test_the_not_delivered_line_names_the_status_with_the_grant() -> None:
    message = _delivered_miss(granted_keys=["delivery_orders.status"])
    assert "current status: Picked Up / In Transit" in message, message


# --- tester pass 2: a value's own '*' never opens WhatsApp bold ---------------------------- #


def test_an_asterisk_in_a_value_does_not_leave_a_stray_bold_marker() -> None:
    """A product code like '*REPLACE' printed raw pairs its '*' with the next label's bold
    marker, and the reply shows a stray '*'. A value's own '*' prints as the look-alike
    U+2217, which WhatsApp does not read as formatting."""
    row = {**_ROW, "lines": [{"product_code": "*REPLACE", "quantity": 1}]}
    envelope = json.loads(present_response("crm_order_management_orders_list", json.dumps({"data": [row]})))
    said = fetch.output_structurer(envelope, {"semantic_input": {}, "access": {"attributes": list(DO_KEYS)}})["response"]
    assert "∗REPLACE (1)" in said, said
    stars = [line for line in said.split("\n") if line.count("*") % 2]
    assert not stars, f"a line with an unpaired '*': {stars!r}"
