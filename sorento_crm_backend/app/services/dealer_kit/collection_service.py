"""Collections: CRUD and the resolver that turns one into tiles.

Resolution is four steps, in this order, and the order is the point:

  1. **Company scope** narrows the candidate products. It runs FIRST, via the
     ORM filter, so a rule can never match another company's catalogue no matter
     what it says (AC-F8).
  2. **The rule** is evaluated by the SHARED ``app/rule_engine`` over registered
     product facts - not a bespoke filter (AC-F3).
  3. **Set algebra**: rule union pins minus exclusions, ordered (AC-F2). Pure,
     and tested exhaustively in ``collection_membership.py``.
  4. **Viewer resolution** turns members into tiles, deciding per reader what
     price (if any) appears. The document never held one (AC-G1).

Discontinued and inactive products are dropped before tiles are built (AC-G4):
a dead tile in a catalogue is an order someone cannot fulfil.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.models.dealer_kit import Collection
from app.models.product import Product
from app.rule_engine.evaluator import collect_fact_keys, evaluate
from app.services.dealer_kit.collection_membership import assemble_members
from app.services.dealer_kit.product_facts import product_facts
from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext
from app.services.error_handler import AppException

PAGE = "page"
LIBRARY = "library"


def get_collection(db: Session, collection_id: str) -> Collection:
    row = db.query(Collection).filter(Collection.id == collection_id).first()
    if row is None:
        # Company scope already ran, so another company's collection and a
        # non-existent one are the same answer.
        raise AppException(status_code=404, message="Collection not found")
    return row


def create_collection(
    db: Session,
    *,
    scope: str = PAGE,
    page_id: Optional[str] = None,
    name: Optional[str] = None,
    conditions: Optional[dict] = None,
    pinned_product_ids: Optional[Sequence[str]] = None,
    excluded_product_ids: Optional[Sequence[str]] = None,
    manual_order: Optional[Sequence[str]] = None,
    user_id: Optional[str] = None,
) -> Collection:
    if scope not in (PAGE, LIBRARY):
        raise AppException(status_code=422, message=f"Unknown collection scope '{scope}'")
    if scope == PAGE and not page_id:
        raise AppException(
            status_code=422, message="A page-scoped collection must belong to a page"
        )
    if scope == LIBRARY and not (name or "").strip():
        raise AppException(status_code=422, message="A reusable collection needs a name")

    row = Collection(
        scope=scope,
        page_id=page_id,
        name=(name or None),
        conditions_json=conditions,
        pinned_product_ids=list(pinned_product_ids or []),
        excluded_product_ids=list(excluded_product_ids or []),
        manual_order=list(manual_order or []),
        created_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_collection(db: Session, collection_id: str, **changes) -> Collection:
    row = get_collection(db, collection_id)
    for field in (
        "name",
        "conditions_json",
        "pinned_product_ids",
        "excluded_product_ids",
        "manual_order",
    ):
        if field in changes:
            setattr(row, field, changes[field])
    db.commit()
    db.refresh(row)
    return row


def save_as_library(db: Session, collection_id: str, name: str) -> Collection:
    """Promote a page-scoped collection into the reusable library (AC-F5).

    The page keeps pointing at the SAME row, so promoting does not orphan the
    block that was using it - which is what a Designer expects when they name
    something they already built.
    """
    if not (name or "").strip():
        raise AppException(status_code=422, message="A reusable collection needs a name")

    row = get_collection(db, collection_id)
    row.scope = LIBRARY
    row.name = name.strip()
    db.commit()
    db.refresh(row)
    return row


def list_library(db: Session) -> list[Collection]:
    """Only reusable collections. Page-scoped ones are an editor implementation
    detail and would be noise in a library list (AC-F4)."""
    return (
        db.query(Collection)
        .filter(Collection.scope == LIBRARY)
        .order_by(Collection.name)
        .all()
    )


def delete_collection(db: Session, collection_id: str) -> None:
    db.delete(get_collection(db, collection_id))
    db.commit()


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def _sellable_products(db: Session) -> list[Product]:
    """Candidates, company-scoped by the ORM filter and already excluding what
    can never be sold. Filtering in SQL rather than after the rule keeps a
    discontinued product from ever being a member."""
    return (
        db.query(Product)
        .options(joinedload(Product.category), joinedload(Product.brand))
        .filter(Product.is_active.is_(True), Product.is_discontinued.is_(False))
        .order_by(Product.product_code)
        .all()
    )


def _matched_ids(db: Session, conditions: Optional[dict], candidates: Iterable[Product]) -> list[str]:
    if not conditions or not conditions.get("rules"):
        # An empty rule matches nothing here, NOT everything. The engine's own
        # convention is that an empty tree is unconditional, which is right for
        # "may this promotion run" but catastrophic for "which products are in
        # this collection" - it would silently put the entire catalogue on the
        # page. A collection with no rule has only its pins.
        return []

    # Resolve only the facts the rule actually reads: a computed fact should not
    # be paid for on every product when no condition mentions it.
    only = collect_fact_keys(conditions)
    return [
        product.id
        for product in candidates
        if evaluate(conditions, product_facts(product, db, only_keys=only))
    ]


def _money(value: Optional[Decimal], currency: str) -> Optional[str]:
    if value is None:
        return None
    return f"{currency} {Decimal(value):,.2f}"


def resolve_members(db: Session, collection: Collection) -> list[Product]:
    """The ordered member products of a collection."""
    candidates = _sellable_products(db)
    by_id = {product.id: product for product in candidates}

    member_ids = assemble_members(
        matched=_matched_ids(db, collection.conditions_json, candidates),
        pinned=collection.pinned_product_ids,
        excluded=collection.excluded_product_ids,
        manual_order=collection.manual_order,
    )

    # A pinned id that is discontinued, deleted or another company's simply is
    # not in `by_id`, so it drops out here rather than becoming a broken tile.
    return [by_id[member_id] for member_id in member_ids if member_id in by_id]


def resolve_tiles(
    db: Session, collection: Collection, viewer: ViewerContext = ANONYMOUS
) -> list[dict]:
    """Members as tiles, with prices decided for THIS viewer."""
    tiles = []
    for product in resolve_members(db, collection):
        currency = product.currency or "MYR"
        tiles.append(
            {
                "product_id": product.id,
                "product_code": product.product_code,
                "product_name": product.product_name,
                "price": _money(product.list_price, currency),
                # Absent unless the document says show it AND the viewer may see
                # it. Both gates, ANDed, and the losing case omits the number
                # entirely rather than sending it to be hidden (AC-G6, AC-G7).
                "invoice_price": (
                    _money(product.invoice_price, currency)
                    if viewer.invoice_price_visible
                    else None
                ),
                "image_url": None,
                "dimensions": _dimensions(product),
                "badges": [],
            }
        )
    return tiles


def _dimensions(product: Product) -> Optional[str]:
    parts = [
        product.dimensions_length,
        product.dimensions_width,
        product.dimensions_height,
    ]
    if not any(part is not None for part in parts):
        return None
    return " x ".join("-" if part is None else f"{Decimal(part):g}" for part in parts) + " mm"
