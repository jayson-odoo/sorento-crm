"""Tender progression: winning path → sales order; close tender without SO."""
from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.schemas.commercial_progression import (
    TenderCloseOutcomeRequest,
    TenderCloseOutcomeResponse,
    WinningPathProgressRequest,
    WinningPathProgressResponse,
)
from app.services.audit_service import log_audit
from app.modules.commercial_core.services.commercial_hierarchy_service import CommercialHierarchyError
from app.modules.commercial_core.services.commercial_progression_service import CommercialProgressionService, get_tender_by_ref
from app.services.error_handler import AppException, handle_internal_error, handle_validation_error
from app.services.user_service import UserPermissionService

router = APIRouter()


def _require_all_permissions(db: Session, user_id: str, slugs: Iterable[str]) -> None:
    svc = UserPermissionService(db)
    if svc.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return
    for slug in slugs:
        if not svc.check_user_has_permission(user_id, slug):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {slug}",
            )


@router.post("/{tender_ref}/winning-path/progress", response_model=WinningPathProgressResponse)
async def progress_winning_path(
    tender_ref: str,
    body: WinningPathProgressRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_all_permissions(
        db,
        current_user["id"],
        (
            "commercial_core.tenders.edit",
            "commercial_core.master_quotations.edit",
            "commercial_core.quotation_revisions.view",
            "commercial_core.sales_orders.add",
        ),
    )
    try:
        tender = get_tender_by_ref(db, tender_ref)
        if tender is None:
            raise handle_validation_error("Tender not found.")
        svc = CommercialProgressionService(db)
        tender_out, so = svc.progress_winning_path(
            tender_id=tender.id,
            quotation_code=body.quotation_code.strip(),
            revision_number=body.revision_number,
            sales_order_number=body.sales_order_number,
        )
        resp = WinningPathProgressResponse(
            tender_code=tender_out.tender_code,
            tender_lifecycle=tender_out.tender_lifecycle,
            tender_outcome=tender_out.tender_outcome,
            sales_order_number=so.sales_order_number,
            quotation_code=body.quotation_code.strip(),
            revision_number=body.revision_number,
        )
        log_audit(
            db,
            "commercial_tender",
            str(tender_out.id),
            "UPDATE",
            user_id=current_user.get("id"),
            description="Winning quotation path progressed to commercial sales order",
            ip_address=request.client.host if request and request.client else None,
        )
        db.commit()
        return resp
    except AppException:
        db.rollback()
        raise
    except CommercialHierarchyError as e:
        db.rollback()
        raise handle_validation_error(str(e))
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.post("/{tender_ref}/close-outcome", response_model=TenderCloseOutcomeResponse)
async def close_tender_outcome(
    tender_ref: str,
    body: TenderCloseOutcomeRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_all_permissions(
        db,
        current_user["id"],
        (
            "commercial_core.tenders.edit",
            "commercial_core.master_quotations.edit",
        ),
    )
    try:
        tender = get_tender_by_ref(db, tender_ref)
        if tender is None:
            raise handle_validation_error("Tender not found.")
        svc = CommercialProgressionService(db)
        tender_out = svc.close_tender_without_sales_order(
            tender_id=tender.id,
            tender_outcome=body.tender_outcome.strip(),
            outcome_notes=body.outcome_notes,
        )
        resp = TenderCloseOutcomeResponse(
            tender_code=tender_out.tender_code,
            tender_lifecycle=tender_out.tender_lifecycle,
            tender_outcome=tender_out.tender_outcome,
        )
        log_audit(
            db,
            "commercial_tender",
            str(tender_out.id),
            "UPDATE",
            user_id=current_user.get("id"),
            description=f"Tender closed without sales order (outcome={tender_out.tender_outcome})",
            ip_address=request.client.host if request and request.client else None,
        )
        db.commit()
        return resp
    except AppException:
        db.rollback()
        raise
    except CommercialHierarchyError as e:
        db.rollback()
        raise handle_validation_error(str(e))
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
