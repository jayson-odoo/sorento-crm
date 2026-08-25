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


def test_orders_list_quantity_trailing_zeros_truncated():
    """A whole-number decimal qty (2.0000) renders as an int; a real fraction keeps its digits."""
    out = env("crm_order_management_orders_list", {
        "data": [{
            "order_number": "X1",
            "lines": [
                {"quantity": "2.0000", "product": {"product_code": "AAA"}},
                {"quantity": "2.5000", "product": {"product_code": "BBB"}},
                {"quantity": "1.125", "product": {"product_code": "CCC"}},
            ],
        }],
    })
    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["Products"] == "AAA (2), BBB (2.5), CCC (1.125)"


def test_orders_by_product_quantity_trailing_zeros_truncated():
    out = env("crm_order_management_orders_by_product_list", {
        "data": [{
            "order_number": "X2",
            "matched_products": [
                {"product_code": "AAA", "quantity": "3.0000", "warehouse_code": "BRW"},
            ],
        }],
    })
    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["Products"] == "AAA (3) @ BRW"


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


def test_incoming_list_allocation_flags_and_unallocated_field():
    """Allocation signal: MCP owns the truth (booleans + number), n8n owns the badge.

    Line A is fully allocated, B carries no allocation at all, C is partially
    allocated (backend gap = 40). The two flags are mutually exclusive.
    """
    out = env("crm_incoming_stock_list", {
        "data": [{
            "shipment_number": "OOLKSF6417",
            "estimated_arrival_date": "2026-01-24",
            "lines": [
                {"product_code": "A", "remaining_incoming_quantity": 100,
                 "unallocated_quantity": None,
                 "warehouse_allocations": [{"warehouse_code": "BRW", "allocated_quantity": 100}]},
                {"product_code": "B", "remaining_incoming_quantity": 34,
                 "unallocated_quantity": None, "warehouse_allocations": []},
                {"product_code": "C", "remaining_incoming_quantity": 40,
                 "unallocated_quantity": 40,
                 "warehouse_allocations": [{"warehouse_code": "BRW", "allocated_quantity": 60}]},
            ],
        }],
    })
    a, b, c = out["items"]
    assert a["flags"]["unallocated"] is False
    assert a["flags"]["partially_allocated"] is False
    assert "Unallocated Quantity" not in {f["label"] for f in a["fields"]}

    assert b["flags"]["unallocated"] is True
    assert b["flags"]["partially_allocated"] is False
    # Pending allocation needs no number - the badge alone carries the signal.
    assert "Unallocated Quantity" not in {f["label"] for f in b["fields"]}

    assert c["flags"]["unallocated"] is False
    assert c["flags"]["partially_allocated"] is True
    fc = {f["label"]: f["value"] for f in c["fields"]}
    assert fc["Unallocated Quantity"] == 40
    # Existing flags survive unchanged.
    assert c["flags"]["discontinued"] is False


def test_incoming_list_missing_gap_key_claims_no_partial():
    """Forward-compat: an older backend omits `unallocated_quantity`.

    Allocations exist, so `unallocated` is false; without the gap the presenter
    must NOT guess a partial from `remaining_incoming_quantity`.
    """
    out = env("crm_incoming_stock_list", {
        "data": [{
            "shipment_number": "SH1",
            "lines": [
                {"product_code": "A", "remaining_incoming_quantity": 100,
                 "warehouse_allocations": [{"warehouse_code": "BRW", "allocated_quantity": 60}]},
            ],
        }],
    })
    flags = out["items"][0]["flags"]
    assert flags["unallocated"] is False
    assert flags["partially_allocated"] is False


def test_incoming_by_product_allocation_flags():
    out = env("crm_incoming_stock_by_product", {
        "data": [{
            "product_code": "A", "product_name": "A",
            "shipments": [
                {"shipping_container_number": "C1", "remaining_incoming_quantity": 34,
                 "unallocated_quantity": None, "warehouse_allocations": []},
                {"shipping_container_number": "C2", "remaining_incoming_quantity": 40,
                 "unallocated_quantity": 25,
                 "warehouse_allocations": [{"warehouse_code": "BRW", "allocated_quantity": 75}]},
            ],
        }],
    })
    first, second = out["items"]
    assert first["flags"]["unallocated"] is True
    assert second["flags"]["partially_allocated"] is True
    assert {f["label"]: f["value"] for f in second["fields"]}["Unallocated Quantity"] == 25


def test_incoming_shipments_carry_no_allocation_flags_set():
    """Shipment-level rows have no allocations - both flags stay false."""
    out = env("crm_incoming_stock_shipments", {
        "data": [{"shipment_number": "SH1", "total_remaining_incoming_quantity": 90,
                  "distinct_products_incoming": 2}],
    })
    flags = out["items"][0]["flags"]
    assert flags["unallocated"] is False
    assert flags["partially_allocated"] is False


def test_promotions_header_only_with_pdf():
    out = env("crm_marketing_promotions_list", {
        "data": [{
            "description": "Promo.pdf", "is_expired": True,
            "start_date": "2026-05-01", "end_date": "2026-05-31",
            "attachments": [{"attachment": {"original_filename": "Promo.pdf", "file_path": "http://x/Promo.pdf"}}],
            # products may be present in raw data but the presenter ignores them
            "products": [{"selling_price": 359.99, "product": {"product_code": "KS-001"}}],
        }],
    })
    assert len(out["items"]) == 1
    f = {x["label"]: x["value"] for x in out["items"][0]["fields"]}
    assert f["Promotion"] == "Promo.pdf"
    assert f["Start Date"] == "2026-05-01"
    # No product fields surfaced.
    assert "Selling Price" not in f
    assert "Product Code" not in f
    assert out["items"][0]["flags"]["expired"] is True
    # promo header pdf carried into attachments
    assert any(a["filename"] == "Promo.pdf" for a in out["attachments"])


def test_attachment_url_is_file_path_verbatim_not_stored_filename():
    """The attachment `url` must be the DB `file_path` object key exactly - never
    reconstructed from `stored_filename` (the editable display name often differs
    from the real key, which produced 404-ing URLs). See presenters de-dupe block."""
    real_key = "http://cdn/promotion/id/CABANA NEW ARRIVAL END USER.pdf"
    out = env("crm_marketing_promotions_list", {
        "data": [{
            "description": "Promo", "start_date": "2026-05-08", "end_date": "2026-08-08",
            "attachments": [{"attachment": {
                "original_filename": "CABANA NEW ARRIVAL (END USER).pdf",
                "stored_filename": "(CABANA) NEW ARRIVAL END USER.pdf",
                "file_path": real_key,
                "mime_type": "application/pdf",
            }}],
        }],
    })
    a = out["attachments"][0]
    assert a["url"] == real_key                                   # url untouched
    assert a["filename"] == "(CABANA) NEW ARRIVAL END USER.pdf"   # display keeps stored_filename
    assert a["url"].endswith("CABANA NEW ARRIVAL END USER.pdf")   # NOT the (CABANA) key


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


def test_product_name_hidden_when_equal_to_code_shown_when_distinct():
    # name == code → name line dropped (redundant in Sorento)
    out = env("crm_master_products_list", {
        "data": [{"product_code": "SRTWT107", "product_name": "SRTWT107"}],
    })
    labels = {x["label"] for x in out["items"][0]["fields"]}
    assert "Product Code" in labels
    assert "Product Name" not in labels

    # name != code → name retained
    out2 = env("crm_master_products_list", {
        "data": [{"product_code": "SRTFC2044", "product_name": "Cistern"}],
    })
    f2 = {x["label"]: x["value"] for x in out2["items"][0]["fields"]}
    assert f2["Product Name"] == "Cistern"


def test_products_price_and_dimensions_default_to_not_defined():
    out = env("crm_master_products_list", {
        "data": [{"product_code": "SRTNODIM", "product_name": "No Dims Product"}],
    })
    f = {x["label"]: x["value"] for x in out["items"][0]["fields"]}
    assert f["List Price"] == "Not defined"
    assert f["Dimensions"] == "Not defined"


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


def test_resource_attachments_no_type_label():
    out = env("crm_resource_attachments_list", {
        "data": [{
            "original_filename": "Dealer Price List.pdf", "file_path": "http://x/Dealer Price List.pdf",
            "mime_type": "application/pdf", "attachment_type": {"type_name": "Direct Access"},
        }],
    })
    labels = [f["label"] for f in out["items"][0]["fields"]]
    assert labels == ["File Name"]          # no "Type" line
    assert out["attachments"][0]["attachmentType"] is None  # type stripped from the file too


def test_resource_attachments_carry_the_upload_date_when_present():
    """Re-uploaded documents keep one name, so the date is what tells them apart.

    Six revisions of the Container Status workbook are six items reading
    "Container Status 2026.xlsx". Without a date the agent cannot say which one
    it is handing over, and rows arrive newest-first for nothing.
    """
    out = env("crm_resource_attachments_list", {
        "data": [
            {"original_filename": "Container Status 2026.xlsx", "file_path": "http://x/a.xlsx",
             "uploaded_at": "2026-08-07T03:09:33"},
            {"original_filename": "Container Status 2026.xlsx", "file_path": "http://x/b.xlsx",
             "uploaded_at": "2026-08-01T09:00:00"},
        ],
    })
    assert [f["value"] for f in out["items"][0]["fields"]] == [
        "Container Status 2026.xlsx", "2026-08-07",
    ]
    # Looked up by label, not by index: a fixture that later carries a company
    # would shift the position and silently assert against the wrong field.
    assert next(
        f["value"] for f in out["items"][1]["fields"] if f["label"] == "Uploaded"
    ) == "2026-08-01"


def test_resource_attachments_same_name_different_company_are_distinguishable():
    """AC-D2. A contact granted both Mocha and Sorento gets a current workbook
    from EACH, and each company names its sheet the same thing - the File ID is
    deliberately withheld from this render, so the Company field is the only
    handle left to tell the two apart.
    """
    out = env("crm_resource_attachments_list", {
        "data": [
            {"original_filename": "Container Status 2026.xlsx", "file_path": "http://x/sorento.xlsx",
             "company_name": "Sorento"},
            {"original_filename": "Container Status 2026.xlsx", "file_path": "http://x/mocha.xlsx",
             "company_name": "Mocha"},
        ],
    })
    assert len(out["items"]) == 2
    company_by_item = [
        next(f["value"] for f in item["fields"] if f["label"] == "Company")
        for item in out["items"]
    ]
    assert company_by_item == ["Sorento", "Mocha"]
    assert company_by_item[0] != company_by_item[1], (
        "same filename, different company - the two items must not read identically"
    )


def test_resource_attachments_no_company_renders_no_company_line():
    """AC-D3. A shared / company-less attachment (`company_name` absent or
    None) must render with NO Company field at all, never an empty one."""
    out = env("crm_resource_attachments_list", {
        "data": [
            {"original_filename": "Shared Catalogue.pdf", "file_path": "http://x/shared.pdf"},
            {"original_filename": "Also Shared.pdf", "file_path": "http://x/also.pdf",
             "company_name": None},
        ],
    })
    for item in out["items"]:
        labels = [f["label"] for f in item["fields"]]
        assert "Company" not in labels


def test_resource_attachments_do_not_expose_the_row_id():
    """Reversed deliberately. The id was added so a human could trace which of
    several identically-named files the agent sent - but `render` is the
    CUSTOMER view, and the uuid went out on WhatsApp under every document. The
    id is still on the raw (non-render) response, which is where someone
    debugging is looking anyway.
    """
    out = env("crm_resource_attachments_list", {
        "data": [{
            "id": "df853300-0000-0000-0000-000000000001",
            "original_filename": "Container Status 2026.xlsx",
            "file_path": "http://x/a.xlsx",
        }],
    })
    labels = {f["label"] for f in out["items"][0]["fields"]}
    assert "File ID" not in labels
    assert "df853300-0000-0000-0000-000000000001" not in json.dumps(out["items"])


def test_uploaded_at_becomes_last_updated_at():
    """An attachment is never edited in place, so the upload IS its freshness.

    Without this every document answer reported `last_updated_at: null` and the
    agent could not say how current the file it handed over was.
    """
    out = env("crm_resource_attachments_list", {
        "data": [
            {"original_filename": "a.xlsx", "file_path": "http://x/a.xlsx",
             "uploaded_at": "2026-08-01T09:00:00"},
            {"original_filename": "b.xlsx", "file_path": "http://x/b.xlsx",
             "uploaded_at": "2026-08-07T03:09:33"},
        ],
    })
    assert out["last_updated_at"] == "2026-08-07T03:09:33"


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


# ---------------------------------------------------------------- field access


def _incoming_row(**clearance):
    """One shipment row as `/incoming-stock/list` returns it, plus whatever
    clearance fields this caller was permitted."""
    return {
        "shipment_number": "SHP-1",
        "shipping_container_number": "SEGU4008631",
        "estimated_arrival_date": "2026-07-08",
        "lines": [
            {
                "product_code": "SRTWB7109",
                "product_name": "Basin Mixer",
                "batch_number": "B-1",
                "remaining_incoming_quantity": 12,
                "warehouse_allocations": [
                    {"warehouse_code": "BRW", "allocated_quantity": 12}
                ],
            }
        ],
        **clearance,
    }


def test_render_shows_the_clearance_fields_a_caller_may_see():
    """The render view had a hardcoded field list that never included any of them,
    so an entitled contact still got nothing."""
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row(eta_delay_date="2026-07-12", liner_code="CMA")],
    })

    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["ETA"] == "2026-07-08"
    assert fields["ETA Delay"] == "2026-07-12"
    assert fields["Liner"] == "CMA"


def test_render_omits_a_field_the_caller_may_not_see():
    """The backend strips denied keys, so they simply are not in the row. Render
    must not invent a blank line for them - a labelled empty value reads as "not
    reached yet"."""
    out = env("crm_incoming_stock_list", {"data": [_incoming_row()]})

    labels = {f["label"] for f in out["items"][0]["fields"]}
    assert "ETA" in labels, "ships allowed, so the backend sent it"
    assert "Gatepass" not in labels
    assert "ETA Delay" not in labels


def test_render_never_gates_the_answer_itself():
    """Product, container, shipment and quantity are what the contact asked about.
    A contact who may not see a gatepass date must still be told what is arriving,
    so none of these may ever be stripped.

    ETA is NOT among them: it is gateable (revocable by an admin) though it ships
    allowed, so it renders as a clearance pair rather than as identity."""
    out = env("crm_incoming_stock_list", {"data": [_incoming_row()]})

    fields = {f["label"]: f["value"] for f in out["items"][0]["fields"]}
    assert fields["Product Code"] == "SRTWB7109"
    assert fields["Product Name"] == "Basin Mixer"
    assert fields["Shipment"] == "SHP-1"
    assert fields["Container"] == "SEGU4008631"
    assert fields["Incoming Quantity"] == 12
    assert "BRW" in str(fields["Warehouse Allocations"])
    assert out["has_result"] is True


def test_render_carries_the_denial_reason_through():
    """Without it the agent cannot tell "you may not see this" from "it has not
    happened yet", so it guesses - and it guesses the second one out loud."""
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row()],
        "field_access": {
            "denied": [
                {
                    "field": "gatepass_date",
                    "agent_code": "incoming_stock_enquiries",
                    "outcome": "field_not_allowed",
                    "reason": "This contact holds the agent, but this field is not allowed on it.",
                }
            ],
            "note": "Absent does NOT mean the value is unknown or not yet reached.",
        },
    })

    assert out["field_access"]["denied"][0]["outcome"] == "field_not_allowed"
    assert "not yet reached" in out["field_access"]["note"]


def test_render_omits_field_access_when_nothing_was_denied():
    out = env("crm_incoming_stock_list", {"data": [_incoming_row()]})
    assert "field_access" not in out


def test_render_fields_carry_the_crm_field_key():
    """A consumer must project on the key, not on the label.

    Two label vocabularies for the same field already disagree - render says
    "ETC", `field_access.FIELD_LABELS` says "ETC (estimated time of container
    closing)" - so label matching means picking one and being unable to
    cross-check the other. The key is stable under any label rename.
    """
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row(etc_date="2026-06-30", coa_permit_no="COA-9")],
    })

    by_key = {f["key"]: f for f in out["items"][0]["fields"] if "key" in f}
    assert by_key["estimated_arrival_date"]["value"] == "2026-07-08"
    assert by_key["etc_date"]["label"] == "ETC"
    assert by_key["coa_permit_no"]["value"] == "COA-9"
    # Identity fields are keyed too - they are just as answerable.
    assert by_key["product_code"]["value"] == "SRTWB7109"
    assert by_key["shipping_container_number"]["value"] == "SEGU4008631"
    assert by_key["remaining_incoming_quantity"]["value"] == 12
    # Every field of this result type carries one; none is null.
    assert all(f.get("key") for f in out["items"][0]["fields"])


def test_render_key_matches_the_denied_vocabulary():
    """Absent-and-denied vs absent-and-not-reached is decided by comparing the
    same token on both sides, so the two must be the same token.
    """
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row()],
        "field_access": {
            "denied": [
                {"field": "gatepass_date", "agent_code": "a", "outcome": "field_not_allowed"}
            ],
            "note": "Absent does NOT mean the value is unknown or not yet reached.",
        },
    })

    keys = {f.get("key") for f in out["items"][0]["fields"]}
    denied = {d["field"] for d in out["field_access"]["denied"]}
    assert "gatepass_date" in denied
    assert "gatepass_date" not in keys, "denied is absent from fields, by design"
    # ...and a field that is simply not reached is in neither set, which is the
    # third branch: "not recorded", never "I can't share that".
    assert "collection_date" not in keys and "collection_date" not in denied


def test_render_stock_fields_carry_the_key():
    """A cross-domain stock/incoming block is sorted by quantity and ETA. Both
    branches matched on display text, and both were dead: `estimated_arrival_date`
    was relabelled `ETA`, and an incoming row labels its quantity `Incoming
    Quantity`, not `Quantity On Hand`. Sorting on the key survives both.
    """
    out = env("crm_inventory_stock_balance_list", {
        "data": [{"product_code": "SRTWT107", "product_name": "Basin",
                  "system_location": "BRW", "system_location_description": "BUKIT RAJA",
                  "quantity_on_hand": 36}],
    })
    by_key = {f["key"]: f["value"] for f in out["items"][0]["fields"] if "key" in f}
    assert by_key["quantity_on_hand"] == 36
    assert by_key["product_code"] == "SRTWT107"
    assert by_key["warehouse"] == "BUKIT RAJA"
    assert by_key["system_location"] == "BRW"


def test_render_stock_keeps_the_key_on_the_placeholder_value():
    """Warehouse / location / quantity always render, "-" when absent, so the row
    shape never varies. The key rides along, so a consumer that projects on key
    still has to expect a non-numeric value there.
    """
    out = env("crm_inventory_stock_balance_list", {"data": [{"product_code": "X"}]})
    by_key = {f["key"]: f["value"] for f in out["items"][0]["fields"] if "key" in f}
    assert by_key["quantity_on_hand"] == "-"
    assert by_key["warehouse"] == "-"


def test_render_by_product_fields_carry_the_key():
    out = env("crm_incoming_stock_by_product", {
        "data": [{
            "product_code": "SRTWB7109",
            "product_name": "Basin Mixer",
            "shipments": [{
                "shipping_container_number": "SEGU4008631",
                "estimated_arrival_date": "2026-07-08",
                "remaining_incoming_quantity": 12,
                "warehouse_allocations": [{"warehouse_code": "BRW", "allocated_quantity": 12}],
            }],
        }],
    })
    by_key = {f["key"]: f["value"] for f in out["items"][0]["fields"] if "key" in f}
    assert by_key["product_code"] == "SRTWB7109"
    assert by_key["estimated_arrival_date"] == "2026-07-08"


def test_render_omits_key_where_the_presenter_has_no_source_key():
    """`key` is omitted, not emitted as null, so a consumer can test for it."""
    out = env("crm_order_management_orders_list", {
        "data": [{"order_number": "202606-1622", "debtor_name": "HANLIM"}],
    })
    assert out["items"][0]["fields"][0] == {"label": "Order Number", "value": "202606-1622"}


# ------------------------------------------------ absent-field vocabulary


def test_denied_entries_gain_the_customer_facing_label():
    """A denial has to be said out loud: "I can't share the ...". The backend
    sends the field key and an admin-register label lives elsewhere, so the
    envelope supplies the CUSTOMER register here.
    """
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row()],
        "field_access": {
            "denied": [
                {"field": "etc_date", "agent_code": "a", "outcome": "field_not_allowed"},
                {"field": "gatepass_date", "agent_code": "a", "outcome": "field_not_allowed"},
            ],
            "note": "Absent does NOT mean the value is unknown or not yet reached.",
        },
    })
    by_field = {d["field"]: d for d in out["field_access"]["denied"]}
    # Customer register: "ETC", not FIELD_LABELS' "ETC (estimated time of
    # container closing)" - this string ends up in a WhatsApp message.
    assert by_field["etc_date"]["label"] == "ETC"
    assert by_field["gatepass_date"]["label"] == "Gatepass"


def test_denied_entry_keeps_a_label_the_backend_already_sent():
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row()],
        "field_access": {
            "denied": [{"field": "etc_date", "label": "Backend Wins", "outcome": "x"}],
            "note": "n",
        },
    })
    assert out["field_access"]["denied"][0]["label"] == "Backend Wins"


def test_incoming_envelope_carries_the_field_vocabulary():
    """The case that needs it has NO denial: several containers, one carries
    `eta_delay_date` and the others do not. Nothing was withheld, so there is no
    `field_access` block to hang a label off, and the absent rows still have to
    be named. Humanising the key gives "Eta delay" and "Etd"; this gives the
    labels a present field would have rendered with.
    """
    out = env("crm_incoming_stock_list", {"data": [_incoming_row()]})
    assert "field_access" not in out, "nothing denied, so no denial block"
    vocab = out["field_vocabulary"]
    assert vocab["eta_delay_date"] == "ETA Delay"
    assert vocab["etd_date"] == "ETD"
    assert vocab["inspection_date"] == "CIDB Inspection"


def test_field_vocabulary_matches_what_a_present_field_renders_as():
    """Derived from `_CLEARANCE_PAIRS`, so the absent wording and the present
    wording cannot drift into two vocabularies - the exact failure that made
    label-matching untenable in the first place.
    """
    out = env("crm_incoming_stock_list", {
        "data": [_incoming_row(etc_date="2026-06-30", eta_delay_date="2026-07-12")],
    })
    rendered = {f["key"]: f["label"] for f in out["items"][0]["fields"] if "key" in f}
    vocab = out["field_vocabulary"]
    for key, label in rendered.items():
        if key in vocab:
            assert vocab[key] == label, f"{key} renders as {label!r} but vocabulary says {vocab[key]!r}"


def test_vocabulary_is_not_emitted_for_unrelated_result_types():
    """It is the clearance vocabulary, not a general one. Shipping it on orders
    or stock would imply those fields exist there.
    """
    out = env("crm_inventory_stock_balance_list", {"data": [{"product_code": "X"}]})
    assert "field_vocabulary" not in out


def test_document_answers_do_not_expose_the_file_uuid():
    """`render` is the CUSTOMER view and goes out on WhatsApp. The File ID row
    put an internal uuid under every document, next to the file itself.
    """
    out = env("crm_resource_attachments_list", {
        "data": [{
            "id": "1e900020-dba5-4e34-ae1c-5e0f90380095",
            "original_filename": "Container Status 2026.xlsx",
            "uploaded_at": "2026-08-08T06:31:13",
            "file_path": "https://cdn/x.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }],
    })
    fields = out["items"][0]["fields"]
    labels = [f["label"] for f in fields]
    assert labels == ["File Name", "Uploaded"]
    assert "1e900020-dba5-4e34-ae1c-5e0f90380095" not in json.dumps(fields)
    # The file itself still ships - that is the answer.
    assert out["attachments"][0]["filename"] == "Container Status 2026.xlsx"


def test_each_attachment_carries_its_own_upload_time():
    """A document class is re-uploaded under the same name, so several entries
    look identical. The envelope-level `last_updated_at` is the newest across the
    whole answer and says nothing about an individual file.
    """
    out = env("crm_resource_attachments_list", {
        "data": [
            {"original_filename": "Container Status 2026.xlsx", "file_path": "https://cdn/new.xlsx",
             "mime_type": "application/vnd.ms-excel", "uploaded_at": "2026-08-08T11:54:05"},
            {"original_filename": "Container Status 2026.xlsx", "file_path": "https://cdn/old.xlsx",
             "mime_type": "application/vnd.ms-excel", "uploaded_at": "2026-07-01T09:00:00"},
        ],
    })
    assert [a["uploadedAt"] for a in out["attachments"]] == [
        "2026-08-08T11:54:05", "2026-07-01T09:00:00",
    ]
    # Envelope keeps the newest of them, which is a different question.
    assert out["last_updated_at"] == "2026-08-08T11:54:05"


def test_attachment_without_an_upload_time_omits_the_key():
    out = env("crm_resource_attachments_list", {
        "data": [{"original_filename": "a.pdf", "file_path": "https://cdn/a.pdf"}],
    })
    assert "uploadedAt" not in out["attachments"][0]


# =============================================================================
# Multi-company reply clarity (UAC AC-C1..AC-C4,
# documentation/plans/multi-company/multi-company-reply-clarity-acceptance-criteria.md).
# =============================================================================


# --- AC-C1: lookup_companies passthrough ------------------------------------


def test_ac_c1_lookup_companies_passes_through_when_present():
    out = env("crm_inventory_stock_balance_list", {
        "data": [],
        "empty": True,
        "lookup_companies": [
            {"id": "00000000-0000-0000-0000-000000000001", "name": "Sorento"},
            {"id": "00000000-0000-0000-0000-000000000002", "name": "Mocha"},
        ],
    })
    assert out.get("lookup_companies") == [
        {"id": "00000000-0000-0000-0000-000000000001", "name": "Sorento"},
        {"id": "00000000-0000-0000-0000-000000000002", "name": "Mocha"},
    ]


def test_ac_c1_lookup_companies_omitted_not_null_when_absent():
    out = env("crm_inventory_stock_balance_list", {
        "data": [{"product_code": "A", "warehouse": "BRW", "quantity_on_hand": 5}],
    })
    assert "lookup_companies" not in out


def test_ac_c1_lookup_companies_omitted_when_explicitly_null():
    out = env("crm_inventory_stock_balance_list", {
        "data": [{"product_code": "A", "warehouse": "BRW", "quantity_on_hand": 5}],
        "lookup_companies": None,
    })
    assert "lookup_companies" not in out


# --- AC-C2: leading Company field, per builder -------------------------------


def test_ac_c2_stock_row_with_company_name_leads_with_company_field():
    out = env("crm_inventory_stock_balance_list", {
        "data": [{
            "product_code": "A", "warehouse": "BRW", "quantity_on_hand": 5,
            "company_name": "Mocha",
        }],
    })
    fields = out["items"][0]["fields"]
    assert fields[0] == {"key": "company_name", "label": "Company", "value": "Mocha"}


def test_ac_c2_stock_row_without_company_name_has_no_company_field():
    out = env("crm_inventory_stock_balance_list", {
        "data": [{"product_code": "A", "warehouse": "BRW", "quantity_on_hand": 5}],
    })
    labels = [f["label"] for f in out["items"][0]["fields"]]
    assert "Company" not in labels


def test_ac_c2_orders_list_smoke_company_field():
    out = env("crm_order_management_orders_list", {
        "data": [{
            "order_number": "X1", "lines": [{"quantity": 1, "product": {"product_code": "AAA"}}],
            "company_name": "Mocha",
        }],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_orders_by_product_smoke_company_field():
    out = env("crm_order_management_orders_by_product_list", {
        "data": [{
            "order_number": "X2",
            "matched_products": [{"product_code": "AAA", "quantity": 1}],
            "company_name": "Mocha",
        }],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_incoming_list_smoke_company_field_from_shipment():
    """The company lives on the shipment (`s`), not the nested line."""
    out = env("crm_incoming_stock_list", {
        "data": [{
            "shipment_number": "SH1", "company_name": "Mocha",
            "lines": [{"product_code": "A", "remaining_incoming_quantity": 5}],
        }],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_incoming_by_product_smoke_company_field_from_product():
    """The company lives on the product group (`p`), not the nested shipment."""
    out = env("crm_incoming_stock_by_product", {
        "data": [{
            "product_code": "A", "company_name": "Mocha",
            "shipments": [{"shipping_container_number": "C1", "remaining_incoming_quantity": 5}],
        }],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_incoming_shipments_smoke_company_field():
    out = env("crm_incoming_stock_shipments", {
        "data": [{"shipment_number": "SH1", "company_name": "Mocha"}],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_promotions_smoke_company_field():
    out = env("crm_marketing_promotions_list", {
        "data": [{"description": "Promo A", "company_name": "Mocha"}],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_promotion_products_smoke_company_field():
    out = env("crm_marketing_promotion_products_list", {
        "data": [{
            "product": {"product_code": "A"}, "promotion": {"description": "Promo A"},
            "company_name": "Mocha",
        }],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_products_smoke_company_field():
    out = env("crm_master_products_list", {
        "data": [{"product_code": "A", "product_name": "A", "company_name": "Mocha"}],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_product_attachments_smoke_company_field():
    out = env("crm_master_product_attachments_list", {
        "data": [{
            "product": {"product_code": "A"}, "attachment": {"original_filename": "a.pdf"},
            "company_name": "Mocha",
        }],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


def test_ac_c2_certificates_smoke_company_field():
    out = env("crm_certificates_list", {
        "data": [{"certificate_number": "CERT-1", "scheme": "PPS", "company_name": "Mocha"}],
    })
    fields = out["items"][0]["fields"]
    assert {"key": "company_name", "label": "Company", "value": "Mocha"} in fields


# --- AC-C3: empty-result intro names the companies searched -----------------


def test_ac_c3_empty_intro_names_two_companies():
    out = env("crm_inventory_stock_balance_list", {
        "data": [], "empty": True,
        "lookup_companies": [
            {"id": "00000000-0000-0000-0000-000000000002", "name": "Mocha"},
            {"id": "00000000-0000-0000-0000-000000000001", "name": "Sorento"},
        ],
    })
    assert out["has_result"] is False
    assert out["intro"] == "No matching results found for Mocha or Sorento."


def test_ac_c3_empty_intro_names_three_or_more_companies():
    out = env("crm_inventory_stock_balance_list", {
        "data": [], "empty": True,
        "lookup_companies": [
            {"id": "1", "name": "A"}, {"id": "2", "name": "B"}, {"id": "3", "name": "C"},
        ],
    })
    assert out["intro"] == "No matching results found for A, B or C."


def test_ac_c3_empty_intro_plain_when_a_company_name_is_missing():
    """F4 (review round): naming only the companies we happen to have a name for
    turns "I checked two companies" into a confident, wrong "I checked Sorento".
    A partial `lookup_companies` falls back to the plain intro."""
    out = env("crm_inventory_stock_balance_list", {
        "data": [], "empty": True,
        "lookup_companies": [
            {"id": "00000000-0000-0000-0000-000000000001", "name": "Sorento"},
            {"id": "00000000-0000-0000-0000-000000000002", "name": None},
        ],
    })
    assert out["intro"] == "No matching results found."


def test_ac_c3_empty_intro_plain_when_every_company_name_is_missing():
    out = env("crm_inventory_stock_balance_list", {
        "data": [], "empty": True,
        "lookup_companies": [{"id": "00000000-0000-0000-0000-000000000001"}],
    })
    assert out["intro"] == "No matching results found."


def test_ac_c3_empty_intro_unchanged_without_lookup_companies():
    out = env("crm_master_products_list", {"data": [], "empty": True})
    assert out["intro"] == "No matching results found."


# --- AC-C4: byte-identical single-company output -----------------------------


def test_ac_c4_byte_identical_when_company_keys_null_vs_absent_stock():
    # Realistic single-company shape: the row DOES carry its own company_id
    # (the ORM column, filled by `from_attributes`); only `company_name` and
    # `lookup_companies` are null because the lookup spanned one company.
    with_nulls = {
        "data": [{
            "product_code": "A", "warehouse": "BRW", "quantity_on_hand": 5,
            "company_id": "00000000-0000-0000-0000-000000000001",
            "company_name": None,
        }],
        "lookup_companies": None,
    }
    without_keys = {
        "data": [{"product_code": "A", "warehouse": "BRW", "quantity_on_hand": 5}],
    }
    assert present_response(
        "crm_inventory_stock_balance_list", json.dumps(with_nulls)
    ) == present_response("crm_inventory_stock_balance_list", json.dumps(without_keys))


def test_ac_c4_byte_identical_when_company_keys_null_vs_absent_orders():
    with_nulls = {
        "data": [{
            "order_number": "X1", "lines": [{"quantity": 1, "product": {"product_code": "AAA"}}],
            "company_id": "00000000-0000-0000-0000-000000000001",
            "company_name": None,
        }],
        "lookup_companies": None,
    }
    without_keys = {
        "data": [{
            "order_number": "X1", "lines": [{"quantity": 1, "product": {"product_code": "AAA"}}],
        }],
    }
    assert present_response(
        "crm_order_management_orders_list", json.dumps(with_nulls)
    ) == present_response("crm_order_management_orders_list", json.dumps(without_keys))


def test_ac_c4_byte_identical_empty_result_null_lookup_companies():
    with_null = {"data": [], "empty": True, "lookup_companies": None}
    without_key = {"data": [], "empty": True}
    assert present_response(
        "crm_master_products_list", json.dumps(with_null)
    ) == present_response("crm_master_products_list", json.dumps(without_key))


# --- QS-C8: summary + pagination passthrough (order-quantity-summary) -----------


_QS_SUMMARY = {
    "scope": "filter", "row_count": 35, "order_count": 35, "delivered_count": 33,
    "pending_count": 2, "customers": ["ECO WORLD SDN BHD"], "customer_count": 1,
    "delivered_from": "2026-03-02", "delivered_to": "2026-07-15",
    "products": [{"product_code": "SRTWC8605", "delivered_quantity": 48, "pending_quantity": 12}],
}

_QS_ROW = {"order_number": "202603-0412", "debtor_name": "ECO WORLD SDN BHD",
           "order_date": "2026-03-01", "actual_delivery_date": "2026-03-02",
           "matched_products": [{"product_code": "SRTWC8605", "quantity": 10}]}


def test_qs_c8_summary_passes_through_untouched_pagination_does_not():
    out = env("crm_order_management_orders_by_product_list", {
        "data": [_QS_ROW],
        "pagination": {"total": 35, "page": 1, "limit": 20},
        "summary": _QS_SUMMARY,
    })
    assert out["summary"] == _QS_SUMMARY
    assert "pagination" not in out  # no reader on the n8n side; row_count lives in summary
    # the rows themselves render exactly as before
    assert out["items"][0]["title"] == "202603-0412"


def test_qs_c8_orders_list_passes_summary_too():
    out = env("crm_order_management_orders_list", {
        "data": [{**_QS_ROW, "lines": []}],
        "pagination": {"total": 1, "page": 1, "limit": 20},
        "summary": {**_QS_SUMMARY, "row_count": 1, "order_count": 1},
    })
    assert out["summary"]["row_count"] == 1


def test_qs_c8_summary_omitted_not_null_when_absent():
    out = env("crm_order_management_orders_by_product_list", {"data": [_QS_ROW]})
    assert "summary" not in out


def test_qs_c8_summary_omitted_when_explicitly_null():
    out = env("crm_order_management_orders_by_product_list", {"data": [_QS_ROW], "summary": None})
    assert "summary" not in out


def test_qs_c6_by_product_catalog_accepts_order_status():
    from sorento_crm_mcp.catalog import CATALOG
    spec = next(s for s in CATALOG if s.name == "crm_order_management_orders_by_product_list")
    assert "order_status" in spec.query_params
    assert "include_summary" in spec.query_params
    lst = next(s for s in CATALOG if s.name == "crm_order_management_orders_list")
    assert "include_summary" in lst.query_params


# --- QS-M: the presenter renders `summary_items` (order-quantity-summary amendment 4) -------
# Same shape as items[]: {title, fields[{key,label,value}]}. Ids mirror tests/uac/QS.md §QS-M.

import json as _json
import pathlib as _pathlib

from sorento_crm_mcp.presenters import summary_items, summary_intro

_QS6 = _json.loads((_pathlib.Path(__file__).parent / "fixtures" / "qs6-envelopes.json").read_text())

_G_ECO = {"customer": "ECO WORLD SDN BHD", "product_code": "SRTWC8605", "order_count": 5,
          "delivered_quantity": 48, "pending_quantity": 17,
          "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"}
_P_8605 = {"product_code": "SRTWC8605", "order_count": 5, "delivered_quantity": 48, "pending_quantity": 17,
           "delivered_from": "2026-03-02", "delivered_to": "2026-07-15"}
_SUM_M1 = {"scope": "filter", "row_count": 5, "order_count": 5, "delivered_count": 3, "pending_count": 2,
           "customers": ["ECO WORLD SDN BHD"], "customer_count": 1,
           "delivered_from": "2026-03-02", "delivered_to": "2026-07-15",
           "products": [_P_8605], "groups": [_G_ECO]}


def _fields(item):
    return [(f["key"], f["label"], f["value"]) for f in item["fields"]]


def test_qs_m1_single_customer_single_product_is_one_item_in_the_item_shape():
    items = summary_items(_SUM_M1)
    assert len(items) == 1
    assert items[0]["title"] == "ECO WORLD SDN BHD · SRTWC8605"
    assert _fields(items[0]) == [
        ("customer", "Customer", "ECO WORLD SDN BHD"),
        ("product_code", "Product Code", "SRTWC8605"),
        ("order_count", "DOs", 5),
        ("delivered_quantity", "Delivered Qty", 48),
        ("pending_quantity", "Pending Qty", 17),
        ("delivered_between", "Delivered", "02/03/2026 – 15/07/2026"),
    ]
    # every field carries a key - consumers match on it, never on the label
    assert all(set(f) == {"key", "label", "value"} for f in items[0]["fields"])


def test_qs_m2_multi_customer_gets_a_leading_total_then_one_item_per_customer():
    g2 = {**_G_ECO, "customer": "HANLIM TRADING SDN BHD", "order_count": 1, "delivered_quantity": 7,
          "pending_quantity": 0, "delivered_from": "2026-08-01", "delivered_to": "2026-08-01"}
    s = {**_SUM_M1, "customer_count": 2, "customers": ["ECO WORLD SDN BHD", "HANLIM TRADING SDN BHD"],
         "products": [{**_P_8605, "order_count": 6, "delivered_quantity": 55, "delivered_to": "2026-08-01"}],
         "groups": [_G_ECO, g2]}
    items = summary_items(s)
    assert [i["title"] for i in items] == ["All customers (2) · SRTWC8605", "ECO WORLD SDN BHD · SRTWC8605",
                                           "HANLIM TRADING SDN BHD · SRTWC8605"]
    total = dict((k, v) for k, _, v in _fields(items[0]))
    assert total["delivered_quantity"] == 55 and total["order_count"] == 6           # products[], not a sum
    assert total["delivered_between"] == "02/03/2026 – 01/08/2026"
    hanlim = dict((k, v) for k, _, v in _fields(items[2]))
    assert hanlim["delivered_between"] == "01/08/2026"                              # same-day span collapses
    assert "pending_quantity" in hanlim and hanlim["pending_quantity"] == 0         # 0 is a value, kept


def test_qs_m3_two_products_bucket_under_their_own_product():
    g_b = {**_G_ECO, "product_code": "SRTWC287-ARL", "order_count": 1, "delivered_quantity": 6, "pending_quantity": 0}
    s = {**_SUM_M1, "products": [{**_P_8605, "product_code": "SRTWC287-ARL", "delivered_quantity": 6}, _P_8605],
         "groups": [g_b, _G_ECO]}   # CRM order: customer then product
    items = summary_items(s)
    assert [i["title"] for i in items] == ["ECO WORLD SDN BHD · SRTWC287-ARL", "ECO WORLD SDN BHD · SRTWC8605"]


def test_qs_m4_real_multi68_envelope():
    S = _QS6["multi68"]["envelope"]["summary"]        # captured before amendment 4: no dates on groups
    items = summary_items(S)
    named = [g for g in S["groups"] if isinstance(g.get("customer"), str) and g["customer"].strip()]
    assert len(items) == 1 + len(named)
    assert items[0]["title"] == f"All customers ({len(named)}) · {S['products'][0]['product_code']}"
    total = dict((k, v) for k, _, v in _fields(items[0]))
    assert total["delivered_quantity"] == S["products"][0]["delivered_quantity"]
    assert "delivered_between" not in total                # old shape has no per-product dates: dropped, not None
    for it, g in zip(items[1:], named):
        assert it["title"] == f"{g['customer'].strip()} · {g['product_code']}"


def test_qs_m5_no_groups_still_states_the_product_total():
    s = {**_SUM_M1, "groups": []}
    items = summary_items(s)
    assert len(items) == 1 and items[0]["title"] == "SRTWC8605"
    assert _fields(items[0])[0] == ("product_code", "Product Code", "SRTWC8605")


def test_qs_m6_unnameable_rows_are_dropped_not_coerced():
    s = {**_SUM_M1, "products": [{"product_code": {}, "delivered_quantity": 5}, _P_8605],
         "groups": [{"customer": {"n": 1}, "product_code": "SRTWC8605", "delivered_quantity": 1}, _G_ECO]}
    items = summary_items(s)
    assert [i["title"] for i in items] == ["ECO WORLD SDN BHD · SRTWC8605"]
    dumped = _json.dumps(items)
    assert '"n": 1' not in dumped and "None" not in dumped and "null" not in dumped   # nothing coerced or leaked


def test_qs_m7_hostile_leaves_never_raise_or_leak():
    hostile = {"scope": "filter", "row_count": "1e5000", "customers": ["X"], "customer_count": True,
               "products": [{"product_code": "P", "order_count": float("nan"), "delivered_quantity": "1e5000",
                             "pending_quantity": "inf", "delivered_from": "not-a-date", "delivered_to": "2026-13-45"}],
               "groups": "nope"}
    items = summary_items(hostile)
    dumped = _json.dumps(items)
    assert "e+" not in dumped and "nan" not in dumped.lower() and "inf" not in dumped.lower()
    assert "not-a-date" not in dumped and "2026-13-45" not in dumped and "None" not in dumped
    for bad in ("not an object", [1, 2], {"products": "x", "groups": 5}):
        assert summary_items(bad) == []
    assert summary_intro(hostile, 3) is None                       # row_count unrenderable -> no intro


def test_qs_m8_intro_states_the_page_geometry():
    assert summary_intro({"row_count": 8}, 2) == "Summary over 8 DOs (showing 2 of them below)."
    assert summary_intro({"row_count": 3}, 3) == "Summary over 3 DOs."
    assert summary_intro({"row_count": 1}, 1) == "Summary over 1 DO."
    assert summary_intro({"row_count": 700, "groups_truncated": True}, 20) == (
        "Summary over 700 DOs (showing 20 of them below). Not every breakdown is shown — add a customer, a product or a date range.")
    assert "Not every breakdown" in summary_intro({"row_count": 9, "products_truncated": True}, 9)


def test_qs_m9_total_uses_the_crm_customer_count_not_the_visible_slice():
    """Codex F: after the 500-row ceiling groups[] may hold ONE row for a product that 68 customers
    took - the Total must still appear and say 68, from products[].customer_count."""
    s = {**_SUM_M1, "customer_count": 68, "groups_truncated": True,
         "products": [{**_P_8605, "customer_count": 68, "order_count": 187, "delivered_quantity": 32649}],
         "groups": [_G_ECO]}
    items = summary_items(s)
    assert items[0]["title"] == "All customers (68) · SRTWC8605"
    assert dict((k, v) for k, _, v in _fields(items[0]))["delivered_quantity"] == 32649
    assert items[1]["title"] == "ECO WORLD SDN BHD · SRTWC8605"
    # and with no customer_count on the product (older CRM) it falls back to the visible rows
    s2 = {**_SUM_M1, "groups": [_G_ECO]}
    assert [i["title"] for i in summary_items(s2)] == ["ECO WORLD SDN BHD · SRTWC8605"]


def test_qs_m0_summary_items_absent_unless_a_real_answer(monkeypatch):
    base = {"data": [{**_QS_ROW, "lines": []}], "pagination": {"total": 1, "page": 1, "limit": 20}}
    out = env("crm_order_management_orders_list", {**base, "summary": _SUM_M1})
    assert out["summary_items"] == summary_items(_SUM_M1)
    assert out["intro"] == "Summary over 5 DOs (showing 1 of them below)."
    assert "summary_lines" not in out
    assert "summary_items" not in env("crm_order_management_orders_list", base)                        # no summary
    assert "summary_items" not in env("crm_order_management_orders_list", {"data": [], "summary": _SUM_M1})  # no rows
    plain = env("crm_order_management_orders_list", {**base, "summary": {"scope": "filter"}})
    assert "summary_items" not in plain and plain["intro"] == "Here are the orders I found."           # degrades: intro untouched
    import sorento_crm_mcp.presenters as _p
    monkeypatch.setattr(_p, "summary_items", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    out2 = env("crm_order_management_orders_list", {**base, "summary": _SUM_M1})
    assert out2["items"] and "summary_items" not in out2 and out2["intro"] == "Here are the orders I found."
