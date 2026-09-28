"""The ETA a contact may be told, and whether the packing list may go with it (#1328).

One resolver for every route that prints a shipment ETA to a chat contact: the stock
ask (`StockService._apply_stock_visibility`) and the three incoming routes
(`/incoming-stock/list`, `/by-product`, `/shipments`). Before this, the stock ask
padded the ETA with the product-or-category `chatbot_eta_offset_days` and the incoming
routes printed the exact date, so one shipment had two answers.

**The switch** is per contact: `respond_contacts.chatbot_eta_offset_applied`, beside
`notify_salesman` / `packing_list_allowed` and edited on the same Access > Chatbot card.
ON (the default, and the stock ask's behaviour before the switch existed) = the shipment
ETA plus the offset; OFF = the exact date.

**The offset** is `stock_ask_limits.effective`'s rule, unchanged: the product's own value,
else its own category's, else 0.

**No contact in play** (a staff session, the raw API key) = the exact date and the
attachment as today: these rules govern what a CONTACT is told. A contact that names
nobody we can find is told the padded date and gets no packing list - the default a
contact row would carry, and never an earlier promise than the one they would get.

**A shipment row names several products.** The incoming list is shipment-rooted, so its
ETA is one date for every line on it. It is padded by the LARGEST offset among the row's
own products: asked about one product, the lines are that product's alone and the date is
the stock ask's date exactly; asked about a supplier or a date window, the contact is never
promised the container sooner than any product on it would be.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.services.stock_ask_limits import NULL_LIMITS, effective as effective_limits

#: The date keys an incoming payload carries that ARE the shipment's arrival promise.
#: `eta_delay_date` is the revised ETA, so it is padded the same way; every other
#: checkpoint (gatepass, warehouse arrival, collection ...) is a recorded event, not a
#: promise, and prints as recorded.
ETA_KEYS: tuple[str, ...] = (
    "estimated_arrival_date",
    "eta_delay_date",
    "nearest_estimated_arrival_date",
)


@dataclass(frozen=True)
class ContactEtaRules:
    """What one contact's chat answers may carry about a shipment."""

    #: Pad the ETA with the product-or-category offset.
    offset_applied: bool
    #: Attach the shipment's packing list.
    packing_list_allowed: bool


#: An unresolved contact: the switch's own default for the ETA, and no file.
UNRESOLVED = ContactEtaRules(offset_applied=True, packing_list_allowed=False)


def rules_for_contact(db: Session, resolved_contact_id: Optional[str]) -> ContactEtaRules:
    """The contact's two switches, read once. Takes the INTERNAL `respond_contacts.id`."""
    if not resolved_contact_id:
        return UNRESOLVED
    from app.models.access import RespondContact

    row = (
        db.query(RespondContact.chatbot_eta_offset_applied, RespondContact.packing_list_allowed)
        .filter(RespondContact.id == str(resolved_contact_id))
        .first()
    )
    if row is None:
        return UNRESOLVED
    return ContactEtaRules(
        # NOT NULL default true; `is not False` keeps the default if it ever read NULL.
        offset_applied=row[0] is not False,
        # NOT NULL default false; `is True` keeps the fail-closed reading.
        packing_list_allowed=row[1] is True,
    )


def offset_days(product: Any, category: Any) -> int:
    """The product's `chatbot_eta_offset_days`, else its own category's, else 0."""
    return effective_limits(product, category)[1]


def visible_eta(eta: Optional[date], offset: int, rules: ContactEtaRules) -> Optional[date]:
    """The ETA this contact may be told: `eta + offset` when their switch is on, else `eta`."""
    if eta is None or not rules.offset_applied or not offset:
        return eta
    return eta + timedelta(days=offset)


# --------------------------------------------------------------- incoming payloads


def _offsets_by_product_code(db: Session, codes: Iterable[str]) -> dict[str, int]:
    """`{lower(product_code): offset}`. A code carried by two companies' products takes the
    larger of their offsets - the same rule a multi-product row follows."""
    from sqlalchemy import func

    from app.models.product import Product, ProductCategory

    wanted = {c.strip().lower() for c in codes if isinstance(c, str) and c.strip()}
    if not wanted:
        return {}
    rows = (
        db.query(Product, ProductCategory)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(func.lower(Product.product_code).in_(wanted))
        .all()
    )
    out: dict[str, int] = {}
    for product, category in rows:
        y = offset_days(product, category if category is not None else NULL_LIMITS)
        key = product.product_code.strip().lower()
        out[key] = max(out.get(key, 0), y)
    return out


def _offsets_by_shipment_number(db: Session, numbers: Iterable[str]) -> dict[str, int]:
    """`{shipment_number: offset}` over each shipment's own product lines, for the
    `/shipments` row that names no product at all."""
    from app.models.procurement import InboundShipment, InboundShipmentLine
    from app.models.product import Product

    wanted = {n for n in numbers if isinstance(n, str) and n}
    if not wanted:
        return {}
    pairs = (
        db.query(InboundShipment.shipment_number, Product.product_code)
        .join(InboundShipmentLine, InboundShipmentLine.shipment_id == InboundShipment.id)
        .join(Product, Product.id == InboundShipmentLine.product_id)
        .filter(InboundShipment.shipment_number.in_(wanted))
        .distinct()
        .all()
    )
    by_code = _offsets_by_product_code(db, {code for _, code in pairs if code})
    out: dict[str, int] = {}
    for number, code in pairs:
        y = by_code.get((code or "").strip().lower(), 0)
        out[number] = max(out.get(number, 0), y)
    return out


def _codes_of(row: dict[str, Any]) -> list[str]:
    if isinstance(row.get("lines"), list):
        return [line.get("product_code") for line in row["lines"] if isinstance(line, dict)]
    if row.get("product_code"):
        return [row["product_code"]]
    return []


def _pad(node: dict[str, Any], offset: int, rules: ContactEtaRules) -> None:
    for key in ETA_KEYS:
        value = node.get(key)
        if isinstance(value, date):
            node[key] = visible_eta(value, offset, rules)


def apply_to_incoming(
    db: Session,
    payload: Any,
    *,
    contact_id: Optional[str],
    space_id: Optional[str] = None,
) -> Any:
    """Apply the contact's ETA offset and packing-list rule to an incoming payload.

    Handles the three incoming shapes: `/list` (shipment rows with `lines`),
    `/by-product` (product rows with `shipments`) and `/shipments` (bare shipment rows).
    Runs BEFORE `field_access.apply_field_access`; the two are independent.
    """
    if not contact_id or not isinstance(payload, dict):
        return payload
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        return payload

    from app.services.field_access import resolve_contact_id

    rules = rules_for_contact(db, resolve_contact_id(db, contact_id, space_id))

    by_code: dict[str, int] = {}
    by_shipment: dict[str, int] = {}
    if rules.offset_applied:
        by_code = _offsets_by_product_code(
            db, [c for row in rows if isinstance(row, dict) for c in _codes_of(row)]
        )
        bare = [
            row.get("shipment_number")
            for row in rows
            if isinstance(row, dict) and not _codes_of(row) and "shipments" not in row
        ]
        by_shipment = _offsets_by_shipment_number(db, bare)

    for row in rows:
        if not isinstance(row, dict):
            continue
        codes = _codes_of(row)
        if codes:
            offset = max((by_code.get((c or "").strip().lower(), 0) for c in codes), default=0)
        else:
            offset = by_shipment.get(row.get("shipment_number"), 0)
        _pad(row, offset, rules)
        if not rules.packing_list_allowed:
            row.pop("attachment", None)
        for shipment in row.get("shipments") or []:
            if not isinstance(shipment, dict):
                continue
            _pad(shipment, offset, rules)
            if not rules.packing_list_allowed:
                shipment.pop("attachment", None)
    return payload
