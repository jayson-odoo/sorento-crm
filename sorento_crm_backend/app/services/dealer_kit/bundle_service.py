"""Bundles: CRUD and read-time resolution.

Two invariants live here, and neither is stored:

  * **Availability is DERIVED from the components, every read** (AC-F10). A
    bundle is available only when every component is active and not
    discontinued. Storing a flag would let it go stale the moment a product was
    discontinued, and a stale "available" is an order nobody can fulfil.
  * **The allocation sums exactly to the bundle price.** That arithmetic lives
    in ``bundle_pricing.py`` with its own golden set; this module only feeds it
    real rows.

A Bundle is never a `products` row. It is never stocked, never costed, never
written to the ledger. What reaches an order is always its components.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.models.dealer_kit import Bundle, BundleComponent
from app.models.product import Product
from app.services.dealer_kit.bundle_pricing import (
    BundleComponentInput,
    allocate_bundle_price,
)
from app.services.error_handler import AppException


def _require(db: Session, bundle_id: str) -> Bundle:
    row = (
        db.query(Bundle)
        .options(joinedload(Bundle.components))
        .filter(Bundle.id == bundle_id)
        .first()
    )
    if row is None:
        raise AppException(status_code=404, message="Bundle not found")
    return row


def create_bundle(
    db: Session,
    *,
    name: str,
    price: Decimal,
    components: Sequence[dict],
    user_id: Optional[str] = None,
) -> Bundle:
    if not components:
        raise AppException(status_code=422, message="A bundle needs at least one component")
    if price is None or Decimal(price) < 0:
        raise AppException(status_code=422, message="A bundle price cannot be negative")

    bundle = Bundle(name=name, price=price, created_by=user_id)
    db.add(bundle)
    db.flush()

    for index, component in enumerate(components):
        quantity = Decimal(str(component.get("quantity", 1)))
        if quantity <= 0:
            raise AppException(
                status_code=422, message="A bundle component needs a positive quantity"
            )
        db.add(
            BundleComponent(
                bundle_id=bundle.id,
                product_id=component["product_id"],
                quantity=quantity,
                sort_order=component.get("sort_order", index),
            )
        )

    db.commit()
    db.refresh(bundle)
    return bundle


def list_bundles(db: Session) -> list[Bundle]:
    return (
        db.query(Bundle)
        .options(joinedload(Bundle.components))
        .order_by(Bundle.name)
        .all()
    )


def delete_bundle(db: Session, bundle_id: str) -> None:
    db.delete(_require(db, bundle_id))
    db.commit()


def _money(value: Optional[Decimal], currency: str = "MYR") -> str:
    return f"{currency} {Decimal(value or 0):,.2f}"


def resolve_bundle(db: Session, bundle_id: str) -> dict:
    """A bundle as rendered: one priced heading, components beneath (AC-F12)."""
    bundle = _require(db, bundle_id)

    product_ids = [component.product_id for component in bundle.components]
    products = (
        {
            product.id: product
            for product in db.query(Product).filter(Product.id.in_(product_ids)).all()
        }
        if product_ids
        else {}
    )

    allocation = {
        line.key: line.allocated
        for line in allocate_bundle_price(
            Decimal(bundle.price),
            [
                BundleComponentInput(
                    key=component.product_id,
                    list_price=(
                        Decimal(products[component.product_id].list_price)
                        if component.product_id in products
                        and products[component.product_id].list_price is not None
                        else None
                    ),
                    quantity=int(component.quantity or 1),
                )
                for component in bundle.components
            ],
        )
    }

    currency = "MYR"
    components = []
    unavailable: list[str] = []

    for component in bundle.components:
        product = products.get(component.product_id)
        # A component whose product has vanished from this company's scope is
        # treated as unavailable rather than skipped: dropping it would quietly
        # change what the bundle IS.
        available = bool(
            product is not None and product.is_active and not product.is_discontinued
        )
        if not available:
            unavailable.append(
                product.product_name if product is not None else "A component product"
            )
        if product is not None and product.currency:
            currency = product.currency

        components.append(
            {
                "product_id": component.product_id,
                "product_code": product.product_code if product else "",
                "product_name": product.product_name if product else "Unavailable product",
                "quantity": int(component.quantity or 1),
                "allocated": _money(allocation.get(component.product_id), currency),
                "available": available,
            }
        )

    return {
        "id": bundle.id,
        "name": bundle.name,
        "price": _money(bundle.price, currency),
        # Derived here, on every read. Never read from a column.
        "available": bool(bundle.is_active and not unavailable),
        "unavailable_reason": (
            f"{unavailable[0]} is discontinued"
            if len(unavailable) == 1
            else f"{len(unavailable)} components are discontinued"
            if unavailable
            else None
        ),
        "components": components,
    }
