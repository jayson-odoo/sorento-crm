"""AutoCount write-back from Project sales (AC-QTSO-CRM).

    GET  /project-sales/autocount-write/capabilities
    POST /project-sales/sales-orders/{pso_id}/autocount
    POST /project-sales/sales-orders/amendments/{amendment_id}/autocount
    POST /project-sales/sales-orders/{pso_id}/autocount/cancel
    POST /project-sales/quotation-documents/{document_id}/autocount
    POST /project-sales/quotation-documents/{document_id}/autocount/cancel

Check order, on every route: permission (`projects.autocount.write`) -> the admin switch
(403, and the Shared Service is never touched) -> the record, found in the caller's company
(404) -> eligibility (409) -> the Shared Service. The company code and every document key come
from the record, never from the request: these routes take no body.

Every answer the Shared Service gave is a 200 with the result dict, a refusal included, so the
dialog can show AutoCount's own words.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id, permission_slugs
from app.database import get_db
from app.dependencies import require_permission
from app.models.project_so import SOAmendment
from app.models.projects import ProjectQuotationDocument
from app.models.user import SystemSetting
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_autocount_write_service import ProjectAutocountWriteService
from app.services.project_so_draft_service import ProjectSODraftService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

WRITE = "projects.autocount.write"
SWITCHED_OFF = (
    "AutoCount quotations and sales orders from Project sales are switched off in Settings."
)


GENERIC_FAILURE = "Something went wrong talking to AutoCount."


class WriteResult(BaseModel):
    outcome: str
    message: str
    doc_no: Optional[str] = None
    lines: List[Dict[str, Any]] = []
    warnings: List[Any] = []
    skipped: List[Dict[str, Any]] = []
    exploded: List[Dict[str, Any]] = []
    waiting: List[Dict[str, Any]] = []


class Capabilities(BaseModel):
    enabled: bool
    sales_orders: Dict[str, Dict[str, Any]] = {}
    quotations: Dict[str, Dict[str, Any]] = {}
    # The AutoCount book SS names for this company; an adopted order waits until it matches.
    sales_orders_book: Optional[str] = None


def _switch_on(db: Session) -> bool:
    row = db.query(SystemSetting).first()
    return bool(getattr(row, "project_autocount_write_enabled", False))


def _require_switch(db: Session) -> None:
    if not _switch_on(db):
        raise AppException(status_code=403, message=SWITCHED_OFF, code="ac_write_switched_off")


def _assert_project_access(db: Session, project_id: Optional[str], current_user: dict) -> None:
    """The same ownership rule the order and quotation routes apply to a write."""
    if not project_id:
        return
    project = projects.get_project_or_404(db, project_id)
    projects.assert_can_write_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )


def _guard(exc: Exception):
    """An application error passes through; anything else is logged here and answered with a
    fixed sentence, so no internal text reaches the screen."""
    if hasattr(exc, "status_code"):
        raise exc
    logger.exception("AutoCount write failed")
    raise handle_internal_error(GENERIC_FAILURE)


@router.get("/autocount-write/capabilities", response_model=Capabilities)
def capabilities(
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    if not _switch_on(db):
        return Capabilities(enabled=False)
    try:
        caps, book = ProjectAutocountWriteService(db).read_capabilities(acting_company_id(db))
        return Capabilities(enabled=True, sales_orders_book=book, **caps)
    except Exception as exc:
        _guard(exc)


def _order_for_write(db: Session, pso_id: str, current_user: dict) -> None:
    validate_uuid_path(pso_id, resource="Sales order")
    order = ProjectSODraftService(db).get_order(pso_id)
    _assert_project_access(db, order.project_id, current_user)


def _document_for_write(db: Session, document_id: str, current_user: dict) -> None:
    validate_uuid_path(document_id, resource="Quotation")
    document = (
        db.query(ProjectQuotationDocument).filter(ProjectQuotationDocument.id == document_id).first()
    )
    if document is None:
        raise AppException(
            status_code=404, message="Quotation not found.", code="quotation_document_not_found"
        )
    _assert_project_access(db, document.project_id, current_user)


def _run(db: Session, call) -> Dict[str, Any]:
    try:
        result = call()
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        _guard(exc)


@router.post("/sales-orders/amendments/{amendment_id}/autocount", response_model=WriteResult)
def update_sales_order(
    amendment_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    validate_uuid_path(amendment_id, resource="Amendment")
    amendment = db.query(SOAmendment).filter(SOAmendment.id == amendment_id).first()
    if amendment is None:
        raise AppException(status_code=404, message="Amendment not found.", code="amendment_not_found")
    _order_for_write(db, amendment.project_sales_order_id, current_user)
    return _run(db, lambda: ProjectAutocountWriteService(db).update_sales_order(amendment_id, current_user))


@router.post("/sales-orders/{pso_id}/autocount", response_model=WriteResult)
def create_sales_order(
    pso_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    _order_for_write(db, pso_id, current_user)
    return _run(db, lambda: ProjectAutocountWriteService(db).create_sales_order(pso_id, current_user))


@router.post("/sales-orders/{pso_id}/autocount/cancel", response_model=WriteResult)
def cancel_sales_order(
    pso_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    _order_for_write(db, pso_id, current_user)
    return _run(db, lambda: ProjectAutocountWriteService(db).cancel_sales_order(pso_id, current_user))


@router.post("/quotation-documents/{document_id}/autocount", response_model=WriteResult)
def send_quotation(
    document_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    _document_for_write(db, document_id, current_user)
    return _run(db, lambda: ProjectAutocountWriteService(db).send_quotation(document_id, current_user))


@router.post("/quotation-documents/{document_id}/autocount/cancel", response_model=WriteResult)
def cancel_quotation(
    document_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    _document_for_write(db, document_id, current_user)
    return _run(db, lambda: ProjectAutocountWriteService(db).cancel_quotation(document_id, current_user))
