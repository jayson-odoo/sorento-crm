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

from app.models.access import RespondContact
from app.models.entity_attachment import EntityAttachmentLink
from app.models.tickets import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    Ticket,
    TicketRespondContactLink,
    TicketWatcher,
)
from app.models.user import User
from app.services import activities_service
from app.services.form_sla_service import emit_form_event

logger = logging.getLogger(__name__)

# Default SLA windows (hours) - overridable later via SLAPolicy lookup.
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


def _has_view_all(db: Session, current_user: dict) -> bool:
    # JWT carries no perms; resolve via DB.
    from app.services.user_service import UserPermissionService
    uid = current_user.get("id")
    if not uid:
        return False
    return UserPermissionService(db).check_user_has_permission(
        str(uid), "tickets.tickets.view_all"
    )


def _is_admin(db: Session, current_user: dict) -> bool:
    from app.services.user_service import UserPermissionService
    uid = current_user.get("id")
    if not uid:
        return False
    slugs = UserPermissionService(db).get_user_role_slugs(str(uid))
    return bool(slugs & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"})


def _has_perm(db: Session, current_user: dict, slug: str) -> bool:
    from app.services.user_service import UserPermissionService
    uid = current_user.get("id")
    if not uid:
        return False
    return UserPermissionService(db).check_user_has_permission(str(uid), slug)


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


def _respond_contact_ref(contact: Optional[RespondContact]) -> Optional[Dict[str, Any]]:
    if contact is None:
        return None
    name = (
        getattr(contact, "name", None)
        or " ".join(
            filter(
                None,
                [getattr(contact, "first_name", None), getattr(contact, "last_name", None)],
            )
        ).strip()
        or getattr(contact, "phone_number", None)
        or str(getattr(contact, "id", ""))
    )
    return {
        "id": str(contact.id),
        "display_name": name or None,
        "phone_number": getattr(contact, "phone_number", None),
        "respond_io_id": getattr(contact, "respond_io_id", None),
    }


def _actor_ref(
    db: Session,
    raised_by: Optional[str],
    raised_by_kind: str,
    user_cache: Dict[str, User],
) -> Optional[Dict[str, Any]]:
    """Resolve a polymorphic raised_by to a {kind, id, display_name, ...} dict.

    Looks up users.id when ``raised_by_kind='user'`` and respond_contacts.id when
    ``raised_by_kind='respond_contact'``. Returns ``None`` for unknown ids."""
    if not raised_by:
        return None
    if raised_by_kind == "respond_contact":
        contact = (
            db.query(RespondContact).filter(RespondContact.id == str(raised_by)).first()
        )
        ref = _respond_contact_ref(contact)
        if ref is None:
            return None
        return {"kind": "respond_contact", **ref}
    user = user_cache.get(str(raised_by))
    ref = _user_ref(user)
    if ref is None:
        return None
    return {
        "kind": "user",
        "id": ref["id"],
        "display_name": ref.get("display_name"),
        "email": ref.get("email"),
        "avatar_url": ref.get("avatar_url"),
    }


def _generate_ticket_number(db: Session) -> str:
    """``TCK-YYYY-NNNNNN`` monotonic per year using MAX(suffix) + 1.

    NOT ``count(*) + 1``: tickets are hard-deleted (project delete standard), which
    leaves gaps in the sequence. With count-based numbering a delete lowers the
    count so the next number collides with an existing row (``uq_tickets_ticket_number``
    → IntegrityError). MAX+1 is stable against deletions. The suffix is fixed-width
    zero-padded, so the lexicographic MAX of ``ticket_number`` is also the numeric MAX.

    A more robust running-number rule via ``DocumentNumberingRule`` can be
    swapped in here without touching callers.
    """
    year = datetime.utcnow().year
    prefix = f"TCK-{year}-"
    latest = (
        db.query(func.max(Ticket.ticket_number))
        .filter(Ticket.ticket_number.like(f"{prefix}%"))
        .scalar()
    )
    last_seq = 0
    if latest:
        try:
            last_seq = int(str(latest)[len(prefix):])
        except (ValueError, TypeError):
            last_seq = 0
    return f"{prefix}{last_seq + 1:06d}"


def _visibility_filter(db: Session, current_user: dict):
    """Return a SQLAlchemy filter restricting to tickets the user can see.

    raised_by-by-user matches only when ``raised_by_kind='user'`` - a respond
    contact's id sharing the same string as a user.id is impossible in practice
    but the discriminator avoids any accidental collision."""
    if _has_view_all(db, current_user) or _is_admin(db, current_user):
        return None
    me = str(current_user.get("id") or "")
    if not me:
        return Ticket.id.is_(None)  # nothing visible
    watcher_match = exists().where(
        and_(TicketWatcher.ticket_id == Ticket.id, TicketWatcher.user_id == me)
    )
    return or_(
        and_(Ticket.raised_by_kind == "user", Ticket.raised_by == me),
        Ticket.assigned_to == me,
        watcher_match,
    )


def can_view(db: Session, ticket_id: str, current_user: dict) -> bool:
    t = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if t is None:
        return False
    if _has_view_all(db, current_user) or _is_admin(db, current_user):
        return True
    me = str(current_user.get("id") or "")
    if not me:
        return False
    if t.raised_by_kind == "user" and t.raised_by and str(t.raised_by) == me:
        return True
    if t.assigned_to and str(t.assigned_to) == me:
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
    user_ids: List[str] = []
    if ticket.raised_by_kind == "user" and ticket.raised_by:
        user_ids.append(str(ticket.raised_by))
    if ticket.assigned_to:
        user_ids.append(str(ticket.assigned_to))
    if ticket.responded_by:
        user_ids.append(str(ticket.responded_by))
    if ticket.resolved_by:
        user_ids.append(str(ticket.resolved_by))
    users = _user_map(db, user_ids)
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

    raised_by_user = (
        _user_ref(users.get(str(ticket.raised_by)))
        if ticket.raised_by_kind == "user" and ticket.raised_by
        else None
    )
    raised_by_actor = _actor_ref(db, ticket.raised_by, ticket.raised_by_kind, users)

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
        "raised_by": str(ticket.raised_by) if ticket.raised_by else None,
        "raised_by_kind": ticket.raised_by_kind,
        "raised_by_user": raised_by_user,
        "raised_by_actor": raised_by_actor,
        "source_channel": ticket.source_channel,
        "source_conversation_id": ticket.source_conversation_id,
        "source_message_id": ticket.source_message_id,
        "source_space_id": ticket.source_space_id,
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
    vf = _visibility_filter(db, current_user)
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
    if filters.get("source_channel"):
        q = q.filter(Ticket.source_channel == filters["source_channel"])
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
    vf = _visibility_filter(db, current_user)
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

    if submitted_now:
        emit_form_event(
            db,
            ENTITY_TYPE,
            str(ticket.id),
            "submit",
            actor_user_id=me,
        )
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
    if not (_is_admin(db, current_user) or _has_perm(db, current_user, "tickets.tickets.delete")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    db.delete(t)
    db.commit()


def bulk_delete_tickets(
    db: Session, *, ids: List[str], current_user: dict
) -> None:
    if not ids:
        return
    if not (_is_admin(db, current_user) or _has_perm(db, current_user, "tickets.tickets.delete")):
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


def _can_change_status(db: Session, ticket: Ticket, current_user: dict) -> bool:
    if _is_admin(db, current_user):
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
    if not _can_change_status(db, t, current_user):
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
    if assignee_id:
        emit_form_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            "assigned",
            actor_user_id=me,
        )
    return ticket_to_response(db, t)


def _ensure_can_edit_response(db: Session, t: Ticket, current_user: dict) -> str:
    if not (_is_admin(db, current_user) or (t.assigned_to and str(t.assigned_to) == str(current_user.get("id") or ""))):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or an admin can edit the response",
        )
    return str(current_user.get("id") or "")


def _ensure_can_edit_resolution(db: Session, t: Ticket, current_user: dict) -> str:
    if not (_is_admin(db, current_user) or (t.assigned_to and str(t.assigned_to) == str(current_user.get("id") or ""))):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignee or an admin can edit the resolution",
        )
    return str(current_user.get("id") or "")


def update_response(
    db: Session,
    *,
    ticket_id: str,
    response_html: str,
    response_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    """Save the response payload only - does not flip status or notify the
    submitter. Use ``update_response_and_reply`` for the full flow."""
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = _ensure_can_edit_response(db, t, current_user)
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

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="response.updated",
        payload={"first_response": is_first, "and_reply": False},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def update_response_and_reply(
    db: Session,
    *,
    ticket_id: str,
    response_html: str,
    response_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    """Save the response, flip the ticket from ``assigned`` to ``responded``,
    notify the submitter via their channel (WhatsApp for respond contacts,
    in-app + email for system users), and emit the form-SLA ``responded``
    event."""
    from app.services import ticket_notification_service

    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = _ensure_can_edit_response(db, t, current_user)
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

    if t.status in ("submitted", "assigned"):
        from_status = t.status
        t.status = "responded"
        activities_service.record_system_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            template="status.changed",
            payload={"from": from_status, "to": "responded", "via": "update_and_reply"},
            actor_id=me,
        )

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="response.updated",
        payload={"first_response": is_first, "and_reply": True},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)

    ticket_notification_service.notify_submitter_on_status_change(
        db, ticket=t, kind="responded"
    )
    emit_form_event(db, ENTITY_TYPE, str(t.id), "responded", actor_user_id=me)
    return ticket_to_response(db, t)


def update_resolution(
    db: Session,
    *,
    ticket_id: str,
    resolution_html: str,
    resolution_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    """Save the resolution payload only - does not flip status or notify the
    submitter. Use ``update_resolution_and_reply`` for the full flow."""
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = _ensure_can_edit_resolution(db, t, current_user)
    now = datetime.utcnow()

    t.resolution_html = resolution_html
    t.resolution_text = resolution_text or _strip_html(resolution_html)
    t.resolved_by = me
    t.resolved_at = now
    if t.submitted_at:
        seconds = (now - t.submitted_at).total_seconds()
        t.resolution_time_hours = Decimal(str(round(seconds / 3600.0, 2)))

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="resolution.updated",
        payload={"and_reply": False},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)
    return ticket_to_response(db, t)


def update_resolution_and_reply(
    db: Session,
    *,
    ticket_id: str,
    resolution_html: str,
    resolution_text: Optional[str],
    current_user: dict,
) -> Dict[str, Any]:
    """Save the resolution, flip the ticket to ``resolved``, notify the
    submitter via their channel, and emit the form-SLA ``resolved`` event."""
    from app.services import ticket_notification_service

    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    me = _ensure_can_edit_resolution(db, t, current_user)
    now = datetime.utcnow()

    t.resolution_html = resolution_html
    t.resolution_text = resolution_text or _strip_html(resolution_html)
    t.resolved_by = me
    t.resolved_at = now
    if t.submitted_at:
        seconds = (now - t.submitted_at).total_seconds()
        t.resolution_time_hours = Decimal(str(round(seconds / 3600.0, 2)))

    if t.status in ("submitted", "assigned", "responded"):
        from_status = t.status
        t.status = "resolved"
        activities_service.record_system_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            template="status.changed",
            payload={"from": from_status, "to": "resolved", "via": "update_and_reply"},
            actor_id=me,
        )

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="resolution.updated",
        payload={"and_reply": True},
        actor_id=me,
    )
    db.commit()
    db.refresh(t)

    ticket_notification_service.notify_submitter_on_status_change(
        db, ticket=t, kind="resolved"
    )
    emit_form_event(db, ENTITY_TYPE, str(t.id), "resolved", actor_user_id=me)
    return ticket_to_response(db, t)


def create_ticket_from_mcp(
    db: Session,
    *,
    title: str,
    priority: str,
    category: str,
    description_html: str,
    description_text: str,
    source_channel: str,
    raised_by: str,
    raised_by_kind: str,
    actor_user_id: Optional[str] = None,
    source_conversation_id: Optional[str] = None,
    source_message_id: Optional[str] = None,
    source_space_id: Optional[str] = None,
    respond_contact_id: Optional[str] = None,
) -> Ticket:
    """Create a DRAFT ticket from the MCP intake endpoint.

    The draft is intentionally minimal: no round-robin assignment, no SLA
    emit, no notifications. The submitter is expected to open the returned
    link, review the preview on a real ticket page, and click "Submit" - 
    that path (``submit_ticket_draft``) is what fires the rest of the
    workflow. This avoids the LLM-confirmation-state-machine fragility
    altogether by delegating the explicit confirm to a real UI."""
    if priority not in TICKET_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"priority must be one of {TICKET_PRIORITIES}",
        )
    if category not in TICKET_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"category must be one of {TICKET_CATEGORIES}",
        )

    ticket = Ticket(
        ticket_number=_generate_ticket_number(db),
        title=title,
        description_html=description_html,
        description_text=description_text or _strip_html(description_html),
        status="draft",
        priority=priority,
        category=category,
        raised_by=raised_by,
        raised_by_kind=raised_by_kind,
        source_channel=source_channel,
        source_conversation_id=source_conversation_id,
        source_message_id=source_message_id,
        source_space_id=source_space_id,
    )
    db.add(ticket)
    db.flush()

    if respond_contact_id:
        db.add(
            TicketRespondContactLink(
                ticket_id=str(ticket.id),
                respond_contact_id=str(respond_contact_id),
                is_primary=True,
                created_by=actor_user_id,
            )
        )

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(ticket.id),
        template="entity.created",
        payload={
            "ticket_number": ticket.ticket_number,
            "status": ticket.status,
            "source_channel": source_channel,
            "raised_by_kind": raised_by_kind,
        },
        actor_id=actor_user_id,
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def submit_ticket_draft(
    db: Session, *, ticket_id: str, current_user: dict
) -> Dict[str, Any]:
    """Promote a draft ticket to submitted/assigned. Round-robin picks an
    assignee from the it_support tier-1 team, fires assignee + team
    notifications, emits the FormSLA ``submit`` event so the SLA timer
    starts. No-op if the ticket is not in ``draft`` status."""
    from app.models.access import AccessAgent
    from app.services import ticket_notification_service
    from app.services.user_service import AccessAgentService

    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    if t.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is not a draft (status={t.status}); cannot submit.",
        )

    me = str(current_user.get("id") or "") or None
    now = datetime.utcnow()

    agent_svc = AccessAgentService(db)
    agent = db.query(AccessAgent).filter(AccessAgent.code == "it_support").first()
    assignee_id: Optional[str] = None
    team_id: Optional[str] = None
    if agent:
        # AC-E4: tickets carry no contact column at all, so there is no company
        # signal to derive from - they route to the incumbent.
        from app.services.company_routing_service import DEFAULT_COMPANY_ID

        team_id = agent_svc.get_team_id_by_tier(
            str(agent.id), 1, team_set_code="it_admin", company_id=DEFAULT_COMPANY_ID
        )
        if team_id:
            assignee = agent_svc.get_next_assignee(str(agent.id), team_id)
            if assignee:
                assignee_id = assignee["id"]

    t.submitted_at = now
    t.sla_response_due_at = now + timedelta(hours=DEFAULT_RESPONSE_SLA_HOURS)
    t.sla_resolution_due_at = now + timedelta(hours=DEFAULT_RESOLUTION_SLA_HOURS)
    if assignee_id:
        t.assigned_to = assignee_id
        t.assigned_at = now
        t.status = "assigned"
    else:
        t.status = "submitted"

    activities_service.record_system_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        template="status.changed",
        payload={"from": "draft", "to": t.status, "via": "submit_draft"},
        actor_id=me,
    )
    if assignee_id:
        activities_service.record_system_event(
            db,
            ENTITY_TYPE,
            str(t.id),
            template="assignee.changed",
            payload={"from": None, "to": assignee_id, "via": "round_robin"},
            actor_id=me,
        )

    db.commit()
    db.refresh(t)

    if assignee_id:
        ticket_notification_service.notify_assignee_and_team_on_create(
            db, ticket=t, assignee_id=assignee_id, team_id=team_id
        )

    primary_link = (
        db.query(TicketRespondContactLink)
        .filter(TicketRespondContactLink.ticket_id == str(t.id))
        .order_by(TicketRespondContactLink.is_primary.desc())
        .first()
    )
    contact_id = (
        str(primary_link.respond_contact_id) if primary_link else None
    )
    emit_form_event(
        db,
        ENTITY_TYPE,
        str(t.id),
        "submit",
        contact_id=contact_id,
        actor_user_id=me,
    )
    return ticket_to_response(db, t)


def cancel_ticket_draft(
    db: Session, *, ticket_id: str, current_user: dict
) -> None:
    """Hard-delete a draft ticket. Only the raiser, the assignee, or an
    admin can cancel."""
    t = _get_or_404(db, ticket_id)
    _ensure_visible(db, t, current_user)
    if t.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is not a draft (status={t.status}); cannot cancel.",
        )
    db.delete(t)
    db.commit()


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
