"""Resolve automation recipient_config to concrete email addresses."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User, UserRoleAssignment


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value or ""))


def resolve_recipients(
    db: Session,
    config: dict[str, Any],
    promotion_context: dict[str, Any] | None = None,
    *,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return list of {email, name, user_id?} dicts, deduped by lowercased email.

    Inputs come from ``Automation.recipient_config``:
      - user_ids: list[str]
      - role_ids: list[str]
      - include_promotion_owner: bool
      - include_assigned_cs_pic: bool  (needs source_id; resolves the active
        customer-service form-SLA assignee for that entity)
      - extra_emails: list[str]
    """
    config = config or {}
    out: dict[str, dict[str, Any]] = {}

    def add(email: str | None, name: str | None = None, user_id: str | None = None) -> None:
        if not email:
            return
        clean = str(email).strip()
        if not _is_valid_email(clean):
            return
        key = clean.lower()
        if key in out:
            return
        out[key] = {"email": clean, "name": name or clean, "user_id": user_id}

    user_ids = list(config.get("user_ids") or [])
    role_ids = list(config.get("role_ids") or [])

    if user_ids:
        users = (
            db.query(User)
            .filter(User.id.in_(user_ids), User.is_trashed.is_(False))
            .all()
        )
        for u in users:
            add(getattr(u, "email", None), getattr(u, "name", None), str(getattr(u, "id")))

    if role_ids:
        rows = (
            db.query(User)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .filter(
                UserRoleAssignment.role_id.in_(role_ids),
                User.is_trashed.is_(False),
                User.status == "ACTIVE",
            )
            .all()
        )
        for u in rows:
            add(getattr(u, "email", None), getattr(u, "name", None), str(getattr(u, "id")))

    if config.get("include_assigned_cs_pic") and source_id:
        from app.models.sla import ConversationSLATracking
        from app.services.sla_scope import open_tracker_scope

        tracker = (
            db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_id == str(source_id),
                ConversationSLATracking.team_set_code == "customer_service",
                *open_tracker_scope(),
            )
            .order_by(ConversationSLATracking.initiated_at.desc())
            .first()
        )
        if tracker is not None and tracker.assigned_to_id:
            pic = (
                db.query(User)
                .filter(User.id == tracker.assigned_to_id, User.is_trashed.is_(False))
                .first()
            )
            if pic is not None:
                add(getattr(pic, "email", None), getattr(pic, "name", None), str(getattr(pic, "id")))

    if config.get("include_promotion_owner") and promotion_context:
        owner_id = (promotion_context.get("promotion") or {}).get("created_by")
        if owner_id:
            owner = db.query(User).filter(User.id == owner_id, User.is_trashed.is_(False)).first()
            if owner is not None:
                add(getattr(owner, "email", None), getattr(owner, "name", None), str(getattr(owner, "id")))

    for raw in config.get("extra_emails") or []:
        add(str(raw))

    return list(out.values())
