"""Utilities for external API endpoints."""
from __future__ import annotations

from datetime import datetime, date
from typing import Iterable, Dict, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.models.product import Product
from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment


def scope_to_attachment_company(db: Session, attachment) -> Optional[str]:
    """Pin the request's company scope to a bound attachment's company (Group G).

    The n8n binding endpoints run under X-API-Key with a ``None`` (all-companies)
    scope, so a match-by-code (product code, packing-list number, ...) could
    otherwise resolve — and bind — an entity in the WRONG company. When the
    attachment carries a ``company_id`` we set the session scope to that single
    company so (1) the central filter restricts every entity-resolution query to
    in-company rows and (2) any child rows created here auto-stamp that company.
    A NULL company_id (shared form attachment, AC-G3) leaves the resolver scope
    untouched. Returns the company id it scoped to, or ``None``.
    """
    company_id = getattr(attachment, "company_id", None)
    if company_id:
        set_company_scope(db, frozenset({str(company_id)}))
        return str(company_id)
    return None


def pin_scope_to_companies(db: Session, company_ids: Iterable[Optional[str]], *, anchor: str) -> str:
    """Pin the request to the company the payload's own anchors belong to.

    An X-API-Key call with no ``contact_id``/``space_id`` resolves to scope
    ``None`` = ALL companies (``company_scope_resolver._resolve_api_key_scope``).
    That is fine for reads, and wrong for any match-by-code: ``product_code`` is
    unique PER COMPANY (``uq_products_company_product_code``, migration 305), and
    11k+ codes currently exist in both companies, so an unscoped lookup picks a
    company by physical row order.

    So the payload has to name its own company through something that IS globally
    unique - a warehouse code, a container number, an SPO - and this pins the rest
    of the request to it. Anchors disagreeing is a 400 rather than a guess: one
    document cannot receive goods into two companies.

    Nothing to go on falls back to the INCUMBENT company, the same rule
    ``_portal_token_scope`` and ``company_scope._owner_company_id`` already use -
    every pre-multi-company row carries that id, so it is what these integrations
    have effectively been resolving to all along. Deterministic beats arbitrary.
    """
    ids = {str(cid) for cid in company_ids if cid}
    if len(ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"{anchor} spans more than one company; one request cannot.",
                "company_ids": sorted(ids),
            },
        )
    resolved = next(iter(ids)) if ids else DEFAULT_COMPANY_ID
    set_company_scope(db, frozenset({resolved}))
    return resolved


def parse_date_value(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Invalid date format: {value}")


def normalize_code(value: str) -> str:
    return value.strip().lower()


def get_products_by_code(db: Session, product_codes: Iterable[str]) -> Dict[str, Product]:
    codes = {normalize_code(code) for code in product_codes if code}
    if not codes:
        return {}
    products = db.query(Product).filter(
        func.lower(Product.product_code).in_(list(codes))
    ).all()
    return {normalize_code(p.product_code): p for p in products}


def get_products_by_code_exact(db: Session, product_codes: Iterable[str]) -> Dict[str, Product]:
    """Find products by exact product_code match (trim only, case-sensitive)."""
    codes = [(c or "").strip() for c in product_codes if (c or "").strip()]
    if not codes:
        return {}
    products = db.query(Product).filter(Product.product_code.in_(codes)).all()
    return {(p.product_code or "").strip(): p for p in products}


def get_warehouses_by_code_or_name(db: Session, values: Iterable[str]) -> Dict[str, Warehouse]:
    keys = {normalize_code(value) for value in values if value}
    if not keys:
        return {}
    warehouses = db.query(Warehouse).filter(
        func.lower(Warehouse.warehouse_code).in_(list(keys)) |
        func.lower(Warehouse.warehouse_name).in_(list(keys))
    ).all()
    # Codes and names share one namespace here, so a warehouse NAMED like another
    # warehouse's CODE would silently take that key over. Names are written first
    # and codes last: `warehouse_code` is the unique column, so it wins the clash.
    result = {}
    for w in warehouses:
        if w.warehouse_name:
            result[normalize_code(w.warehouse_name)] = w
    for w in warehouses:
        result[normalize_code(w.warehouse_code)] = w
    return result


def get_inbound_shipment_by_container_number(
    db: Session, shipping_container_number: str
) -> Optional[InboundShipment]:
    """Find inbound shipment by shipping_container_number (case-insensitive)."""
    if not (shipping_container_number or "").strip():
        return None
    key = normalize_code(shipping_container_number)
    # Ordered, because a container number is not unique: packing-list duplicate
    # detection keys on container + ETA + shipment_date precisely because the same
    # container comes back on later voyages. Unordered, "the" shipment was whatever
    # the seq scan happened to hand back, and could change under the caller between
    # two identical requests. Oldest first, so a re-post binds where the first did.
    shipment = (
        db.query(InboundShipment)
        .filter(func.lower(InboundShipment.shipping_container_number) == key)
        .order_by(InboundShipment.created_at, InboundShipment.id)
        .first()
    )
    return shipment
