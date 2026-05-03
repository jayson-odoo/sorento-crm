"""Tickets business logic.

Visibility: non-admins (users without ``tickets.tickets.view_all``) see
only tickets where they are ``raised_by``, ``assigned_to``, or a watcher.

Status workflow: ``draft -> submitted -> assigned -> responded -> resolved``.

SLA tracking mirrors ``ConversationSLATracking``: response_time_hours and
resolution_time_hours are computed in hours from ``submitted_at`` to the
respective milestone.

Dual-flow status flips:
- ``update_response`` first call -> sets ``first_response_at`` +
  ``response_time_hours`` and bumps ``assigned -> responded``.
- ``update_resolution`` -> bumps ``responded -> resolved`` and stamps
  ``resolution_time_hours``.
- ``handle_activity_posted`` (Activities adapter on_post): if actor is
  the assignee and ticket is ``assigned``, calls ``change_status`` to
  ``responded`` so a chat message in the panel counts as a response.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from app.models.entity_attachment import EntityAttachmentLink
from app.models.tickets import (
    TICKET_STATUSES,
    Ticket,
    TicketRespondContactLink,
    TicketWatcher,
)
from app.models.user import User
from app.services import activities_service

logger = logging.getLogger(__name__)

# Default SLA windows (hours) — overridable later via SLAPolicy lookup.
DEFAULT_RESPONSE_SLA_HOURS = 24
DEFAULT_RESOLUTION_SLA_HOURS = 72

ENTITY_TYPE = "ticket"

# Allowed status transitions. `resolved -> draft` is forbidden so resolved
# tickets cannot silently be wiped back to drafts.
_FORBIDDEN_TRANSITIONS = {("resolved", "draft")}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    return _HTML_TAG_RE.sub("", html).strip() or None


def _has_view_all(current_user: dict) -> bool:
    perms = set(current_user.get("permissions") or [])
    if not perms:
        return False
    return "tickets.tickets.view_all" in perms


def _is_admin(current_user: dict) -> bool:
    roles = set(current_user.get("role_slugs") or current_user.get("roles") or [])
    if not roles:
        return False
    return bool(roles & {"superadmin", "admin"})


def _has_perm(current_user: dict, slug: str) -> bool:
    return slug in set(current_user.get("permissions") or [])


def _user_ref(user: Optional[User]) -> Optional[Dict[str, Any]]:
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
        "display_name": name,
        "email": getattr(user, "email", None),
        "avatar_url": getattr(user, "avatar_url", None),
    }


def _generate_ticket_number(db: Session) -> str:
    """``TCK-YYYY-NNNNNN`` monotonic per year using a simple count + 1.

    A more robust running-number rule via ``DocumentNumberingRule`` can be
    swapped in here without touching callers.
    """
    year = datetime.utcnow().year
    prefix = f"TCK-{year}-"
    count = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.ticket_number.like(f"{prefix}%"))
        .scalar()
        or 0
    )
    return f"{prefix}{int(count) + 1:06d}"


def _visibility_filter(current_user: dict):
    """Return a SQLAlchemy filter restricting to tickets the user can see."""
    if _has_view_all(current_user) or _is_admin(current_user):
        return None
    me = str(current_user.get("id") or "")
    if not me:
        return Ticket.id.is_(None)  # nothing visible
    watcher_match = exists().where(
        and_(TicketWatcher.ticket_id == Ticket.id, TicketWatcher.user_id == me)
    )
    return or_(
        Ticket.raised_by == me,
        Ticket.assigned_to == me,
        watcher_match,
    )


def can_view(db: Session, ticket_id: str, current_user: dict) -> bool:
    t = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if t is None:
        return False
    if _has_view_all(current_user) or _is_admin(current_user):
        return True
    me = str(current_user.get("id") or "")
    if not me:
        return False
    if str(t.raised_by) == me or (t.assigned_to and str(t.assigned_to) == me):
        return True
    watch = (
        db.query(TicketWatcher)
        .filter(TicketWatcher.ticket_id == ticket_id, TicketWatcher.user_id == me)
        .first()
    )
    return watch is not None


def _ensure_visible(db: Session, ticket: Ticket, current_user: dict) -> None:
    if not can_view(db, str(ticket.id), current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _get_or_404(db: Session, ticket_id: str) -> Ticket:
    t = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return t


def _user_map(db: Session, user_ids: List[str]) -> Dict[str, User]:
    cleaned = list({u for u in user_ids if u})
    if not cleaned:
        return {}
    return {
        str(u.id): u
        for u in db.query(User).filter(User.id.in_(cleaned)).all()
    }


def _watchers_for(db: Session, ticket_id: str) -> List[TicketWatcher]:
    return (
        db.query(TicketWatcher)
        .filter(TicketWatcher.ticket_id == ticket_id)
        .order_by(TicketWatcher.added_at.asc())
        .all()
    )


def _respond_contacts(db: Session, ticket_id: str) -> List[TicketRespondContactLink]:
    return (
        db.query(TicketRespondContactLink)
        .filter(TicketRespondContactLink.ticket_id == ticket_id)
        .order_by(
            TicketRespondContactLink.is_primary.desc(),
            TicketRespondContactLink.created_at.asc(),
        )
        .all()
    )


def _attachments(db: Session, ticket_id: str) -> List[EntityAttachmentLink]:
    return (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.entity_type == ENTITY_TYPE,
            EntityAttachmentLink.entity_id == ticket_id,
        )
        .all()
    )


def ticket_to_response(
    db: Session, ticket: Ticket, *, hydrate_links: bool = True
) -> Dict[str, Any]:
    """Serialize a Ticket SQLAlchemy row to a TicketResponse-compatible dict."""
    user_ids = [
        ticket.raised_by,
        ticket.assigned_to,
        ticket.responded_by,
        ticket.resolved_by,
    ]
    users = _user_map(db, [str(u) for u in user_ids if u])
    watchers_rows: List[TicketWatcher] = (
        _watchers_for(db, str(ticket.id)) if hydrate_links else []
    )
    contacts_rows: List[TicketRespondContactLink] = (
        _respond_contacts(db, str(ticket.id)) if hydrate_links else []
    )
    attachments_rows: List[EntityAttachmentLink] = (
        _attachments(db, str(ticket.id)) if hydrate_links else []
    )

    watcher_user_ids = [str(w.user_id) for w in watchers_rows]
    watcher_users = _user_map(db, watcher_user_ids) if watchers_rows else {}

    now = datetime.utcnow()
    is_overdue_response = bool(
        ticket.sla_response_due_at
        and ticket.first_response_at is None
        and ticket.sla_response_due_at < now
    )
    is_overdue_resolution = bool(
        ticket.sla_resolution_due_at
        and ticket.resolved_at is None
        and ticket.sla_resolution_due_at < now
    )

    return {
        "id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "description_html": ticket.description_html,
        "description_text": ticket.description_text,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "due_date": ticket.due_date,
        "raised_by": str(ticket.raised_by),
        "raised_by_user": _user_ref(users.get(str(ticket.raised_by))),
        "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
        "assigned_to_user": _user_ref(users.get(str(ticket.assigned_to))) if ticket.assigned_to else None,
        "response_html": ticket.response_html,
        "response_text": ticket.response_text,
        "responded_by": str(ticket.responded_by) if ticket.responded_by else None,
        "responded_by_user": _user_ref(users.get(str(ticket.responded_by))) if ticket.responded_by else None,
        "resolution_html": ticket.resolution_html,
        "resolution_text": ticket.resolution_text,
        "resolved_by": str(ticket.resolved_by) if ticket.resolved_by else None,
        "resolved_by_user": _user_ref(users.get(str(ticket.resolved_by))) if ticket.resolved_by else None,
        "submitted_at": ticket.submitted_at,
        "assigned_at": ticket.assigned_at,
        "first_response_at": ticket.first_response_at,
        "responded_at": ticket.responded_at,
        "resolved_at": ticket.resolved_at,
        "sla_response_due_at": ticket.sla_response_due_at,
        "sla_resolution_due_at": ticket.sla_resolution_due_at,
        "response_time_hours": ticket.response_time_hours,
        "resolution_time_hours": ticket.resolution_time_hours,
        "watchers": [
            {
                "user_id": str(w.user_id),
                "display_name": (
                    _user_ref(watcher_users.get(str(w.user_id))) or {}
                ).get("display_name"),
                "email": (_user_ref(watcher_users.get(str(w.user_id))) or {}).get("email"),
                "avatar_url": (_user_ref(watcher_users.get(str(w.user_id))) or {}).get(
                    "avatar_url"
                ),
                "added_at": w.added_at,
            }
            for w in watchers_rows
        ],
        "respond_contacts": [
            {
                "respond_contact_id": str(c.respond_contact_id),
                "name": None,
                "phone_number": None,
                "respond_io_id": str(c.respond_contact_id),
                "is_primary": bool(c.is_primary),
            }
            for c in contacts_rows
        ],
        "attachments": [
            {
                "id": str(a.id),
                "attachment_id": str(a.attachment_id),
                "file_name": None,
                "file_url": None,
                "file_size_bytes": None,
                "uploaded_at": a.created_at,
            }
            for a in attachments_rows
        ],
        "is_overdue_response": is_overdue_response,
        "is_overdue_resolution": is_overdue_resolution,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


# --- queries -----------------------------------------------------------


def list_tickets(
    db: Session,
    *,
    filters: Dict[str, Any],
    page: int,
    limit: int,
    current_user: dict,
) -> Dict[str, Any]:
    q = db.query(Ticket)
    vf = _visibility_filter(current_user)
    if vf is not None:
        q = q.filter(vf)
    if filters.get("status"):
        q = q.filter(Ticket.status == filters["status"])
    if filters.get("assigned_to"):
        q = q.filter(Ticket.assigned_to == filters["assigned_to"])
    if filters.get("raised_by"):
        q = q.filter(Ticket.raised_by == filters["raised_by"])
    if filters.get("priority"):
        q = q.filter(Ticket.priority == filters["priority"])
    if filters.get("category"):
        q = q.filter(Ticket.category == filters["category"])
    if filters.get("due_before"):
        try:
            cutoff = datetime.fromisoformat(filters["due_before"]).date()
            q = q.filter(Ticket.due_date.isnot(None), Ticket.due_date <= cutoff)
        except ValueError:
            pass
    if filters.get("q"):
        like = f"%{filters['q'].strip()}%"
        q = q.filter(
            or_(
                Ticket.title.ilike(like),
                Ticket.description_text.ilike(like),
                Ticket.ticket_number.ilike(like),
            )
        )

    total = int(q.count() or 0)
    rows = (
        q.order_by(Ticket.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    data = [ticket_to_response(db, t) for t in rows]
    return {
        "data": data,
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def kanban(
    db: Session,
    *,
    filters: Dict[str, Any],
    current_user: dict,
    column_cap: int = 100,
) -> Dict[str, Any]:
    q = db.query(Ticket)
    vf = _visibility_filter(current_user)
    if vf is not None:
        q = q.filter(vf)
    for key in ("status", "assigned_to", "raised_by", "priority", "category"):
        v = filters.get(key)
        if v:
            q = q.filter(getattr(Ticket, key) == v)
    rows = q.order_by(Ticket.updated_at.desc()).limit(column_cap * len(TICKET_STATUSES)).all()

    columns: Dict[str, List[Dict[str, Any]]] = {s: [] for s in TICKET_STATUSES}
    counts: Dict[str, int] = {s: 0 for s in TICKET_STATUSES}
    for t in rows:
        if len(columns.get(t.status, [])) >= column_cap:
            counts[t.status] = counts.get(t.status, 0) + 1
            continue
        columns[t.status].append(ticket_to_response(db, t, hydrate_links=False))
        counts[t.status] = counts.get(t.status, 0) + 1
    return {"columns": columns, "counts": counts}


def get_ticket(db: Session, *, ticket_id: str, current_user: dict) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    return ticket_to_response(db, t)


# --- mutations ---------------------------------------------------------


def create_ticket(
    db: Session, *, data: Any, current_user: dict
) -> Dict[str, Any]:
    me = str(current_user.get("id") or "")
    if not me:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    submitted_now = not bool(getattr(data, "save_as_draft", False))
    now = datetime.utcnow() if submitted_now else None
    sla_response_due = (
        now + timedelta(hours=DEFAULT_RESPONSE_SLA_HOURS) if now else None
    )
    sla_resolution_due = (
        now + timedelta(hours=DEFAULT_RESOLUTION_SLA_HOURS) if now else None
    )

    ticket = Ticket(
        ticket_number=_generate_ticket_number(db),
        title=data.title,
        description_html=getattr(data, "description_html", None),
        description_text=getattr(data, "description_text", None)
        or _strip_html(getattr(data, "description_html", None)),
        status="draft" if not submitted_now else "submitted",
        priority=data.priority,
        category=data.category,
        due_date=getattr(data, "due_date", None),
        raised_by=me,
        assigned_to=getattr(data, "assigned_to", None) or None,
        submitted_at=now,
        sla_response_due_at=sla_response_due,
        sla_resolution_due_at=sla_resolution_due,
    )
    db.add(ticket)
    db.flush()

    for att_id in getattr(data, "attachment_ids", None) or []:
        db.add(
            EntityAttachmentLink(
                entity_type=ENTITY_TYPE,
                entity_id=str(ticket.id),
                attachment_id=att_id,
                created_by=me,
            )
        )

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(ticket.id),
        template="entity.created",
        payload={"ticket_number": ticket.ticket_number, "status": ticket.status},
        actor_id=me,
    )

    db.commit()
    db.refresh(ticket)
    return ticket_to_response(db, ticket)


def update_ticket(
    db: Session, *, ticket_id: str, data: Any, current_user: dict
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = str(current_user.get("id") or "")

    if data.title is not None:
        t.title = data.title
    if data.description_html is not None:
        t.description_html = data.description_html
        t.description_text = (
            data.description_text or _strip_html(data.description_html)
        )
    elif data.description_text is not None:
        t.description_text = data.description_text
    if data.priority is not None:
        t.priority = data.priority
    if data.category is not None:
        t.category = data.category
    if data.due_date is not None:
        t.due_date = data.due_date

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="entity.updated",
        payload={"ticket_number": t.ticket_number},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def delete_ticket(
    db: Session, *, ticket_id: str, current_user: dict
) -> None:
    t = _get_or_404(db, ticket_id)
    if not (_is_admin(current_user) or _has_perm(current_user, "tickets.tickets.delete")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    db.delete(t)
    db.commit()


def bulk_delete_tickets(
    db: Session, *, ids: List[str], current_user: dict
) -> None:
    if not ids:
        return
    if not (_is_admin(current_user) or _has_perm(current_user, "tickets.tickets.delete")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    db.query(Ticket).filter(Ticket.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def _validate_transition(from_status: str, to_status: str) -> None:
    if to_status not in TICKET_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {to_status}",
        )
    if (from_status, to_status) in _FORBIDDEN_TRANSITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transition not allowed: {from_status} -> {to_status}",
        )


def _can_change_status(ticket: Ticket, current_user: dict) -> bool:
    if _is_admin(current_user):
        return True
    me = str(current_user.get("id") or "")
    return bool(ticket.assigned_to and str(ticket.assigned_to) == me)


def change_status(
    db: Session,
    *,
    ticket_id: str,
    new_status: str,
    note: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    _validate_transition(t.status, new_status)
    if not _can_change_status(t, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or an admin can move this ticket",
        )

    me = str(current_user.get("id") or "")
    now = datetime.utcnow()
    from_status = t.status
    t.status = new_status

    if new_status == "submitted" and t.submitted_at is None:
        t.submitted_at = now
        t.sla_response_due_at = now + timedelta(hours=DEFAULT_RESPONSE_SLA_HOURS)
        t.sla_resolution_due_at = now + timedelta(hours=DEFAULT_RESOLUTION_SLA_HOURS)
    elif new_status == "assigned" and t.assigned_at is None:
        t.assigned_at = now
    elif new_status == "responded":
        t.responded_at = now
        if t.first_response_at is None:
            t.first_response_at = now
            if t.submitted_at:
                seconds = (t.first_response_at - t.submitted_at).total_seconds()
                t.response_time_hours = Decimal(str(round(seconds / 3600.0, 2)))
        if not t.responded_by:
            t.responded_by = me
    elif new_status == "resolved":
        t.resolved_at = now
        if not t.resolved_by:
            t.resolved_by = me
        if t.submitted_at:
            seconds = (t.resolved_at - t.submitted_at).total_seconds()
            t.resolution_time_hours = Decimal(str(round(seconds / 3600.0, 2)))

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="status.changed",
        payload={"from": from_status, "to": new_status, "note": note},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def assign(
    db: Session,
    *,
    ticket_id: str,
    assignee_id: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = str(current_user.get("id") or "")
    prev_assignee = str(t.assigned_to) if t.assigned_to else None
    t.assigned_to = assignee_id or None
    if assignee_id and t.assigned_at is None:
        t.assigned_at = datetime.utcnow()
    # Auto-bump submitted -> assigned when picking an assignee.
    if assignee_id and t.status == "submitted":
        t.status = "assigned"
    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="assignee.changed",
        payload={"from": prev_assignee, "to": assignee_id},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def update_response(
    db: Session,
    *,
    ticket_id: str,
    response_html: str,
    response_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    if not (_is_admin(current_user) or (t.assigned_to and str(t.assigned_to) == str(current_user.get("id") or ""))):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or an admin can edit the response",
        )
    me = str(current_user.get("id") or "")
    now = datetime.utcnow()
    is_first = t.first_response_at is None

    t.response_html = response_html
    t.response_text = response_text or _strip_html(response_html)
    t.responded_by = me
    t.responded_at = now
    if is_first:
        t.first_response_at = now
        if t.submitted_at:
            seconds = (now - t.submitted_at).total_seconds()
            t.response_time_hours = Decimal(str(round(seconds / 3600.0, 2)))

    if t.status == "assigned":
        from_status = t.status
        t.status = "responded"
        activities_service.record_system_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            template="status.changed",
            payload={"from": from_status, "to": "responded", "auto": True},
            actor_id=me,
        )

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="response.updated",
        payload={"first_response": is_first},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def update_resolution(
    db: Session,
    *,
    ticket_id: str,
    resolution_html: str,
    resolution_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    if not (_is_admin(current_user) or (t.assigned_to and str(t.assigned_to) == str(current_user.get("id") or ""))):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or an admin can edit the resolution",
        )
    me = str(current_user.get("id") or "")
    now = datetime.utcnow()

    t.resolution_html = resolution_html
    t.resolution_text = resolution_text or _strip_html(resolution_html)
    t.resolved_by = me
    t.resolved_at = now
    if t.submitted_at:
        seconds = (now - t.submitted_at).total_seconds()
        t.resolution_time_hours = Decimal(str(round(seconds / 3600.0, 2)))

    if t.status in ("responded", "assigned"):
        from_status = t.status
        t.status = "resolved"
        activities_service.record_system_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            template="status.changed",
            payload={"from": from_status, "to": "resolved", "auto": True},
            actor_id=me,
        )

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="resolution.updated",
        payload={},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def add_watchers(
    db: Session,
    *,
    ticket_id: str,
    user_ids: List[str],
    current_user: dict,
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = str(current_user.get("id") or "")
    existing = {
        str(w.user_id)
        for w in db.query(TicketWatcher).filter(TicketWatcher.ticket_id == ticket_id).all()
    }
    added = []
    for uid in {u for u in user_ids if u}:
        if uid in existing:
            continue
        db.add(
            TicketWatcher(
                ticket_id=ticket_id,
                user_id=uid,
                added_by=me or None,
            )
        )
        added.append(uid)
    if added:
        activities_service.record_system_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            template="watchers.added",
            payload={"user_ids": added},
            actor_id=me,
        )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def remove_watcher(
    db: Session,
    *,
    ticket_id: str,
    user_id: str,
    current_user: dict,
) -> None:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = str(current_user.get("id") or "")
    row = (
        db.query(TicketWatcher)
        .filter(TicketWatcher.ticket_id == ticket_id, TicketWatcher.user_id == user_id)
        .first()
    )
    if row is None:
        return
    db.delete(row)
    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="watchers.removed",
        payload={"user_id": user_id},
        actor_id=me,
    )
    db.commit()


def link_attachment(
    db: Session,
    *,
    ticket_id: str,
    attachment_id: str,
    current_user: dict,
) -> Dict[str, Any]:
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = str(current_user.get("id") or "")
    existing = (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.entity_type == ENTITY_TYPE,
            EntityAttachmentLink.entity_id == ticket_id,
            EntityAttachmentLink.attachment_id == attachment_id,
        )
        .first()
    )
    if existing:
        return {"id": str(existing.id), "attachment_id": attachment_id}
    link = EntityAttachmentLink(
        entity_type=ENTITY_TYPE,
        entity_id=ticket_id,
        attachment_id=attachment_id,
        created_by=me or None,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": str(link.id), "attachment_id": attachment_id}


def unlink_attachment(
    db: Session, *, link_id: str, current_user: dict
) -> None:
    link = (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.id == link_id, EntityAttachmentLink.entity_type == ENTITY_TYPE)
        .first()
    )
    if link is None:
        return
    # visibility check via parent ticket
    t = db.query(Ticket).filter(Ticket.id == link.entity_id).first()
    if t is not None:
        _ensure_visible(db, t, current_user)
    db.delete(link)
    db.commit()


# --- activities adapter callbacks --------------------------------------


def respond_contacts_for(db: Session, ticket_id: str) -> List[Dict[str, Any]]:
    rows = _respond_contacts(db, ticket_id)
    return [
        {
            "contact_id": str(r.respond_contact_id),
            "name": None,
            "phone": None,
            "is_primary": bool(r.is_primary),
        }
        for r in rows
    ]


def handle_activity_posted(
    db: Session, ticket_id: str, actor_id: str, body_html: str
) -> None:
    """Activities-registry on_post: if the actor is the assignee and the
    ticket is currently ``assigned``, auto-bump to ``responded`` so a
    chat post counts as a response. Runs inside the activities service's
    own transaction (no extra commit here)."""
    t = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if t is None:
        return
    if not t.assigned_to or str(t.assigned_to) != str(actor_id):
        return
    if t.status != "assigned":
        return
    now = datetime.utcnow()
    t.status = "responded"
    t.responded_at = now
    if t.first_response_at is None:
        t.first_response_at = now
        if t.submitted_at:
            seconds = (now - t.submitted_at).total_seconds()
            t.response_time_hours = Decimal(str(round(seconds / 3600.0, 2)))
    if not t.responded_by:
        t.responded_by = str(actor_id)
    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="status.changed",
        payload={"from": "assigned", "to": "responded", "auto": True, "via": "activity"},
        actor_id=str(actor_id),
    )
