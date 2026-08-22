"""Composer message snippets: admin CRUD + `$variable` resolution (UAC AC-L4).

Respond.io's snippets are a client-side feature of their app with no API, so
this is the self-hosted equivalent. Two jobs live here:

1. **CRUD** for the admin listing (workspace-global, hard delete).
2. **Insert-time variable resolution.** A snippet body stores `$tokens`; the
   composer picker asks for them RESOLVED against the ticket it is open on, and
   what lands in the input is plain text the assignee can then edit. Nothing is
   ever stored resolved, so editing a snippet reaches every future insert.

The token set is deliberately tiny and CLOSED: `$contact_name`,
`$assignee_name`, `$ticket_ref`. Anything else that looks like a token is left
exactly as typed, because a snippet is free text a person wrote - "$50 deposit"
must survive an insert, and silently blanking an unrecognised token would be the
worst possible failure (the contact reads the hole, not us).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.message_snippet import MessageSnippet
from app.schemas.message_snippet import MessageSnippetCreate, MessageSnippetUpdate
from app.services.error_handler import handle_conflict, handle_not_found

# What a person is called when we do not know their name. "Hi ," is worse than
# "Hi there," and it is the contact who reads it.
UNKNOWN_CONTACT_NAME = "there"
# Matches the drawer's own default sender name (`sender_name` on the send route).
UNKNOWN_ASSIGNEE_NAME = "Customer Service"

SNIPPET_VARIABLES = ("contact_name", "assignee_name", "ticket_ref")

# `$` followed by an identifier. The FULL identifier is looked up, so
# `$contact_names` is a token named "contact_names" - unknown, left literal -
# rather than `$contact_name` with a stray "s" glued on.
_TOKEN_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

_SORTABLE = {
    "name": MessageSnippet.name,
    "shortcut": MessageSnippet.shortcut,
    "is_active": MessageSnippet.is_active,
    "created_at": MessageSnippet.created_at,
    "updated_at": MessageSnippet.updated_at,
}


@dataclass(frozen=True)
class SnippetContext:
    """Everything a snippet body may refer to. Empty strings mean "unknown"."""

    contact_name: str = ""
    assignee_name: str = ""
    ticket_ref: str = ""


def ticket_reference(tracking_id: Optional[str]) -> str:
    """A short, human-quotable reference for a ticket.

    The conversation SLA table has no reference column and inventing one would
    need a sequence plus a backfill for every existing row. The last six hex
    characters of the id are stable, collision-safe enough to quote in a
    WhatsApp message, and short enough that nobody reads it as a UUID - which is
    the rule the "no UUIDs in the UI" mandate is actually protecting.
    """
    raw = str(tracking_id or "").replace("-", "")
    if not raw:
        return ""
    return f"ENQ-{raw[-6:].upper()}"


def _contact_display_name(contact: Any) -> str:
    if contact is None:
        return ""
    name = (getattr(contact, "name", None) or "").strip()
    if name:
        return name
    parts = [
        (getattr(contact, "first_name", None) or "").strip(),
        (getattr(contact, "last_name", None) or "").strip(),
    ]
    return " ".join(p for p in parts if p).strip()


def snippet_context_for_tracking(
    tracking: Any, *, viewer_name: Optional[str] = None
) -> SnippetContext:
    """Build the substitution context from a conversation SLA tracking row.

    ``viewer_name`` (the person doing the inserting) wins over the row's
    assignee: a manager answering on a colleague's behalf signs their OWN name,
    and the assignee is only the fallback when the viewer is unknown.
    """
    return SnippetContext(
        contact_name=_contact_display_name(getattr(tracking, "contact", None)),
        assignee_name=(viewer_name or "").strip()
        or (getattr(tracking, "assigned_to", None) or "").strip(),
        ticket_ref=ticket_reference(getattr(tracking, "id", None)),
    )


def resolve_snippet_variables(body: str, context: SnippetContext) -> str:
    """Substitute the known `$tokens`; leave everything else exactly as typed."""
    if not body:
        return ""
    values = {
        "contact_name": context.contact_name.strip() or UNKNOWN_CONTACT_NAME,
        "assignee_name": context.assignee_name.strip() or UNKNOWN_ASSIGNEE_NAME,
        "ticket_ref": context.ticket_ref.strip(),
    }

    def _sub(match: re.Match) -> str:
        token = match.group(1)
        if token not in values:
            return match.group(0)
        # An empty resolution (no ticket ref) leaves the token rather than a
        # hole: a visible "$ticket_ref" is a bug someone reports, an invisible
        # gap is one nobody notices.
        return values[token] or match.group(0)

    return _TOKEN_RE.sub(_sub, body)


class MessageSnippetService:
    """CRUD for message snippets, plus the composer's resolved picker list."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- admin CRUD

    def list_snippets(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_field: str = "name",
        sort_dir: str = "asc",
    ) -> dict:
        q = self.db.query(MessageSnippet)
        if query:
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    MessageSnippet.name.ilike(term),
                    MessageSnippet.shortcut.ilike(term),
                    MessageSnippet.body.ilike(term),
                )
            )
        if is_active is not None:
            q = q.filter(MessageSnippet.is_active.is_(is_active))

        total = q.count()
        column = _SORTABLE.get(sort_field or "name", MessageSnippet.name)
        q = q.order_by(column.desc() if (sort_dir or "asc").lower() == "desc" else column.asc())
        rows = q.offset(max(0, (page - 1)) * limit).limit(limit).all()
        return {
            "data": rows,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get_snippet(self, snippet_id: str) -> MessageSnippet:
        row = (
            self.db.query(MessageSnippet)
            .filter(MessageSnippet.id == str(snippet_id))
            .first()
        )
        if not row:
            raise handle_not_found("Message snippet", snippet_id)
        return row

    def _assert_shortcut_free(self, shortcut: Optional[str], exclude_id: Optional[str] = None):
        if not shortcut:
            return
        q = self.db.query(MessageSnippet).filter(
            func.lower(MessageSnippet.shortcut) == shortcut.lower()
        )
        if exclude_id:
            q = q.filter(MessageSnippet.id != str(exclude_id))
        if q.first():
            raise handle_conflict(
                f"A snippet with the shortcut '{shortcut}' already exists."
            )

    def _commit_or_conflict(self, shortcut: Optional[str]) -> None:
        """Commit, turning the shortcut index's veto into the same 409 the
        pre-check gives.

        ``_assert_shortcut_free`` is a read-then-write check, so two admins
        saving the same shortcut at once both pass it and the second one hits
        ``uq_message_snippets_shortcut``. That is the index doing its job; the
        caller still deserves "that shortcut is taken" rather than an internal
        error.
        """
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise handle_conflict(
                f"A snippet with the shortcut '{shortcut}' already exists."
                if shortcut
                else "That snippet conflicts with an existing one."
            )

    def create_snippet(
        self, payload: MessageSnippetCreate, created_by: Optional[str] = None
    ) -> MessageSnippet:
        self._assert_shortcut_free(payload.shortcut)
        row = MessageSnippet(**payload.model_dump(), created_by=created_by)
        self.db.add(row)
        self._commit_or_conflict(payload.shortcut)
        self.db.refresh(row)
        return row

    def update_snippet(
        self, snippet_id: str, payload: MessageSnippetUpdate
    ) -> MessageSnippet:
        row = self.get_snippet(snippet_id)
        data = payload.model_dump(exclude_unset=True)
        if "shortcut" in data:
            self._assert_shortcut_free(data["shortcut"], exclude_id=snippet_id)
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = func.now()
        self._commit_or_conflict(data.get("shortcut", row.shortcut))
        self.db.refresh(row)
        return row

    def delete_snippet(self, snippet_id: str) -> dict:
        """Hard delete (product standard). A snippet has no dependants: the text
        was copied into the message the moment it was inserted."""
        row = self.get_snippet(snippet_id)
        self.db.delete(row)
        self.db.commit()
        return {"message": "Message snippet deleted successfully"}

    # -------------------------------------------------------- composer picker

    def list_for_composer(
        self,
        *,
        query: Optional[str] = None,
        context: Optional[SnippetContext] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Active snippets for the "/" picker, each with its body resolved.

        Filtering is server-side on name AND shortcut so typing "/stk" narrows
        the same way whichever the admin named it by. The picker keeps filtering
        client-side over this list as the user types - the round trip is for the
        first "/" only.
        """
        ctx = context or SnippetContext()
        q = self.db.query(MessageSnippet).filter(MessageSnippet.is_active.is_(True))
        if query:
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(MessageSnippet.name.ilike(term), MessageSnippet.shortcut.ilike(term))
            )
        rows = q.order_by(MessageSnippet.name.asc()).limit(max(1, min(limit, 200))).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "shortcut": row.shortcut,
                "body": row.body,
                "resolved_body": resolve_snippet_variables(row.body or "", ctx),
            }
            for row in rows
        ]
