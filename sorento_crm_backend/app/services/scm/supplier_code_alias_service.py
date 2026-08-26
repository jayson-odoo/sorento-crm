"""Recording what a supplier's code means, and putting the rows already on file right.

The ladder (`supplier_code_matcher`) answers what it can and writes its answers down. This
module is the other half: what a PERSON decides, and what happens to the rows uploaded
before they decided it.

The re-bind is the point. The loading plan is read off `scm.supplier_inventory` and the PI
convert off `scm.proforma_invoice_line`, so an answer that only takes effect on the next
upload is an answer nobody gets to use today - the operator would have to re-upload a file
they already uploaded to see their own decision.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.scm import (
    ProformaInvoice,
    ProformaInvoiceLine,
    SupplierInventory,
    SupplierProductCodeAlias,
)
from app.services.error_handler import AppException
from app.services.scm.supplier_code_matcher import resolve
from app.services.scm.supplier_scope import is_uuid as _is_uuid

_MANUAL = "manual"


def _uuid() -> str:
    return str(uuid.uuid4())


def _product_or_404(db: Session, product_id: str) -> Product:
    """One of OUR products, through the ORM so the company filter applies: a code cannot be
    bound to another company's catalogue."""
    if not _is_uuid(product_id):
        raise AppException(404, "That product does not exist.", detail="product_id")
    product = db.query(Product).filter(Product.id == str(product_id)).first()
    if product is None:
        raise AppException(404, "That product does not exist.", detail="product_id")
    return product


def create(
    db: Session,
    *,
    supplier_id: str,
    supplier_code: str,
    product_id: str,
    actor: Optional[str] = None,
) -> dict:
    """"This code is that product." Replaces whatever was recorded before, and re-binds.

    Replaces rather than adds: one supplier code means one product, and two rows saying
    different things is the state the identity index exists to forbid. A manual pick landing
    on top of an automatic one is the normal path - it is how a guess gets corrected.

    Does not commit.
    """
    code = (supplier_code or "").strip()
    if not code:
        raise AppException(422, "Name the code the supplier wrote.", detail="supplier_code")
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    product = _product_or_404(db, product_id)

    existing = (
        db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.supplier_code.ilike(code),
        )
        .first()
    )
    if existing is None:
        existing = SupplierProductCodeAlias(
            id=_uuid(),
            supplier_id=str(supplier_id),
            supplier_code=code,
            product_id=str(product.id),
            source=_MANUAL,
            matched_by=_MANUAL,
            created_by=actor,
        )
        db.add(existing)
    else:
        existing.product_id = str(product.id)
        existing.source = _MANUAL
        existing.matched_by = _MANUAL
        existing.created_by = actor
    db.flush()

    rebound = _rebind(db, supplier_id, code, str(product.id))
    return {
        "id": str(existing.id),
        "supplier_code": existing.supplier_code,
        "product_id": str(product.id),
        "product_code": product.product_code,
        "source": existing.source,
        "matched_by": existing.matched_by,
        **rebound,
    }


def delete(db: Session, alias_id: str, *, actor: Optional[str] = None) -> dict:
    """Forget this decision, and put the rows back to whatever the ladder says now.

    Not "leave them where they are": the binding existed BECAUSE of this alias, and a row
    still pointing at a product whose reason has been deleted is a binding nobody can
    account for. The ladder is re-run WITHOUT remembering, so deleting a correction does not
    immediately resurrect the guess it corrected as a fresh automatic alias.
    """
    if not _is_uuid(alias_id):
        raise AppException(404, "That code match does not exist.", detail="alias_id")
    alias = (
        db.query(SupplierProductCodeAlias)
        .filter(SupplierProductCodeAlias.id == str(alias_id))
        .first()
    )
    if alias is None:
        raise AppException(404, "That code match does not exist.", detail="alias_id")

    supplier_id = str(alias.supplier_id)
    code = alias.supplier_code
    db.delete(alias)
    db.flush()

    found = resolve(db, supplier_id, [code], remember=False, actor=actor)
    match = found.get(code)
    rebound = _rebind(db, supplier_id, code, match.product_id if match else None)
    return {"deleted": 1, **rebound}


def list_for_supplier(db: Session, supplier_id: str) -> list[dict]:
    """What is on record for this supplier, in names a person reads - never an id."""
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    rows = (
        db.query(SupplierProductCodeAlias, Product)
        .join(Product, Product.id == SupplierProductCodeAlias.product_id)
        .filter(SupplierProductCodeAlias.supplier_id == str(supplier_id))
        .order_by(SupplierProductCodeAlias.supplier_code)
        .all()
    )
    return [
        {
            "id": str(alias.id),
            "supplier_code": alias.supplier_code,
            "product_code": product.product_code,
            "product_name": product.product_name,
            "source": alias.source,
            "matched_by": alias.matched_by,
            "created_by": alias.created_by,
            "created_at": alias.created_at.isoformat() if alias.created_at else None,
        }
        for alias, product in rows
    ]


def _rebind(
    db: Session, supplier_id: str, code: str, product_id: Optional[str]
) -> dict:
    """Point every row already uploaded under this code at the product it now means.

    Both readers, in the same transaction: the stock list feeds the loading plan and the
    invoice lines feed the convert, and a decision that reached one of them and not the
    other would have the two screens disagreeing about the same code.
    """
    stock = (
        db.query(SupplierInventory)
        .filter(
            SupplierInventory.supplier_id == str(supplier_id),
            SupplierInventory.item_code.ilike(code),
        )
        .all()
    )
    for row in stock:
        row.product_id = product_id

    lines = (
        db.query(ProformaInvoiceLine)
        .join(ProformaInvoice, ProformaInvoice.id == ProformaInvoiceLine.invoice_id)
        .filter(
            ProformaInvoice.supplier_id == str(supplier_id),
            ProformaInvoiceLine.item_code.ilike(code),
        )
        .all()
    )
    for line in lines:
        line.product_id = product_id
    db.flush()
    return {
        "rebound_stock_rows": len(stock),
        "rebound_invoice_lines": len(lines),
    }
