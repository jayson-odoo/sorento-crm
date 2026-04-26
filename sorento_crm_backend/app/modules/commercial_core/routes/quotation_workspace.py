"""Master quotation revision workspace API."""
from __future__ import annotations

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.modules.commercial_core.schemas.quotation_messaging import (
    QuotationEmailPreviewRequest,
    QuotationEmailPreviewResponse,
    QuotationEmailSendRequest,
    QuotationEmailSendResponse,
)
from app.modules.commercial_core.schemas.commercial_quotations import (
    ApplyQuotationPackageTemplateBody,
    EntityAttachmentLinkItem,
    LinkAttachmentBody,
    MasterQuotationAdvanceBody,
    MasterQuotationAttachmentLinkBody,
    MasterQuotationCompareRow,
    MasterQuotationDetailResponse,
    MasterQuotationListItem,
    MasterQuotationTableRow,
    MasterQuotationTaskBoardSchedulePreviewRequest,
    MasterQuotationTaskBoardSchedulePreviewResponse,
    MasterQuotationUpdate,
    PricingApprovalDecision,
    ProjectMasterQuotationCreate,
    QuotationRevisionCreate,
    QuotationRevisionResponse,
    QuotationRevisionUpdate,
    QuotationStageBrief,
    SetRevisionPointerBody,
    WorkspaceActivityCreate,
    WorkspaceActivityOut,
    WorkspaceActivityPatch,
)
from app.schemas.common import ListResponse, PaginationResponse
from app.modules.commercial_core.services import commercial_master_quotation_workspace_service as mq_ws
from app.modules.commercial_core.services.commercial_pipeline_service import CommercialPipelineService
from app.modules.commercial_core.services.commercial_hierarchy_service import CommercialHierarchyError
from app.modules.commercial_core.services.commercial_hierarchy_service import ToleranceAdvanceConfirmationRequired
from app.modules.commercial_core.services.commercial_quotation_price_policy import (
    collect_tolerance_breaches,
    complete_pricing_approval,
    compute_snapshot_subtotal,
    compute_valid_until_from_snapshot,
    ordered_active_quotation_stages,
    pricing_line_hints_for_snapshot,
)
from app.modules.commercial_core.services.commercial_quotation_document_service import CommercialQuotationDocumentService
from app.modules.commercial_core.services.commercial_quotation_email_flow_service import CommercialQuotationEmailFlowService
from app.modules.commercial_core.services.commercial_quotation_revision_service import CommercialQuotationRevisionService
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.error_handler import AppException, handle_internal_error
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


def _hierarchy_http(exc: CommercialHierarchyError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _stage_brief(m) -> QuotationStageBrief | None:
    st = getattr(m, "quotation_stage", None)
    if not st:
        return None
    return QuotationStageBrief(
        stage_code=st.code,
        stage_name=st.label,
        is_terminal=bool(st.is_terminal),
    )


def _serialize_master_table_row(db: Session, m) -> MasterQuotationTableRow:
    st = getattr(m, "quotation_stage", None)
    stage = (
        QuotationStageBrief(
            stage_code=st.code,
            stage_name=st.label,
            is_terminal=bool(st.is_terminal),
        )
        if st
        else None
    )
    t = getattr(m, "tender", None)
    p = t.project if t else None
    lead = p.lead if p else None
    cust = getattr(m, "customer", None) or (lead.customer if lead else None)
    owner = getattr(m, "owner", None)
    amt = getattr(m, "quoted_amount", None)
    currency = getattr(m, "quoted_currency", None)
    wr = getattr(m, "current_working_revision", None)
    if amt is None and wr is not None and isinstance(wr.pricing_snapshot, dict):
        amt = compute_snapshot_subtotal(dict(wr.pricing_snapshot or {}))
    if amt is not None and (not currency or not str(currency).strip()):
        currency = "MYR"
    owner_name = None
    if owner:
        nm = ((owner.name or "").strip() or getattr(owner, "email", None) or "").strip()
        owner_name = nm or None
    if wr is not None and isinstance(wr.pricing_snapshot, dict):
        meta = wr.pricing_snapshot.get("quotation_meta")
        if isinstance(meta, dict):
            sid = meta.get("salesperson_user_id")
            if sid and str(sid).strip():
                su = db.query(User).filter(User.id == str(sid).strip()).first()
                if su:
                    nm = ((su.name or "").strip() or (su.email or "").strip())
                    if nm:
                        owner_name = nm
    wr_num = int(wr.revision_number) if wr is not None and getattr(wr, "revision_number", None) is not None else None
    return MasterQuotationTableRow(
        id=str(m.id),
        tender_code=t.tender_code if t else "",
        quotation_code=m.quotation_code,
        title=m.title,
        project_id=str(p.id) if p else "",
        project_title=(p.title if p else "") or "",
        lead_id=str(lead.id) if lead else "",
        lead_code=lead.lead_code if lead else "",
        customer_id=str(cust.id) if cust else None,
        client_name=(cust.customer_name if cust else None) or None,
        quotation_stage=stage,
        owner_user_id=str(m.owner_user_id) if m.owner_user_id else None,
        owner_name=owner_name,
        quoted_amount=str(amt) if amt is not None else None,
        quoted_currency=currency,
        current_working_revision_number=wr_num,
        created_at=m.created_at,
    )


def _serialize_master_list_item(m) -> MasterQuotationListItem:
    cust = getattr(m, "customer", None)
    details = dict(getattr(m, "commercial_details", None) or {})
    lead_id = str(details.get("lead_id") or "").strip() or None
    lead_code = str(details.get("lead_code") or "").strip() or None
    cur = getattr(m, "current_working_revision", None)
    fin = getattr(m, "final_selected_revision", None)
    t = getattr(m, "tender", None)
    owner = getattr(m, "owner", None)
    owner_name = None
    if owner:
        nm = ((owner.name or "").strip() or getattr(owner, "email", None) or "").strip()
        owner_name = nm or None
    amt = getattr(m, "quoted_amount", None)
    return MasterQuotationListItem(
        id=str(m.id),
        tender_code=t.tender_code if t else "",
        quotation_code=m.quotation_code,
        title=m.title,
        lead_id=lead_id,
        lead_code=lead_code,
        customer_id=str(cust.id) if cust else None,
        customer_name=(cust.customer_name if cust else None) or None,
        path_role=m.path_role,
        quotation_stage=_stage_brief(m),
        current_working_revision_number=cur.revision_number if cur else None,
        final_selected_revision_number=fin.revision_number if fin else None,
        quoted_amount=str(amt) if amt is not None else None,
        quoted_currency=m.quoted_currency,
        owner_name=owner_name,
        created_at=m.created_at,
    )


def _working_revision_editable(db: Session, m) -> bool:
    ap = (getattr(m, "pricing_approval_status", None) or "").strip().lower()
    if ap == "pending":
        return False
    stages = ordered_active_quotation_stages(db)
    if not stages or not m.quotation_stage_id:
        return False
    return str(m.quotation_stage_id) == str(stages[0].id)


def _serialize_master_detail(db: Session, m) -> MasterQuotationDetailResponse:
    t = m.tender
    cust = getattr(m, "customer", None)
    details = dict(m.commercial_details or {}) if isinstance(m.commercial_details, dict) else {}
    intended = details.get("pricing_intended_execution_state")
    appr_id = getattr(m, "pricing_approver_user_id", None)
    desc = details.get("description")
    rem = details.get("remark")
    qpt_id = details.get("quotation_package_template_id")
    qpt_name = details.get("quotation_package_template_name")
    tt_id = details.get("task_template_id")
    tt_name = details.get("task_template_name")
    return MasterQuotationDetailResponse(
        id=str(m.id),
        tender_id=str(m.tender_id),
        project_id=str(t.project_id) if t and getattr(t, "project_id", None) else None,
        tender_code=t.tender_code if t else "",
        quotation_code=m.quotation_code,
        title=m.title,
        customer_id=str(cust.id) if cust else None,
        customer_name=(cust.customer_name if cust else None) or None,
        path_role=m.path_role,
        quotation_stage=_stage_brief(m),
        quoted_amount=m.quoted_amount,
        quoted_currency=m.quoted_currency,
        valid_until=m.valid_until,
        payment_terms=getattr(m, "payment_terms", None),
        description=str(desc).strip() if desc is not None and str(desc).strip() else None,
        remark=str(rem).strip() if rem is not None and str(rem).strip() else None,
        pricing_approval_status=getattr(m, "pricing_approval_status", None) or "not_required",
        pricing_intended_execution_state=str(intended) if intended else None,
        pricing_approver_user_id=str(appr_id) if appr_id else None,
        current_working_revision_id=str(m.current_working_revision_id) if m.current_working_revision_id else None,
        final_selected_revision_id=str(m.final_selected_revision_id) if m.final_selected_revision_id else None,
        task_board=dict(m.task_board) if isinstance(m.task_board, dict) else {},
        working_revision_editable=_working_revision_editable(db, m),
        quotation_package_template_id=str(qpt_id).strip() if qpt_id else None,
        quotation_package_template_name=str(qpt_name).strip() if qpt_name else None,
        task_template_id=str(tt_id).strip() if tt_id else None,
        task_template_name=str(tt_name).strip() if tt_name else None,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _serialize_revision(db: Session, m, rev) -> QuotationRevisionResponse:
    snap = dict(rev.pricing_snapshot or {})
    breaches = collect_tolerance_breaches(db, snap)
    hints = pricing_line_hints_for_snapshot(db, snap)
    vu = compute_valid_until_from_snapshot(snap)
    return QuotationRevisionResponse(
        id=str(rev.id),
        master_quotation_id=str(rev.master_quotation_id),
        revision_number=rev.revision_number,
        pricing_snapshot=snap,
        revision_notes=rev.revision_notes,
        tolerance_breaches=breaches,
        pricing_line_hints=hints,
        computed_valid_until=vu,
        final_selected_at=rev.final_selected_at,
        created_at=rev.created_at,
        is_current_working=bool(m.current_working_revision_id == rev.id),
        is_final_selected=bool(m.final_selected_revision_id == rev.id),
    )


@router.get(
    "/projects/{project_id}/master-quotations",
    response_model=ListResponse[MasterQuotationListItem],
)
async def list_master_quotations_for_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        rows = svc.list_masters_for_project(project_id)
        data = [_serialize_master_list_item(m) for m in rows]
        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=len(data), page=1, limit=max(len(data), 1)),
            empty=len(data) == 0,
        )
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/projects/{project_id}/master-quotations",
    response_model=MasterQuotationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_master_quotation_for_project(
    project_id: str,
    body: ProjectMasterQuotationCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.add")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.create_master_quotation_for_project(
            project_id,
            actor_user_id=current_user.get("id") or "",
            title=body.title,
            customer_id=body.customer_id,
            lead_id=body.lead_id,
            valid_until=body.valid_until,
            description=body.description,
            remark=body.remark,
            owner_user_id=body.owner_user_id,
            task_template_id=body.task_template_id,
            quotation_package_template_id=body.quotation_package_template_id,
        )
        db.commit()
        mq = svc.get_master_by_id(str(mq.id))
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("create_master_quotation_for_project failed: project_id=%s", project_id)
        raise handle_internal_error(str(e))


@router.get(
    "/master-quotations",
    response_model=ListResponse[MasterQuotationTableRow],
)
async def list_master_quotations_global(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
    quotation_stage_code: Optional[str] = Query(None),
    scope: Literal["mine", "all"] = Query("all"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    """Paginated master quotations across all tenders (global list UI)."""
    try:
        svc = CommercialPipelineService(db)
        rows, total = svc.list_master_quotations_table(
            user_id=current_user.get("id") or "",
            scope=scope,
            page=page,
            limit=limit,
            search=search,
            owner_user_id=owner_user_id,
            quotation_stage_code=quotation_stage_code,
        )
        data = [_serialize_master_table_row(db, m) for m in rows]
        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=len(data) == 0,
        )
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/master-quotations/{master_id}",
    response_model=MasterQuotationDetailResponse,
)
async def get_master_quotation_by_id(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        m = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, m)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/duplicate",
    response_model=MasterQuotationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_master_quotation_endpoint(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.add")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.duplicate_master_quotation(master_id, actor_user_id=current_user.get("id") or "")
        db.commit()
        mq = svc.get_master_by_id(str(mq.id))
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.patch(
    "/master-quotations/{master_id}",
    response_model=MasterQuotationDetailResponse,
)
async def patch_master_quotation(
    master_id: str,
    body: MasterQuotationUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.update_master_quotation(
            master_id,
            body.model_dump(exclude_unset=True),
            actor_user_id=current_user.get("id") or "",
        )
        db.commit()
        mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/task-board/schedule/preview",
    response_model=MasterQuotationTaskBoardSchedulePreviewResponse,
)
async def preview_master_task_board_schedule(
    master_id: str,
    body: MasterQuotationTaskBoardSchedulePreviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        # Ensure membership/permission via service guards.
        out = svc.preview_master_task_board_schedule(
            master_id,
            task_board=body.task_board,
            baseline_start_date=body.baseline_start_date,
            changed_task_id=body.changed_task_id,
        )
        return MasterQuotationTaskBoardSchedulePreviewResponse(**out)
    except CommercialHierarchyError as e:
        raise _hierarchy_http(e)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/task-board/schedule/apply",
    response_model=MasterQuotationTaskBoardSchedulePreviewResponse,
)
async def apply_master_task_board_schedule(
    master_id: str,
    body: MasterQuotationTaskBoardSchedulePreviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        out = svc.apply_master_task_board_schedule(
            master_id,
            actor_user_id=current_user.get("id") or "",
            task_board=body.task_board,
            baseline_start_date=body.baseline_start_date,
            changed_task_id=body.changed_task_id,
        )
        db.commit()
        return MasterQuotationTaskBoardSchedulePreviewResponse(**out)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/apply-quotation-package-template",
    response_model=MasterQuotationDetailResponse,
)
async def apply_quotation_package_template_to_working_revision(
    master_id: str,
    body: ApplyQuotationPackageTemplateBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    """Replace working revision lines and quotation meta from a configured package template."""
    try:
        svc = CommercialQuotationRevisionService(db)
        svc.replace_working_revision_from_quotation_package_template(
            master_id,
            quotation_package_template_id=body.quotation_package_template_id,
            actor_user_id=current_user.get("id") or "",
        )
        db.commit()
        mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/advance-stage",
    response_model=MasterQuotationDetailResponse,
)
async def advance_master_quotation_stage(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
    body: MasterQuotationAdvanceBody | None = Body(None),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        raw = body or MasterQuotationAdvanceBody()
        mq = svc.advance_master_quotation_stage(
            master_id,
            actor_user_id=current_user.get("id") or "",
            confirm_tolerance_breach=raw.confirm_tolerance_breach,
        )
        db.commit()
        mq = svc.get_master_by_id(master_id)
        if (getattr(mq, "pricing_approval_status", None) or "").strip().lower() == "pending":
            CommercialPipelineService(db)._notify_pricing_approval_request(mq)
            db.commit()
            mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except ToleranceAdvanceConfirmationRequired as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TOLERANCE_CONFIRMATION_REQUIRED",
                "breaches": e.breaches,
                "message": str(e),
            },
        )
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/retreat-stage",
    response_model=MasterQuotationDetailResponse,
)
async def retreat_master_quotation_stage(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.retreat_master_quotation_stage(master_id, actor_user_id=current_user.get("id") or "")
        db.commit()
        mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.get(
    "/tenders/by-code/{tender_code}/master-quotations",
    response_model=ListResponse[MasterQuotationListItem],
)
async def list_master_quotations_for_tender(
    tender_code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        rows = svc.list_masters_for_tender_code(tender_code)
        data = [_serialize_master_list_item(m) for m in rows]
        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=len(data), page=1, limit=max(len(data), 1)),
            empty=len(data) == 0,
        )
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/tenders/by-code/{tender_code}/master-quotations/by-code/{quotation_code}",
    response_model=MasterQuotationDetailResponse,
)
async def get_master_quotation_by_codes(
    tender_code: str,
    quotation_code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        m = svc.get_master_by_tender_and_quotation_codes(tender_code, quotation_code)
        return _serialize_master_detail(db, m)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/master-quotations/{master_id}/revisions",
    response_model=List[QuotationRevisionResponse],
)
async def list_revisions(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.get_master_by_id(master_id)
        revs = svc.list_revisions(master_id)
        return [_serialize_revision(db, mq, r) for r in revs]
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/revisions",
    response_model=QuotationRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_revision(
    master_id: str,
    body: QuotationRevisionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.add")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.get_master_by_id(master_id)
        rev = svc.create_revision(
            master_id,
            actor_user_id=current_user.get("id") or "",
            copy_from_revision_id=body.copy_from_revision_id,
            revision_notes=body.revision_notes,
            pricing_snapshot=body.pricing_snapshot,
        )
        db.commit()
        db.refresh(rev)
        mq = svc.get_master_by_id(master_id)
        return _serialize_revision(db, mq, rev)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.patch(
    "/master-quotations/{master_id}/current-revision",
    response_model=MasterQuotationDetailResponse,
)
async def set_current_working_revision(
    master_id: str,
    body: SetRevisionPointerBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.set_current_working_revision(
            master_id, body.revision_id, actor_user_id=current_user.get("id") or ""
        )
        db.commit()
        mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.patch(
    "/master-quotations/{master_id}/final-revision",
    response_model=MasterQuotationDetailResponse,
)
async def set_final_selected_revision(
    master_id: str,
    body: SetRevisionPointerBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.set_final_selected_revision(
            master_id, body.revision_id, actor_user_id=current_user.get("id") or ""
        )
        db.commit()
        mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.get(
    "/quotation-revisions/{revision_id}",
    response_model=QuotationRevisionResponse,
)
async def get_revision(
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        rev = svc.get_revision(revision_id)
        mq = svc.get_master_by_id(str(rev.master_quotation_id))
        return _serialize_revision(db, mq, rev)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch(
    "/quotation-revisions/{revision_id}",
    response_model=QuotationRevisionResponse,
)
async def update_revision(
    revision_id: str,
    body: QuotationRevisionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        rev = svc.update_revision(
            revision_id,
            actor_user_id=current_user.get("id") or "",
            pricing_snapshot=body.pricing_snapshot,
            revision_notes=body.revision_notes,
        )
        db.commit()
        db.refresh(rev)
        mq = svc.get_master_by_id(str(rev.master_quotation_id))
        return _serialize_revision(db, mq, rev)
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.get(
    "/quotation-revisions/{revision_id}/attachment-links",
    response_model=List[EntityAttachmentLinkItem],
)
async def list_revision_attachment_links(
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.view")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        et, eid = svc.revision_attachment_entity(revision_id)
        att_svc = EntityAttachmentService(db)
        links = att_svc.list_links(et, eid)
        out: List[EntityAttachmentLinkItem] = []
        for link in links:
            att = link.attachment
            out.append(
                EntityAttachmentLinkItem(
                    id=str(link.id),
                    attachment_id=str(link.attachment_id),
                    file_name=getattr(att, "original_filename", None) if att else None,
                    file_path=getattr(att, "file_path", None) if att else None,
                )
            )
        return out
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/quotation-revisions/{revision_id}/attachment-links",
    status_code=status.HTTP_201_CREATED,
)
async def link_revision_attachment(
    revision_id: str,
    body: LinkAttachmentBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        et, eid = svc.revision_attachment_entity(revision_id)
        att_svc = EntityAttachmentService(db)
        link = att_svc.link_existing_attachment(
            et,
            eid,
            body.attachment_id.strip(),
            created_by=current_user.get("id"),
        )
        db.commit()
        db.refresh(link)
        return {"link_id": str(link.id), "message": "Linked."}
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete(
    "/quotation-revisions/{revision_id}/attachment-links/{link_id}",
    status_code=status.HTTP_200_OK,
)
async def unlink_revision_attachment(
    revision_id: str,
    link_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        et, _ = svc.revision_attachment_entity(revision_id)
        att_svc = EntityAttachmentService(db)
        att_svc.delete_link(link_id, entity_type=et)
        db.commit()
        return {"message": "Unlinked."}
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/quotation-revisions/{revision_id}/print-pdf")
def print_quotation_revision_pdf(
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.view")),
):
    try:
        svc = CommercialQuotationDocumentService(db)
        pdf, filename = svc.generate_quotation_pdf(revision_id, user_id=current_user.get("id") or "")
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except CommercialHierarchyError as e:
        raise _hierarchy_http(e)
    except AppException:
        raise
    except Exception as e:
        logger.exception("print-pdf failed revision_id=%s", revision_id)
        raise handle_internal_error(str(e))


@router.post(
    "/quotation-revisions/{revision_id}/email-preview",
    response_model=QuotationEmailPreviewResponse,
)
async def preview_quotation_revision_email(
    revision_id: str,
    body: Optional[QuotationEmailPreviewRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_revisions.view")),
):
    try:
        req = body or QuotationEmailPreviewRequest()
        flow = CommercialQuotationEmailFlowService(db)
        data = flow.preview(
            revision_id,
            user_id=current_user.get("id") or "",
            template_id=req.template_id,
        )
        return QuotationEmailPreviewResponse(**data)
    except CommercialHierarchyError as e:
        raise _hierarchy_http(e)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/quotation-revisions/{revision_id}/send-email",
    response_model=QuotationEmailSendResponse,
)
def send_quotation_revision_email(
    revision_id: str,
    body: QuotationEmailSendRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        flow = CommercialQuotationEmailFlowService(db)
        ok, err = flow.send(
            revision_id,
            user_id=current_user.get("id") or "",
            to_list=body.to,
            cc_list=body.cc,
            bcc_list=body.bcc,
            subject=body.subject,
            body_html=body.body_html,
        )
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err or "Send failed")
        db.commit()
        return QuotationEmailSendResponse(ok=True)
    except HTTPException:
        raise
    except CommercialHierarchyError as e:
        db.rollback()
        raise _hierarchy_http(e)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.get(
    "/tenders/by-code/{tender_code}/master-quotations/compare",
    response_model=List[MasterQuotationCompareRow],
)
async def compare_master_quotations_under_tender(
    tender_code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        rows = mq_ws.list_compare_rows(db, tender_code)
        out: List[MasterQuotationCompareRow] = []
        for r in rows:
            st = r["stage"]
            out.append(
                MasterQuotationCompareRow(
                    tender_code=r["tender_code"],
                    quotation_code=r["quotation_code"],
                    title=r["title"],
                    path_role=r["path_role"],
                    quotation_stage=QuotationStageBrief(
                        stage_code=st["stage_code"],
                        stage_name=st["stage_name"],
                        is_terminal=st["is_terminal"],
                    ),
                    owner=r.get("owner"),
                    salesperson_name=r.get("salesperson_name"),
                    quoted_amount=r.get("quoted_amount"),
                    quoted_currency=r.get("quoted_currency"),
                    updated_at=r["updated_at"],
                )
            )
        return out
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/pricing-approval",
    response_model=MasterQuotationDetailResponse,
)
async def pricing_approval_decision(
    master_id: str,
    body: PricingApprovalDecision,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = CommercialQuotationRevisionService(db)
        mq = svc.get_master_by_id(master_id)
        complete_pricing_approval(
            db,
            mq,
            actor_user_id=current_user.get("id") or "",
            approved=body.approved,
            notes=body.notes,
        )
        db.commit()
        mq = svc.get_master_by_id(master_id)
        return _serialize_master_detail(db, mq)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.get(
    "/master-quotations/{master_id}/workspace-activities",
    response_model=List[WorkspaceActivityOut],
)
async def list_workspace_activities(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_activities.view")),
):
    try:
        rows = mq_ws.list_activities(db, master_id)
        return [WorkspaceActivityOut.model_validate(r) for r in rows]
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/workspace-activities",
    response_model=WorkspaceActivityOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_activity(
    master_id: str,
    body: WorkspaceActivityCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_activities.add")),
):
    try:
        row = mq_ws.create_activity(db, master_id, body.model_dump(exclude_none=True))
        return WorkspaceActivityOut.model_validate(row)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch(
    "/master-quotations/{master_id}/workspace-activities/{activity_id}",
    response_model=WorkspaceActivityOut,
)
async def patch_workspace_activity(
    master_id: str,
    activity_id: str,
    body: WorkspaceActivityPatch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_activities.edit")),
):
    try:
        row = mq_ws.patch_activity(db, master_id, activity_id, body.model_dump(exclude_none=True))
        return WorkspaceActivityOut.model_validate(row)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete(
    "/master-quotations/{master_id}/workspace-activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workspace_activity(
    master_id: str,
    activity_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.quotation_activities.delete")),
):
    try:
        mq_ws.delete_activity(db, master_id, activity_id)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/master-quotations/{master_id}/attachment-links")
async def list_master_quotation_attachment_links(
    master_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        CommercialQuotationRevisionService(db).get_master_by_id(master_id)
        return mq_ws.list_mq_attachment_payloads(db, master_id)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/master-quotations/{master_id}/attachment-links", status_code=status.HTTP_201_CREATED)
async def link_master_quotation_attachment(
    master_id: str,
    body: MasterQuotationAttachmentLinkBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        CommercialQuotationRevisionService(db).get_master_by_id(master_id)
        return mq_ws.link_mq_attachment(
            db, master_id, body.attachment_id.strip(), created_by=current_user.get("id")
        )
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete("/master-quotations/{master_id}/attachment-links/{link_id}")
async def unlink_master_quotation_attachment(
    master_id: str,
    link_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        CommercialQuotationRevisionService(db).get_master_by_id(master_id)
        mq_ws.unlink_mq_attachment(db, link_id)
        return {"message": "Unlinked."}
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
