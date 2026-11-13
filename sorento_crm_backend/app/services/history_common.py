"""Helpers the History reads share (STANDARD-HISTORY wave 2): the order inquiry History,
the planning (SO) History and the sales order History all merge `audit_logs` rows for the
same two spellings of the OI row entity, window raises the same way and print times the same.
Wave 5 (the price tag request History) shares the event and line builders and the actor names."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

#: Both spellings: the audit type the writer uses, and the table name older tooling used.
ROW_AUDIT_TYPES = ("project_order_inquiry_rows", "order_inquiry_rows")
#: Rows created this close to a raise or a revision were made by it.
RAISE_WINDOW = timedelta(seconds=5)


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def history_event(event_id, kind, at, actor_id, title, lines, actor=None) -> dict:
    """One event in the wave 1 shape; `_actor_id` is a user id the caller resolves and pops."""
    return {
        "id": event_id, "kind": kind, "at": iso(at) if hasattr(at, "isoformat") else at,
        "actor": actor, "_actor_id": actor_id, "title": title, "lines": list(lines),
    }


def history_line(index: int, event_id: str, so_line_no, item_code, qty, change: str) -> dict:
    """One change line of an event. No row stands behind it, so the key is the event's own."""
    return {
        "row_id": f"{event_id}:{index}",
        "so_line_no": so_line_no,
        "item_code": item_code,
        "qty": qty,
        "change": change.replace(" -> ", " → "),
    }


def contact_names(db, contact_ids: Iterable) -> Dict[str, str]:
    """`contact id -> name` in one query, the portal's own display name rule."""
    from app.models.access import RespondContact
    from app.services.portal_service import PortalService

    ids = {str(i) for i in contact_ids if i}
    if not ids:
        return {}
    rows = db.query(RespondContact).filter(RespondContact.id.in_(list(ids))).all()
    out = {}
    for contact in rows:
        name = PortalService._contact_display_name(contact)  # noqa: SLF001
        if name:
            out[str(contact.id)] = name
    return out


def audit_actor(db, audits) -> dict:
    """`audit id -> who did it, in words`, names resolved in one batch (identity S0).

    An impersonated write reads "<real> on behalf of <effective>", an integration's
    "<integration> on behalf of <user>" (the bare integration when no user is behind it),
    a portal write (`actor_type = contact`) the contact's name, anything else the user's
    name. No person and no integration: None."""
    from app.models.integration import Integration
    from app.services.audit_actor_label import on_behalf_of_label
    from app.services.project_service import resolve_user_names

    audits = list(audits)
    user_ids = set()
    integration_ids = set()
    contact_ids = set()
    for a in audits:
        for uid in (a.user_id, getattr(a, "real_user_id", None)):
            if uid:
                user_ids.add(str(uid))
        if getattr(a, "actor_type", None) == "integration" and getattr(a, "integration_id", None):
            integration_ids.add(str(a.integration_id))
        if getattr(a, "actor_type", None) == "contact" and getattr(a, "contact_id", None):
            contact_ids.add(str(a.contact_id))
    names = resolve_user_names(db, user_ids) if user_ids else {}
    integrations = (
        {str(i): n for i, n in db.query(Integration.id, Integration.name).filter(Integration.id.in_(list(integration_ids))).all()}
        if integration_ids
        else {}
    )
    contacts = contact_names(db, contact_ids)
    out = {}
    for a in audits:
        user = names.get(str(a.user_id)) if a.user_id else None
        real_id = getattr(a, "real_user_id", None)
        impersonating = getattr(a, "auth_method", None) == "impersonation" or (
            real_id is not None and str(real_id) != str(a.user_id)
        )
        if impersonating and real_id and names.get(str(real_id)) and user:
            label = on_behalf_of_label(names[str(real_id)], user)
        elif getattr(a, "actor_type", None) == "integration":
            integration = integrations.get(str(a.integration_id)) if a.integration_id else None
            label = (f"{integration} on behalf of {user}" if user else integration) if integration else user
        elif getattr(a, "actor_type", None) == "contact":
            label = (contacts.get(str(a.contact_id)) if a.contact_id else None) or user
        else:
            label = user
        out[str(a.id)] = label
    return out
