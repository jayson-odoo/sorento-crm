"""Stock Debt snapshots: the board frozen at a moment, with a decision per product
(STOCK-DEBT-SNAPSHOT, AC-1 .. AC-18).

    POST /project-sales/stock-debt/snapshots
    GET  /project-sales/stock-debt/snapshots
    GET  /project-sales/stock-debt/snapshots/{id}
    GET  /project-sales/stock-debt/snapshots/{id}/rows
    GET  /project-sales/stock-debt/snapshots/{id}/rows/{row_id}/lines
    PUT  /project-sales/stock-debt/snapshots/{id}/rows/{row_id}/decision
    POST /project-sales/stock-debt/snapshots/{id}/export
    GET  /project-sales/stock-debt/snapshots/{id}/rows/{row_id}/po-link
    POST /project-sales/stock-debt/snapshots/{id}/rows/{row_id}/po-link/link
    POST /project-sales/stock-debt/snapshots/{id}/rows/{row_id}/po-link/unlink
    POST /project-sales/stock-debt/snapshots/{id}/rows/{row_id}/po-link/relink
    POST /project-sales/stock-debt/po-link/relocate
    POST /project-sales/stock-debt/po-link/operations/{operation_id}/resume

The PO link routes (AC-LINK-CRM-UI) need `projects.stock_debt.link_po`: they write to AutoCount
through the Shared Service.

Delete is the deferred action `stock_debt_snapshot.delete` (`app/services/record_actions.py`),
not a route. Every route needs `projects.stock_debt.view` and is session only (`require_permission`): a snapshot
carries order inquiry data, so there is no API-key read.
Mounted before the stock debt router so the literal `snapshots` segment is never read as a
`{product_id}`.
"""
from __future__ import annotations

from typing import Optional, get_args

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.download import DownloadResponse
from app.schemas.stock_debt_snapshot import (
    DecisionFilter,
    PoLinkIn,
    PoLinkOptions,
    PoLinkResult,
    PoLinkResults,
    PoRelinkIn,
    PoRelocateIn,
    PoResumeIn,
    PoUnlinkIn,
    SnapshotCreate,
    SnapshotDecisionIn,
    SnapshotDetail,
    SnapshotExportIn,
    SnapshotLineList,
    SnapshotList,
    SnapshotRow,
    SnapshotRowList,
)
from app.services.error_handler import AppException, handle_internal_error
from app.services.scm.stock_debt_po_link_service import StockDebtPoLinkService
from app.services.scm.stock_debt_snapshot_service import StockDebtSnapshotService
from app.services.uuid_path_param import validate_uuid_path
from app.utils.multi_value import multi_choices

router = APIRouter()

VIEW = "projects.stock_debt.view"
LINK_PO = "projects.stock_debt.link_po"
BASE = "/stock-debt/snapshots"


@router.post(BASE, response_model=SnapshotDetail, status_code=201)
def create_snapshot(
    payload: SnapshotCreate,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Freeze the board for the filters given. Plain `def`: one synchronous read of the book."""
    try:
        service = StockDebtSnapshotService(db)
        snapshot = service.create(
            name=payload.name,
            filters=payload.filters.model_dump(),
            user_id=str(current_user["id"]),
        )
        return service.get(str(snapshot.id), str(current_user["id"]))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(BASE, response_model=SnapshotList)
def list_snapshots(
    query: Optional[str] = Query(None, description="Matches the snapshot name."),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return StockDebtSnapshotService(db).list(
            user_id=str(current_user["id"]), query=query, page=page, limit=limit
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(BASE + "/{snapshot_id}", response_model=SnapshotDetail)
def get_snapshot(
    snapshot_id: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(snapshot_id, resource="Snapshot")
        return StockDebtSnapshotService(db).get(snapshot_id, str(current_user["id"]))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(BASE + "/{snapshot_id}/rows", response_model=SnapshotRowList)
def list_snapshot_rows(
    snapshot_id: str,
    query: Optional[str] = Query(None, description="Product code or name."),
    # Several are OR-ed; `undecided` / `decided` combine with the real values (FILTER-MULTISELECT PR6).
    decision: Optional[list[str]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    decisions = multi_choices(decision, get_args(DecisionFilter), "decision")
    try:
        validate_uuid_path(snapshot_id, resource="Snapshot")
        return StockDebtSnapshotService(db).rows(
            snapshot_id, query=query, decision=decisions, page=page, limit=limit
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(BASE + "/{snapshot_id}/rows/{row_id}/lines", response_model=SnapshotLineList)
def snapshot_row_lines(
    snapshot_id: str,
    row_id: str,
    month: Optional[str] = Query(
        None, description="One bucket: `YYYY-MM`, `tba`, `undated` or `unlocated`."
    ),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(snapshot_id, resource="Snapshot")
        validate_uuid_path(row_id, resource="Snapshot row")
        return StockDebtSnapshotService(db).lines(
            snapshot_id, row_id, month, str(current_user["id"])
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(BASE + "/{snapshot_id}/rows/{row_id}/decision", response_model=SnapshotRow)
def set_snapshot_decision(
    snapshot_id: str,
    row_id: str,
    payload: SnapshotDecisionIn,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(snapshot_id, resource="Snapshot")
        validate_uuid_path(row_id, resource="Snapshot row")
        return StockDebtSnapshotService(db).set_decision(
            snapshot_id,
            row_id,
            user_id=str(current_user["id"]),
            decision=payload.decision,
            warehouse_id=payload.warehouse_id,
            note=payload.note,
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(BASE + "/{snapshot_id}/export", response_model=DownloadResponse, status_code=201)
def export_snapshot(
    snapshot_id: str,
    payload: SnapshotExportIn,
    # Session only, for the reason `export_stock_debt` gives: a download row and a worker job
    # are a write.
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Queue the workbook of the STORED snapshot through My Downloads, the pipeline
    `export_stock_debt` uses. The guards run before any `user_downloads` row exists."""
    from app.api.v1.projects._common import acting_company_id
    from app.services.download_service import DownloadService
    from app.services.pdf_render import in_malaysia
    from app.services.queue_service import enqueue_job
    from app.tasks.export_tasks import generate_stock_debt_snapshot_xlsx

    try:
        validate_uuid_path(snapshot_id, resource="Snapshot")
        snapshot = StockDebtSnapshotService(db)._get_snapshot(snapshot_id)
        user_id = str(current_user["id"])
        if DownloadService(db).has_in_flight(user_id=user_id, kind="stock_debt_snapshot_xlsx"):
            raise AppException(
                status_code=409,
                message="A snapshot export is already being prepared - check My Downloads.",
            )
        company_id = acting_company_id(db)
        # `created_at` is naive UTC; the filename carries the office's day (AC-16), so a
        # snapshot taken 00:00-08:00 Malaysia time is not dated the day before.
        taken_on = in_malaysia(snapshot.created_at).strftime("%d%m%Y")
        download = DownloadService(db).create(
            user_id=user_id,
            kind="stock_debt_snapshot_xlsx",
            filename=f"stock-debt-snapshot-{taken_on}.xlsx",
        )
        try:
            enqueue_job(
                generate_stock_debt_snapshot_xlsx,
                str(download.id),
                user_id,
                snapshot_id,
                split=payload.split,
                show_aux=payload.show_aux,
                company_id=company_id,
                queue_name="imports",
                job_timeout=600,
            )
        except Exception as e:  # noqa: BLE001
            DownloadService(db).mark_failed(
                str(download.id), f"Could not queue snapshot export: {e}"
            )
            raise AppException(
                status_code=503,
                message="Could not queue snapshot export. Please try again.",
            )
        return DownloadResponse.model_validate(DownloadService(db).get(str(download.id)))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# --------------------------------------------------------------- PO link (AC-LINK-CRM-UI)

PO_LINK = BASE + "/{snapshot_id}/rows/{row_id}/po-link"


SWITCHED_OFF = "AutoCount links from Stock Debt are switched off in Settings."


def _require_switch(db: Session) -> None:
    """Owner, 5 Nov: the PO actions stay inert until the switch is on (System Settings)."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if not bool(getattr(row, "stock_debt_po_link_enabled", False)):
        raise AppException(status_code=403, message=SWITCHED_OFF)


def _guard(exc: Exception):
    raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(PO_LINK, response_model=PoLinkOptions)
def po_link_options(
    snapshot_id: str,
    row_id: str,
    current_user: dict = Depends(require_permission(LINK_PO)),
    db: Session = Depends(get_db),
):
    """What AutoCount can do now, and the open PO lines of the row's product."""
    validate_uuid_path(snapshot_id, resource="Snapshot")
    validate_uuid_path(row_id, resource="Snapshot row")
    _require_switch(db)
    try:
        return StockDebtPoLinkService(db).options(snapshot_id, row_id)
    except Exception as exc:
        _guard(exc)


@router.post(PO_LINK + "/link", response_model=PoLinkResults)
def po_link_link(
    snapshot_id: str,
    row_id: str,
    payload: PoLinkIn,
    current_user: dict = Depends(require_permission(LINK_PO)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(snapshot_id, resource="Snapshot")
    validate_uuid_path(row_id, resource="Snapshot row")
    _require_switch(db)
    try:
        out = StockDebtPoLinkService(db, current_user).link(
            snapshot_id, row_id, [line.model_dump() for line in payload.lines]
        )
        db.commit()
        return out
    except Exception as exc:
        _guard(exc)


@router.post(PO_LINK + "/unlink", response_model=PoLinkResults)
def po_link_unlink(
    snapshot_id: str,
    row_id: str,
    payload: PoUnlinkIn,
    current_user: dict = Depends(require_permission(LINK_PO)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(snapshot_id, resource="Snapshot")
    validate_uuid_path(row_id, resource="Snapshot row")
    _require_switch(db)
    try:
        out = StockDebtPoLinkService(db, current_user).unlink(snapshot_id, row_id, payload.po_line_ids)
        db.commit()
        return out
    except Exception as exc:
        _guard(exc)


@router.post(PO_LINK + "/relink", response_model=PoLinkResults)
def po_link_relink(
    snapshot_id: str,
    row_id: str,
    payload: PoRelinkIn,
    current_user: dict = Depends(require_permission(LINK_PO)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(snapshot_id, resource="Snapshot")
    validate_uuid_path(row_id, resource="Snapshot row")
    _require_switch(db)
    try:
        out = StockDebtPoLinkService(db, current_user).relink(
            snapshot_id, row_id, [move.model_dump() for move in payload.moves]
        )
        db.commit()
        return out
    except Exception as exc:
        _guard(exc)


@router.post("/stock-debt/po-link/relocate", response_model=PoLinkResult)
def po_link_relocate(
    payload: PoRelocateIn,
    current_user: dict = Depends(require_permission(LINK_PO)),
    db: Session = Depends(get_db),
):
    """Move a linked PO row to its SO row's location (after `LOCATION_NOT_MOVED`)."""
    _require_switch(db)
    try:
        validate_uuid_path(payload.po_line_id, resource="PO line")
        out = StockDebtPoLinkService(db, current_user).relocate(payload.po_line_id)
        db.commit()
        return out
    except Exception as exc:
        _guard(exc)


@router.post("/stock-debt/po-link/operations/{operation_id}/resume", response_model=PoLinkResult)
def po_link_resume(
    operation_id: str,
    payload: PoResumeIn,
    current_user: dict = Depends(require_permission(LINK_PO)),
    db: Session = Depends(get_db),
):
    """Ask the Shared Service to re-read AutoCount and finish an operation it stopped."""
    _require_switch(db)
    try:
        validate_uuid_path(payload.po_line_id, resource="PO line")
        out = StockDebtPoLinkService(db, current_user).resume(
            operation_id, payload.po_line_id, payload.sales_order_line_id
        )
        db.commit()
        return out
    except Exception as exc:
        _guard(exc)
