"""CATALOG-IMAGES: read a supplier catalogue PDF, review its photos, attach them to products.

Every route needs ``dealer_kit.page.edit`` (the dealer kit owns the flyer and catalogue readers);
Attach also writes products, so it needs ``master_data.products.edit`` as well.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.services import catalogue_photo_service as svc
from app.services.dealer_kit import flyer_reading_service as flyer_svc

router = APIRouter()

_EDIT = require_permission("dealer_kit.page.edit")
_PRODUCTS_EDIT = require_permission("master_data.products.edit")
_CHUNK_BYTES = 1024 * 1024


class PhotoPatch(BaseModel):
    product_id: Optional[str] = None
    decision: Optional[Literal["attach", "skip", "keep_both", "replace"]] = None
    also_attach_product_ids: Optional[list[str]] = None


async def _read_within_limit(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        flyer_svc.assert_within_limit(total)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_catalogue(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
) -> dict:
    data = await _read_within_limit(file)
    await run_in_threadpool(svc.check_upload, data, file.content_type)

    def _create() -> dict:
        reading = svc.create_from_upload(
            db, file_name=file.filename or "catalogue.pdf", data=data, user_id=user.get("id")
        )
        return svc.detail(db, reading)

    return await run_in_threadpool(_create)


@router.get("/{reading_id}")
def get_reading(reading_id: str, db: Session = Depends(get_db), user: dict = Depends(_EDIT)) -> dict:
    return svc.detail(db, svc.get_reading(db, reading_id))


@router.get("/{reading_id}/photos")
def list_photos(
    reading_id: str,
    tab: Literal["ready", "duplicate", "needs_product", "skipped"] = Query("ready"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: Literal["asc", "desc"] = Query("asc"),
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
) -> dict:
    reading = svc.get_reading(db, reading_id)
    return svc.list_photos(db, reading, tab=tab, page=page, limit=limit, sort=sort, direction=dir)


@router.patch("/{reading_id}/photos/{photo_id}")
def patch_photo(
    reading_id: str,
    photo_id: str,
    body: PhotoPatch,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
) -> dict:
    reading = svc.get_reading(db, reading_id)
    return svc.patch_photo(db, reading, photo_id, body.model_dump(exclude_unset=True))


@router.post("/{reading_id}/attach")
def attach(
    reading_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
    _products: dict = Depends(_PRODUCTS_EDIT),
) -> dict:
    reading = svc.get_reading(db, reading_id)
    return svc.attach(db, reading, user.get("id"))
