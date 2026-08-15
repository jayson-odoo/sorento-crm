"""The Conversations inbox list (UAC AC-N1).

One screen: every contact we have ever exchanged a message with, newest
conversation first, filtered by a tab and an optional name / phone search. The
thread itself is never loaded here - the caller picks a row and then calls the
contact-keyed thread endpoints.

Three things decide the shape of this module.

**It has to survive 10 000+ contacts.** So: keyset pagination (never OFFSET),
and ONE SQL statement per page. Both the tab predicates and the per-row ticket
counts are folded into that single statement - the counts through a LATERAL
join applied AFTER the page's LIMIT, so the aggregate runs `limit` times, not
once per contact in the database. A per-row thread fetch is exactly what AC-N1
forbids, so the last message comes from a `DISTINCT ON (contact_id)` over
``chat_histories`` served by ``ix_chat_histories_contact_sent_desc``
(alembic 330).

**The cursor is a pair, not a timestamp.** A bulk ingest writes many messages
with the same ``sent_at``; a cursor on time alone silently drops every row after
the first of a tie. The keyset is therefore ``(sort_at, contact_pk)`` compared
as a row value, matching ``ORDER BY sort_at DESC, contact_pk DESC``.

**"Newest first" is not the same clock on every tab.** Mine / Unassigned / All
sort by last message time; Mentioned sorts by the newest note that mentions the
caller (AC-N1: "a note that mentions me, newest first") - the message that
triggered the mention may be months old.

Scaling follow-up (noted in PLAN S4.9): the `DISTINCT ON` walks one index entry
per stored message. If that stops being cheap, the fix is a
``respond_contacts.last_message_at`` column maintained by the ingest, and this
module's CTE becomes a column read. Nothing else changes.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Text, and_, cast, func, or_, select, true, tuple_
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.chat_history import ChatHistory
from app.models.sla import ConversationSLATracking
from app.models.ticket_comment import ConversationTicketComment
from app.services.error_handler import handle_validation_error

TAB_MINE = "mine"
TAB_MENTIONED = "mentioned"
TAB_UNASSIGNED = "unassigned"
TAB_ALL = "all"
TABS = (TAB_MINE, TAB_MENTIONED, TAB_UNASSIGNED, TAB_ALL)

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
SNIPPET_MAX = 160


# --------------------------------------------------------------------------- #
# Cursor                                                                       #
# --------------------------------------------------------------------------- #


def encode_cursor(sort_at: datetime, contact_pk: str) -> str:
    """Opaque, but deliberately decodable by us: it is a keyset position, not a
    secret. Base64 keeps it URL-safe and keeps callers from parsing it."""
    raw = f"{sort_at.isoformat()}|{contact_pk}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(raw: Optional[str]) -> Optional[tuple[datetime, str]]:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
        stamp, _, contact_pk = decoded.partition("|")
        return datetime.fromisoformat(stamp), contact_pk
    except (ValueError, UnicodeDecodeError, binascii.Error):
        # A cursor the client did not get from us. Refusing is better than
        # silently restarting from page one, which reads as duplicated rows.
        raise handle_validation_error("Invalid cursor.")


# --------------------------------------------------------------------------- #
# Pieces                                                                       #
# --------------------------------------------------------------------------- #


def _like_pattern(q: str) -> str:
    """`%`, `_` and the escape character are literals in a user's search."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _open_conversation_ticket_clause():
    """An OPEN ticket on the CONVERSATION side of the shared table.

    `conversation_sla_tracking` also holds form-SLA stage rows, discriminated
    only by `source_entity_type`; counting those here would show a complaint
    stage as an open enquiry on the contact's inbox row.
    """
    from app.services.form_sla_service import FORM_SLA_TYPES

    return and_(
        ConversationSLATracking.is_resolved.is_(False),
        or_(
            ConversationSLATracking.source_entity_type.is_(None),
            ConversationSLATracking.source_entity_type.notin_(FORM_SLA_TYPES),
        ),
    )


def _last_message_cte():
    return (
        select(
            ChatHistory.contact_id.label("contact_key"),
            ChatHistory.sent_at.label("last_at"),
            ChatHistory.message.label("last_message"),
            ChatHistory.type.label("last_direction"),
        )
        .distinct(ChatHistory.contact_id)
        .order_by(
            ChatHistory.contact_id,
            ChatHistory.sent_at.desc(),
            ChatHistory.id.desc(),
        )
        .cte("last_msg")
    )


def _mentions_cte(viewer_user_id: str):
    return (
        select(
            ConversationTicketComment.respond_contact_id.label("contact_pk"),
            func.max(ConversationTicketComment.created_at).label("mentioned_at"),
        )
        .where(
            ConversationTicketComment.respond_contact_id.isnot(None),
            ConversationTicketComment.mentioned_user_ids.any(str(viewer_user_id)),
        )
        .group_by(ConversationTicketComment.respond_contact_id)
        .cte("mentions")
    )


def _snippet(body: Optional[str]) -> Optional[str]:
    text = (body or "").strip()
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= SNIPPET_MAX:
        return collapsed
    return collapsed[: SNIPPET_MAX - 1].rstrip() + "…"


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


# --------------------------------------------------------------------------- #
# The read                                                                     #
# --------------------------------------------------------------------------- #


def list_conversations(
    db: Session,
    *,
    viewer_user_id: str,
    tab: str = TAB_ALL,
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """One keyset page of the inbox. Exactly one SQL statement.

    ``my_open_ticket_id`` is only populated when the caller holds EXACTLY ONE
    open ticket for that contact: that is the only case where a reply can be
    stamped without guessing which enquiry it answers (AC-N2), so a caller that
    holds two must not be handed one of them.
    """
    tab = (tab or TAB_ALL).strip().lower()
    if tab not in TABS:
        raise handle_validation_error(
            f"Unknown tab '{tab}'. Expected one of: {', '.join(TABS)}."
        )
    limit = max(1, min(int(DEFAULT_LIMIT if limit is None else limit), MAX_LIMIT))
    viewer = str(viewer_user_id)
    after = decode_cursor(cursor)

    last_msg = _last_message_cte()

    if tab == TAB_MENTIONED:
        mentions = _mentions_cte(viewer)
        sort_at = mentions.c.mentioned_at
        mentioned_at = mentions.c.mentioned_at
        source = RespondContact.__table__.join(
            mentions, mentions.c.contact_pk == RespondContact.id
        ).outerjoin(last_msg, last_msg.c.contact_key == RespondContact.respond_io_id)
    else:
        mentioned_at = func.cast(None, ConversationTicketComment.created_at.type)
        # "All" is defined by AC-N1 as every contact with ANY message, so the
        # message join is the filter. On the ticket tabs a contact with an open
        # ticket but no stored message still has to be reachable, so the join
        # is outer and the sort falls back to when we learnt about them.
        if tab == TAB_ALL:
            source = RespondContact.__table__.join(
                last_msg, last_msg.c.contact_key == RespondContact.respond_io_id
            )
            sort_at = last_msg.c.last_at
        else:
            source = RespondContact.__table__.outerjoin(
                last_msg, last_msg.c.contact_key == RespondContact.respond_io_id
            )
            sort_at = func.coalesce(last_msg.c.last_at, RespondContact.created_at)

    conditions = []
    if tab == TAB_MINE:
        conditions.append(
            select(1)
            .select_from(ConversationSLATracking)
            .where(
                ConversationSLATracking.respond_contact_id == RespondContact.id,
                ConversationSLATracking.assigned_to_id == viewer,
                _open_conversation_ticket_clause(),
            )
            .exists()
        )
    elif tab == TAB_UNASSIGNED:
        conditions.append(
            select(1)
            .select_from(ConversationSLATracking)
            .where(
                ConversationSLATracking.respond_contact_id == RespondContact.id,
                ConversationSLATracking.assigned_to_id.is_(None),
                _open_conversation_ticket_clause(),
            )
            .exists()
        )

    needle = (q or "").strip()
    if needle:
        pattern = _like_pattern(needle)
        conditions.append(
            or_(
                RespondContact.name.ilike(pattern, escape="\\"),
                RespondContact.phone_number.ilike(pattern, escape="\\"),
            )
        )

    if after is not None:
        conditions.append(
            tuple_(sort_at, RespondContact.id) < tuple_(after[0], after[1])
        )

    page = (
        select(
            RespondContact.id.label("contact_pk"),
            RespondContact.respond_io_id.label("respond_io_id"),
            RespondContact.phone_number.label("phone"),
            RespondContact.name.label("name"),
            last_msg.c.last_at.label("last_message_at"),
            last_msg.c.last_message.label("last_message"),
            last_msg.c.last_direction.label("last_direction"),
            mentioned_at.label("mentioned_at"),
            sort_at.label("sort_at"),
        )
        .select_from(source)
        .where(*conditions)
        .order_by(sort_at.desc(), RespondContact.id.desc())
        # One extra row is the has-more probe: cheaper and more honest than a
        # COUNT, which AC-N1 rules out anyway.
        .limit(limit + 1)
        .cte("page")
    )

    is_mine = ConversationSLATracking.assigned_to_id == viewer
    counts = (
        select(
            func.count().label("open_ticket_count"),
            func.count().filter(is_mine).label("my_open_ticket_count"),
            func.min(cast(ConversationSLATracking.id, Text))
            .filter(is_mine)
            .label("my_open_ticket_id"),
        )
        .select_from(ConversationSLATracking)
        .where(
            ConversationSLATracking.respond_contact_id == page.c.contact_pk,
            _open_conversation_ticket_clause(),
        )
        .lateral("ticket_counts")
    )

    stmt = (
        select(page, counts)
        .select_from(page.join(counts, true()))
        .order_by(page.c.sort_at.desc(), page.c.contact_pk.desc())
    )

    rows = db.execute(stmt).mappings().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = []
    for row in rows:
        my_count = int(row["my_open_ticket_count"] or 0)
        items.append(
            {
                "contact_ref": row["respond_io_id"] or row["phone"],
                "respond_io_id": row["respond_io_id"],
                "phone": row["phone"],
                "name": row["name"],
                "last_message_at": _iso(row["last_message_at"]),
                "last_message_snippet": _snippet(row["last_message"]),
                "last_message_direction": row["last_direction"],
                "mentioned_at": _iso(row["mentioned_at"]),
                "open_ticket_count": int(row["open_ticket_count"] or 0),
                "my_open_ticket_count": my_count,
                # Ambiguous at two: the reply route would have to guess which
                # enquiry the message answers, so nothing is offered.
                "my_open_ticket_id": row["my_open_ticket_id"] if my_count == 1 else None,
            }
        )

    next_cursor = (
        encode_cursor(rows[-1]["sort_at"], str(rows[-1]["contact_pk"]))
        if has_more and rows
        else None
    )
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": limit,
        "tab": tab,
        "query": needle,
    }
