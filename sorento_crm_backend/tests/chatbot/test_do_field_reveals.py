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

from app.services.chatbot.lanes.business import fetch
from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import present_response

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


def test_both_order_list_tools_declare_the_five_keys() -> None:
    specs = {spec.name: spec for spec in CATALOG}
    for tool in ("crm_order_management_orders_list",):
        declared = {key for key, _label in specs[tool].restricted_fields}
        assert set(DO_KEYS) <= declared, (tool, declared)
