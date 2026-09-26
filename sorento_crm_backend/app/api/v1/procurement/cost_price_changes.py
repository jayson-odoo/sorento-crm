"""Cost-price change-set routes (#1288, Lane A): upload, review, apply.

Mounted at `/api/v1/procurement/cost-price-changes` under the existing `procurement` module
guard. `decide`/`decide-all`/`return`/`apply` depend on `get_current_user` ONLY (never the
API-key variant, AC-S2-19): `verify` is a Sorento-staff permission a public/automation
principal must never reach.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission, require_permission
from app.services.company_scope_resolver import apply_company_scope
from app.services.procurement import cost_price_change_service as service
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

UPLOAD_PERM = service.UPLOAD_PERM
VIEW_PERM = service.VIEW_PERM
VERIFY_PERM = service.VERIFY_PERM


def _scoped(company_scope) -> frozenset:
    return company_scope if isinstance(company_scope, (frozenset, set)) else frozenset()


@router.post("/probe")
async def probe_price_list(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(UPLOAD_PERM)),
    company_scope=Depends(apply_company_scope),
    db: Session = Depends(get_db),
):
    data = await file.read()
    return service.probe(db, data, file.filename or "upload.xlsx", company_scope=_scoped(company_scope))


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_price_list(
    file: UploadFile = File(...),
    supplier_id: str = Form(...),
    currency: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    current_user: dict = Depends(require_permission(UPLOAD_PERM)),
    company_scope=Depends(apply_company_scope),
    db: Session = Depends(get_db),
):
    data = await file.read()
    return service.upload(
        db, current_user, data=data, filename=file.filename or "upload.xlsx",
        supplier_id=supplier_id, currency=currency, start_date=start_date, end_date=end_date,
        company_scope=_scoped(company_scope),
    )


@router.get("")
async def list_change_sets(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    query: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    supplier_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    return service.list_sets(
        db, page=page, limit=limit, sort=sort, dir=dir, query=query,
        status=status_filter, supplier_id=supplier_id,
    )


@router.get("/{id}")
async def get_change_set(
    id: str,
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(id, resource="Cost price change")
    return service.get_detail(db, id, current_user)


@router.get("/{id}/lines")
async def get_change_set_lines(
    id: str,
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    return service.get_lines(db, id)


@router.patch("/{id}/lines/{line_id}")
async def patch_change_set_line(
    id: str,
    line_id: str,
    body: dict,
    current_user: dict = Depends(require_permission(UPLOAD_PERM)),
    db: Session = Depends(get_db),
):
    return service.patch_line(db, id, line_id, body, current_user)


@router.post("/{id}/submit")
async def submit_change_set(
    id: str,
    current_user: dict = Depends(require_permission(UPLOAD_PERM)),
    db: Session = Depends(get_db),
):
    return service.submit(db, id, current_user)


@router.patch("/{id}/lines/{line_id}/decision")
async def decide_change_set_line(
    id: str,
    line_id: str,
    body: dict,
    # Gated on `view` here, not `verify`: a set already applied/frozen (or any other
    # wrong status) must read 409, not 403, for a caller who can at least see the set -
    # the service checks status BEFORE the real `verify` permission for that reason.
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    return service.decide(db, id, line_id, body, current_user)


@router.post("/{id}/decide-all")
async def decide_all_change_set_lines(
    id: str,
    body: dict,
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    return service.decide_all(db, id, body.get("decision"), current_user)


@router.post("/{id}/return")
async def return_change_set(
    id: str,
    body: dict,
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    return service.return_set(db, id, body.get("reason") or "", current_user)


@router.post("/{id}/apply")
async def apply_change_set(
    id: str,
    # Which slug actually applies depends on the SET's status (`upload` for a Draft
    # staff set with verification off, `verify` for Pending) - the service enforces
    # the right one once it knows which; the route only needs the caller to hold
    # at least one of the two to reach it at all.
    current_user: dict = Depends(require_any_permission([UPLOAD_PERM, VERIFY_PERM])),
    db: Session = Depends(get_db),
):
    return service.apply(db, id, current_user)


@router.delete("/{id}")
async def discard_change_set(
    id: str,
    current_user: dict = Depends(require_permission(UPLOAD_PERM)),
    db: Session = Depends(get_db),
):
    service.discard(db, id)
    return {"message": "Discarded"}


@router.get("/{id}/source-file")
async def download_source_file(
    id: str,
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    data, filename = service.get_source_file(db, id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{id}/history")
async def get_change_set_history(
    id: str,
    current_user: dict = Depends(require_permission(VIEW_PERM)),
    db: Session = Depends(get_db),
):
    return service.get_history(db, id)
