"""Integrations API: Ideas iframe embed-session mint (SSO, §5.3, AC-42/44).

Called by the sorento FE when a logged-in user opens ``/ideas`` or ``/ideas/{id}``.
Mints a signed assertion for that user, exchanges it at the shared-service
``/embed/session`` endpoint, and returns ``{ iframe_url, token, expires_at }`` the FE
iframes.

Auth: JWT logged-in user only (``get_current_user``) — this is a first-party FE call,
never an X-API-Key / n8n path. Dormant settings → a clean 404 (feature not available),
never a 500; a shared-service outage → a clean 502 the FE turns into a retry state.
Secrets (signing secret, assertion, embed token) are never logged or echoed in errors.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.ideation_embed import (
    IdeationEmbedSessionRequest,
    IdeationEmbedSessionResponse,
)
from app.services.ideation_embed_service import (
    IdeationEmbedNotConfigured,
    IdeationEmbedUpstreamError,
    create_embed_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/embed-session",
    response_model=IdeationEmbedSessionResponse,
    status_code=status.HTTP_200_OK,
)
def create_ideation_embed_session(
    payload: IdeationEmbedSessionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mint an embed session for the logged-in user (board or a specific idea)."""
    _ = db  # auth dependency owns the session; no query needed here
    try:
        result = create_embed_session(current_user, idea_id=payload.idea_id)
    except IdeationEmbedNotConfigured:
        # Feature dormant (settings blank) — clean 4xx, not a 500 (AC-32).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The Ideas workspace isn't available on this deployment.",
        )
    except IdeationEmbedUpstreamError:
        # Shared-service down/misconfigured — clean 502, FE shows retry (AC-44).
        # Detail is generic: no secret, assertion, or internal URL leaks.
        logger.warning("ideation embed session mint upstream error.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't start a secure Ideas session. Please try again.",
        )
    return IdeationEmbedSessionResponse(**result)
