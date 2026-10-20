"""CHAT-STATE r7 v2 AC-R7-6 (red): a promotion / file / order row carries its id so a pick can fetch exactly that row.

The id rides at the TOP LEVEL of the item (`_Builder.item(entity_id=...)`, presenters.py:287/:329), never inside
`fields` (a field is printed to the customer). Raw rows are the real tool-result shapes of the existing
presenter tests (tests/test_presenters.py:205-225 promotions, :14-30 orders).
"""
import json

from sorento_crm_mcp.presenters import present_response

PID = "6f1c1c1e-0000-4000-8000-0000000000a1"
AID = "6f1c1c1e-0000-4000-8000-0000000000b2"
OID = "6f1c1c1e-0000-4000-8000-0000000000c3"


def env(tool, data):
    return json.loads(present_response(tool, json.dumps(data)))


def _promo():
    return env("crm_marketing_promotions_list", {"data": [{
        "id": PID, "description": "Promo.pdf", "is_expired": False,
        "start_date": "2026-10-01", "end_date": "2026-10-31",
        "attachments": [{"attachment": {"id": AID, "original_filename": "Promo.pdf", "file_path": "http://x/Promo.pdf"}}],
    }]})


def test_a_promotion_item_carries_the_promotion_id_at_top_level():
    assert _promo()["items"][0].get("id") == PID


def test_an_attachment_entry_carries_the_attachment_id():
    assert _promo()["attachments"][0].get("id") == AID


def test_an_order_item_carries_the_order_id_at_top_level():
    out = env("crm_order_management_orders_list", {"data": [{
        "id": OID, "order_number": "202606-1622", "debtor_name": "HANLIM", "order_date": "2026-06-10",
        "lines": [{"quantity": 3, "product": {"product_code": "SRTWB7109"}}],
    }]})
    assert out["items"][0].get("id") == OID


def test_guard_no_id_is_ever_a_printed_field_value():
    out = _promo()
    printed = json.dumps([f["value"] for i in out["items"] for f in i["fields"]])
    assert PID not in printed and AID not in printed
