"""Email outbox admin API. List, view, retry, cancel rows."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission
from app.models.email_outbox import EmailOutbox
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.email_outbox import EmailOutboxRowResponse
from app.services.email_outbox_service import cancel as cancel_outbox, retry as retry_outbox
from app.services.error_handler import handle_internal_error

router = APIRouter()

_MAX_BULK = 500


class BulkOutboxRequest(BaseModel):
    row_ids: list[str] = Field(..., min_length=1, max_length=_MAX_BULK)


class BulkOutboxResult(BaseModel):
    requested: int
    succeeded: int
    failed: int
    failed_ids: list[str]


def _to_response(row: EmailOutbox) -> EmailOutboxRowResponse:
    return EmailOutboxRowResponse(
        id=str(row.id),
        event_key=row.event_key,
        recipient_email=row.recipient_email,
        recipients_json=row.recipients_json,
        subject=row.subject,
        body_text=row.body_text,
        body_html=row.body_html,
        from_name=row.from_name,
        metadata=row.metadata_json,
        priority=int(row.priority or 10),
        status=row.status,
        scheduled_for=row.scheduled_for,
        sent_at=row.sent_at,
        attempt_count=int(row.attempt_count or 0),
        max_attempts=int(row.max_attempts or 5),
        error_message=row.error_message,
        cancel_reason=row.cancel_reason,
        coalesce_key=row.coalesce_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/email-outbox", response_model=ListResponse[EmailOutboxRowResponse])
async def list_email_outbox(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    status_filter: Optional[str] = Query(None, alias="status"),
    event_key: Optional[str] = Query(None),
    query: Optional[str] = Query(None, description="Search recipient or subject"),
    current_user: dict = Depends(require_permission("system.email_outbox.view")),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(EmailOutbox)
        if status_filter:
            q = q.filter(EmailOutbox.status == status_filter.strip())
        if event_key:
            q = q.filter(EmailOutbox.event_key == event_key.strip())
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(or_(EmailOutbox.recipient_email.ilike(term), EmailOutbox.subject.ilike(term)))
        total = q.count()
        offset = (page - 1) * limit
        rows = (
            q.order_by(EmailOutbox.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "data": [_to_response(r) for r in rows],
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise handle_internal_error(str(exc))


@router.get("/email-outbox/{row_id}", response_model=EmailOutboxRowResponse)
async def get_email_outbox(
    row_id: str,
    current_user: dict = Depends(require_permission("system.email_outbox.view")),
    db: Session = Depends(get_db),
):
    row = db.query(EmailOutbox).filter(EmailOutbox.id == row_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outbox row not found")
    return _to_response(row)


@router.post("/email-outbox/{row_id}/retry", response_model=EmailOutboxRowResponse)
async def retry_email_outbox(
    row_id: str,
    current_user: dict = Depends(require_permission("system.email_outbox.manage")),
    db: Session = Depends(get_db),
):
    ok = retry_outbox(db, row_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Row cannot be retried in its current state")
    row = db.query(EmailOutbox).filter(EmailOutbox.id == row_id).first()
    return _to_response(row)


@router.post("/email-outbox/{row_id}/cancel", response_model=EmailOutboxRowResponse)
async def cancel_email_outbox(
    row_id: str,
    current_user: dict = Depends(require_permission("system.email_outbox.manage")),
    db: Session = Depends(get_db),
):
    ok = cancel_outbox(db, row_id, reason="cancelled_by_admin")
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Row cannot be cancelled in its current state")
    row = db.query(EmailOutbox).filter(EmailOutbox.id == row_id).first()
    return _to_response(row)


def _bulk_apply(db: Session, row_ids: list[str], action) -> BulkOutboxResult:
    """Apply a per-row action across a selection; a row that can't transition (or
    errors) is counted as failed, never aborting the batch — partial success is
    the expected outcome for a mixed selection."""
    seen: set[str] = set()
    failed: list[str] = []
    succeeded = 0
    for rid in row_ids:
        if rid in seen:
            continue
        seen.add(rid)
        try:
            if action(db, rid):
                succeeded += 1
            else:
                failed.append(rid)
        except Exception:  # noqa: BLE001 — one bad row must not sink the batch
            failed.append(rid)
    return BulkOutboxResult(
        requested=len(seen), succeeded=succeeded, failed=len(failed), failed_ids=failed
    )


@router.post("/email-outbox/bulk-retry", response_model=BulkOutboxResult)
async def bulk_retry_email_outbox(
    payload: BulkOutboxRequest,
    current_user: dict = Depends(require_permission("system.email_outbox.manage")),
    db: Session = Depends(get_db),
):
    """Retry many outbox rows at once. Rows not in a retryable state are reported
    in ``failed_ids`` rather than 400-ing the whole request."""
    return _bulk_apply(db, payload.row_ids, retry_outbox)


@router.post("/email-outbox/bulk-cancel", response_model=BulkOutboxResult)
async def bulk_cancel_email_outbox(
    payload: BulkOutboxRequest,
    current_user: dict = Depends(require_permission("system.email_outbox.manage")),
    db: Session = Depends(get_db),
):
    """Cancel many outbox rows at once (partial success reported in failed_ids)."""
    return _bulk_apply(
        db, payload.row_ids, lambda d, rid: cancel_outbox(d, rid, reason="cancelled_by_admin")
    )
