"""What a price tag is ABOUT: the product behind a bound layer, resolved live.

The canvas edits shapes. This module is where those shapes learn what they are
showing - the code, the name, the dimensions, the spec lines, the photos and the
two prices - so a tag can be designed against the real catalogue rather than
against placeholder text.

Everything here is a READ, resolved at the moment it is asked for. Nothing it
returns is ever written into a saved document (ADR 0008): the document holds a
binding and any text a designer typed over it, and this module answers the
binding again on every open, every preview and every render. That is what makes
a promotion ending overnight change the PDF rather than leave a stale price on a
tag somebody prints next week.

Three rules it does not get to decide for itself:

* **Prices come from ``resolve_prices``.** The promotion window, the audience
  gate and "is this offer worth showing" all live there, and a second copy of
  them beside the tag code would be a second commercial answer.
* **Photos come from ``product_images``.** Trade imagery is tagged ``dealer``,
  and the tag designer is the same gate as the catalogue tile.
* **Set prices come from ``resolve_set_price``.** Ticking members IS the
  formula, and the price on a furniture set tag has to agree with the price on
  the set's own detail page.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.product import Product
from app.models.product_set import ProductSet, ProductSetMember
from app.services.dealer_kit.pricing import resolve_prices
from app.services.dealer_kit.product_images import gallery_images
from app.services.dealer_kit.viewer import ViewerContext

logger = logging.getLogger(__name__)

# The editor and the tag sheet designer are STAFF surfaces: marketing is
# designing a tag they are about to send to a printer, so they see the offer the
# tag will print. `is_internal_copy` is what says "this render is the brochure's
# own copy", which is exactly what a proof is.
STAFF_VIEWER = ViewerContext(
    is_staff=True,
    access_codes=frozenset(),
    show_invoice_price=False,
    is_internal_copy=True,
)


def staff_viewer() -> ViewerContext:
    """The viewer a CRM-side tag surface resolves prices and photos for."""
    return STAFF_VIEWER


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_dimensions_mm(length, width, height) -> Optional[str]:
    """``800 x 500 x 220 mm``, or nothing when no dimension is recorded.

    One rule, shared with the catalogue tile (``collection_service._dimensions``
    delegates here). Two formatters would eventually print a tag and its tile
    with different punctuation for the same product.

    A missing single dimension prints as ``-`` rather than collapsing the
    string: "800 x - x 220" says which measurement is missing, "800 x 220" is a
    lie about which is which.

    Trailing zeros go. ``dimensions_length`` is ``NUMERIC(10,2)``, so a row read
    back from the database is ``Decimal("800.00")`` and Decimal's ``g`` format
    keeps the scale it was stored at - which printed "800.00 x 500.00 x 220.00
    mm" on a tag whose flyer says "800 x 500 x 220 mm". ``normalize()`` drops the
    stored scale without touching a genuine fraction, so 12.50 still prints as
    12.5.

    ``Decimal(str(part))``, never ``Decimal(part)``: a measurement that comes
    from the reviewed spec row arrives as a JSON number, which is a Python
    FLOAT, and ``Decimal(407.3)`` is 407.2999999999999886313162278383970260620
    exactly. Printed, that is 28 digits of binary noise on a physical tag, and
    the spec branch wins over the master columns so it is the branch a real
    product with a fractional measurement takes. Going through ``str`` keeps the
    number that was measured.
    """
    parts = [length, width, height]
    if not any(part is not None for part in parts):
        return None
    return (
        " x ".join(
            "-" if part is None else f"{Decimal(str(part)).normalize():f}"
            for part in parts
        )
        + " mm"
    )


def _clean_lines(values: Iterable) -> list[str]:
    """Non-empty, stripped lines. Blank entries are noise on a printed tag."""
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text:
            out.append(text)
    return out


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_products(
    db: Session, query: Optional[str], limit: int = 20
) -> list[Product]:
    """Products for the editor's picker, searched on the server.

    The same shape as the master-data product select (code or name, active only,
    ordered by code) rather than a new index: 22,000 products is far past what a
    client-side filter can see, and a picker that silently hides most of the
    catalogue is worse than a slow one.
    """
    statement = db.query(Product).filter(Product.is_active.is_(True))

    if query and query.strip():
        needle = f"%{query.strip()}%"
        statement = statement.filter(
            or_(
                Product.product_code.ilike(needle),
                Product.product_name.ilike(needle),
            )
        )

    return statement.order_by(Product.product_code).limit(limit).all()


def search_product_sets(
    db: Session, query: Optional[str], limit: int = 20
) -> list[ProductSet]:
    """Product sets for the editor's picker."""
    statement = db.query(ProductSet).filter(ProductSet.is_active.is_(True))

    if query and query.strip():
        needle = f"%{query.strip()}%"
        statement = statement.filter(
            or_(
                ProductSet.set_code.ilike(needle),
                ProductSet.name.ilike(needle),
            )
        )

    return statement.order_by(ProductSet.set_code).limit(limit).all()


def get_product(db: Session, product_id: str) -> Optional[Product]:
    return db.query(Product).filter(Product.id == product_id).first()


def get_product_set(db: Session, set_id: str) -> Optional[ProductSet]:
    return (
        db.query(ProductSet)
        .options(joinedload(ProductSet.members).joinedload(ProductSetMember.product))
        .filter(ProductSet.id == set_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Spec lines and dimensions
# ---------------------------------------------------------------------------

# The registry's keys for the three printed measurements.
_SPEC_DIMENSION_KEYS = ("dim_length", "dim_width", "dim_height")


def _spec_row(db: Session, product: Product):
    from app.models.product_spec import ProductSpecifications

    return (
        db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id == product.id)
        .first()
    )


def _flyer_lines(db: Session, product: Product) -> list[str]:
    from app.models.product_spec import ProductFlyerText

    row = (
        db.query(ProductFlyerText)
        .filter(ProductFlyerText.product_code == product.product_code)
        .first()
    )
    if row is None:
        return []
    lines = row.lines if isinstance(row.lines, list) else []
    return _clean_lines(lines)


def spec_lines(db: Session, product: Product, spec_row=None) -> list[str]:
    """What the tag prints under the product name.

    Three sources in order of authority (D27): the derived spec sentence, then
    the printed flyer's own lines, then the product description. The description
    is a real fallback rather than a placeholder - most of the catalogue has no
    derived specs, and a tag with nothing under the name is a tag marketing has
    to type by hand.
    """
    row = spec_row if spec_row is not None else _spec_row(db, product)
    if row is not None and (row.rendered_text or "").strip():
        return _clean_lines(row.rendered_text.splitlines())

    flyer = _flyer_lines(db, product)
    if flyer:
        return flyer

    return _clean_lines((product.description or "").splitlines())


def _spec_display_value(raw) -> str:
    """One reviewed spec value, as a person reads it.

    `True` prints as `Yes` because a tag that said `True` under "Overflow"
    would be reading a database out loud. A whole number prints without the
    `.0` JSON gives a float, for the same reason `format_dimensions_mm`
    normalises a Decimal: the flyer says `407 mm`, never `407.0 mm`.
    """
    if isinstance(raw, bool):
        return "Yes" if raw else "No"
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw)


def product_specs(db: Session, product: Product, spec_row=None) -> list[dict]:
    """The product's reviewed specs, key by key, for `{{spec.<key>}}` (D58).

    `spec_lines` has always carried the rendered spec SENTENCE, which is one
    block of text: a tag could print all of it or none of it. A merge field
    asks for one value, so this joins the two halves that answer that - the
    registry, which says which keys exist and what each is called, and the
    product's reviewed row, which says which of them this product carries.

    Only keys the product actually has are returned, so a token naming
    anything else resolves to nothing rather than to an empty labelled row.
    The unit comes from the REGISTRY rather than from the stored value: the
    registry is what the master-data screen edits, and a row written before a
    unit was set would otherwise print without one forever.
    """
    from app.services.product_spec_registry import active_registry

    row = spec_row if spec_row is not None else _spec_row(db, product)
    values = row.values if row is not None and isinstance(row.values, dict) else {}
    if not values:
        return []

    specs: list[dict] = []
    for key in active_registry(db):
        if key.spec_key not in values:
            continue
        stored = values[key.spec_key]
        # A value is stored bare or wrapped as {"value": ...}; `dimensions_text`
        # already reads both, and the catalogue holds both shapes.
        raw = stored.get("value") if isinstance(stored, dict) else stored
        if raw is None:
            continue
        specs.append(
            {
                "key": key.spec_key,
                "label": key.label,
                "value": _spec_display_value(raw),
                "unit": key.unit,
            }
        )
    return specs


def dimensions_text(product: Product, spec_row=None) -> str:
    """Dimensions from the reviewed spec values, else from the product master.

    The spec values win because they are what somebody checked against the
    printed flyer; the master columns are an import and are wrong often enough
    that the flyer-reading slice exists to correct them.
    """
    if spec_row is not None and isinstance(spec_row.values, dict):
        measured = [
            (spec_row.values.get(key) or {}).get("value")
            if isinstance(spec_row.values.get(key), dict)
            else spec_row.values.get(key)
            for key in _SPEC_DIMENSION_KEYS
        ]
        if any(value is not None for value in measured):
            return format_dimensions_mm(*measured) or ""

    return (
        format_dimensions_mm(
            product.dimensions_length,
            product.dimensions_width,
            product.dimensions_height,
        )
        or ""
    )


# ---------------------------------------------------------------------------
# Tag data
# ---------------------------------------------------------------------------


def product_tag_data(
    db: Session,
    product: Product,
    viewer: ViewerContext,
    promotion_id: Optional[str] = None,
    *,
    with_images: bool = True,
) -> dict:
    """Everything a product block draws, for THIS viewer, right now."""
    spec_row = _spec_row(db, product)
    prices = resolve_prices(db, [product], viewer, promotion_id).get(product.id)

    return {
        "id": product.id,
        "code": product.product_code or "",
        "name": product.product_name or "",
        "dimensions": dimensions_text(product, spec_row),
        "spec_lines": spec_lines(db, product, spec_row),
        # Key by key, beside the rendered sentence: `{{spec.material}}` asks a
        # question `spec_lines` cannot answer (D58).
        "specs": product_specs(db, product, spec_row),
        "images": gallery_images(db, product, viewer) if with_images else [],
        "list_price": prices.list_price if prices else None,
        "offer_price": prices.offer_price if prices else None,
        "promotion_id": prices.promotion_id if prices else None,
        # PLAN D14 (price-tag-feedback-r2): CRM-owned, manual entry or a
        # non-empty AutoCount sync. Null renders an editor placeholder and
        # nothing on print (S7).
        "barcode": product.barcode or None,
    }


def _member_products(product_set: ProductSet) -> list[ProductSetMember]:
    return sorted(
        list(product_set.members or []), key=lambda m: (m.sort_order or 0, m.id)
    )


def product_set_tag_data(
    db: Session,
    product_set: ProductSet,
    viewer: ViewerContext,
    promotion_id: Optional[str] = None,
) -> dict:
    """The set's members, and what the set costs.

    The list price is the set's OWN rule (``resolve_set_price``): the ticked
    members, times their quantities, or the override somebody typed. The offer
    is the same sum with each ticked member at its promotional price where one
    applies - and absent entirely when no member is on offer, so a set with
    nothing promoted prints a plain list price rather than a discount of zero.
    """
    from app.services.product_set_service import resolve_set_price

    members = _member_products(product_set)
    member_products = [m.product for m in members if m.product is not None]

    prices = (
        resolve_prices(db, member_products, viewer, promotion_id)
        if member_products
        else {}
    )

    set_price = resolve_set_price(product_set)

    offer_total = Decimal("0")
    any_offer = False
    # A member the pricing engine cannot price is not worth nothing, and the sum
    # used to add it as RM 0: a three-piece set with one unpriced member printed
    # a set offer far below the sum of its parts, which is a discount nobody
    # authorised, on paper, in a dealer's hands. Zero IS the unpriced case here -
    # `products.list_price` is NOT NULL and defaults to nought, so
    # `_a_real_price` answers None for it. When that happens the offer is
    # abandoned entirely and the tag prints the set's list price, which is the
    # set's own rule and is always true.
    every_member_priced = True
    for member in members:
        if not member.contributes_to_price or member.product is None:
            continue
        view = prices.get(member.product.id)
        unit = None
        if view is not None:
            if view.offer_price is not None:
                any_offer = True
                unit = view.offer_price
            else:
                unit = view.list_price
        if unit is None:
            every_member_priced = False
            continue
        quantity = Decimal(str(member.quantity)) if member.quantity is not None else Decimal("1")
        offer_total += unit * quantity

    return {
        "id": product_set.id,
        "set_code": product_set.set_code or "",
        "name": product_set.name or "",
        "members": [
            {
                "product_id": member.product_id,
                "code": (member.product.product_code or "") if member.product else "",
                "name": (member.product.product_name or "") if member.product else "",
                "dimensions": dimensions_text(member.product) if member.product else "",
                "quantity": member.quantity,
            }
            for member in members
        ],
        "list_price": set_price.resolved,
        "offer_price": (
            offer_total.quantize(Decimal("0.01"))
            if any_offer and every_member_priced
            else None
        ),
        "promotion_id": promotion_id if (any_offer and every_member_priced) else None,
    }


# ---------------------------------------------------------------------------
# Request lines
# ---------------------------------------------------------------------------


def _set_member_text(members: Sequence[dict]) -> str:
    """``- CODE (NAME) 800 x 500 x 220 mm`` per member (AC-L.4)."""
    lines = []
    for member in members:
        head = f"- {member['code']}"
        if member.get("name"):
            head += f" ({member['name']})"
        if member.get("dimensions"):
            head += f" {member['dimensions']}"
        lines.append(head)
    return "\n".join(lines)


def resolve_request_line_data(db: Session, request) -> list[dict]:
    """Display data for every line of a price tag request.

    The one resolver behind both the designer's left panel and the print
    payload, so what marketing approves on screen and what the PDF prints are
    the same numbers from the same call. The marketing override wins over the
    resolved offer (D9) - it is a decision somebody made and logged a reason
    for, and the engine has no way to know about it.
    """
    viewer = staff_viewer()
    promotion_id = getattr(request, "promotion_id", None)
    rows: list[dict] = []

    for line in sorted(request.lines, key=lambda l: (l.sort_order or 0, l.id)):
        data: dict
        set_members = ""

        if line.product_set_id:
            product_set = get_product_set(db, line.product_set_id)
            if product_set is None:
                continue
            data = product_set_tag_data(db, product_set, viewer, promotion_id)
            set_members = _set_member_text(data["members"])
            code, name = data["set_code"], data["name"]
            # A set has no spec row of its own: the specs belong to its members,
            # and a set tag lists the members rather than their materials. Same
            # for barcode - a set has no single EAN either (S7).
            dimensions, specs, images, spec_values = "", "", [], []
            barcode = None
        elif line.product_id:
            product = get_product(db, line.product_id)
            if product is None:
                continue
            data = product_tag_data(db, product, viewer, promotion_id)
            code, name = data["code"], data["name"]
            dimensions = data["dimensions"]
            specs = "\n".join(data["spec_lines"])
            images = data["images"]
            spec_values = data["specs"]
            barcode = data["barcode"]
        else:
            continue

        sell_price = data["offer_price"]
        if line.marketing_price_override is not None:
            sell_price = Decimal(str(line.marketing_price_override))

        rows.append(
            {
                "line_id": line.id,
                "code": code,
                "name": name,
                "dimensions": dimensions,
                "spec_lines": specs,
                "specs": spec_values,
                "set_members": set_members,
                "images": images,
                "list_price": data["list_price"],
                "sell_price": sell_price,
                "show_promo_price": line.show_promo_price,
                "included_accessories": line.included_accessories or "",
                "quantity": line.quantity,
                "barcode": barcode,
            }
        )

    return rows


__all__ = [
    "STAFF_VIEWER",
    "dimensions_text",
    "format_dimensions_mm",
    "get_product",
    "get_product_set",
    "product_set_tag_data",
    "product_specs",
    "product_tag_data",
    "resolve_request_line_data",
    "search_products",
    "search_product_sets",
    "spec_lines",
    "staff_viewer",
]
