"""Party costing profiles and their product lists (AC-PC-01, AC-PC-02, AC-CG-12)."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.costing import CustomerCostingProduct, CustomerCostingProfile
from app.models.order import Customer
from app.models.product import Product
from app.services.costing.formula import to_decimal
from app.services.error_handler import AppException

PROFILE_METHODS = ("primary", "average", "last_po")


def not_found(what: str) -> AppException:
    return AppException(status_code=404, message=f"{what} not found.", code="NOT_FOUND")


def valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def get_customer(db: Session, customer_id: str) -> Customer:
    if not valid_uuid(customer_id):
        raise not_found("Customer")
    customer = db.query(Customer).filter(Customer.id == str(customer_id)).first()
    if customer is None:
        raise not_found("Customer")
    return customer


def get_profile(db: Session, customer_id: str) -> Optional[CustomerCostingProfile]:
    return db.query(CustomerCostingProfile).filter(CustomerCostingProfile.customer_id == str(customer_id)).first()


def party_view(db: Session, customer: Customer) -> dict:
    """The contract's `Party` object. A customer with no profile has `has_profile: false`."""
    profile = get_profile(db, customer.id)
    count = (
        db.query(func.count(CustomerCostingProduct.id))
        .filter(CustomerCostingProduct.customer_id == customer.id)
        .scalar()
    ) or 0
    return {
        "customer_id": str(customer.id),
        "customer_code": customer.customer_code,
        "customer_name": customer.customer_name,
        "has_profile": profile is not None,
        "markup_pct": float(profile.markup_pct) if profile else None,
        "cost_method": profile.cost_method if profile else None,
        "is_active": bool(profile.is_active) if profile else None,
        "product_count": int(count),
    }


def get_party(db: Session, customer_id: str) -> dict:
    return party_view(db, get_customer(db, customer_id))


def product_ids(db: Session, customer_id: str) -> list:
    customer = get_customer(db, customer_id)
    return [
        str(pid) for (pid,) in db.query(CustomerCostingProduct.product_id)
        .filter(CustomerCostingProduct.customer_id == customer.id).all()
    ]


def put_party(
    db: Session, customer_id: str, *, markup_pct: float, cost_method: Optional[str],
    is_active: bool, actor: Optional[str],
) -> dict:
    customer = get_customer(db, customer_id)
    if markup_pct is None or to_decimal(markup_pct) < 0:
        raise AppException(status_code=422, message="The party mark-up must be zero or more.")
    if cost_method is not None and cost_method not in PROFILE_METHODS:
        raise AppException(
            status_code=422, message="A party cost method is Primary supplier, Average or Last PO price."
        )
    markup = to_decimal(markup_pct)
    profile = get_profile(db, customer.id)
    if profile is None:
        db.add(CustomerCostingProfile(
            customer_id=customer.id, markup_pct=markup, cost_method=cost_method,
            is_active=bool(is_active), created_by=actor,
        ))
    else:
        if to_decimal(profile.markup_pct) != markup:
            profile.markup_pct = markup
        if profile.cost_method != cost_method:
            profile.cost_method = cost_method
        if bool(profile.is_active) != bool(is_active):
            profile.is_active = bool(is_active)
    db.commit()
    return party_view(db, customer)


def add_products(db: Session, customer_id: str, product_ids: Iterable[str], *, actor: Optional[str]) -> dict:
    """Add products to a party's list. Adding one twice is a no-op. An unknown id adds nothing
    at all."""
    customer = get_customer(db, customer_id)
    if get_profile(db, customer.id) is None:
        raise not_found("Costing profile")
    ids = list(dict.fromkeys(str(p) for p in product_ids))
    if not all(valid_uuid(p) for p in ids):
        raise not_found("Product")
    found = {
        str(pid) for (pid,) in db.query(Product.id).filter(Product.id.in_(ids)).all()
    } if ids else set()
    if len(found) != len(ids):
        raise not_found("Product")
    have = {
        str(pid) for (pid,) in db.query(CustomerCostingProduct.product_id)
        .filter(CustomerCostingProduct.customer_id == customer.id).all()
    }
    new = [p for p in ids if p not in have]
    for pid in new:
        db.add(CustomerCostingProduct(
            id=str(uuid.uuid4()), customer_id=customer.id, product_id=pid, added_by=actor,
        ))
    db.commit()
    return {"added": len(new), "already": len(ids) - len(new)}


def unlink_product_by_id(db: Session, party_product_id: str) -> None:
    """The parked `costing_party_product.unlink` action's handler: remove one product from a
    party's list. Already gone is not an error; the product itself stays."""
    if not valid_uuid(party_product_id):
        return
    row = db.query(CustomerCostingProduct).filter(CustomerCostingProduct.id == str(party_product_id)).first()
    if row is not None:
        db.delete(row)
        db.flush()
