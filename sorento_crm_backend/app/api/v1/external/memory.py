"""External API for n8n conversation-frame memory (open/update/close/search/current)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.memory import (
    FrameCloseRequest,
    FrameCloseResponse,
    FrameCurrentFrame,
    FrameCurrentResponse,
    FrameOpenRequest,
    FrameOpenResponse,
    FrameSearchHit,
    FrameSearchRequest,
    FrameSearchResponse,
    FrameUpdateRequest,
    FrameUpdateResponse,
)
from app.services.frame_service import FrameService

logger = logging.getLogger(__name__)

router = APIRouter()


def _frame_to_current_schema(frame) -> FrameCurrentFrame:
    return FrameCurrentFrame(
        id=str(frame.id),
        contact_id=frame.contact_id,
        space_id=frame.space_id,
        channel=frame.channel,
        domain=frame.domain,
        intent=frame.intent,
        active_entities=frame.active_entities or {},
        access_levels_used=list(frame.access_levels_used or []),
        tools_used=list(frame.tools_used or []),
        result_refs=list(frame.result_refs or []),
        pending_request=frame.pending_request or {},
        last_user_message=frame.last_user_message,
        last_assistant_summary=frame.last_assistant_summary,
        status=frame.status,
        started_at=frame.started_at,
        last_activity_at=frame.last_activity_at,
    )


@router.post("/frames/open", response_model=FrameOpenResponse, status_code=status.HTTP_201_CREATED)
def open_frame(
    payload: FrameOpenRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        frame = FrameService(db).open_frame(
            contact_id=payload.contact_id,
            space_id=payload.space_id,
            channel=payload.channel,
            domain=payload.domain,
            intent=payload.intent,
            active_entities=payload.active_entities,
            access_levels_used=payload.access_levels_used,
            tools_used=payload.tools_used,
            result_refs=payload.result_refs,
            pending_request=payload.pending_request,
            last_user_message=payload.last_user_message,
            last_assistant_summary=payload.last_assistant_summary,
        )
    except Exception as e:
        db.rollback()
        logger.exception("Failed to open frame: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to open frame") from e
    return FrameOpenResponse(frame_id=str(frame.id), status=frame.status)


@router.post("/frames/update", response_model=FrameUpdateResponse, status_code=status.HTTP_200_OK)
def update_frame(
    payload: FrameUpdateRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    patch = payload.patch.model_dump(exclude_none=True)
    try:
        frame = FrameService(db).update_frame(payload.frame_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        logger.exception("Failed to update frame: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update frame") from e
    return FrameUpdateResponse(ok=True, frame_id=str(frame.id))


@router.post("/frames/close", response_model=FrameCloseResponse, status_code=status.HTTP_200_OK)
def close_frame(
    payload: FrameCloseRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        frame = FrameService(db).close_frame(payload.frame_id, reason=payload.reason, summary=payload.summary)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        logger.exception("Failed to close frame: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to close frame") from e
    return FrameCloseResponse(ok=True, frame_id=str(frame.id), embedding_queued=bool(frame.summary))


@router.post("/frames/search", response_model=FrameSearchResponse, status_code=status.HTTP_200_OK)
def search_frames(
    payload: FrameSearchRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    hits = FrameService(db).search_frames(
        contact_id=payload.contact_id,
        space_id=payload.space_id,
        query_text=payload.query_text,
        k=payload.k,
    )
    return FrameSearchResponse(frames=[FrameSearchHit(**h) for h in hits])


@router.get("/frames/current", response_model=FrameCurrentResponse, status_code=status.HTTP_200_OK)
def current_frame(
    contact_id: str = Query(...),
    space_id: str = Query(...),
    channel: str = Query("whatsapp"),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    frame = FrameService(db).get_open_frame(contact_id, space_id, channel)
    if frame is None:
        return FrameCurrentResponse(frame=None)
    return FrameCurrentResponse(frame=_frame_to_current_schema(frame))
