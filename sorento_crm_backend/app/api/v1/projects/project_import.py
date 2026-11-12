"""Project import runs (PLAN-project-import-12nov.md, "Routes"; AC-PI-08..11, 36, 39..41).

    GET  /projects/import/runs                      projects.import.view
    POST /projects/import/runs                      projects.import.run   (multipart `file`)
    GET  /projects/import/runs/{run_id}             projects.import.view
    PUT  /projects/import/runs/{run_id}/columns     projects.import.run
    GET  /projects/import/runs/{run_id}/lines       projects.import.view
    PUT  /projects/import/runs/{run_id}/lines       projects.import.run
    PUT  /projects/import/runs/{run_id}/lines/bulk  projects.import.run
    POST /projects/import/runs/{run_id}/preview     projects.import.run
    GET  /projects/import/runs/{run_id}/rows        projects.import.view
    POST /projects/import/runs/{run_id}/import      projects.import.run   (202, queued)

Revert is the deferred record action `project_import_run.revert`
(`app/services/record_actions.py`), parked through `/api/v1/pending-actions`.
A run of another company reads as 404. Session only (`require_permission`).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error
from app.services.project_import import service
from app.utils.multi_value import multi_values

router = APIRouter()

VIEW = "projects.import.view"
RUN = "projects.import.run"


class ColumnsIn(BaseModel):
    sheets: list[str] = Field(default_factory=list)
    columns: dict[str, Optional[str]] = Field(default_factory=dict)


class LineIn(BaseModel):
    kind: str
    customer_value_key: Optional[str] = ""
    value_key: str
    action: str
    target_id: Optional[str] = None
    new_title: Optional[str] = None


class BulkLinesIn(BaseModel):
    kind: str
    keys: list[list[str]] = Field(default_factory=list, max_length=5000)
    action: str
    target_id: Optional[str] = None
    new_title: Optional[str] = None


def _raise(exc: Exception):
    raise exc if hasattr(exc, "status_code") else handle_internal_error("The import request failed.")


@router.get("/runs")
def list_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    status: Optional[list[str]] = Query(None),
    uploaded_by: Optional[list[str]] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return service.list_runs(
            db, page=page, limit=limit, sort=sort, direction=dir, query=query,
            status=multi_values(status, "status"), uploaded_by=multi_values(uploaded_by, "uploaded_by"),
        )
    except Exception as exc:
        _raise(exc)


@router.post("/runs", status_code=201)
def create_run(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(RUN)),
    db: Session = Depends(get_db),
):
    from app.api.v1.projects._common import acting_company_id

    try:
        content = file.file.read(service.MAX_UPLOAD_BYTES + 1)
        run = service.create_run(
            db, company_id=acting_company_id(db), user_id=str(current_user["id"]),
            filename=file.filename or "upload.xlsx", content=content,
        )
        db.commit()
        return service.serialize_run(db, run, full=True)
    except Exception as exc:
        db.rollback()
        _raise(exc)


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return service.serialize_run(db, service.get_run(db, run_id), full=True)
    except Exception as exc:
        _raise(exc)


@router.put("/runs/{run_id}/columns")
def save_columns(
    run_id: str,
    payload: ColumnsIn,
    current_user: dict = Depends(require_permission(RUN)),
    db: Session = Depends(get_db),
):
    try:
        run = service.get_run(db, run_id)
        service.save_columns(
            db, run, sheets=payload.sheets,
            columns={k: v for k, v in payload.columns.items() if v},
            user_id=str(current_user["id"]),
        )
        db.commit()
        return service.serialize_run(db, run, full=True)
    except Exception as exc:
        db.rollback()
        _raise(exc)


@router.get("/runs/{run_id}/lines")
def list_lines(
    run_id: str,
    kind: str = Query(...),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        run = service.get_run(db, run_id)
        lines = service.list_lines(db, run, kind=kind, status=status)
        todo = sum(1 for line in lines if line["status"] == "todo") if not status else None
        return {"data": lines, "total": len(lines), "todo": todo}
    except Exception as exc:
        _raise(exc)


@router.put("/runs/{run_id}/lines")
def set_line(
    run_id: str,
    payload: LineIn,
    current_user: dict = Depends(require_permission(RUN)),
    db: Session = Depends(get_db),
):
    try:
        run = service.get_run(db, run_id)
        line = service.set_line(
            db, run, kind=payload.kind, value_key=payload.value_key,
            customer_value_key=payload.customer_value_key or "", action=payload.action,
            target_id=payload.target_id, new_title=payload.new_title,
            user_id=str(current_user["id"]),
        )
        db.commit()
        return line
    except Exception as exc:
        db.rollback()
        _raise(exc)


@router.put("/runs/{run_id}/lines/bulk")
def bulk_set(
    run_id: str,
    payload: BulkLinesIn,
    current_user: dict = Depends(require_permission(RUN)),
    db: Session = Depends(get_db),
):
    from app.services.error_handler import AppException

    try:
        run = service.get_run(db, run_id)
        keys = []
        for pair in payload.keys:
            if len(pair) != 2:
                raise AppException(422, "Each key is [customer value, value].", code="project_import_key_invalid")
            keys.append((pair[0], pair[1]))
        lines = service.bulk_set(
            db, run, kind=payload.kind, keys=keys, action=payload.action,
            target_id=payload.target_id, new_title=payload.new_title,
            user_id=str(current_user["id"]),
        )
        db.commit()
        return {"data": lines}
    except Exception as exc:
        db.rollback()
        _raise(exc)


@router.post("/runs/{run_id}/preview")
def preview(
    run_id: str,
    current_user: dict = Depends(require_permission(RUN)),
    db: Session = Depends(get_db),
):
    try:
        run = service.get_run(db, run_id)
        report = service.preview(db, run, user_id=str(current_user["id"]))
        db.commit()
        return {"counts": report["counts"], "codes": report["codes"],
                "sheet_errors": report["sheet_errors"]}
    except Exception as exc:
        db.rollback()
        _raise(exc)


@router.get("/runs/{run_id}/rows")
def list_rows(
    run_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    outcome: Optional[list[str]] = Query(None),
    code: Optional[list[str]] = Query(None),
    sheet: Optional[list[str]] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        run = service.get_run(db, run_id)
        return service.list_rows(
            db, run, page=page, limit=limit, query=query,
            outcome=multi_values(outcome, "outcome"), code=multi_values(code, "code"),
            sheet=multi_values(sheet, "sheet"),
        )
    except Exception as exc:
        _raise(exc)


@router.post("/runs/{run_id}/import", status_code=202)
def start_import(
    run_id: str,
    current_user: dict = Depends(require_permission(RUN)),
    db: Session = Depends(get_db),
):
    try:
        run = service.get_run(db, run_id)
        job_id = service.start_import(db, run, user_id=str(current_user["id"]))
        db.commit()
        return {"job_id": job_id}
    except Exception as exc:
        db.rollback()
        _raise(exc)
