"""PRICETAG-UPGRADE-VARIANTS S3: a product's variant family for a "family tag".

The family is the `products.variant_of_id` tree under a product (any depth), never
`family_code` (that groups every model sharing the code stem). Company scope applies through
the session's ORM filter, like every other product read.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.product import Product


def _member_products(db: Session, product_id: Optional[str]) -> list[Product]:
    """Every product under ``product_id`` in the variant tree, ordered by code, itself left out.

    Walked one level at a time; a product already seen is never walked again, so a hand-made
    cycle (a base linked under its own descendant) cannot loop.
    """
    if not product_id:
        return []
    seen: set[str] = {str(product_id)}
    found: list[Product] = []
    frontier = [str(product_id)]
    while frontier:
        children = db.query(Product).filter(Product.variant_of_id.in_(frontier)).all()
        frontier = []
        for child in children:
            if child.id in seen:
                continue
            seen.add(child.id)
            found.append(child)
            frontier.append(child.id)
    found.sort(key=lambda p: (p.product_code or "", p.id))
    return found


def variant_members(db: Session, product_id: Optional[str]) -> list[dict]:
    """`[{product_id, code, name, list_price, is_discontinued, is_active}]` for the tree."""
    return [
        {
            "product_id": p.id,
            "code": p.product_code or "",
            "name": p.product_name or "",
            "list_price": p.list_price,
            "is_discontinued": bool(p.is_discontinued),
            "is_active": bool(p.is_active),
        }
        for p in _member_products(db, product_id)
    ]


def tag_variants(db: Session, product_id: Optional[str], excluded_ids=None) -> list[dict]:
    """The payload `variants` of a tag: live members (active, not discontinued, not excluded on
    the line), each `{product_id, code, specs}` through the product's own spec builder."""
    from app.services.dealer_kit.tag_data_service import product_specs

    excluded = {str(i) for i in excluded_ids or []}
    return [
        {"product_id": p.id, "code": p.product_code or "", "specs": product_specs(db, p)}
        for p in _member_products(db, product_id)
        if p.is_active and not p.is_discontinued and p.id not in excluded
    ]


def chooser(db: Session, product_id: str) -> Optional[dict]:
    """What the request line's "Variants on this tag" control lists: the members, live and
    discontinued (an inactive one is left out), and the line product's own list price for the
    "Variants price differently" warning. None when the product is not visible."""
    own = db.query(Product).filter(Product.id == product_id).first()
    if own is None:
        return None
    return {
        "members": [
            {
                "product_id": m["product_id"],
                "code": m["code"],
                "name": m["name"],
                "list_price": m["list_price"],
                "is_discontinued": m["is_discontinued"],
            }
            for m in variant_members(db, product_id)
            if m["is_active"]
        ],
        "own_list_price": own.list_price,
    }
