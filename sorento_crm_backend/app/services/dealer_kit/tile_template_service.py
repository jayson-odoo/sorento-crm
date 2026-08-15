"""Tile designs: which product fields a tile shows, and in what order.

A tile design is stored as a document rather than columns because it is meant to
grow - today it is an ordered field list, and the plan is a mini-grid with
static assets alongside the bound fields. Putting `fields` in a JSONB `doc` now
means adding a background image later is a document change, not a migration.

The field list is a WHITELIST. A design can only bind fields the renderer knows
how to draw, so a typo becomes a 422 at authoring time instead of a blank space
in a printed catalogue that nobody notices until it is at the printer.
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.dealer_kit import TileTemplate
from app.services.error_handler import AppException

# Every field the tile renderer can draw. Adding one here means teaching
# `TileGrid` to render it in the same change.
TILE_FIELDS: tuple[str, ...] = (
    "image",
    "name",
    "code",
    "price",
    # The promotion's figure, drawn beside the list price with the list price
    # struck through. Bound on its own it prints the offer ALONE, which is how a
    # consumer flyer that never quotes LP is designed. Either binding falls back
    # to the list price with no offer styling when no offer reaches this reader
    # (ADR 0008 rule 5), so a tile never looks discounted to itself.
    "offerPrice",
    "dimensions",
    "badges",
    "cta",
)


def _validate(fields: Sequence[str]) -> list[str]:
    cleaned = [str(field).strip() for field in fields if str(field).strip()]
    if not cleaned:
        raise AppException(
            status_code=422, message="A tile design must show at least one field"
        )

    unknown = [field for field in cleaned if field not in TILE_FIELDS]
    if unknown:
        raise AppException(
            status_code=422,
            message=(
                f"Unknown tile field(s): {', '.join(unknown)}. "
                f"Expected any of: {', '.join(TILE_FIELDS)}"
            ),
        )

    # Order is the design, so it is preserved - but a field twice is a mistake,
    # not an instruction to draw it twice.
    seen: dict[str, None] = {}
    for field in cleaned:
        seen[field] = None
    return list(seen)


def get_template(db: Session, template_id: str) -> TileTemplate:
    row = db.query(TileTemplate).filter(TileTemplate.id == template_id).first()
    if row is None:
        raise AppException(status_code=404, message="Tile design not found")
    return row


def list_templates(db: Session) -> list[TileTemplate]:
    return db.query(TileTemplate).order_by(TileTemplate.name).all()


def create_template(
    db: Session, *, name: str, fields: Sequence[str], user_id: Optional[str] = None
) -> TileTemplate:
    if not (name or "").strip():
        raise AppException(status_code=422, message="A tile design needs a name")

    row = TileTemplate(
        name=name.strip(), doc={"fields": _validate(fields)}, created_by=user_id
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_template(
    db: Session,
    template_id: str,
    *,
    name: Optional[str] = None,
    fields: Optional[Sequence[str]] = None,
) -> TileTemplate:
    row = get_template(db, template_id)

    if name is not None:
        if not name.strip():
            raise AppException(status_code=422, message="A tile design needs a name")
        row.name = name.strip()

    if fields is not None:
        # Replace the whole document rather than merging: a design is the list,
        # and merging would leave a removed field silently still rendering.
        row.doc = {**(row.doc or {}), "fields": _validate(fields)}

    db.commit()
    db.refresh(row)
    return row


def delete_template(db: Session, template_id: str) -> None:
    db.delete(get_template(db, template_id))
    db.commit()


def fields_of(template: TileTemplate) -> list[str]:
    """The ordered field list, tolerating a document written before this shape."""
    doc = template.doc or {}
    fields = doc.get("fields")
    return list(fields) if isinstance(fields, list) else []
