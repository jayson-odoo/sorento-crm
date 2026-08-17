"""Proforma invoices: the supplier's priced document, uploaded and held (G3b).

Same two-step shape as every other upload channel here - `preview` and `?validate_only=true`
describe, `apply` writes - because a proforma can carry five invoices at once and nothing
should be written from a single click.

The supplier travels with the file because the file never says reliably who wrote it: Kailu's
letterhead is a Hong Kong management company, Jinbaichuan's is a title cell in Chinese. The
currency does NOT have to travel with it: the document usually states it and the supplier's
price list often does, so the form field is the last resort rather than the first question
(AC-P3.1).
"""
from __future__ import annotations

import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.scm import ProformaInvoice
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service
from app.services.scm.upload_intake import read_upload

router = APIRouter()

# Writing a supplier's document of record is the operator's capability, not the reader's, so
# it sits behind its own permission - swept onto whoever already runs the module's uploads
# by migration 374.
_UPLOAD = require_permission("scm.proforma_invoice.upload")
_READ = require_permission("scm.dashboard.view")


def _actor(user: Optional[dict]) -> Optional[str]:
    """The caller's human name, never their id - same rule as every other SCM provenance."""
    user = user or {}
    return user.get("name") or user.get("email") or None


def _assert_supplier(db: Session, supplier_id: str) -> None:
    """A file uploaded against a supplier we do not hold is a form mistake, not a 500.

    Without this the insert dies on the foreign key (or on `invalid input syntax for type
    uuid` when the field is not an id at all) and the operator is told the server broke.
    """
    try:
        _uuid.UUID(str(supplier_id))
    except (ValueError, AttributeError, TypeError):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    row = db.execute(
        text("SELECT 1 FROM suppliers WHERE id = :i"), {"i": supplier_id}
    ).first()
    if row is None:
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")


def _invoice_or_404(db: Session, invoice_id: str) -> ProformaInvoice:
    try:
        _uuid.UUID(str(invoice_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proforma invoice not found"
        )
    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).first()
    if invoice is None:
        # A 404 rather than an empty document: the id came from somewhere, and rendering
        # another company's invoice would be worse than saying no.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proforma invoice not found"
        )
    return invoice


@router.post("/proforma-invoices/preview")
async def preview_proforma_invoice(
    file: UploadFile = File(..., description="The supplier's proforma invoice"),
    supplier_id: str = Form(..., description="Which supplier sent it"),
    currency: Optional[str] = Form(
        None, description="Only needed when neither the document nor the price list says"
    ),
    _user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Every invoice the file holds, in which currency, and which codes we do not hold."""
    _assert_supplier(db, supplier_id)
    return proforma_invoice_service.preview(
        db,
        await read_upload(file),
        supplier_id=supplier_id,
        currency=currency,
        source_ref=file.filename,
    )


@router.post("/proforma-invoices/apply")
async def apply_proforma_invoice(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    supplier_id: str = Form(...),
    currency: Optional[str] = Form(None),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """One proforma invoice per document block. Re-uploading the same file updates in place."""
    _assert_supplier(db, supplier_id)
    data = await read_upload(file)
    if validate_only:
        return proforma_invoice_service.validate(
            db, data, supplier_id=supplier_id, currency=currency, source_ref=file.filename
        )

    out = proforma_invoice_service.apply(
        db,
        data,
        supplier_id=supplier_id,
        currency=currency,
        source_ref=file.filename,
        actor=_actor(current_user),
    )
    db.commit()
    return out


@router.get("/proforma-invoices")
def list_proforma_invoices(
    supplier_id: Optional[str] = Query(None, description="Whose invoices to show"),
    limit: int = Query(25, ge=1, le=100),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Invoices we have read, newest first."""
    q = db.query(ProformaInvoice)
    if supplier_id:
        q = q.filter(ProformaInvoice.supplier_id == supplier_id)
    rows = q.order_by(ProformaInvoice.created_at.desc()).limit(limit).all()
    return {
        "data": [
            proforma_invoice_service.serialize(db, r, with_lines=False) for r in rows
        ],
        "total": len(rows),
    }


@router.get("/proforma-invoices/{invoice_id}")
def get_proforma_invoice(
    invoice_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The header with every line it carries, priced as the supplier stated them."""
    return proforma_invoice_service.serialize(db, _invoice_or_404(db, invoice_id))


@router.delete("/proforma-invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proforma_invoice(
    invoice_id: str,
    _user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Hard delete, with its lines, per the CRUD standard."""
    db.delete(_invoice_or_404(db, invoice_id))
    db.commit()
