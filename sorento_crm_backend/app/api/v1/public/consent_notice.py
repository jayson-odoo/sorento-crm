"""The PDPA collection notice, readable without signing in.

A consumer has to be able to read what they are agreeing to BEFORE identifying themselves.
Requiring authentication to see a privacy notice is a contradiction, so this route sits
under `public` alongside the portal it serves.

Read-only and current-version-only on purpose: the portal never needs an old version, and
exposing the full history publicly would let anyone enumerate drafts.
"""
from fastapi import APIRouter, Query
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.services.consent_notice_service import (
    CONSUMER_INTAKE_KEY,
    current_notice,
    stamp_for,
)

router = APIRouter()


@router.get("/consent-notice")
async def get_current_consent_notice(
    notice_key: str = Query(CONSUMER_INTAKE_KEY),
    db: Session = Depends(get_db),
):
    """The published notice a portal must display before collecting anything.

    `notice: null` is a meaningful answer, not an error: it means nothing lawful exists to
    show, and the caller must refuse to collect rather than proceed with a blank. A 404
    would read as "wrong URL" and invite a retry.
    """
    notice = current_notice(db, notice_key)
    if notice is None:
        return {"notice": None, "notice_key": notice_key}
    return {
        "notice_key": notice.notice_key,
        "version": notice.version,
        # What the caller writes onto the profile when the person submits.
        "stamp": stamp_for(notice),
        "purpose": notice.purpose,
        "body_en": notice.body_en,
        "body_ms": notice.body_ms,
        "published_at": notice.published_at,
    }
