"""Sales Targets API (plan 3.1, 3.8, 16.3; UAC S1-1 to S1-29, S6-4 to S6-7).

Slugs (S1-13): the list, a detail and the modal's options need `sales.targets.view`, or
`sales.targets.view_own`, which narrows them to the user's own agents' agent targets (AI-TOOLS-WAVE2); create
needs `.add`; a header edit, a period's figure, Duplicate and Add figure need `.edit`; DELETE
needs `.delete`. Point ratios: read with `.view`, written with `.edit`; the dealer Excel import
needs `.edit` for its dry run as well as the apply (lane SALES-TARGET-DEALER). Plain `def`
handlers: nothing here awaits (LESSONS-LEARNT), the import included (its read is synchronous).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission, require_permission
from app.schemas.download import DownloadResponse
from app.schemas.sales import (
    SalesPointRatioIn,
    SalesPointRatioList,
    SalesPointRatioOut,
    SalesTargetChildCreate,
    SalesTargetCreate,
    SalesTargetDetail,
    SalesTargetImportResult,
    SalesTargetList,
    SalesTargetOptions,
    SalesTargetPeriodUpdate,
    SalesTargetUpdate,
)
from app.services.error_handler import AppException
from app.services.sales import dealer_target_import, target_service
from app.services.uuid_path_param import validate_uuid_path
from app.utils.multi_value import multi_uuids, multi_values
from app.utils.heavy_work import heavy

router = APIRouter()
logger = logging.getLogger(__name__)

VIEW = "sales.targets.view"
ADD = "sales.targets.add"
EDIT = "sales.targets.edit"
DELETE = "sales.targets.delete"
#: Own-only (owner ruling 5 Nov, AI-TOOLS-WAVE2): without VIEW, only the agent targets of the user's own sales
#: agents (`own_scope.sales_target_clause`); the assistant's `sales_target` entity reads the same rule.
VIEW_OWN = "sales.targets.view_own"
_READ = require_any_permission([VIEW, VIEW_OWN])


def _reraise(db: Session, exc: Exception):
    # A refusal (AppException) is raised before or inside the write's savepoint, which has
    # already been rolled back, so the rest of the session stays as it was. Anything else is
    # logged here and answered with a generic message: the body never carries the error text,
    # which for a database error holds the statement and its parameters.
    if isinstance(exc, AppException):
        raise exc
    db.rollback()
    logger.exception("sales targets request failed")
    raise AppException(
        status_code=500, message="Something went wrong. Please try again.", code="INTERNAL_ERROR"
    ) from exc


def _user_id(user: dict) -> Optional[str]:
    return str(user["id"]) if user and user.get("id") else None


def _load(db: Session, target_id: str, user: Optional[dict] = None):
    validate_uuid_path(target_id, resource="Target")
    target = target_service.get_target_or_404(db, target_id)
    own = _own_agents(db, user) if user else None
    if own is not None and not (target.subject_kind == "agent" and target.sales_agent_id in own):
        # Someone else's target reads as one that does not exist (the own-scope 404 rule).
        raise AppException(status_code=404, message="Target not found.", code="NOT_FOUND")
    return target


def _own_agents(db: Session, user: dict) -> Optional[set]:
    """The user's own agent ids when they hold only VIEW_OWN; None when they see every target."""
    from app.services import own_scope

    user_id = str(user["id"])
    if not own_scope.user_is_limited(db, user_id, VIEW, VIEW_OWN):
        return None
    return set(own_scope.me(db, user_id).agent_ids)


def _own_rows(body: dict, subject: str, own: Optional[set]) -> dict:
    """The list cut to the user's own agents' agent targets; team and dealer lists empty, and the
    company-wide summary figures (unassigned sales, agents with no team) not shown."""
    if own is None:
        return body
    rows = [r for r in body["rows"] if subject == "agent" and r.get("sales_agent_id") in own]
    return {**body, "rows": rows, "unassigned_amount": 0.0, "no_team_count": 0}


@router.get("", response_model=SalesTargetList)
def list_targets(
    on: Optional[date] = Query(None),
    subject: Literal["agent", "team", "dealer"] = Query("team"),
    sales_team_id: Optional[list[str]] = Query(None),
    query: Optional[str] = Query(None),
    #: Every target of the kind, one row each, whole-range figures (Targets > Teams / Agents).
    all: bool = Query(False),
    user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    # Several teams are OR-ed; `none` (agents in no team) is a pseudo-value beside real team ids.
    picked = multi_values(sales_team_id) or []
    team_ids = [
        *(["none"] if "none" in picked else []),
        *(multi_uuids([v for v in picked if v != "none"], "Team") or []),
    ] or None
    try:
        # A dealer has no "No target" rows: its tab is always the whole list.
        own = _own_agents(db, user)
        if all or subject == "dealer":
            body = target_service.list_all_targets(
                db, subject=subject, sales_team_id=team_ids, query=query
            )
        else:
            body = target_service.list_targets(
                db, on=on, subject=subject, sales_team_id=team_ids, query=query
            )
        return _own_rows(body, subject, own)
    except Exception as exc:
        _reraise(db, exc)


# Before `/{target_id}`, which would otherwise capture it.
@router.get("/options", response_model=SalesTargetOptions)
def target_options(
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    try:
        return target_service.options(db)
    except Exception as exc:
        _reraise(db, exc)


def _ratio_out(row) -> dict:
    return {"id": row.id, "effective_from": row.effective_from, "rm_per_point": float(row.rm_per_point)}


@router.get("/point-ratios", response_model=SalesPointRatioList)
def list_point_ratios(
    _user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    try:
        return {"rows": [_ratio_out(r) for r in target_service.point_ratios(db)]}
    except Exception as exc:
        _reraise(db, exc)


@router.post("/point-ratios", response_model=SalesPointRatioOut)
def save_point_ratio(
    payload: SalesPointRatioIn,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """One ratio per date: the same date again replaces it (ruling 5, a dated history)."""
    try:
        with db.begin_nested():
            row = target_service.save_point_ratio(db, payload.effective_from, payload.rm_per_point)
        db.commit()
        return _ratio_out(row)
    except Exception as exc:
        _reraise(db, exc)


#: A dealer targets workbook is a few hundred rows; anything this size is not one.
MAX_IMPORT_BYTES = 10 * 1024 * 1024


#: The picks form field: one entry per row, a few dozen bytes each.
MAX_PICKS_BYTES = 512 * 1024


@router.get("/import/template")
@heavy
def dealer_targets_template(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    _user: dict = Depends(require_permission(EDIT)),
):
    """An empty workbook in the delivered layout plus a CUSTOMER CODE column (gate-fail item 2)."""
    year = year or target_service._today().year
    return Response(
        content=dealer_target_import.template_workbook(year),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="dealer-targets-template-{year}.xlsx"'},
    )


@router.post("/import", response_model=SalesTargetImportResult)
@heavy
def import_dealer_targets(
    file: UploadFile = File(...),
    picks: Optional[str] = Form(None),
    dry_run: bool = Query(True),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The dealer targets Excel (UAC D3): a dry run writes nothing and reports every row;
    `dry_run=false` creates or updates the targets in one transaction. `picks` (JSON, owner
    ruling 16 Oct 09:12) names, per "<sheet>!<row>", the customer the user picked for a row the
    name match left open, or "skip"."""
    try:
        data = file.file.read(MAX_IMPORT_BYTES + 1)
        if len(data) > MAX_IMPORT_BYTES:
            raise AppException(status_code=422, message="That file is too large.", code="FILE_TOO_LARGE")
        chosen = None
        if picks:
            if len(picks.encode("utf-8")) > MAX_PICKS_BYTES:
                raise AppException(status_code=422, message="Too many picks.", code="INVALID_PICKS")
            try:
                chosen = json.loads(picks)
            except (ValueError, RecursionError) as exc:
                raise AppException(status_code=422, message="Picks are not valid JSON.", code="INVALID_PICKS") from exc
        year = year or target_service._today().year
        if dry_run:
            with db.begin_nested() as nested:
                result = dealer_target_import.run(
                    db, data, year=year, dry_run=True, user_id=_user_id(user), picks=chosen
                )
                nested.rollback()
            return result
        with db.begin_nested():
            result = dealer_target_import.run(
                db, data, year=year, dry_run=False, user_id=_user_id(user), picks=chosen
            )
        db.commit()
        return result
    except Exception as exc:
        _reraise(db, exc)


#: Targets per commission statement file (TARGET-COMMISSION-VIEW): each target is one
#: achievement read, so the list's multi-select is capped rather than left unbounded.
MAX_STATEMENT_TARGETS = 50


class CommissionStatementRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)
    on: Optional[date] = None


def statement_filename(targets, now: datetime) -> str:
    """`commission-statement-TGT-000008-20261104.xlsx`, or `...-3-targets-...` for many."""
    name = targets[0].target_no if len(targets) == 1 else f"{len(targets)}-targets"
    return f"commission-statement-{name}-{now:%Y%m%d}.xlsx"


@router.post("/commission-statement", response_model=DownloadResponse)
def commission_statement(
    payload: CommissionStatementRequest = Body(default_factory=CommissionStatementRequest),
    current_user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    """The commission statement (xlsx) of one or more targets, through My Downloads (owner hand
    test, 4 Nov): the target page's figures, the tier table used and the documents behind each
    period's Achieved (TARGET-COMMISSION-VIEW).

    The order inquiry export's shape (`app/api/v1/projects/order_inquiries.py`
    `_queue_worklist_export`): every refusal (422 none / too many, 404 unknown or another
    company's target) comes BEFORE the `user_downloads` row; the row is created, the render
    enqueued on `imports`, and an enqueue failure marks the row failed and answers 503."""
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.services.sales.team_service import acting_company_id
    from app.tasks.export_tasks import generate_commission_statement_xlsx

    try:
        picked = list(dict.fromkeys(multi_uuids(payload.ids, "Targets") or []))
        if not picked:
            raise AppException(status_code=422, message="Pick at least one target.", code="NO_TARGETS")
        if len(picked) > MAX_STATEMENT_TARGETS:
            raise AppException(
                status_code=422,
                message=f"Pick at most {MAX_STATEMENT_TARGETS} targets per statement.",
                code="TOO_MANY_TARGETS",
            )
        targets = [_load(db, target_id, current_user) for target_id in picked]
        # The worker has no request scope: the caller's own company travels with the job.
        company_id = acting_company_id(db)
        on = payload.on or target_service._today()
        user_id = str(current_user["id"])
        kind = "commission_statement_xlsx"
        single = len(targets) == 1
        source = {"source_entity_type": "sales_target", "source_entity_id": targets[0].id} if single else {}
        service = DownloadService(db)
        if service.has_in_flight(user_id=user_id, kind=kind, **source):
            raise AppException(
                status_code=409,
                message="A commission statement is already being prepared - check My Downloads.",
                code="EXPORT_IN_FLIGHT",
            )
        now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).replace(tzinfo=None)
        download = service.create(
            user_id=user_id, kind=kind, filename=statement_filename(targets, now), **source
        )
        try:
            enqueue_job(
                generate_commission_statement_xlsx,
                str(download.id),
                [t.id for t in targets],
                on.isoformat(),
                user_id,
                company_id=company_id,
                queue_name="imports",
                job_timeout=600,
            )
        except Exception as exc:
            service.mark_failed(str(download.id), f"Could not queue the commission statement: {exc}")
            raise AppException(
                status_code=503,
                message="Could not queue the commission statement. Please try again.",
                code="EXPORT_NOT_QUEUED",
            ) from exc
        return DownloadResponse.model_validate(service.get(str(download.id)))
    except Exception as exc:
        _reraise(db, exc)


@router.post("", response_model=SalesTargetDetail, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: SalesTargetCreate,
    user: dict = Depends(require_permission(ADD)),
    db: Session = Depends(get_db),
):
    try:
        own = _own_agents(db, user)
        if own is not None and not (payload.subject_kind == "agent" and payload.sales_agent_id in own):
            # An own-only holder writes only their own agents' agent targets (security review, wave 2).
            raise AppException(
                status_code=403, message="You can set targets only for your own agents.", code="NOT_OWN_AGENT"
            )
        with db.begin_nested():
            target = target_service.create_target(db, payload, user_id=_user_id(user))
        db.commit()
        db.refresh(target)
        return target_service.target_detail(db, target)
    except Exception as exc:
        _reraise(db, exc)


@router.get("/{target_id}", response_model=SalesTargetDetail)
def get_target(
    target_id: str,
    on: Optional[date] = Query(None),
    user: dict = Depends(_READ),
    db: Session = Depends(get_db),
):
    try:
        return target_service.target_detail(db, _load(db, target_id, user), on=on)
    except Exception as exc:
        _reraise(db, exc)


@router.patch("/{target_id}", response_model=SalesTargetDetail)
def update_target(
    target_id: str,
    payload: SalesTargetUpdate,
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The header, the commission tiers and every changed figure in one request (F1, F2)."""
    try:
        target = _load(db, target_id, user)
        with db.begin_nested():
            target_service.update_target(db, target, payload, user_id=_user_id(user))
        db.commit()
        db.refresh(target)
        return target_service.target_detail(db, target)
    except Exception as exc:
        _reraise(db, exc)


@router.patch("/{target_id}/periods/{period_id}", response_model=SalesTargetDetail)
def update_period(
    target_id: str,
    period_id: str,
    payload: SalesTargetPeriodUpdate,
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        target = _load(db, target_id, user)
        validate_uuid_path(period_id, resource="Period")
        with db.begin_nested():
            target_service.update_period(db, target, period_id, payload.target_value)
        db.commit()
        db.refresh(target)
        return target_service.target_detail(db, target)
    except Exception as exc:
        _reraise(db, exc)


@router.post(
    "/{target_id}/duplicate", response_model=SalesTargetDetail, status_code=status.HTTP_201_CREATED
)
def duplicate_target(
    target_id: str,
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        source = _load(db, target_id, user)
        with db.begin_nested():
            copy = target_service.duplicate_target(db, source, user_id=_user_id(user))
        db.commit()
        db.refresh(copy)
        return target_service.target_detail(db, copy)
    except Exception as exc:
        _reraise(db, exc)


@router.post(
    "/{target_id}/children", response_model=SalesTargetDetail, status_code=status.HTTP_201_CREATED
)
def add_child(
    target_id: str,
    payload: SalesTargetChildCreate,
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Add figure (S1-28): returns the team target, re-summed."""
    try:
        validate_uuid_path(payload.sales_agent_id, resource="Sales Agent")
        parent = _load(db, target_id, user)
        with db.begin_nested():
            target_service.add_child(
                db, parent, payload.sales_agent_id, payload.target_value, user_id=_user_id(user)
            )
        db.commit()
        db.refresh(parent)
        return target_service.target_detail(db, parent)
    except Exception as exc:
        _reraise(db, exc)


@router.delete("/{target_id}")
def delete_target(
    target_id: str,
    user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Immediate hard delete. The screens park `sales_target.delete` instead (D7)."""
    try:
        target = _load(db, target_id, user)
        name = target.name
        with db.begin_nested():
            target_service.delete_target(db, target)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        _reraise(db, exc)
