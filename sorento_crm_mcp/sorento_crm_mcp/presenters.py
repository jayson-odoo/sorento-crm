"""Render-envelope presenters for the consolidated MCP list tools.

When a tool is called with `view=render`, its (already sanitized) data response is
transformed into ONE uniform envelope so the n8n / messaging consumer needs only a
generic renderer instead of per-tool field-mapping code:

    {
      "result_type": "orders",
      "intro": "Here are the orders I found.",
      "items": [
        {"title": "...", "fields": [{"label": "...", "value": "..."}],
         "flags": {"discontinued": false, "expired": false, "expiring_soon": false,
                   "unallocated": false, "partially_allocated": false}}
      ],
      "attachments": [{"url","filename","mimeType","attachmentType"}],
      "action_links": [{"label","url","type"}],
      "last_updated_at": "...",
      "has_result": true
    }

The envelope is intentionally MARKDOWN-FREE - `fields` carry label/value pairs only.
The consumer owns the skin (bold, numbering, footer). This keeps the envelope
channel-agnostic (WhatsApp, email, web can each render it differently).

`view=render` is OPT-IN: without it, tools return their raw data shape unchanged, so
the AI assistant (which still reads raw) is not affected until it migrates.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

# Tools that support `view=render`. Used by server._compile_tool to inject the
# `view` param into the generated input schema, and by the dispatcher below.
PRESENTER_TOOLS: frozenset[str] = frozenset(
    {
        "crm_order_management_orders_list",
        "crm_order_management_orders_by_product_list",
        "crm_incoming_stock_list",
        "crm_incoming_stock_by_product",
        "crm_incoming_stock_shipments",
        "crm_marketing_promotions_list",
        "crm_marketing_promotion_products_list",
        "crm_master_products_list",
        "crm_master_product_attachments_list",
        "crm_certificates_list",
        "crm_resource_attachments_list",
        "crm_inventory_stock_balance_list",
        "crm_forms_management_forms_list",
        "crm_portal_link_get",
    }
)

_DEFAULT_INTRO = {
    "crm_order_management_orders_list": "Here are the orders I found.",
    "crm_order_management_orders_by_product_list": "Here are the orders I found.",
    "crm_incoming_stock_list": "Here is the incoming stock I found.",
    "crm_incoming_stock_by_product": "Here is the incoming stock I found.",
    "crm_incoming_stock_shipments": "Here are the incoming shipments I found.",
    "crm_marketing_promotions_list": "Here are the matching promotions.",
    "crm_marketing_promotion_products_list": "Here are the matching promotion products.",
    "crm_master_products_list": "Here are the matching products.",
    "crm_master_product_attachments_list": "Here are the product files I found.",
    "crm_certificates_list": "Here are the certificates I found.",
    "crm_resource_attachments_list": "Here are the documents I found.",
    "crm_inventory_stock_balance_list": "Stock details found for the requested products.",
    "crm_forms_management_forms_list": "Here are the forms I found.",
    "crm_portal_link_get": "Here is the link you requested.",
}

_RESULT_TYPE = {
    "crm_order_management_orders_list": "orders",
    "crm_order_management_orders_by_product_list": "orders",
    "crm_incoming_stock_list": "incoming_stock",
    "crm_incoming_stock_by_product": "incoming_stock",
    "crm_incoming_stock_shipments": "incoming_shipments",
    "crm_marketing_promotions_list": "promotions",
    "crm_marketing_promotion_products_list": "promotion_products",
    "crm_master_products_list": "products",
    "crm_master_product_attachments_list": "product_attachments",
    "crm_certificates_list": "certificates",
    "crm_resource_attachments_list": "attachments",
    "crm_inventory_stock_balance_list": "stock",
    "crm_forms_management_forms_list": "forms",
    "crm_portal_link_get": "portal_link",
}

_STOCK_TOOL = "crm_inventory_stock_balance_list"

# The stock tool answers in whichever shape the contact's visibility policy
# allows, so its result_type is decided per RESPONSE, not per tool.
_STOCK_MODE_RESULT_TYPE = {
    "compact": "stock_compact",
    "availability": "stock_availability",
}

_STOCK_COMPACT_INTRO = "Stock summary for the requested products."
# The dealer answer, verbatim. This IS the outbound WhatsApp text (n8n prints the
# intro and nothing else for this mode), so the wording is the contract.
_AVAILABILITY_ASK = "How many units do you need?"
_AVAILABILITY_YES = "Yes, we have stock."
_AVAILABILITY_NO = "Sorry, we do not have enough stock for that quantity."
_AVAILABILITY_MIXED = "Here is the stock availability for the requested products."

# Passthrough keys preserved from the raw response into the envelope (e.g. the
# escalation hint attached after sanitize). Kept so render mode loses nothing.
_PASSTHROUGH_KEYS = (
    "suggested_escalation",
    "escalate_team",
    "escalated_agent",
    "fallback_used",
    "alternatives",
    "relaxed_axis",
    # Every company the backend actually searched, present only when the lookup
    # spanned more than one (see `stamp_lookup_companies` backend-side). A
    # single-company reply never carries it, so it stays byte-identical.
    "lookup_companies",
    # Which fields were withheld from this caller and why. Without it, `render`
    # drops a denied field silently and the agent cannot tell "you may not see
    # this" from "it has not happened yet" - so it guesses, and it guesses the
    # second one out loud.
    "field_access",
    # Which stock-visibility policy answered, so the consumer can branch on the
    # mode (which format to print, whether to ask the quantity question again)
    # instead of inferring it from which block happens to be present.
    "stock_visibility",
)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _filled(v: Any) -> bool:
    return v is not None and str(v).strip() != ""


def _money(v: Any) -> str | None:
    if not _filled(v):
        return None
    try:
        return f"MYR {float(v):.2f}"
    except (TypeError, ValueError):
        return f"MYR {v}"


def _qty(v: Any) -> Any:
    """Render a quantity compactly - drop a meaningless fractional part.

    ``2.0000`` -> ``"2"``, ``2.5000`` -> ``"2.5"``, ``2.125`` -> ``"2.125"``.
    Non-numeric / None passes through unchanged. Decimal (not float) so we never
    introduce binary artefacts on an already-clean value.
    """
    if v is None:
        return v
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return v
    if d == d.to_integral_value():
        return str(d.to_integral_value())
    s = format(d, "f")  # fixed-point, never exponent notation
    return s.rstrip("0").rstrip(".") if "." in s else s


def _dims(o: dict) -> str | None:
    l, w, h = o.get("dimensions_length"), o.get("dimensions_width"), o.get("dimensions_height")
    if any(_filled(x) for x in (l, w, h)):
        fmt = lambda x: x if _filled(x) else "-"
        return f"{fmt(l)} x {fmt(w)} x {fmt(h)} mm"
    return None


def _distinct_name(code: Any, name: Any) -> str | None:
    """Product name only when it differs from the code.

    Sorento usually sets product_name == product_code, so showing both is
    redundant. Surface the name only when it carries extra info (code != name).
    """
    if not _filled(name):
        return None
    if _filled(code) and str(name).strip() == str(code).strip():
        return None
    return name


def _att_type(a: dict) -> str | None:
    t = a.get("attachment_type")
    if not t:
        return None
    if isinstance(t, str):
        return t
    return t.get("description") or t.get("type_name")


class _Builder:
    """Accumulates items + attachments + action_links while walking the rows."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.attachments: list[dict[str, Any]] = []
        self.action_links: list[dict[str, Any]] = []

    def item(
        self,
        title: Any,
        pairs: list[tuple[Any, ...]],
        *,
        discontinued=False,
        expired=False,
        expiring_soon=False,
        unallocated=False,
        partially_allocated=False,
    ) -> None:
        # A pair is either (label, value) or (key, label, value). The 3-tuple form
        # carries the CRM field key, which is what a consumer must match on: the
        # label is display text and two vocabularies for the same field already
        # disagree (render says "ETC", field_access.FIELD_LABELS says "ETC
        # (estimated time of container closing)"). The key is also what
        # `field_access.denied[].field` reports, so a consumer can tell "withheld"
        # from "not yet reached" by comparing the same token on both sides.
        # `key` is omitted, never null, when the source key is unknown.
        fields: list[dict[str, Any]] = []
        for pair in pairs:
            key, lbl, val = pair if len(pair) == 3 else (None, *pair)
            if not _filled(val):
                continue
            fields.append(
                {"label": lbl, "value": val} if key is None else {"key": key, "label": lbl, "value": val}
            )
        if not fields:
            return
        self.items.append(
            {
                "title": title if _filled(title) else None,
                "fields": fields,
                "flags": {
                    "discontinued": bool(discontinued),
                    "expired": bool(expired),
                    # Mutually exclusive with `expired` - a renewal deadline is
                    # not a dead document, and collapsing the two would have the
                    # consumer refuse to serve a certificate that is still valid.
                    "expiring_soon": bool(expiring_soon),
                    "unallocated": bool(unallocated),
                    "partially_allocated": bool(partially_allocated),
                },
            }
        )

    def raw_item(self, title: Any, fields: list[dict[str, Any]], flags: dict[str, Any]) -> None:
        """An item whose fields and flags the SOURCE already shaped.

        `item()` maps a raw CRM row: it drops empty values and stamps the five
        standard flags. The stock-visibility blocks arrive pre-shaped by the
        policy - an `availability` answer has no fields AT ALL (that is the
        point of the mode) and carries its own two flags - so mapping them
        through `item()` would delete the answer for being empty.
        """
        self.items.append(
            {
                "title": title if _filled(title) else None,
                "fields": fields,
                "flags": flags,
            }
        )

    def attach(self, a: Any) -> None:
        if not isinstance(a, dict):
            return
        url = a.get("file_path") or a.get("url")
        if not _filled(url):
            return
        entry = {
            "url": url,
            "filename": a.get("stored_filename") or a.get("filename") or a.get("original_filename"),
            "mimeType": a.get("mime_type") or a.get("mimeType"),
            "attachmentType": _att_type(a),
        }
        # When the file was uploaded, per FILE. A document class is re-uploaded
        # under the same name - six revisions of "Container Status 2026.xlsx" are
        # six identical-looking entries - so without this a consumer handing over
        # one of them cannot say how current it is. The envelope-level
        # `last_updated_at` is the newest across the whole answer, which says
        # nothing about the individual file when more than one comes back.
        # Already Malaysia wall-clock: the sanitizer rewrites `uploaded_at`
        # before the presenter sees it.
        uploaded = a.get("uploaded_at")
        if _filled(uploaded):
            entry["uploadedAt"] = uploaded
        self.attachments.append(entry)

    def link(self, label: str, url: str, link_type: str = "portal_link") -> None:
        if _filled(url):
            self.action_links.append({"label": label, "url": url, "type": link_type})


# --------------------------------------------------------------------------
# per-tool builders
# --------------------------------------------------------------------------
def _wh_alloc(allocs: Any) -> str:
    return ", ".join(
        f"{a.get('warehouse_code')} ({a.get('allocated_quantity')})" for a in (allocs or [])
    )


def _alloc_state(row: Any) -> tuple[bool, bool, Any]:
    """Allocation signal for one incoming line: (unallocated, partially_allocated, gap).

    Mutually exclusive booleans. `unallocated` = nothing has been claimed by any
    warehouse yet; `partially_allocated` = some but not all of the shipped quantity is
    claimed, with `gap` carrying the remainder for the consumer's badge text.

    The gap is NOT computed here - the backend derives it against `quantity_shipped`
    (allocations are never decremented on receipt, so `remaining_incoming_quantity` is
    the wrong base) and ships only the gap, so the shipped total never reaches a
    consumer. A backend that predates the field simply omits it: allocations exist, so
    nothing is claimed rather than a partial guessed from the wrong number.
    """
    if not isinstance(row, dict):
        return False, False, None
    if not (row.get("warehouse_allocations") or []):
        # The empty allocation list is itself the signal; no number to show.
        return True, False, None
    gap = row.get("unallocated_quantity")
    try:
        gap = int(gap)
    except (TypeError, ValueError):
        return False, False, None
    return False, gap > 0, (gap if gap > 0 else None)


def _orders_list(rows: list[dict], b: _Builder) -> None:
    for o in rows:
        lines = o.get("lines") or []
        wh = o.get("warehouse")
        if not _filled(wh) and lines:
            w = lines[0].get("warehouse") or {}
            wh = w.get("warehouse_code")
        prods = ", ".join(
            f"{(l.get('product') or {}).get('product_code') or l.get('product_code')} ({_qty(l.get('quantity'))})"
            for l in lines
        )
        b.item(
            o.get("order_number"),
            [
                ("company_name", "Company", o.get("company_name")),
                ("Order Number", o.get("order_number")),
                ("Customer", o.get("debtor_name")),
                ("Order Date", o.get("order_date")),
                ("Actual Delivery Date", o.get("actual_delivery_date")),
                ("Status", o.get("order_status")),
                ("Pickup Time", o.get("pickup_time")),
                ("Transporter", o.get("transporter")),
                ("Driver", o.get("driver_name")),
                ("Lorry Plate", o.get("lorry_plate")),
                ("Warehouse", wh),
                ("Products", prods),
            ],
        )


def _orders_by_product(rows: list[dict], b: _Builder) -> None:
    for o in rows:
        prods = ", ".join(
            f"{m.get('product_code')} ({_qty(m.get('quantity'))})"
            + (f" @ {m.get('warehouse_code')}" if _filled(m.get("warehouse_code")) else "")
            for m in (o.get("matched_products") or [])
        )
        b.item(
            o.get("order_number"),
            [
                ("company_name", "Company", o.get("company_name")),
                ("Order Number", o.get("order_number")),
                ("Customer", o.get("debtor_name")),
                ("Order Date", o.get("order_date")),
                ("Actual Delivery Date", o.get("actual_delivery_date")),
                ("Products", prods),
            ],
        )


#: Clearance fields, in the order a person narrates a container's journey, paired
#: with the label to render. Every one is gated server-side per contact, so the key
#: is simply ABSENT when this caller may not see it - and `b.item` drops empty
#: pairs, so a denied field renders as nothing rather than as a blank row.
#:
#: These sit AFTER the identity pairs (company, product, shipment, container - what
#: the row IS) and BEFORE the quantity pairs. The journey is what a contact asks
#: about, so it leads; quantity and allocation close the row. Nothing is lost when a
#: field is denied: the key is absent and `b.item` skips it, so a contact entitled to
#: none of these reads identity straight into quantity, exactly as before.
#:
#: ETA is the exception that proves the rule - it IS gateable (an admin can revoke
#: it) but ships allowed, so it lives in this list rather than the identity block.
_CLEARANCE_PAIRS = (
    ("estimated_arrival_date", "ETA"),
    ("eta_delay_date", "ETA Delay"),
    ("inspection_date", "CIDB Inspection"),
    ("approval_date", "CIDB Approval"),
    ("gatepass_date", "Gatepass"),
    ("warehouse_arrival_date", "Warehouse Arrival"),
    ("informed_collection_date", "Collection Informed"),
    ("collection_date", "Collection"),
    ("loading_date", "Loading"),
    ("etc_date", "ETC"),
    ("etd_date", "ETD"),
    ("liner_code", "Liner"),
    ("china_forwarder", "China Forwarder"),
    ("malaysia_forwarder", "Malaysia Forwarder"),
    ("consignee", "Consignee"),
    ("delivery_warehouse", "Delivery Warehouse"),
    ("free_days_available", "Free Days Available"),
    ("loc", "Location"),
    ("stacked", "Stacked"),
    ("coa_permit_no", "COA Permit No."),
)


def _incoming_list(rows: list[dict], b: _Builder) -> None:
    for s in rows:
        for l in s.get("lines") or []:
            unallocated, partial, gap = _alloc_state(l)
            b.item(
                l.get("product_code"),
                [
                    ("company_name", "Company", s.get("company_name")),
                    ("product_code", "Product Code", l.get("product_code")),
                    (
                        "product_name",
                        "Product Name",
                        _distinct_name(l.get("product_code"), l.get("product_name")),
                    ),
                    ("shipment_number", "Shipment", s.get("shipment_number")),
                    ("shipping_container_number", "Container", s.get("shipping_container_number")),
                    *((key, label, s.get(key)) for key, label in _CLEARANCE_PAIRS),
                    (
                        "remaining_incoming_quantity",
                        "Incoming Quantity",
                        l.get("remaining_incoming_quantity"),
                    ),
                    (
                        "warehouse_allocations",
                        "Warehouse Allocations",
                        _wh_alloc(l.get("warehouse_allocations")),
                    ),
                    ("unallocated_quantity", "Unallocated Quantity", gap),
                ],
                unallocated=unallocated,
                partially_allocated=partial,
            )
        if s.get("attachment"):
            b.attach(s["attachment"])


def _incoming_by_product(rows: list[dict], b: _Builder) -> None:
    for p in rows:
        for s in p.get("shipments") or []:
            unallocated, partial, gap = _alloc_state(s)
            b.item(
                p.get("product_code"),
                [
                    ("company_name", "Company", p.get("company_name")),
                    ("product_code", "Product Code", p.get("product_code")),
                    (
                        "product_name",
                        "Product Name",
                        _distinct_name(p.get("product_code"), p.get("product_name")),
                    ),
                    (
                        "shipping_container_number",
                        "Shipment Container",
                        s.get("shipping_container_number"),
                    ),
                    (
                        "estimated_arrival_date",
                        "Estimated Arrival Date",
                        s.get("estimated_arrival_date"),
                    ),
                    ("batch_number", "Batch", s.get("batch_number")),
                    (
                        "remaining_incoming_quantity",
                        "Incoming Quantity",
                        s.get("remaining_incoming_quantity"),
                    ),
                    (
                        "warehouse_allocations",
                        "Warehouse Allocations",
                        _wh_alloc(s.get("warehouse_allocations")),
                    ),
                    ("unallocated_quantity", "Unallocated Quantity", gap),
                ],
                unallocated=unallocated,
                partially_allocated=partial,
            )
            if s.get("attachment"):
                b.attach(s["attachment"])


def _incoming_shipments(rows: list[dict], b: _Builder) -> None:
    for s in rows:
        b.item(
            s.get("shipment_number"),
            [
                ("company_name", "Company", s.get("company_name")),
                ("Shipment", s.get("shipment_number")),
                ("Container", s.get("shipping_container_number")),
                ("Estimated Arrival Date", s.get("estimated_arrival_date")),
                ("Total Incoming Quantity", s.get("total_remaining_incoming_quantity")),
                ("Distinct Products", s.get("distinct_products_incoming")),
            ],
        )
        if s.get("attachment"):
            b.attach(s["attachment"])


def _promo_filename(promo: dict) -> Any:
    for a in promo.get("attachments") or []:
        att = a.get("attachment") or a
        if att.get("original_filename") or att.get("stored_filename"):
            return att.get("original_filename") or att.get("stored_filename")
    return promo.get("description")


def _promotions(rows: list[dict], b: _Builder) -> None:
    # Header-only: one item per promotion + its PDF. SKU detail lives in the PDF,
    # so products are intentionally not enumerated.
    for promo in rows:
        name = _promo_filename(promo)
        b.item(
            name,
            [
                ("company_name", "Company", promo.get("company_name")),
                ("Promotion", name),
                ("Start Date", promo.get("start_date")),
                ("End Date", promo.get("end_date")),
            ],
            expired=promo.get("is_expired") is True,
        )
        for a in promo.get("attachments") or []:
            b.attach(a.get("attachment") or a)


def _promotion_products(rows: list[dict], b: _Builder) -> None:
    for pp in rows:
        prod = pp.get("product") or {}
        promo = pp.get("promotion") or {}
        b.item(
            prod.get("product_code"),
            [
                ("company_name", "Company", pp.get("company_name")),
                ("Product Code", prod.get("product_code")),
                ("Product Name", _distinct_name(prod.get("product_code"), prod.get("product_name"))),
                ("Promotion", promo.get("description")),
                ("Selling Price", _money(pp.get("selling_price"))),
                ("List Price", _money(prod.get("list_price"))),
                ("Dimensions", _dims(prod)),
            ],
            discontinued=prod.get("is_discontinued") is True,
            expired=pp.get("is_expired") is True,
        )
        for a in pp.get("promotion_attachments") or []:
            b.attach(a.get("attachment") or a)


def _products(rows: list[dict], b: _Builder) -> None:
    for p in rows:
        desc = p.get("description")
        b.item(
            p.get("product_code"),
            [
                ("company_name", "Company", p.get("company_name")),
                ("Product Code", p.get("product_code")),
                ("Product Name", _distinct_name(p.get("product_code"), p.get("product_name"))),
                ("Description", desc if _filled(desc) and desc != p.get("product_name") else None),
                # Always surface price + dimensions for the products list; when the
                # row has no value, render "Not defined" instead of dropping the line.
                ("List Price", _money(p.get("list_price")) or "Not defined"),
                ("Dimensions", _dims(p) or "Not defined"),
            ],
            discontinued=p.get("is_discontinued") is True,
        )
        for a in p.get("attachments") or []:
            b.attach(a)


def _product_attachments(rows: list[dict], b: _Builder) -> None:
    for r in rows:
        prod = r.get("product") or {}
        att = r.get("attachment") or {}
        # Cert-bearing rows carry a nested `certificate{}`; every other row has
        # no such key. Absent key = no Valid Until field and `expired` stays
        # false, so the 951 Technical Specifications and all Product Photos rows
        # render exactly as before.
        cert = r.get("certificate") or {}
        if not isinstance(cert, dict):
            cert = {}
        state = cert.get("validity_state")
        b.item(
            prod.get("product_code"),
            [
                ("company_name", "Company", r.get("company_name")),
                ("Product Code", prod.get("product_code")),
                ("Product Name", _distinct_name(prod.get("product_code"), prod.get("product_name"))),
                ("Description", prod.get("description")),
                ("Dimensions", _dims(prod)),
                ("Attachment Type", _att_type(att)),
                ("File Name", att.get("original_filename") or att.get("stored_filename")),
                ("Certificate Number", cert.get("certificate_number")),
                ("Valid Until", cert.get("valid_until")),
                # Says which of the three states this file is in, so the consumer
                # never has to compare Valid Until against today itself.
                ("Validity", _validity_label(state)),
            ],
            discontinued=prod.get("is_discontinued") is True,
            # Reuses the envelope's EXISTING flags.expired (same mechanism as
            # _promotions), so the n8n renderer needs no update to say "found
            # but expired" for a lapsed certificate.
            expired=cert.get("is_expired") is True,
            expiring_soon=state == "expiring_soon",
        )
        b.attach(att)


def _certificate_file(row: dict) -> dict | None:
    """The CURRENT revision's file for one certificate row, or None.

    Superseded revisions are never returned (MCP-8): only the revision the row
    points at is a candidate. Shapes accepted, in order - a nested
    `current_revision.attachment`, a top-level `attachment`, the `is_current`
    entry of an expanded `revisions[]`, and finally the signed-url pair the
    backend adds for `resolve_signed_urls=true`. Returns None when nothing
    usable is present so the caller emits an EMPTY attachments array rather than
    a null or broken url entry (MCP-11).
    """
    candidates: list[Any] = []
    current = row.get("current_revision")
    if isinstance(current, dict):
        candidates.append(current.get("attachment"))
    candidates.append(row.get("attachment"))
    for revision in row.get("revisions") or []:
        if isinstance(revision, dict) and revision.get("is_current") is True:
            candidates.append(revision.get("attachment"))
    for candidate in candidates:
        if isinstance(candidate, dict) and _filled(
            candidate.get("file_path") or candidate.get("url")
        ):
            return candidate

    url = row.get("download_url") or row.get("preview_url")
    if _filled(url):
        return {
            "url": url,
            "filename": row.get("attachment_filename")
            or row.get("original_filename")
            or row.get("stored_filename"),
            "mime_type": row.get("mime_type"),
            "attachment_type": row.get("attachment_type_name"),
        }
    return None


# The backend's derived validity codes, in the words a person reads. An
# unmapped code falls through de-slugged rather than being dropped - a state the
# envelope cannot name is still better than silence about validity.
_VALIDITY_LABELS = {
    "valid": "Valid",
    "expiring_soon": "Expiring soon",
    "expired": "Expired",
    "not_yet_valid": "Not yet valid",
    "unknown": "Unknown",
}


def _validity_label(state: Any) -> str | None:
    code = str(state or "").strip()
    if not code:
        return None
    known = _VALIDITY_LABELS.get(code)
    if known:
        return known
    words = code.replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else None


def _certificates(rows: list[dict], b: _Builder) -> None:
    for c in rows:
        number = c.get("certificate_number")
        scheme = c.get("scheme")
        title = " ".join(str(x) for x in (scheme, number) if _filled(x)) or number
        state = c.get("validity_state")
        b.item(
            title,
            [
                ("company_name", "Company", c.get("company_name")),
                ("Scheme", scheme),
                ("Certificate Number", number),
                ("Certifying Body", c.get("certifying_body")),
                ("Valid Until", c.get("valid_until")),
                # Humanized: the raw code (`expiring_soon`) leaked into rendered
                # WhatsApp/email output.
                ("Validity", _validity_label(state)),
                ("Covered Products", c.get("covered_product_count")),
            ],
            # Same flags the promotions presenter sets, so an expired certificate
            # is reported as found-but-expired rather than served as live.
            expired=c.get("is_expired") is True,
            expiring_soon=state == "expiring_soon",
        )
        current_file = _certificate_file(c)
        if current_file is not None:
            b.attach(current_file)


#: Every clearance field's CUSTOMER-facing label, keyed the way the envelope keys
#: its fields. Derived from `_CLEARANCE_PAIRS`, so it cannot drift from what a
#: present field renders as.
#:
#: Why it ships at all: an absent field carries no label to borrow, so a consumer
#: saying "not recorded yet" has only the key to name it with. Humanising works by
#: luck - `gatepass_date` -> "Gatepass" is right, `etd_date` -> "Etd" and
#: `eta_delay_date` -> "Eta delay" are not, and no heuristic fixes an acronym
#: without becoming this table. Harvesting the label off a sibling row that DOES
#: carry the field covers the mixed case, but not the case where no row has it.
#:
#: This is the customer register, deliberately: `FIELD_LABELS` backend-side says
#: "ETC (estimated time of container closing)" for an admin choosing grants, this
#: says "ETC" for a dealer reading a chat message.
_CLEARANCE_VOCABULARY = {key: label for key, label in _CLEARANCE_PAIRS}


def _annotate_field_access(envelope: dict[str, Any], tool_name: str) -> None:
    """Give a consumer the labels it needs to name a field it did not receive.

    Both additions are SIBLINGS of `items` and nothing renders them today, so an
    existing consumer is byte-identical. Putting the vocabulary inside
    `items[].fields` instead - by letting empty values through - would push ~20
    blank clearance rows into every incoming envelope, and any renderer that
    renders what it is given would read them out to a customer. That is the dump
    this whole design exists to prevent, arriving through the back door.

    `field_vocabulary` is TOP LEVEL, not inside `field_access`, because the case
    that needs it most has no denial at all: four containers, one carries
    `eta_delay_date` and three do not. Nothing was withheld, so there is no
    `field_access` block to hang it off, and the three rows still have to be
    named out loud.
    """
    fa = envelope.get("field_access")
    if isinstance(fa, dict):
        denied = fa.get("denied")
        if isinstance(denied, list):
            for d in denied:
                # `label` only where we actually know one - never a humanised
                # guess, which is what the consumer can already do for itself.
                if (
                    isinstance(d, dict)
                    and "label" not in d
                    and d.get("field") in _CLEARANCE_VOCABULARY
                ):
                    d["label"] = _CLEARANCE_VOCABULARY[d["field"]]
    if _RESULT_TYPE.get(tool_name) == "incoming_stock":
        envelope["field_vocabulary"] = dict(_CLEARANCE_VOCABULARY)


def _resource_attachments(rows: list[dict], b: _Builder) -> None:
    # No "Type" line - the attachment type (e.g. "Direct Access") is internal
    # plumbing, not meaningful to the end user. Just the file name + the file.
    for att in rows:
        name = att.get("original_filename") or att.get("stored_filename")
        # Upload date, because a document class that is RE-uploaded keeps its name:
        # six revisions of "Container Status 2026.xlsx" render as six identical
        # items, and the agent cannot say which one is current. Rows already
        # arrive newest-first, so the date turns that order into something the
        # agent can state out loud.
        uploaded = att.get("uploaded_at")
        day = str(uploaded)[:10] if _filled(uploaded) else None
        # No File ID. It was added here so a human debugging an answer could find
        # the row again among identically-named files - but `render` is the
        # CUSTOMER-facing view, and it went straight out to dealers on WhatsApp:
        # "File ID: 1e900020-dba5-4e34-ae1c-5e0f90380095" under every document,
        # on every resource-attachment answer, next to the file itself. The uuid
        # is still on the raw (non-render) response and in the CRM UI, which is
        # where someone debugging is looking anyway.
        # Company, because a contact who buys from both Mocha and Sorento gets a
        # current workbook from EACH, and each company names its sheet the same
        # thing. This render deliberately withholds the File ID (above), so the
        # company name is the only handle left to tell the two apart. Absent /
        # shared files (company_id NULL) render no line at all: `b.item` drops any
        # pair whose value is not `_filled`, so nothing empty reaches the reader.
        b.item(
            name,
            [
                ("original_filename", "File Name", name),
                ("company_name", "Company", att.get("company_name")),
                ("uploaded_at", "Uploaded", day),
            ],
        )
        # Strip the type so the delivered attachment carries no "Direct Access" label.
        no_type = {k: v for k, v in att.items() if k != "attachment_type"} if isinstance(att, dict) else att
        b.attach(no_type)


def _stock(rows: list[dict], b: _Builder) -> None:
    def _as_dict(v):
        return v if isinstance(v, dict) else {}

    def _as_str(v):
        return v if isinstance(v, str) and v.strip() else None

    for s in rows:
        # Row shape varies by backend vocab:
        #   • legacy: s["warehouse"] = {warehouse_code, warehouse_name, location}
        #   • Sage:   s["system_location"] = {system_location: <code>, warehouse: <wh name>}
        # Plus flat-key fallbacks. Resolve the location CODE (e.g. "BRW-BB") and the
        # actual WAREHOUSE name (e.g. "BUKIT RAJA") from whichever shape is present.
        prod = _as_dict(s.get("product"))
        wh = _as_dict(s.get("warehouse"))
        sl = _as_dict(s.get("system_location"))
        product_code = prod.get("product_code") or s.get("product_code")
        product_name = prod.get("product_name") or s.get("product_name")
        # System Location = the location code.
        sysloc = (
            sl.get("system_location")
            or wh.get("system_location")
            or wh.get("warehouse_code")
            or _as_str(s.get("system_location"))
            or s.get("warehouse_code")
        )
        # Warehouse = the actual warehouse name.
        wh_name = (
            sl.get("warehouse")
            or sl.get("system_location_description")
            or wh.get("warehouse")
            or wh.get("system_location_description")
            or wh.get("warehouse_name")
            or wh.get("location")
            or _as_str(s.get("warehouse"))
            # Flat-key fallback. Its sibling `system_location` is already handled
            # flat in the sysloc chain above; without this line a flat row renders
            # System Location but leaves Warehouse as "-".
            or _as_str(s.get("system_location_description"))
            or s.get("warehouse_name")
        )
        is_discontinued = (prod.get("is_discontinued") is True) or (s.get("is_discontinued") is True)
        qoh = s.get("quantity_on_hand") if s.get("quantity_on_hand") is not None else s.get("quantity")
        # Warehouse / System Location always render (even when absent) so every
        # stock row has the same shape - a row with no warehouse joined must not
        # silently drop the fields. "-" placeholder keeps the field present.
        b.item(
            product_code,
            [
                ("company_name", "Company", s.get("company_name")),
                ("product_code", "Product Code", product_code),
                ("product_name", "Product Name", _distinct_name(product_code, product_name)),
                ("warehouse", "Warehouse", wh_name if _filled(wh_name) else "-"),
                ("system_location", "System Location", sysloc if _filled(sysloc) else "-"),
                ("quantity_on_hand", "Quantity On Hand", qoh if qoh is not None else "-"),
            ],
            discontinued=is_discontinued,
        )


def _stock_int(v: Any) -> Any:
    """A quantity as a plain int. n8n prints `Total: ${value}` straight into the
    message, so a Decimal-shaped string ("500.0000") would be read out as-is."""
    if v is None:
        return v
    try:
        return int(Decimal(str(v)))
    except (InvalidOperation, TypeError, ValueError):
        return v


def _stock_compact(payload: dict, b: _Builder) -> None:
    """`compact`: one item per product, Total then the allowed locations.

    Location order is the backend's (already sorted by code). Re-sorting here
    would let the two answers disagree about the same stock.
    """
    for entry in payload.get("stock_summary") or []:
        if not isinstance(entry, dict):
            continue
        fields: list[dict[str, Any]] = [
            {"label": "Total", "value": _stock_int(entry.get("total_on_hand"))}
        ]
        for loc in entry.get("locations") or []:
            if not isinstance(loc, dict):
                continue
            # `warehouse_code` is what the backend declares. `system_location` is
            # the same value under the Sage vocabulary name, read in case a
            # sanitizer relabels the block on the way here.
            code = loc.get("warehouse_code") or loc.get("system_location")
            if not _filled(code):
                continue
            fields.append(
                {"label": str(code), "value": _stock_int(loc.get("quantity_on_hand"))}
            )
        # No `key` on these pairs: the label IS data (the location the contact is
        # allowed to see), not a CRM field name a consumer could match on.
        b.raw_item(entry.get("product_code"), fields, dict(entry.get("flags") or {}))


def _stock_availability(payload: dict, b: _Builder) -> None:
    """`availability`: yes / no / ask, and nothing else.

    `fields` stays empty on purpose. This mode exists so a dealer is never told a
    quantity, and an empty field list is the only shape that cannot carry one.
    """
    for entry in payload.get("stock_availability") or []:
        if not isinstance(entry, dict):
            continue
        b.raw_item(
            entry.get("product_code"),
            [],
            {
                "needs_quantity": bool(entry.get("needs_quantity")),
                "available": entry.get("available"),
            },
        )


def _availability_intro(payload: dict) -> str:
    """The whole reply, in one line.

    Several products can disagree. Any product still missing its quantity makes
    the turn a question, not an answer - so ask, and say nothing about the rest.
    Otherwise a shared yes or no speaks for all of them; a split verdict cannot,
    so the intro steps back and the per-item flags carry it.
    """
    entries = [
        e for e in (payload.get("stock_availability") or []) if isinstance(e, dict)
    ]
    if any(e.get("needs_quantity") for e in entries):
        return _AVAILABILITY_ASK
    verdicts = {e.get("available") for e in entries}
    if verdicts == {True}:
        return _AVAILABILITY_YES
    if verdicts == {False}:
        return _AVAILABILITY_NO
    return _AVAILABILITY_MIXED


def _forms(rows: list[dict], b: _Builder) -> None:
    for f in rows:
        b.item(f.get("name"), [("Form Name", f.get("name"))])
        # Narrowed form lookups carry the attachment so the form file can be sent.
        if f.get("attachment"):
            b.attach(f["attachment"])


def _portal_link(payload: dict, b: _Builder) -> None:
    url = payload.get("portal_link") or payload.get("url")
    if not _filled(url) and isinstance(payload.get("data"), dict):
        url = payload["data"].get("portal_link") or payload["data"].get("url")
    b.link(payload.get("label") or "Portal Link", url)


def _generic(rows: list[dict], b: _Builder) -> None:
    for r in rows:
        if not isinstance(r, dict):
            continue
        b.item(
            None,
            [(k, v) for k, v in r.items() if v is not None and not isinstance(v, (dict, list))],
        )
        if r.get("attachment"):
            b.attach(r["attachment"])
        for a in r.get("attachments") or []:
            b.attach(a.get("attachment") or a if isinstance(a, dict) else a)


_BUILDERS = {
    "crm_order_management_orders_list": _orders_list,
    "crm_order_management_orders_by_product_list": _orders_by_product,
    "crm_incoming_stock_list": _incoming_list,
    "crm_incoming_stock_by_product": _incoming_by_product,
    "crm_incoming_stock_shipments": _incoming_shipments,
    "crm_marketing_promotions_list": _promotions,
    "crm_marketing_promotion_products_list": _promotion_products,
    "crm_master_products_list": _products,
    "crm_master_product_attachments_list": _product_attachments,
    "crm_certificates_list": _certificates,
    "crm_resource_attachments_list": _resource_attachments,
    "crm_inventory_stock_balance_list": _stock,
    "crm_forms_management_forms_list": _forms,
}


# --------------------------------------------------------------------------
# last_updated_at walk
# --------------------------------------------------------------------------
def _latest_updated(node: Any, depth: int = 0) -> str | None:
    best: str | None = None
    if depth > 6 or not isinstance(node, (dict, list)):
        return best
    if isinstance(node, dict):
        # `uploaded_at` counts: an attachment is never edited in place, so the
        # upload IS its last-updated moment. Without it every document answer
        # reported `last_updated_at: null` and the agent could not say how fresh
        # the file it just handed over actually is.
        for key in ("updated_at", "last_updated_at", "uploaded_at"):
            v = node.get(key)
            if _filled(v) and (best is None or str(v) > best):
                best = str(v)
        children = node.values()
    else:
        children = node
    for child in children:
        sub = _latest_updated(child, depth + 1)
        if sub and (best is None or sub > best):
            best = sub
    return best


def _company_names(lookup_companies: Any) -> str | None:
    """Join the backend's `lookup_companies` names: Mocha or Sorento; A, B or C.

    Order is the backend's (already sorted by name); this only joins.

    Returns None unless EVERY entry has a name. Naming only the companies we
    happen to have a name for would turn "I checked your two companies" into a
    confident, wrong "I checked Sorento" - so an entry with a missing name
    drops the whole clause and the reply falls back to the plain intro.
    """
    if not isinstance(lookup_companies, list) or not lookup_companies:
        return None
    if not all(
        isinstance(c, dict) and _filled(c.get("name")) for c in lookup_companies
    ):
        return None
    names = [str(c.get("name")).strip() for c in lookup_companies]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " or " + names[-1]


def _stock_mode(tool_name: str, data: dict[str, Any]) -> str:
    """Which stock-visibility policy shaped this response.

    Anything other than the two summary modes (including a response with no
    policy block at all, i.e. every caller that is not a contact) is `detailed`,
    which is the envelope this tool has always produced.
    """
    if tool_name != _STOCK_TOOL:
        return "detailed"
    block = data.get("stock_visibility")
    mode = block.get("mode") if isinstance(block, dict) else None
    return mode if mode in _STOCK_MODE_RESULT_TYPE else "detailed"


# --------------------------------------------------------------------------
# dispatcher
# --------------------------------------------------------------------------
def present_response(tool_name: str, raw: str) -> str:
    """Transform a sanitized tool JSON string into the render envelope JSON string.

    Falls back to returning `raw` unchanged on any parse error or unknown shape, so
    enabling `view=render` can never harden into a hard failure for the caller.
    """
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if not isinstance(data, dict):
        return raw

    rows = data.get("data")
    if not isinstance(rows, list):
        rows = [] if rows is None else ([rows] if isinstance(rows, dict) else [])

    b = _Builder()
    stock_mode = _stock_mode(tool_name, data)
    if tool_name == "crm_portal_link_get":
        _portal_link(data, b)
    elif stock_mode == "compact":
        _stock_compact(data, b)
    elif stock_mode == "availability":
        _stock_availability(data, b)
    else:
        builder = _BUILDERS.get(tool_name, _generic)
        builder(rows, b)

    # de-dupe attachments by (url, filename). The `url` is the DB `file_path` and is
    # the ONLY resolvable object key - return it verbatim. Do NOT rewrite its last
    # segment from `filename` (the editable `stored_filename`): the stored/display
    # name often differs from the real key (parens/spaces sanitized at upload), so
    # patching it in produced URLs that 404 (e.g. a promotion whose stored_filename
    # kept "(CABANA) … END USER.pdf" while the object key is "CABANA … END USER.pdf").
    seen: set[tuple[Any, Any]] = set()
    attachments: list[dict[str, Any]] = []
    for a in b.attachments:
        sig = (a["url"], a.get("filename"))
        if sig in seen:
            continue
        seen.add(sig)
        attachments.append(a)

    has_result = bool(b.items or attachments or b.action_links)
    if attachments:
        intro = "I have attached the file(s) below."
    elif not has_result:
        # An empty answer over more than one company has to name the companies it
        # searched, or the reader cannot tell "not stocked anywhere" from "I only
        # looked at one of your two companies".
        searched = _company_names(data.get("lookup_companies"))
        intro = (
            f"No matching results found for {searched}."
            if searched
            else "No matching results found."
        )
    elif stock_mode == "compact":
        intro = _STOCK_COMPACT_INTRO
    elif stock_mode == "availability":
        intro = _availability_intro(data)
    else:
        intro = _DEFAULT_INTRO.get(tool_name, "Here are the results I found.")

    envelope: dict[str, Any] = {
        "result_type": _STOCK_MODE_RESULT_TYPE.get(stock_mode)
        or _RESULT_TYPE.get(tool_name, "result"),
        "intro": intro,
        "items": b.items,
        "attachments": attachments,
        "action_links": b.action_links,
        "last_updated_at": _latest_updated(data),
        "has_result": has_result,
    }
    for k in _PASSTHROUGH_KEYS:
        if k in data and _filled(data.get(k)):
            envelope[k] = data[k]
    _annotate_field_access(envelope, tool_name)
    return json.dumps(envelope)
