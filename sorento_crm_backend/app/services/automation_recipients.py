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
    """Return list of {email, name, user_id?, cc} dicts, deduped by lowercased email.

    Inputs come from ``Automation.recipient_config``. To (``cc`` False):
    - user_ids, role_ids, extra_emails
    - include_promotion_owner: bool
    - include_assigned_cs_pic: bool  (needs source_id; resolves the active
        customer-service form-SLA assignee for that entity)
    Cc (``cc`` True, DEALER-OI-ROUTE explicit Cc):
    - cc_user_ids, cc_role_ids, cc_emails
    - include_actor: bool  (the person who raised the triggering event, read
        from `promotion_context["actor"]["email"]`; a trigger with no actor adds
        nothing)
    - include_requester / include_raiser: bool (people read off the context)

    With ``explicit_to_cc`` (set by the To/Cc picker on save) every To address is
    resolved before any Cc one, so an address named on both is To. Without it (card Q2 (b),
    a row nobody has re-saved since Cc existed) the list resolves in its old order and every
    entry is marked ``legacy``, so `order_for_email` sends it as before: first address To,
    the rest Cc. `order_for_email` puts the list in send order and says how many are To.
    """
    config = config or {}
    out: dict[str, dict[str, Any]] = {}
    cc = False

    def add(email: str | None, name: str | None = None, user_id: str | None = None) -> None:
        if not email:
            return
        clean = str(email).strip()
        if not _is_valid_email(clean):
            return
        key = clean.lower()
        if key in out:
            return
        out[key] = {"email": clean, "name": name or clean, "user_id": user_id, "cc": cc}

    def add_users(user_ids: list[Any]) -> None:
        if not user_ids:
            return
        users = (
            db.query(User)
            .filter(User.id.in_(user_ids), User.is_trashed.is_(False))
            .all()
        )
        for u in users:
            add(getattr(u, "email", None), getattr(u, "name", None), str(getattr(u, "id")))

    def add_roles(role_ids: list[Any]) -> None:
        if not role_ids:
            return
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

    def to_lists() -> None:
        add_users(list(config.get("user_ids") or []))
        add_roles(list(config.get("role_ids") or []))

    def cs_pic() -> None:
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

    def owner() -> None:
        if config.get("include_promotion_owner") and promotion_context:
            owner_id = (promotion_context.get("promotion") or {}).get("created_by")
            if owner_id:
                owner = db.query(User).filter(User.id == owner_id, User.is_trashed.is_(False)).first()
                if owner is not None:
                    add(getattr(owner, "email", None), getattr(owner, "name", None), str(getattr(owner, "id")))

    def extra() -> None:
        for raw in config.get("extra_emails") or []:
            add(str(raw))

    def cc_lists() -> None:
        add_users(list(config.get("cc_user_ids") or []))
        add_roles(list(config.get("cc_role_ids") or []))
        for raw in config.get("cc_emails") or []:
            add(str(raw))

    def actor() -> None:
        if config.get("include_actor") and promotion_context:
            actor = promotion_context.get("actor") or {}
            if actor.get("email"):
                add(actor.get("email"), actor.get("name"))

    def requester() -> None:
        # PLAN-oi-request-cs-reserve.md 3.6 (AC-RS-16): Cc the person who REQUESTED the
        # reserve and/or the person who RAISED the order inquiry - two more of the same
        # "read a person off the context" shape `include_actor` already is, added in this
        # order so `include_requester` resolves before `include_raiser` (the reserved
        # mail's own To/Cc order: with no To configured, the first of them is To).
        if config.get("include_requester") and promotion_context:
            requester = promotion_context.get("requester") or {}
            if requester.get("email"):
                add(requester.get("email"), requester.get("name"))
            # OI-STAGED-NOTIFY: a bulk (park, send all) email names every requester in it.
            for person in promotion_context.get("requesters") or []:
                add((person or {}).get("email"), (person or {}).get("name"))

    def raiser() -> None:
        if config.get("include_raiser") and promotion_context:
            raiser = promotion_context.get("raiser") or {}
            if raiser.get("email"):
                add(raiser.get("email"), raiser.get("name"))
            for person in promotion_context.get("raisers") or []:
                add((person or {}).get("email"), (person or {}).get("name"))

    if config.get("explicit_to_cc"):
        # Every To address before any Cc one, so an address named on both is To.
        for step in (to_lists, cs_pic, owner, extra):
            step()
        cc = True
        for step in (cc_lists, actor, requester, raiser):
            step()
        return list(out.values())

    # Card Q2 (b): a row nobody has re-saved in the To/Cc picker resolves in today's order
    # and sends as today, first address To and everyone else Cc (`order_for_email`).
    for step in (to_lists, cs_pic, actor, owner, requester, raiser, extra):
        step()
    cc = True
    cc_lists()
    for entry in out.values():
        entry["legacy"] = True
    return list(out.values())


def order_for_email(
    recipients: list[dict[str, Any]], actor_email: str | None
) -> tuple[list[dict[str, Any]], int]:
    """`(ordered, to_count)` for ONE email to everyone (DEALER-OI-ROUTE explicit To/Cc):
    To first, then Cc, then the actor's own address last (AC-H26: it never displaces the
    real To). `to_count` is how many leading addresses go on To; at least one, so an
    email with only Cc configured still has a To."""
    actor = (actor_email or "").strip().lower()

    def is_actor(r: dict[str, Any]) -> bool:
        return bool(actor) and (r.get("email") or "").strip().lower() == actor

    if any(r.get("legacy") for r in recipients):
        # Card Q2 (b): a row not yet re-saved in the To/Cc picker sends as it always did:
        # the first address that is not the actor's To, everyone else Cc, the actor last.
        ordered = [r for r in recipients if not is_actor(r)] + [
            r for r in recipients if is_actor(r)
        ]
        ordered = [{**r, "cc": index > 0} for index, r in enumerate(ordered)]
        return ordered, (1 if ordered else 0)

    to = [r for r in recipients if not r.get("cc") and not is_actor(r)]
    cc = [r for r in recipients if r.get("cc") and not is_actor(r)]
    ordered = to + cc + [r for r in recipients if is_actor(r)]
    # The actor is never counted as To, even when also configured under To.
    return ordered, (max(len(to), 1) if ordered else 0)


def to_count(ordered: list[dict[str, Any]]) -> int:
    """How many leading entries of an `order_for_email` list are To (at least one)."""
    n = 0
    for r in ordered:
        if r.get("cc"):
            break
        n += 1
    return max(n, 1) if ordered else 0
