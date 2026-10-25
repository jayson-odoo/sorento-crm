"""BARCODE-IMPORT: set product barcodes from a sheet, Test (preview) then Apply.

Both routes are gated on `master_data.products.edit`: apply writes products, and preview
reads the whole catalogue's codes and barcodes back.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services import product_barcode_import_service as svc

router = APIRouter()

_EDIT = require_permission("master_data.products.edit")


@router.post("/barcode-import/preview")
async def preview_barcode_import(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: dict = Depends(_EDIT)
) -> dict[str, Any]:
    """What the file would do, per row, plus the token apply needs. Writes nothing."""
    data, name = await svc.read_barcode_upload(file)
    return await run_in_threadpool(svc.preview, db, data, name, user_id=user.get("id"))


@router.post("/barcode-import/apply")
async def apply_barcode_import(
    file: UploadFile = File(...),
    preview_token: str = Form(""),
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
) -> dict[str, Any]:
    """Write only the New and Change rows, in one transaction. Refused (409) unless the token
    covers this file, user and active company."""
    data, name = await svc.read_barcode_upload(file)
    await run_in_threadpool(svc.check_preview_token, data, user.get("id"), preview_token, db)

    def _apply_and_commit() -> dict[str, Any]:
        out = svc.apply(db, data, name)
        db.commit()
        return out

    return await run_in_threadpool(_apply_and_commit)
