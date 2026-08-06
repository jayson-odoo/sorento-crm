"""Render-envelope presenters for the consolidated MCP list tools.

When a tool is called with `view=render`, its (already sanitized) data response is
transformed into ONE uniform envelope so the n8n / messaging consumer needs only a
generic renderer instead of per-tool field-mapping code:

    {
      "result_type": "orders",
      "intro": "Here are the orders I found.",
      "items": [
        {"title": "...", "fields": [{"label": "...", "value": "..."}],
         "flags": {"discontinued": false, "expired": false,
                   "unallocated": false, "partially_allocated": false}}
      ],
      "attachments": [{"url","filename","mimeType","attachmentType"}],
      "action_links": [{"label","url","type"}],
      "last_updated_at": "...",
      "has_result": true
    }

The envelope is intentionally MARKDOWN-FREE — `fields` carry label/value pairs only.
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

# Passthrough keys preserved from the raw response into the envelope (e.g. the
# escalation hint attached after sanitize). Kept so render mode loses nothing.
_PASSTHROUGH_KEYS = (
    "suggested_escalation",
    "escalate_team",
    "escalated_agent",
    "fallback_used",
    "alternatives",
    "relaxed_axis",
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
    """Render a quantity compactly — drop a meaningless fractional part.

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
        pairs: list[tuple[str, Any]],
        *,
        discontinued=False,
        expired=False,
        unallocated=False,
        partially_allocated=False,
    ) -> None:
        fields = [{"label": lbl, "value": val} for lbl, val in pairs if _filled(val)]
        if not fields:
            return
        self.items.append(
            {
                "title": title if _filled(title) else None,
                "fields": fields,
                "flags": {
                    "discontinued": bool(discontinued),
                    "expired": bool(expired),
                    "unallocated": bool(unallocated),
                    "partially_allocated": bool(partially_allocated),
                },
            }
        )

    def attach(self, a: Any) -> None:
        if not isinstance(a, dict):
            return
        url = a.get("file_path") or a.get("url")
        if not _filled(url):
            return
        self.attachments.append(
            {
                "url": url,
                "filename": a.get("stored_filename") or a.get("filename") or a.get("original_filename"),
                "mimeType": a.get("mime_type") or a.get("mimeType"),
                "attachmentType": _att_type(a),
            }
        )

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

    The gap is NOT computed here — the backend derives it against `quantity_shipped`
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
                ("Order Number", o.get("order_number")),
                ("Customer", o.get("debtor_name")),
                ("Order Date", o.get("order_date")),
                ("Actual Delivery Date", o.get("actual_delivery_date")),
                ("Products", prods),
            ],
        )


def _incoming_list(rows: list[dict], b: _Builder) -> None:
    for s in rows:
        for l in s.get("lines") or []:
            unallocated, partial, gap = _alloc_state(l)
            b.item(
                l.get("product_code"),
                [
                    ("Product Code", l.get("product_code")),
                    ("Product Name", _distinct_name(l.get("product_code"), l.get("product_name"))),
                    ("Shipment", s.get("shipment_number")),
                    ("Container", s.get("shipping_container_number")),
                    ("Estimated Arrival Date", s.get("estimated_arrival_date")),
                    ("Batch", l.get("batch_number")),
                    ("Incoming Quantity", l.get("remaining_incoming_quantity")),
                    ("Warehouse Allocations", _wh_alloc(l.get("warehouse_allocations"))),
                    ("Unallocated Quantity", gap),
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
                    ("Product Code", p.get("product_code")),
                    ("Product Name", _distinct_name(p.get("product_code"), p.get("product_name"))),
                    ("Shipment Container", s.get("shipping_container_number")),
                    ("Estimated Arrival Date", s.get("estimated_arrival_date")),
                    ("Batch", s.get("batch_number")),
                    ("Incoming Quantity", s.get("remaining_incoming_quantity")),
                    ("Warehouse Allocations", _wh_alloc(s.get("warehouse_allocations"))),
                    ("Unallocated Quantity", gap),
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
        b.item(
            prod.get("product_code"),
            [
                ("Product Code", prod.get("product_code")),
                ("Product Name", _distinct_name(prod.get("product_code"), prod.get("product_name"))),
                ("Description", prod.get("description")),
                ("Dimensions", _dims(prod)),
                ("Attachment Type", _att_type(att)),
                ("File Name", att.get("original_filename") or att.get("stored_filename")),
                ("Valid Until", cert.get("valid_until")),
            ],
            discontinued=prod.get("is_discontinued") is True,
            # Reuses the envelope's EXISTING flags.expired (same mechanism as
            # _promotions), so the n8n renderer needs no update to say "found
            # but expired" for a lapsed certificate.
            expired=cert.get("is_expired") is True,
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


def _certificates(rows: list[dict], b: _Builder) -> None:
    for c in rows:
        number = c.get("certificate_number")
        scheme = c.get("scheme")
        title = " ".join(str(x) for x in (scheme, number) if _filled(x)) or number
        b.item(
            title,
            [
                ("Scheme", scheme),
                ("Certificate Number", number),
                ("Certifying Body", c.get("certifying_body")),
                ("Valid Until", c.get("valid_until")),
                ("Validity", c.get("validity_state")),
                ("Covered Products", c.get("covered_product_count")),
            ],
            # Same flag the promotions presenter sets, so an expired certificate
            # is reported as found-but-expired rather than served as live.
            expired=c.get("is_expired") is True,
        )
        current_file = _certificate_file(c)
        if current_file is not None:
            b.attach(current_file)


def _resource_attachments(rows: list[dict], b: _Builder) -> None:
    # No "Type" line — the attachment type (e.g. "Direct Access") is internal
    # plumbing, not meaningful to the end user. Just the file name + the file.
    for att in rows:
        name = att.get("original_filename") or att.get("stored_filename")
        b.item(name, [("File Name", name)])
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
            # System Location but leaves Warehouse as "—".
            or _as_str(s.get("system_location_description"))
            or s.get("warehouse_name")
        )
        is_discontinued = (prod.get("is_discontinued") is True) or (s.get("is_discontinued") is True)
        qoh = s.get("quantity_on_hand") if s.get("quantity_on_hand") is not None else s.get("quantity")
        # Warehouse / System Location always render (even when absent) so every
        # stock row has the same shape — a row with no warehouse joined must not
        # silently drop the fields. "—" placeholder keeps the field present.
        b.item(
            product_code,
            [
                ("Product Code", product_code),
                ("Product Name", _distinct_name(product_code, product_name)),
                ("Warehouse", wh_name if _filled(wh_name) else "—"),
                ("System Location", sysloc if _filled(sysloc) else "—"),
                ("Quantity On Hand", qoh if qoh is not None else "—"),
            ],
            discontinued=is_discontinued,
        )


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
        for key in ("updated_at", "last_updated_at"):
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
    if tool_name == "crm_portal_link_get":
        _portal_link(data, b)
    else:
        builder = _BUILDERS.get(tool_name, _generic)
        builder(rows, b)

    # de-dupe attachments by (url, filename). The `url` is the DB `file_path` and is
    # the ONLY resolvable object key — return it verbatim. Do NOT rewrite its last
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
        intro = "No matching results found."
    else:
        intro = _DEFAULT_INTRO.get(tool_name, "Here are the results I found.")

    envelope: dict[str, Any] = {
        "result_type": _RESULT_TYPE.get(tool_name, "result"),
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
    return json.dumps(envelope)
