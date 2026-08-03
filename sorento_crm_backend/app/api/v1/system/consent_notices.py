"""Admin surface for the PDPA collection notice.

Four verbs and no DELETE. A published notice is the evidence that a person agreed to
particular words, so it can be superseded but never removed or edited - which is why the
write path is create-draft, edit-draft, publish, and nothing else.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.consent_notice import ConsentNotice
from app.services.consent_notice_service import (
    CONSUMER_INTAKE_KEY,
    create_notice,
    current_notice,
    publish_notice,
    stamp_for,
    update_notice,
)

router = APIRouter()

# Settings-level permission: whoever configures the system owns the wording it shows.
_VIEW = "system_management.settings.view"
_EDIT = "system_management.settings.edit"


class _NoticeCreate(BaseModel):
    notice_key: str = Field(CONSUMER_INTAKE_KEY, min_length=1, max_length=64)
    purpose: str = Field(..., min_length=1, max_length=32)
    body_en: str = ""
    body_ms: str = ""


class _NoticeUpdate(BaseModel):
    body_en: Optional[str] = None
    body_ms: Optional[str] = None
    purpose: Optional[str] = None


def _serialize(notice: ConsentNotice) -> dict:
    return {
        "id": str(notice.id),
        "notice_key": notice.notice_key,
        "version": notice.version,
        "stamp": stamp_for(notice),
        "purpose": notice.purpose,
        "body_en": notice.body_en,
        "body_ms": notice.body_ms,
        "is_published": bool(notice.is_published),
        "published_at": notice.published_at,
        "created_at": notice.created_at,
    }


@router.get("/consent-notices")
async def list_consent_notices(
    notice_key: Optional[str] = Query(None),
    _perm: dict = Depends(require_permission(_VIEW)),
    db: Session = Depends(get_db),
):
    """Every version, newest first. The history IS the audit trail."""
    query = db.query(ConsentNotice)
    if notice_key:
        query = query.filter(ConsentNotice.notice_key == notice_key)
    rows = query.order_by(
        ConsentNotice.notice_key.asc(), ConsentNotice.version.desc()
    ).all()
    return {"data": [_serialize(r) for r in rows], "total": len(rows)}


@router.get("/consent-notices/current")
async def get_current(
    notice_key: str = Query(CONSUMER_INTAKE_KEY),
    _perm: dict = Depends(require_permission(_VIEW)),
    db: Session = Depends(get_db),
):
    notice = current_notice(db, notice_key)
    return {"notice": _serialize(notice) if notice else None, "notice_key": notice_key}


@router.post("/consent-notices", status_code=201)
async def create_draft(
    payload: _NoticeCreate,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Start a new version. Drafts are never served to a consumer."""
    notice = create_notice(
        db,
        notice_key=payload.notice_key,
        purpose=payload.purpose,
        body_en=payload.body_en,
        body_ms=payload.body_ms,
        created_by=current_user.get("id"),
    )
    db.commit()
    db.refresh(notice)
    return _serialize(notice)


@router.put("/consent-notices/{notice_id}")
async def edit_draft(
    notice_id: str,
    payload: _NoticeUpdate,
    _perm: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Edit a DRAFT. A published notice refuses with `consent_notice_published`."""
    notice = update_notice(db, notice_id, **payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(notice)
    return _serialize(notice)


@router.post("/consent-notices/{notice_id}/publish")
async def publish(
    notice_id: str,
    current_user: dict = Depends(require_permission(_EDIT)),
    db: Session = Depends(get_db),
):
    """Make this version the one consumers see. Both languages required (s.7(2))."""
    notice = publish_notice(db, notice_id, published_by=current_user.get("id"))
    db.commit()
    db.refresh(notice)
    return _serialize(notice)
