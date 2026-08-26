"""Proforma invoices: the supplier's priced document, uploaded and held (G3b).

Same two-step shape as every other upload channel here - `preview` and `?validate_only=true`
describe, `apply` writes - because a proforma can carry five invoices at once and nothing
should be written from a single click.

The supplier travels with the file because the file never says reliably who wrote it: Kailu's
letterhead is a Hong Kong management company, Jinbaichuan's is a title cell in Chinese. The
currency does NOT have to travel with it: the document usually states it and the supplier's
price list often does, so the form field is the last resort rather than the first question
(AC-P3.1).

No SQL is written in here; the handlers call service functions that do their own scoped reads. Every read, every lookup and every refusal lives in
`proforma_invoice_service`; this module takes the HTTP shape apart, calls one function and
commits. That is the layering rule, and it is also what makes the company scope impossible to
forget - a raw supplier SELECT written here would have bypassed the ORM's filter.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service
from app.services.scm.upload_intake import read_upload

router = APIRouter()

# Writing a supplier's document of record is the operator's capability, not the reader's, so
# it sits behind its own permission - swept onto whoever already runs the module's uploads
# by migration 375.
_UPLOAD = require_permission("scm.proforma_invoice.upload")
_READ = require_permission("scm.dashboard.view")
# The convert action WRITES an inbound shipment, so it sits behind the same permission the
# packing-list channel's own writes use (`fulfilment.py`'s `_WRITE`), not the proforma
# upload permission - it is a shipment write that happens to be triggered from this screen.
_SHIPMENT_WRITE = require_permission("scm.reorder.run")


class ConvertToDraftShipmentRequest(BaseModel):
    proforma_invoice_ids: List[str] = Field(
        ..., min_length=1, description="One or more proforma invoices to draft into one shipment."
    )
    override_capacity: bool = Field(
        False, description="Load the container even though it is over its planned volume."
    )
    override_reason: Optional[str] = Field(
        None, description="Why it is being loaded anyway. Required with `override_capacity`."
    )
    line_quantities: Optional[Dict[str, float]] = Field(
        None,
        description="Per PI line id, how much to place. A line left out places what it has "
                    "left, which is the normal case (AC-F10).",
    )
    target_shipment_id: Optional[str] = Field(
        None,
        description="An existing DRAFT packing list to add to, instead of creating one.",
    )


class ProformaInvoiceUpdate(BaseModel):
    container_size_id: Optional[str] = Field(
        None, description="Which box this invoice is fitted into. Null = the tenant default."
    )


class ProformaLineUpdate(BaseModel):
    qty: float = Field(..., ge=0, description="Sorento's own quantity. The supplier's is kept.")


class MarkAsRevisionRequest(BaseModel):
    previous_id: str = Field(..., description="The invoice this one is a revision of.")


def _revision_map(raw: Optional[str]) -> Optional[dict]:
    """`{"<document index>": "<invoice id>"}` off the multipart form, or nothing.

    A JSON field rather than one id, because one FILE holds several documents (the
    pre-loading list is five) and the operator answers "is this a revision" per document.
    Sent as a string because the rest of this upload is multipart, not JSON.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise AppException(422, "Could not read which invoices this file revises.",
                           detail="revision_of")
    if not isinstance(parsed, dict):
        raise AppException(422, "Could not read which invoices this file revises.",
                           detail="revision_of")
    return {str(k): v for k, v in parsed.items() if v}


class BulkDeleteRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)


def _actor(user: Optional[dict]) -> Optional[str]:
    """The caller's human name, never their id - same rule as every other SCM provenance."""
    user = user or {}
    return user.get("name") or user.get("email") or None


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
    proforma_invoice_service.assert_supplier(db, supplier_id)
    data = await read_upload(file)
    return await run_in_threadpool(
        proforma_invoice_service.preview,
        db,
        data,
        supplier_id=supplier_id,
        currency=currency,
        source_ref=file.filename,
    )


@router.post("/proforma-invoices/apply")
async def apply_proforma_invoice(
    file: UploadFile = File(..., description="The same file the preview was taken from"),
    supplier_id: str = Form(...),
    currency: Optional[str] = Form(None),
    revision_of: Optional[str] = Form(
        None,
        description='{"<document index>": "<invoice id>"} - which documents in this file '
                    "supersede an invoice already on file (AC-E7).",
    ),
    validate_only: bool = Query(
        False,
        description="Test the file and write nothing. Returns {valid, errors, warnings, summary}.",
    ),
    current_user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """One proforma invoice per document block. Re-uploading the same file updates in place."""
    proforma_invoice_service.assert_supplier(db, supplier_id)
    data = await read_upload(file)
    if validate_only:
        return await run_in_threadpool(
            proforma_invoice_service.validate,
            db,
            data,
            supplier_id=supplier_id,
            currency=currency,
            source_ref=file.filename,
        )

    out = await run_in_threadpool(
        proforma_invoice_service.apply,
        db,
        data,
        supplier_id=supplier_id,
        currency=currency,
        source_ref=file.filename,
        actor=_actor(current_user),
        revision_of=_revision_map(revision_of),
    )
    db.commit()
    return out


@router.post("/proforma-invoices/convert-to-draft-shipment", status_code=status.HTTP_201_CREATED)
def convert_proforma_invoices_to_draft_shipment(
    payload: ConvertToDraftShipmentRequest = Body(...),
    current_user: dict = Depends(_SHIPMENT_WRITE),
    db: Session = Depends(get_db),
):
    """One or more proforma invoices become one DRAFT inbound shipment (`/scm/incoming`).

    A container is routinely several factories' PIs landing in the same box, so more than
    one invoice - from different suppliers - is not a mistake; every shipment line still
    carries its own supplier. The real packing list, when it arrives, is uploaded through
    the existing `/scm/packing-lists/apply` path, unchanged by this action.
    """
    out = proforma_invoice_service.convert_to_draft_shipment(
        db,
        payload.proforma_invoice_ids,
        created_by=(current_user or {}).get("id"),
        override_capacity=payload.override_capacity,
        override_reason=payload.override_reason,
        line_quantities=payload.line_quantities,
        target_shipment_id=payload.target_shipment_id,
    )
    db.commit()
    return out


@router.post("/proforma-invoices/bulk-delete")
def bulk_delete_proforma_invoices(
    payload: BulkDeleteRequest = Body(...),
    _user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Hard delete several proforma invoices at once. A PI already converted to a draft
    shipment is refused, not silently skipped - the response names which ones and why.
    """
    out = proforma_invoice_service.bulk_delete(db, payload.ids)
    db.commit()
    return out


@router.get("/proforma-invoices")
def list_proforma_invoices(
    supplier_id: Optional[str] = Query(None, description="Whose invoices to show"),
    placement: Optional[str] = Query(
        None,
        description="not_converted / converted / split - where the goods have got to (AC-F6).",
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, description="Skip this many, so a second page is reachable"),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Invoices we have read, newest first. `total` counts all of them, not just this page."""
    return proforma_invoice_service.list_for_supplier(
        db, supplier_id=supplier_id, placement=placement, limit=limit, offset=offset
    )


# Declared BEFORE `/proforma-invoices/{invoice_id}`: a literal path that comes after a
# path parameter is swallowed by it, and the id lookup would answer 404 for this route.
@router.get("/proforma-invoices/draft-shipments")
def list_draft_shipments(
    supplier_id: Optional[str] = Query(
        None, description="Only the drafts already carrying this factory's goods"
    ),
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The draft packing lists a convert can be ADDED to (AC-F10)."""
    return {"data": proforma_invoice_service.draft_shipments(db, supplier_id=supplier_id)}


@router.get("/inbound-shipments/{shipment_id}/source-proforma-invoices")
def source_proforma_invoices_for_shipment(
    shipment_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """Which proforma invoices this container was drafted from (AC-F9).

    One endpoint for the four places that show it - the Details card, the Lines column, the
    Timeline entry and the Documents list - because they are four readings of the same link
    rows, and four fetches would be four chances for them to disagree.
    """
    return proforma_invoice_service.source_proforma_invoices(db, shipment_id)


@router.post("/proforma-invoices/{invoice_id}/mark-as-revision-of")
def mark_proforma_invoice_as_revision(
    invoice_id: str,
    payload: MarkAsRevisionRequest = Body(...),
    _user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Link a PI uploaded as new to the document it actually revises (AC-E11)."""
    out = proforma_invoice_service.mark_as_revision_of(db, invoice_id, payload.previous_id)
    db.commit()
    return out


@router.get("/proforma-invoices/{invoice_id}/export")
def export_proforma_invoice(
    invoice_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The adjusted invoice as a workbook, in the supplier's own block layout (AC-E4)."""
    payload = proforma_invoice_service.serialize(
        db, proforma_invoice_service.get_or_404(db, invoice_id)
    )
    filename = proforma_invoice_service.export_filename(payload)
    return Response(
        content=proforma_invoice_service.to_xlsx(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/proforma-invoices/{invoice_id}")
def update_proforma_invoice(
    invoice_id: str,
    payload: ProformaInvoiceUpdate = Body(...),
    _user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Which container this invoice is being fitted into (AC-D4)."""
    out = proforma_invoice_service.set_container_size(
        db, invoice_id, payload.container_size_id
    )
    db.commit()
    return out


@router.patch("/proforma-invoices/{invoice_id}/lines/{line_id}")
def adjust_proforma_invoice_line(
    invoice_id: str,
    line_id: str,
    payload: ProformaLineUpdate = Body(...),
    current_user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Sorento's own quantity for one line. `supplier_qty` is never touched (AC-E2).

    Returns the WHOLE invoice, not the line: the fill bar, the totals and the was/now
    figures all move together, and a caller re-reading them one at a time would paint a
    document that briefly disagrees with itself.
    """
    out = proforma_invoice_service.adjust_line(
        db, invoice_id, line_id, qty=payload.qty, actor=_actor(current_user)
    )
    db.commit()
    return out


@router.delete("/proforma-invoices/{invoice_id}/lines/{line_id}")
def remove_proforma_invoice_line(
    invoice_id: str,
    line_id: str,
    current_user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Hard delete of one line - it is not going in this container. Returns the invoice."""
    out = proforma_invoice_service.remove_line(
        db, invoice_id, line_id, actor=_actor(current_user)
    )
    db.commit()
    return out


@router.get("/proforma-invoices/{invoice_id}")
def get_proforma_invoice(
    invoice_id: str,
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The header with every line it carries, priced as the supplier stated them."""
    return proforma_invoice_service.serialize(
        db, proforma_invoice_service.get_or_404(db, invoice_id)
    )


@router.delete("/proforma-invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proforma_invoice(
    invoice_id: str,
    _user: dict = Depends(_UPLOAD),
    db: Session = Depends(get_db),
):
    """Hard delete, with its lines, per the CRUD standard."""
    proforma_invoice_service.delete(db, invoice_id)
    db.commit()
