"""The Selection spine: what somebody chose, resolved for whoever is reading.

A Selection stores product ids and quantities. Every number a user sees - price,
availability, dimensions, the total - is worked out HERE, at read time, from the
product rows as they are now and the viewer in front of us.

The important difference from collection resolution: that one filters
discontinued products out of the candidate set before they can become tiles,
which is right, because nobody chose them. Here somebody DID choose it. Dropping
the line would edit a person's basket behind their back and change a total they
had already read. The line stays, marked unavailable, and it does not count
toward the total - a total including something nobody can buy is a promise that
cannot be kept.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.dealer_kit import Selection, SelectionLine
from app.models.product import Product
from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext
from app.services.error_handler import AppException


def create_selection(
    db: Session,
    user_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    name: Optional[str] = None,
    source_page_id: Optional[str] = None,
) -> Selection:
    """Start a Selection for exactly one owner.

    Checked here as well as in the database because a 400 naming the problem is
    kinder than an IntegrityError, and checked in the DATABASE as well as here
    because the next caller may not come through this function.
    """
    if bool(user_id) == bool(contact_id):
        raise AppException(
            status_code=400,
            message="A selection belongs to exactly one owner: a user or a contact.",
            code="selection_owner_required",
        )

    selection = Selection(
        user_id=user_id,
        contact_id=contact_id,
        name=name,
        source_page_id=source_page_id,
    )
    db.add(selection)
    db.flush()
    return selection


def get_selection(db: Session, selection_id: str) -> Selection:
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise AppException(status_code=404, message="Selection not found")
    return selection


def list_lines(db: Session, selection: Selection) -> list[SelectionLine]:
    return (
        db.query(SelectionLine)
        .filter(SelectionLine.selection_id == selection.id)
        .order_by(SelectionLine.sort_order, SelectionLine.created_at)
        .all()
    )


def _assert_product_exists(db: Session, product_id: str) -> None:
    """A product id the catalogue does not have is a 404, not a 500.

    Without this the insert reaches the foreign key and the caller gets an
    opaque server error for what is simply a bad id. The lookup runs under the
    caller's company scope, so another company's product reads as missing -
    which is the correct answer, and the same one an attacker probing ids gets.
    """
    exists = db.query(Product.id).filter(Product.id == product_id).first()
    if not exists:
        raise AppException(
            status_code=404,
            message="That product is not in the catalogue.",
            code="product_not_found",
        )


def add_line(
    db: Session, selection: Selection, product_id: str, quantity: Decimal | float | int = 1
) -> SelectionLine:
    """Add a product, or add to it if it is already there.

    Picking the same thing twice means two of them, not a duplicate row and not
    a silently ignored click.
    """
    amount = Decimal(str(quantity))
    if amount <= 0:
        raise AppException(
            status_code=400,
            message="Quantity must be greater than zero.",
            code="selection_quantity_invalid",
        )

    existing = _find_line(db, selection, product_id)
    if existing:
        existing.quantity = (existing.quantity or Decimal("0")) + amount
        db.flush()
        return existing

    _assert_product_exists(db, product_id)
    line = SelectionLine(
        selection_id=selection.id,
        product_id=product_id,
        quantity=amount,
        sort_order=len(list_lines(db, selection)),
    )
    db.add(line)
    db.flush()
    return line


def set_quantity(
    db: Session, selection: Selection, product_id: str, quantity: Decimal | float | int
) -> Optional[SelectionLine]:
    """Set an absolute quantity. Zero removes the line, which is what a user
    who typed 0 meant."""
    amount = Decimal(str(quantity))
    line = _find_line(db, selection, product_id)
    if not line:
        # Setting an absent product to zero is already true, so do not make the
        # caller prove the id exists to tell us nothing should change.
        return None if amount <= 0 else add_line(db, selection, product_id, amount)

    if amount <= 0:
        db.delete(line)
        db.flush()
        return None

    line.quantity = amount
    db.flush()
    return line


def remove_line(db: Session, selection: Selection, product_id: str) -> bool:
    line = _find_line(db, selection, product_id)
    if not line:
        return False
    db.delete(line)
    db.flush()
    return True


def _find_line(db: Session, selection: Selection, product_id: str) -> Optional[SelectionLine]:
    return (
        db.query(SelectionLine)
        .filter(
            SelectionLine.selection_id == selection.id,
            SelectionLine.product_id == product_id,
        )
        .first()
    )


def resolve_selection(
    db: Session, selection: Selection, viewer: ViewerContext = ANONYMOUS
) -> dict:
    """The Selection as this viewer may see it, with a total they can trust."""
    lines = list_lines(db, selection)
    products = _products_by_id(db, [line.product_id for line in lines])

    resolved: list[dict] = []
    total = Decimal("0")
    currency = "MYR"

    for line in lines:
        product = products.get(line.product_id)
        if product is None:
            # The FK is RESTRICT, so this means the row was removed out of band.
            # Say so rather than dropping the line the user is looking at.
            resolved.append(_missing_line(line))
            continue

        currency = product.currency or currency
        available = bool(product.is_active) and not bool(product.is_discontinued)
        quantity = line.quantity or Decimal("0")
        price = product.list_price

        if available and price is not None:
            total += Decimal(str(price)) * quantity

        resolved.append(
            {
                "line_id": line.id,
                "product_id": product.id,
                "product_code": product.product_code,
                "product_name": product.product_name,
                "quantity": float(quantity),
                "price": _money(price),
                # Both gates, ANDed, and the losing case omits the number rather
                # than sending it to be hidden (AC-G6, AC-G7).
                "invoice_price": (
                    _money(product.invoice_price) if viewer.invoice_price_visible else None
                ),
                "line_total": _money(
                    Decimal(str(price)) * quantity if price is not None else None
                ),
                "dimensions_mm": _dimensions_mm(product),
                "is_available": available,
                "unavailable_reason": None if available else _reason(product),
            }
        )

    return {
        "id": selection.id,
        "name": selection.name,
        "currency": currency,
        "lines": resolved,
        "total": _money(total),
        "unavailable_count": sum(1 for line in resolved if not line["is_available"]),
    }


def _missing_line(line: SelectionLine) -> dict:
    return {
        "line_id": line.id,
        "product_id": line.product_id,
        "product_code": None,
        "product_name": "Product no longer in the catalogue",
        "quantity": float(line.quantity or 0),
        "price": None,
        "invoice_price": None,
        "line_total": None,
        "dimensions_mm": None,
        "is_available": False,
        "unavailable_reason": "removed",
    }


def _reason(product: Product) -> str:
    return "discontinued" if product.is_discontinued else "inactive"


def _products_by_id(db: Session, product_ids: Sequence[str]) -> dict[str, Product]:
    if not product_ids:
        return {}
    # Deliberately NOT the sellable-products filter used for collections: a
    # product the user chose must come back even when it is no longer for sale,
    # so that it can be shown as unavailable instead of vanishing.
    rows = db.query(Product).filter(Product.id.in_(list(product_ids))).all()
    return {product.id: product for product in rows}


def _dimensions_mm(product: Product) -> Optional[dict]:
    """Millimetres as numbers, for the 3D view to scale a box with.

    All three or nothing. A product with a length and no height cannot be drawn
    honestly, and filling the gap with a default produces a box that looks
    deliberate and is wrong - worse than one that admits it is a guess (AC-V2).
    """
    parts = (
        product.dimensions_length,
        product.dimensions_width,
        product.dimensions_height,
    )
    if any(part is None for part in parts):
        return None

    length, width, height = (float(part) for part in parts)
    if length <= 0 or width <= 0 or height <= 0:
        return None

    return {"length": length, "width": width, "height": height}


def _money(value: Decimal | float | None) -> Optional[str]:
    if value is None:
        return None
    return f"{Decimal(str(value)):.2f}"


def save_room(db: Session, selection: Selection, room: dict | None) -> Selection:
    """Store the outline and placements as given.

    Deliberately opaque to the backend beyond the outline: the shape of a
    placement belongs to the designer and will keep moving, and a Pydantic model
    here would mean a backend release every time a drag handle changes. What is
    promised is that it round-trips unchanged.
    """
    selection.room_json = room
    db.flush()
    return selection


def room_area_sqm(room: dict | None) -> Optional[float]:
    """Shoelace area of the outline, in square metres. DERIVED, never stored.

    Stored area is area that disagrees with the polygon the moment somebody
    drags a wall, and the disagreement is invisible until a customer asks why
    the quote says 12 and the drawing says 14 (AC-R5).

    The absolute value is taken on purpose: a user who dragged their walls
    anticlockwise has not drawn a negative room.
    """
    if not isinstance(room, dict):
        return None

    outline = room.get("outline")
    if not isinstance(outline, list) or len(outline) < 3:
        return None

    try:
        points = [(float(point["x"]), float(point["y"])) for point in outline]
    except (KeyError, TypeError, ValueError):
        return None

    doubled = 0.0
    for index, (x, y) in enumerate(points):
        next_x, next_y = points[(index + 1) % len(points)]
        doubled += x * next_y - next_x * y

    # mm^2 -> m^2
    return round(abs(doubled / 2) / 1_000_000, 2)
