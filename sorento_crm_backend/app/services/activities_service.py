"""Business logic for the generic Activities & Notes panel.

Stays entity-agnostic — module specifics (visibility, post side-effects,
respond contact lookup) are delegated to the adapter registered in
``activities_registry``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.activities import ActivityEvent, ActivityMention, InternalNote
from app.models.user import User
from app.services.activities_registry import (
    ActivitiesAdapter,
    get_adapter,
    is_registered,
)

logger = logging.getLogger(__name__)

_DEFAULT_PAGE = 25
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    return _HTML_TAG_RE.sub("", html).strip() or None


def _user_to_actor(user: Optional[User]) -> Optional[Dict[str, Any]]:
    if user is None:
        return None
    name = (
        getattr(user, "full_name", None)
        or getattr(user, "name", None)
        or getattr(user, "email", None)
        or str(getattr(user, "id", ""))
    )
    return {
        "id": str(user.id),
        "name": name,
        "email": getattr(user, "email", None),
        "avatar_url": getattr(user, "avatar_url", None),
    }


def _resolve_adapter(entity_type: str) -> ActivitiesAdapter:
    if not is_registered(entity_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown activity entity_type: {entity_type}",
        )
    return get_adapter(entity_type)


def _ensure_can_view(
    db: Session, adapter: ActivitiesAdapter, entity_id: str, current_user: dict
) -> None:
    if adapter.can_view is None:
        return
    try:
        ok = bool(adapter.can_view(db, entity_id, current_user))
    except Exception:
        logger.exception("activities can_view raised for %s", adapter.entity_type)
        ok = False
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _event_to_dict(
    event: ActivityEvent, actor: Optional[User], mentioned_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    return {
        "id": str(event.id),
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "kind": event.kind,
        "body_html": event.body_html,
        "body_text": event.body_text,
        "system_template": event.system_template,
        "system_payload": event.system_payload,
        "actor": _user_to_actor(actor),
        "created_at": event.created_at,
        "attachments": [],
        "mentioned_user_ids": list(mentioned_ids or []),
    }


def list_activities(
    db: Session,
    entity_type: str,
    entity_id: str,
    current_user: dict,
    *,
    limit: int = _DEFAULT_PAGE,
    before_cursor: Optional[str] = None,
) -> Dict[str, Any]:
    adapter = _resolve_adapter(entity_type)
    _ensure_can_view(db, adapter, entity_id, current_user)
    q = db.query(ActivityEvent).filter(
        ActivityEvent.entity_type == entity_type,
        ActivityEvent.entity_id == entity_id,
    )
    if before_cursor:
        try:
            cutoff = datetime.fromisoformat(before_cursor)
            q = q.filter(ActivityEvent.created_at < cutoff)
        except ValueError:
            pass
    rows: List[ActivityEvent] = (
        q.order_by(desc(ActivityEvent.created_at)).limit(limit + 1).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    actor_ids = {str(r.actor_id) for r in rows if r.actor_id}
    actors: Dict[str, User] = {}
    if actor_ids:
        for u in db.query(User).filter(User.id.in_(list(actor_ids))).all():
            actors[str(u.id)] = u
    event_ids = [str(r.id) for r in rows if r.kind == "user_update"]
    mentions_by_event: Dict[str, List[str]] = {}
    if event_ids:
        for m in (
            db.query(ActivityMention)
            .filter(ActivityMention.activity_event_id.in_(event_ids))
            .all()
        ):
            mentions_by_event.setdefault(str(m.activity_event_id), []).append(
                str(m.mentioned_user_id)
            )
    items = [
        _event_to_dict(
            r,
            actors.get(str(r.actor_id)) if r.actor_id else None,
            mentions_by_event.get(str(r.id), []),
        )
        for r in rows
    ]
    next_cursor = rows[-1].created_at.isoformat() if rows and has_more else None
    return {"items": items, "has_more": has_more, "next_cursor": next_cursor}


def post_activity(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    body_html: str,
    body_text: Optional[str],
    attachment_ids: List[str],
    mentioned_user_ids: List[str],
    current_user: dict,
) -> Dict[str, Any]:
    adapter = _resolve_adapter(entity_type)
    _ensure_can_view(db, adapter, entity_id, current_user)
    text = body_text or _strip_html(body_html)
    actor_id = str(current_user.get("id") or "")
    event = ActivityEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        kind="user_update",
        body_html=body_html,
        body_text=text,
        actor_id=actor_id or None,
    )
    db.add(event)
    db.flush()
    cleaned_mentions = [u for u in {u for u in mentioned_user_ids if u}]
    for uid in cleaned_mentions:
        db.add(ActivityMention(activity_event_id=event.id, mentioned_user_id=uid))
    if adapter.on_post is not None:
        try:
            adapter.on_post(db, entity_id, actor_id, body_html)
        except Exception:
            logger.exception("activities on_post hook failed for %s", entity_type)
    db.commit()
    db.refresh(event)
    actor_user = (
        db.query(User).filter(User.id == event.actor_id).first() if event.actor_id else None
    )
    return _event_to_dict(event, actor_user, cleaned_mentions)


def record_system_event(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    template: str,
    payload: Optional[Dict[str, Any]] = None,
    actor_id: Optional[str] = None,
    body_text: Optional[str] = None,
    commit: bool = False,
) -> ActivityEvent:
    """Append a system row. Callers usually leave commit=False — the caller's
    own transaction will commit. Standalone callers can pass commit=True."""
    event = ActivityEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        kind="system",
        body_text=body_text,
        system_template=template,
        system_payload=payload or {},
        actor_id=actor_id,
    )
    db.add(event)
    db.flush()
    if commit:
        db.commit()
        db.refresh(event)
    return event


def list_internal_notes(
    db: Session,
    entity_type: str,
    entity_id: str,
    current_user: dict,
    *,
    limit: int = _DEFAULT_PAGE,
    before_cursor: Optional[str] = None,
) -> Dict[str, Any]:
    adapter = _resolve_adapter(entity_type)
    _ensure_can_view(db, adapter, entity_id, current_user)
    me = str(current_user.get("id") or "")
    q = db.query(InternalNote).filter(
        InternalNote.entity_type == entity_type,
        InternalNote.entity_id == entity_id,
        InternalNote.author_id == me,
    )
    if before_cursor:
        try:
            cutoff = datetime.fromisoformat(before_cursor)
            q = q.filter(InternalNote.created_at < cutoff)
        except ValueError:
            pass
    rows: List[InternalNote] = (
        q.order_by(desc(InternalNote.created_at)).limit(limit + 1).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    user = db.query(User).filter(User.id == me).first() if me else None
    actor = _user_to_actor(user)
    items = [
        {
            "id": str(r.id),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "author_id": str(r.author_id),
            "author": actor,
            "body_html": r.body_html,
            "body_text": r.body_text,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
    next_cursor = rows[-1].created_at.isoformat() if rows and has_more else None
    return {"items": items, "has_more": has_more, "next_cursor": next_cursor}


def post_internal_note(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    body_html: str,
    body_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    adapter = _resolve_adapter(entity_type)
    _ensure_can_view(db, adapter, entity_id, current_user)
    me = str(current_user.get("id") or "")
    if not me:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    note = InternalNote(
        entity_type=entity_type,
        entity_id=entity_id,
        author_id=me,
        body_html=body_html,
        body_text=body_text or _strip_html(body_html),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    user = db.query(User).filter(User.id == me).first()
    return {
        "id": str(note.id),
        "entity_type": note.entity_type,
        "entity_id": note.entity_id,
        "author_id": str(note.author_id),
        "author": _user_to_actor(user),
        "body_html": note.body_html,
        "body_text": note.body_text,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def update_internal_note(
    db: Session,
    note_id: str,
    *,
    body_html: Optional[str],
    body_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    me = str(current_user.get("id") or "")
    note = (
        db.query(InternalNote)
        .filter(InternalNote.id == note_id, InternalNote.author_id == me)
        .first()
    )
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if body_html is not None:
        note.body_html = body_html
        note.body_text = body_text or _strip_html(body_html)
    elif body_text is not None:
        note.body_text = body_text
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    user = db.query(User).filter(User.id == me).first()
    return {
        "id": str(note.id),
        "entity_type": note.entity_type,
        "entity_id": note.entity_id,
        "author_id": str(note.author_id),
        "author": _user_to_actor(user),
        "body_html": note.body_html,
        "body_text": note.body_text,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def delete_internal_note(db: Session, note_id: str, current_user: dict) -> None:
    me = str(current_user.get("id") or "")
    note = (
        db.query(InternalNote)
        .filter(InternalNote.id == note_id, InternalNote.author_id == me)
        .first()
    )
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    db.delete(note)
    db.commit()


def list_entity_contacts(
    db: Session,
    entity_type: str,
    entity_id: str,
    current_user: dict,
) -> List[Dict[str, Any]]:
    adapter = _resolve_adapter(entity_type)
    _ensure_can_view(db, adapter, entity_id, current_user)
    if adapter.get_respond_contacts is None:
        return []
    try:
        return list(adapter.get_respond_contacts(db, entity_id) or [])
    except Exception:
        logger.exception("get_respond_contacts failed for %s", entity_type)
        return []


def list_messages(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    contact_id: str,
    cursor: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    """Phase 2 stub: real Respond.io proxy lands in Phase 4. Returning an
    empty page keeps the FE Messages tab rendering cleanly with the
    'no messages yet' state when a contact is selected."""
    _ = _resolve_adapter(entity_type)
    return {"items": [], "has_more": False, "next_cursor": None}


def send_message(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    contact_id: str,
    body: str,
    attachment_ids: List[str],
    current_user: dict,
) -> Dict[str, Any]:
    """Phase 2 stub: queues the outbound message and writes a system
    Activities row so the feed reflects it. Real Respond.io send-out is
    wired in Phase 4."""
    adapter = _resolve_adapter(entity_type)
    _ensure_can_view(db, adapter, entity_id, current_user)
    record_system_event(
        db,
        entity_type,
        entity_id,
        template="message.sent",
        payload={"contact_id": contact_id},
        actor_id=str(current_user.get("id") or "") or None,
        body_text=body,
        commit=True,
    )
    return {"contact_id": contact_id, "queued": True}


def mark_mention_seen(db: Session, event_id: str, current_user: dict) -> Dict[str, Any]:
    me = str(current_user.get("id") or "")
    row = (
        db.query(ActivityMention)
        .filter(
            ActivityMention.activity_event_id == event_id,
            ActivityMention.mentioned_user_id == me,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mention not found")
    if row.seen_at is None:
        row.seen_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return {"id": str(row.id), "seen_at": row.seen_at}
