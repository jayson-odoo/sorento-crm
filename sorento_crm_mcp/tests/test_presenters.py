"""Render-envelope presenter coverage (view=render).

Verifies each tool's sanitized data maps into the uniform envelope:
{result_type, intro, items[{title,fields,flags}], attachments, action_links,
last_updated_at, has_result}.
"""
import json

from sorento_crm_mcp.presenters import present_response


def env(tool, data):
    return json.loads(present_response(tool, json.dumps(data)))


def test_orders_list_one_item_per_order_products_inline():
    out = env("crm_order_management_orders_list", {
        "data": [{
            "order_number": "202606-1622", "debtor_name": "HANLIM",
            "order_date": "2026-06-10", "actual_delivery_date": "2026-06-11",
            "order_status": "Picked Up / In Transit", "pickup_time": "09:34:00",
            "transporter": "SORENTO", "driver_name": "AZHAR", "lorry_plate": "VQP1678",
            "warehouse": "BRW",
            "lines": [{"quantity": 3, "product": {"product_code": "SRTWB7109"}}],
        }],
    })
    assert out["result_type"] == "orders"
    assert len(out["items"]) == 1
    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["Order Number"] == "202606-1622"
    assert fields["Customer"] == "HANLIM"
    assert fields["Products"] == "SRTWB7109 (3)"
    assert out["has_result"] is True


def test_incoming_list_one_item_per_line_with_attachment():
    out = env("crm_incoming_stock_list", {
        "data": [{
            "shipment_number": "OOLKSF6417", "shipping_container_number": "UETU5190029",
            "estimated_arrival_date": "2026-01-24",
            "attachment": {"filename": "PL.xlsx", "file_path": "http://x/PL.xlsx", "mime_type": "app/xlsx"},
            "lines": [
                {"product_code": "A", "product_name": "A", "remaining_incoming_quantity": 100,
                 "warehouse_allocations": [{"warehouse_code": "BRW", "allocated_quantity": 100}]},
                {"product_code": "B", "product_name": "B", "remaining_incoming_quantity": 34,
                 "warehouse_allocations": []},
            ],
        }],
    })
    assert len(out["items"]) == 2
    f0 = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert f0["Incoming Quantity"] == 100
    assert f0["Warehouse Allocations"] == "BRW (100)"
    # No aggregate total field leaks into the item.
    assert "Total Incoming Quantity" not in f0
    # Attachment lifted to envelope + intro switches to file mode.
    assert len(out["attachments"]) == 1
    assert out["intro"] == "I have attached the file(s) below."


def test_promotions_one_item_per_product_keeps_header_file_and_expired_flag():
    out = env("crm_marketing_promotions_list", {
        "data": [{
            "description": "Promo.pdf", "is_expired": True,
            "attachments": [{"attachment": {"original_filename": "Promo.pdf", "file_path": "http://x/Promo.pdf"}}],
            "products": [{
                "selling_price": 359.99,
                "product": {"product_code": "KS-001", "product_name": "Sink", "list_price": 599.99,
                            "dimensions_length": 900, "dimensions_width": 470, "dimensions_height": 230},
            }],
        }],
    })
    assert len(out["items"]) == 1
    f = {x["label"]: x["value"] for x in out["items"][0]["fields"]}
    assert f["Promotion"] == "Promo.pdf"
    assert f["Selling Price"] == "MYR 359.99"
    assert f["List Price"] == "MYR 599.99"
    assert f["Dimensions"] == "900 x 470 x 230 mm"
    assert out["items"][0]["flags"]["expired"] is True
    # promo header pdf carried into attachments
    assert any(a["filename"] == "Promo.pdf" for a in out["attachments"])


def test_products_item_plus_nested_attachments():
    out = env("crm_master_products_list", {
        "data": [{
            "product_code": "SRTFC2044", "product_name": "Cistern", "list_price": "1200.00",
            "attachments": [
                {"original_filename": "a.jpg", "file_path": "http://x/a.jpg",
                 "attachment_type": {"type_name": "Product Photos"}},
            ],
        }],
    })
    assert out["result_type"] == "products"
    f = {x["label"]: x["value"] for x in out["items"][0]["fields"]}
    assert f["List Price"] == "MYR 1200.00"
    assert len(out["attachments"]) == 1
    assert out["attachments"][0]["attachmentType"] == "Product Photos"


def test_stock_uses_relabelled_location_fields():
    out = env("crm_inventory_stock_balance_list", {
        "data": [{"product_code": "SRTWT107", "product_name": "SRTWT107",
                  "system_location": "BRW", "system_location_description": "BUKIT RAJA",
                  "quantity_on_hand": 36, "updated_at": "2026-06-12T09:28:56+08:00"}],
    })
    f = {x["label"]: x["value"] for x in out["items"][0]["fields"]}
    assert f["Warehouse"] == "BUKIT RAJA"
    assert f["System Location"] == "BRW"
    assert f["Quantity On Hand"] == 36
    assert out["last_updated_at"] == "2026-06-12T09:28:56+08:00"


def test_forms_minimal_name_only():
    out = env("crm_forms_management_forms_list", {"data": [{"name": "Renovation Form", "attachment_id": "x"}]})
    assert out["items"][0]["fields"] == [{"label": "Form Name", "value": "Renovation Form"}]
    assert out["attachments"] == []


def test_forms_narrowed_carries_attachment():
    out = env("crm_forms_management_forms_list", {
        "data": [{
            "name": "Renovation Form",
            "attachment": {"original_filename": "RENO.pdf", "file_path": "http://x/RENO.pdf",
                           "mime_type": "application/pdf", "attachment_type": {"type_name": "Marketing Forms"}},
        }],
    })
    assert out["items"][0]["fields"][0]["value"] == "Renovation Form"
    assert len(out["attachments"]) == 1
    assert out["attachments"][0]["filename"] == "RENO.pdf"
    assert out["intro"] == "I have attached the file(s) below."


def test_portal_link_becomes_action_link():
    out = env("crm_portal_link_get", {"portal_link": "https://portal/x", "label": "Complaint Portal"})
    assert out["action_links"] == [{"label": "Complaint Portal", "url": "https://portal/x", "type": "portal_link"}]
    assert out["has_result"] is True


def test_empty_result_envelope():
    out = env("crm_master_products_list", {"data": [], "empty": True})
    assert out["items"] == []
    assert out["attachments"] == []
    assert out["has_result"] is False
    assert out["intro"] == "No matching results found."


def test_invalid_json_returns_raw_unchanged():
    assert present_response("crm_master_products_list", "not json") == "not json"
