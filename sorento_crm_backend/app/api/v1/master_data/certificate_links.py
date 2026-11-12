"""CERT-LINK-CLEANUP: "Certificate links to check" report routes.

Thin: the decisions live in `app/services/certificate_link_report_service.py`. Remove is not here:
it is the `certificate_link.remove` pending action (10 s countdown, `record_actions.py`), parked
through the generic `/pending-actions` route like every other destructive record action.
Card: documentation/plans/certificates/CARD-cert-link-cleanup-08nov.md.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.services import certificate_link_report_service as report
from app.services.error_handler import AppException, handle_internal_error
from app.services.uuid_list_param import parse_uuid_list
from app.utils.multi_value import multi_values

router = APIRouter()

_VIEW = "master_data.certificates.view"
_EDIT = "master_data.certificates.edit"


class CertificateLinkIds(BaseModel):
    ids: List[str] = Field(default_factory=list, max_length=1000)


# ai: not-for-assistant an admin data-quality worklist of certificate-product link verdicts, worked through by a person with bulk Confirm and Remove; the assistant already reads which products a certificate covers through the certificates entity
@router.get("/")
def list_certificate_links(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None, description="Sort column (allowlisted server-side)."),
    dir: Optional[str] = Query(None, description="asc | desc."),
    query: Optional[str] = Query(None, description="Product code or name, certificate number, code on certificate."),
    certificate_ids: Optional[List[str]] = Query(None),
    attachment_type_ids: Optional[List[str]] = Query(None),
    verdict: Optional[List[str]] = Query(None, description="found, check, not_found, scanned, no_file, pending."),
    source: Optional[List[str]] = Query(None, description="ai | manual."),
    status_: Optional[List[str]] = Query(None, alias="status", description="Certificate status: active | archived."),
    current_user: dict = Depends(require_permission(_VIEW)),
    db: Session = Depends(get_db),
):
    """Every certificate-product link with its text-check verdict, plus counts per verdict."""
    try:
        return report.list_links(
            db,
            page=page,
            limit=limit,
            sort=sort,
            dir=dir,
            query=query,
            certificate_ids=parse_uuid_list(certificate_ids, param_name="certificate_ids"),
            attachment_type_ids=parse_uuid_list(attachment_type_ids, param_name="attachment_type_ids"),
            verdict=multi_values(verdict),
            source=multi_values(source),
            status=multi_values(status_),
        )
    except (HTTPException, AppException):
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/check")
def check_certificate_links(
    current_user: dict = Depends(require_permission(_VIEW)),
    db: Session = Depends(get_db),
):
    """Queue a text check for every certificate (in scope) with links not yet checked."""
    try:
        return {"queued": report.queue_pending(db)}
    except (HTTPException, AppException):
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/confirm")
def confirm_certificate_links(
    payload: CertificateLinkIds,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """A person confirms these links: source becomes manual, one audit row per link."""
    try:
        ids = parse_uuid_list(payload.ids, param_name="ids") or []
        return {"confirmed": report.confirm_links(db, ids, str(current_user.get("id") or "") or None)}
    except (HTTPException, AppException):
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
