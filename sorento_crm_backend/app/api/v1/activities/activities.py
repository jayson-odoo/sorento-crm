"""Generic per-entity Activities & Notes endpoints.

Mounted at ``/api/v1/activities``. Every route is keyed on
``(entity_type, entity_id)`` and routed through the adapter registered in
``app.services.activities_registry`` so consuming modules (tickets, leads,
complaints, …) plug in a permission/visibility/post-callback bundle and
inherit the whole panel.

Phase 1 ships the route surface with stubbed handlers so the OpenAPI schema
exposes the full contract; behaviour is filled in Phase 2 by
``activities_service``. Tests can hit each path and verify auth + module
guard wiring without depending on the service layer.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.schemas.activities import (
    ActivityEventCreate,
    ActivityEventResponse,
    EntityMessageSendRequest,
    InternalNoteCreate,
    InternalNoteResponse,
    InternalNoteUpdate,
)

router = APIRouter()


@router.get("/{entity_type}/{entity_id}/activities")
def list_activities(
    entity_type: str,
    entity_id: str,
    limit: int = Query(25, ge=1, le=100),
    before: Optional[str] = Query(None, description="ISO created_at cursor"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    from app.services.activities_service import list_activities as _impl
    return _impl(db, entity_type, entity_id, current_user, limit=limit, before_cursor=before)


@router.post(
    "/{entity_type}/{entity_id}/activities",
    response_model=ActivityEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_activity(
    entity_type: str,
    entity_id: str,
    body: ActivityEventCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import post_activity as _impl
    return _impl(
        db,
        entity_type,
        entity_id,
        body_html=body.body_html,
        body_text=body.body_text,
        attachment_ids=body.attachment_ids,
        mentioned_user_ids=body.mentioned_user_ids,
        current_user=current_user,
    )


@router.get("/{entity_type}/{entity_id}/notes")
def list_notes(
    entity_type: str,
    entity_id: str,
    limit: int = Query(25, ge=1, le=100),
    before: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import list_internal_notes as _impl
    return _impl(db, entity_type, entity_id, current_user, limit=limit, before_cursor=before)


@router.post(
    "/{entity_type}/{entity_id}/notes",
    response_model=InternalNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_note(
    entity_type: str,
    entity_id: str,
    body: InternalNoteCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import post_internal_note as _impl
    return _impl(
        db,
        entity_type,
        entity_id,
        body_html=body.body_html,
        body_text=body.body_text,
        current_user=current_user,
    )


@router.patch("/notes/{note_id}", response_model=InternalNoteResponse)
def update_note(
    note_id: str,
    body: InternalNoteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import update_internal_note as _impl
    return _impl(
        db,
        note_id,
        body_html=body.body_html,
        body_text=body.body_text,
        current_user=current_user,
    )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import delete_internal_note as _impl
    _impl(db, note_id, current_user)


@router.get("/{entity_type}/{entity_id}/contacts")
def list_entity_contacts(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    from app.services.activities_service import list_entity_contacts as _impl
    return _impl(db, entity_type, entity_id, current_user)


@router.get("/{entity_type}/{entity_id}/messages")
def list_messages(
    entity_type: str,
    entity_id: str,
    contact_id: str = Query(..., min_length=1),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
):
    from app.services.activities_service import list_messages as _impl
    return _impl(
        db,
        entity_type,
        entity_id,
        contact_id=contact_id,
        cursor=cursor,
        current_user=current_user,
    )


@router.post("/{entity_type}/{entity_id}/messages")
def send_message(
    entity_type: str,
    entity_id: str,
    body: EntityMessageSendRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import send_message as _impl
    return _impl(
        db,
        entity_type,
        entity_id,
        contact_id=body.contact_id,
        body=body.body,
        attachment_ids=body.attachment_ids,
        current_user=current_user,
    )


@router.post("/{entity_type}/{entity_id}/mentions/{event_id}/seen")
def mark_mention_seen(
    entity_type: str,
    entity_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.activities_service import mark_mention_seen as _impl
    return _impl(db, event_id, current_user)
