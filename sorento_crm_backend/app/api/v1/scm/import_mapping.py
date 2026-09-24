"""The inline import column mapper's own two endpoints (B4/B5,
PLAN-import-column-mapper-24sep.md): probe a supplier file's headers, and save what the
operator picked. The FE's `importMappingService.ts` is the contract this module answers -
built against it first (Phase 1, mocked), wired for real here (Phase 2).

Guard: `require_any_permission` over the union of the permissions the doc types' OWN
upload endpoints already require - `scm.proforma_invoice.upload` (proforma invoice /
packing list, `proforma_invoices.py`) and `scm.reorder.run` (stock list, `fulfilment.py`).
A caller who can reach either page already holds one of the two; a combined-doc_types save
from the Upload supplier documents dialog only ever needs the ONE its caller already has,
never both (T4's own combined-save case grants only the proforma one).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission
from app.services.scm import import_mapping_service
from app.services.scm.supplier_scope import assert_supplier
from app.services.scm.upload_intake import read_upload

router = APIRouter()

_MAP = require_any_permission(["scm.proforma_invoice.upload", "scm.reorder.run"])


class ImportMappingRow(BaseModel):
    header: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)


class ImportMappingSaveRequest(BaseModel):
    supplier_id: str
    doc_types: List[str] = Field(..., min_length=1)
    mappings: List[ImportMappingRow] = Field(default_factory=list)


@router.post("/import-mapping/probe")
async def probe_import_mapping(
    file: UploadFile = File(..., description="The supplier's file"),
    supplier_id: str = Form(...),
    doc_types: List[str] = Form(
        ..., description="One entry normally; two for a combined file (G4/AC-M13)."
    ),
    header_row: Optional[int] = Form(
        None, description="The stepper's current pick (AC-M3); omitted on the first probe."
    ),
    _user: dict = Depends(_MAP),
    db: Session = Depends(get_db),
):
    """Every column the file's own shape names, with what this supplier's resolver
    already knows about each one."""
    assert_supplier(db, supplier_id)
    data = await read_upload(file)
    return await run_in_threadpool(
        import_mapping_service.probe,
        db,
        data,
        supplier_id=supplier_id,
        doc_types=doc_types,
        header_row=header_row,
    )


@router.post("/import-mapping/save")
def save_import_mapping(
    payload: ImportMappingSaveRequest,
    _user: dict = Depends(_MAP),
    db: Session = Depends(get_db),
):
    """Upsert this supplier's mapping - a re-map replaces, never accumulates (AC-M6)."""
    assert_supplier(db, payload.supplier_id)
    import_mapping_service.save(
        db,
        supplier_id=payload.supplier_id,
        doc_types=payload.doc_types,
        mappings=[(row.header, row.field) for row in payload.mappings],
    )
    db.commit()
    return {"ok": True}
