"""Utilities for external API endpoints."""
from __future__ import annotations

from datetime import datetime, date
from typing import Iterable, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.base import set_company_scope
from app.models.product import Product
from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment, InboundShipmentLine


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
    result = {}
    for w in warehouses:
        result[normalize_code(w.warehouse_code)] = w
        result[normalize_code(w.warehouse_name)] = w
    return result


def get_inbound_shipment_by_container_number(
    db: Session, shipping_container_number: str
) -> Optional[InboundShipment]:
    """Find inbound shipment by shipping_container_number (case-insensitive)."""
    if not (shipping_container_number or "").strip():
        return None
    key = normalize_code(shipping_container_number)
    shipment = (
        db.query(InboundShipment)
        .filter(func.lower(InboundShipment.shipping_container_number) == key)
        .first()
    )
    return shipment


def get_shipment_line_by_product(
    db: Session, shipment_id: str, product_id: str
) -> Optional[InboundShipmentLine]:
    """Find first inbound shipment line for this shipment and product."""
    return (
        db.query(InboundShipmentLine)
        .filter(
            InboundShipmentLine.shipment_id == shipment_id,
            InboundShipmentLine.product_id == product_id,
        )
        .first()
    )
