"""Contact-thread scroll-back pagination and in-thread search (UAC AC-L7 / AC-L8).

The drawer used to load exactly one page of a contact's conversation and had no
way to reach anything older ("i scroll up already then can't find any older").
This module adds the two reads that fix it, both scoped to ONE contact:

``fetch_thread_page``
    A window of the thread addressed by a cursor that IS a Respond message id:
    ``before`` (older), ``after`` (newer) or ``around`` (jump to a match, the
    union of a before-half and an after-half centred on the anchor). Whatever
    the direction, **items come back oldest-to-newest** so the caller never
    reverses anything.

``search_thread``
    ILIKE over the locally stored message text, newest-first and capped. v1
    searches ``chat_histories.message`` only (the message body); contact
    name/phone are not part of an in-thread search.

Two lanes serve the page:

1. **Respond.io cursor (primary).** Respond is the system of record for a
   WhatsApp conversation, so it is the only source that can be trusted to reach
   the true start of the thread, and its message objects carry attachments,
   delivery receipts and sender source - a scrolled-back page therefore renders
   identically to the live window instead of degrading to bare text. Verified
   against the live API 2026-08-15: ``cursorId=<id>`` returns messages OLDER
   than the anchor, newest-first; ``cursorId=-<id>`` returns messages NEWER than
   the anchor, oldest-first.
2. **``chat_histories`` keyset (fallback + search substrate).** Used when the
   Respond lane is unavailable (no API key, timeout, HTTP error), and always for
   search. Keyset on ``(sent_at, id)`` under a ``(channel, contact_id)``
   equality prefix, which is exactly what
   ``ix_chat_histories_channel_contact_sent_id`` indexes - never OFFSET, and
   ``sent_at`` rather than ``created_at`` because ``created_at`` is INGEST
   order: a backfilled 2026-05 message is written today and would sort as the
   newest thing in the thread. Both leading columns must be in the predicate
   for that index to be usable at all; see ``_base_query``.

Every Respond page we fetch is written into ``chat_histories`` (idempotent,
best-effort, never mark-read and never a window-cache write) so that search
coverage grows over history that predates our ingest. A failure to persist is
logged and the read still answers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import unquote

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.chat_history import CHAT_HISTORY_DEDUPE_PREDICATE, ChatHistory

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
# Respond.io caps GET /v2/contact/{id}/message/list at 50 per page.
RESPOND_MAX_PAGE = 50
SEARCH_DEFAULT_LIMIT = 100
SEARCH_MAX_LIMIT = 200
SNIPPET_RADIUS = 60


@dataclass(frozen=True)
class ThreadContact:
    """Everything the two lanes need about the contact whose thread this is.

    ``respond_io_id`` is BOTH the Respond API identifier and the value stored in
    ``chat_histories.contact_id`` - the two happen to agree, which is why one
    field serves both lanes. It is never surfaced to the UI.
    """

    respond_io_id: str
    phone_number: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    channel: str = "whatsapp"


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------


def _message_id_to_ms(message_id: Any) -> Optional[int]:
    """Respond message ids ARE epoch microseconds (see chat_message_resolver)."""
    try:
        raw = int(str(message_id))
    except (TypeError, ValueError):
        return None
    if raw > 1e14:
        return raw // 1000
    if raw > 1e11:
        return raw
    return None


def _epoch_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _local_status(row: ChatHistory) -> list[dict]:
    """Delivery receipts reconstructed from the stored columns.

    The frontend reads the bubble clock off ``status[].timestamp`` first and
    falls back to ``messageId``; a row with neither renders with no date pill,
    so a bare timestamp entry is always emitted as the floor.
    """
    entries: list[dict] = []
    if row.delivery_status:
        entries.append(
            {
                "value": str(row.delivery_status),
                "timestamp": _epoch_ms(row.respond_ts or row.sent_at),
            }
        )
    if row.delivered_ts:
        entries.append({"value": "delivered", "timestamp": _epoch_ms(row.delivered_ts)})
    if row.read_ts:
        entries.append({"value": "read", "timestamp": _epoch_ms(row.read_ts)})
    if not entries:
        entries.append({"timestamp": _epoch_ms(row.respond_ts or row.sent_at)})
    return entries


def _row_to_item(row: ChatHistory) -> dict:
    """A `chat_histories` row in the shape the chat list already renders.

    Fidelity note: the local table stores text only, so a scrolled-back media
    message shows the caption/placeholder the ingest wrote, and ``sender.source``
    is unknown (the column does not exist). Both are full on the Respond lane,
    which is why that lane is primary.
    """
    numeric_id = None
    try:
        numeric_id = int(str(row.message_id)) if row.message_id is not None else None
    except (TypeError, ValueError):
        numeric_id = None
    return {
        "messageId": numeric_id,
        "traffic": row.type,
        "message": {"type": "text", "text": row.message or ""},
        "sender": {"source": "contact" if row.type == "incoming" else None},
        "status": _local_status(row),
        "replyTo": (
            {"messageId": row.reply_to_message_id, "message": {"text": row.reply_to_message}}
            if row.reply_to_message_id
            else None
        ),
        "source": "local",
    }


def _respond_item(item: dict) -> dict:
    out = dict(item)
    out["source"] = "respond"
    return out


def _respond_item_text(item: dict) -> str:
    """Storable text for a Respond message.

    The body when there is one, else a typed placeholder carrying the filename -
    "[file] quotation.pdf" is something a person can actually search for, where a
    bare "[attachment]" is not.
    """
    message = item.get("message") if isinstance(item.get("message"), dict) else {}
    body = (message.get("text") or "").strip()
    if body:
        return body
    kind = (message.get("type") or "").strip() or "attachment"
    attachment = message.get("attachment") if isinstance(message.get("attachment"), dict) else None
    if attachment:
        name = unquote(str(attachment.get("fileName") or "")).strip()
        sub = (attachment.get("type") or "").strip()
        label = sub or kind
        return f"[{label}] {name}".strip() if name else f"[{label}]"
    return f"[{kind}]"


# ---------------------------------------------------------------------------
# Local keyset lane
# ---------------------------------------------------------------------------


def _base_query(db: Session, contact: ThreadContact):
    """Every local-lane read, scoped to one contact ON ONE CHANNEL.

    The channel predicate is not cosmetic: the only composite index over this
    table is ``ix_chat_histories_channel_contact_sent_id (channel, contact_id,
    sent_at, id)``, which leads on ``channel`` - a contact-only filter cannot
    use it and the keyset walk degrades to a scan of the whole table. It is also
    correct: ``persist_messages`` writes ``contact.channel``, so a thread is a
    per-channel conversation.
    """
    return db.query(ChatHistory).filter(
        ChatHistory.channel == contact.channel,
        ChatHistory.contact_id == contact.respond_io_id,
    )


def _anchor_row(db: Session, contact: ThreadContact, message_id: str) -> Optional[ChatHistory]:
    return (
        _base_query(db, contact)
        .filter(ChatHistory.message_id == str(message_id))
        .order_by(ChatHistory.sent_at.asc(), ChatHistory.id.asc())
        .first()
    )


def _older_than(q, anchor: ChatHistory):
    return q.filter(
        or_(
            ChatHistory.sent_at < anchor.sent_at,
            (ChatHistory.sent_at == anchor.sent_at) & (ChatHistory.id < anchor.id),
        )
    )


def _newer_than(q, anchor: ChatHistory):
    return q.filter(
        or_(
            ChatHistory.sent_at > anchor.sent_at,
            (ChatHistory.sent_at == anchor.sent_at) & (ChatHistory.id > anchor.id),
        )
    )


def _local_page(
    db: Session,
    contact: ThreadContact,
    *,
    before: Optional[str],
    after: Optional[str],
    around: Optional[str],
    limit: int,
) -> dict:
    base = _base_query(db, contact)

    if around:
        anchor = _anchor_row(db, contact, around)
        if anchor is not None:
            older_n = max(0, (limit - 1) // 2)
            newer_n = max(0, limit - 1 - older_n)
            older = (
                _older_than(_base_query(db, contact), anchor)
                .order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc())
                .limit(older_n)
                .all()
            )
            newer = (
                _newer_than(_base_query(db, contact), anchor)
                .order_by(ChatHistory.sent_at.asc(), ChatHistory.id.asc())
                .limit(newer_n)
                .all()
            )
            rows = list(reversed(older)) + [anchor] + newer
            return _page_payload(
                [_row_to_item(r) for r in rows],
                has_more_older=len(older) == older_n and older_n > 0,
                has_more_newer=len(newer) == newer_n and newer_n > 0,
                limit=limit,
                source="local",
                anchor_message_id=str(around),
            )
        # Unknown anchor: fall through to the newest page rather than 404 - the
        # thread still has to render something.

    if after:
        anchor = _anchor_row(db, contact, after)
        if anchor is not None:
            rows = (
                _newer_than(base, anchor)
                .order_by(ChatHistory.sent_at.asc(), ChatHistory.id.asc())
                .limit(limit)
                .all()
            )
            return _page_payload(
                [_row_to_item(r) for r in rows],
                has_more_older=True,
                has_more_newer=len(rows) == limit,
                limit=limit,
                source="local",
            )

    if before:
        anchor = _anchor_row(db, contact, before)
        if anchor is not None:
            rows = (
                _older_than(base, anchor)
                .order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc())
                .limit(limit)
                .all()
            )
            rows.reverse()
            return _page_payload(
                [_row_to_item(r) for r in rows],
                has_more_older=len(rows) == limit,
                has_more_newer=True,
                limit=limit,
                source="local",
            )

    rows = (
        base.order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc()).limit(limit).all()
    )
    rows.reverse()
    return _page_payload(
        [_row_to_item(r) for r in rows],
        has_more_older=len(rows) == limit,
        has_more_newer=False,
        limit=limit,
        source="local",
    )


def _page_payload(
    items: list[dict],
    *,
    has_more_older: bool,
    has_more_newer: bool,
    limit: int,
    source: str,
    anchor_message_id: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    def _first_cursor(candidates: list[dict]) -> Optional[str]:
        """The edge id the caller pages from.

        Walks inward past any item with no message id: an item that cannot be a
        cursor must not become one, or the next request silently restarts from
        the newest page.
        """
        for item in candidates:
            raw = item.get("messageId")
            if raw is not None:
                return str(raw)
        return None

    return {
        "items": items,
        "has_more_older": bool(has_more_older),
        "has_more_newer": bool(has_more_newer),
        "oldest_message_id": _first_cursor(items),
        "newest_message_id": _first_cursor(list(reversed(items))),
        "anchor_message_id": anchor_message_id,
        "limit": limit,
        "source": source,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Respond.io lane
# ---------------------------------------------------------------------------


def _respond_call(client, identifier: str, *, limit: int, cursor: Optional[str]) -> list[dict]:
    payload = client.list_messages(identifier, limit=min(limit, RESPOND_MAX_PAGE), cursor=cursor)
    items = payload.get("items") if isinstance(payload, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _respond_page(
    client,
    contact: ThreadContact,
    *,
    before: Optional[str],
    after: Optional[str],
    around: Optional[str],
    limit: int,
) -> dict:
    ident = contact.respond_io_id

    if around:
        older_n = max(0, (limit - 1) // 2)
        newer_n = max(0, limit - 1 - older_n)
        older = list(reversed(_respond_call(client, ident, limit=older_n, cursor=str(around)))) if older_n else []
        newer = _respond_call(client, ident, limit=newer_n, cursor=f"-{around}") if newer_n else []
        anchor = client.get_message(ident, around)
        anchor_items = [anchor] if isinstance(anchor, dict) and anchor.get("messageId") is not None else []
        items = older + anchor_items + newer
        return _page_payload(
            [_respond_item(i) for i in items],
            has_more_older=len(older) == older_n and older_n > 0,
            has_more_newer=len(newer) == newer_n and newer_n > 0,
            limit=limit,
            source="respond",
            anchor_message_id=str(around),
        )

    if after:
        # cursorId=-<id> yields NEWER messages, already ascending.
        items = _respond_call(client, ident, limit=limit, cursor=f"-{after}")
        return _page_payload(
            [_respond_item(i) for i in items],
            has_more_older=True,
            has_more_newer=len(items) == limit,
            limit=limit,
            source="respond",
        )

    # Newest page (no cursor) and the older walk both come back newest-first.
    items = _respond_call(client, ident, limit=limit, cursor=str(before) if before else None)
    items = list(reversed(items))
    return _page_payload(
        [_respond_item(i) for i in items],
        has_more_older=len(items) == limit,
        has_more_newer=bool(before),
        limit=limit,
        source="respond",
    )


# ---------------------------------------------------------------------------
# Persistence (best-effort cache fill for search)
# ---------------------------------------------------------------------------


def persist_messages(db: Session, contact: ThreadContact, items: Iterable[dict]) -> int:
    """Store Respond messages in `chat_histories`, skipping ones already held.

    Deliberately NOT the external ingest's ON CONFLICT alone: that arbiter is a
    PARTIAL unique index (``created_at >= 2026-08-14``), so a row ingested before
    the cutover is invisible to it and a naive upsert would insert a duplicate.
    The explicit "which of these ids do we already hold" probe covers both eras;
    the ON CONFLICT clause stays as the race guard between concurrent readers.
    """
    rows: list[dict] = []
    for item in items:
        message_id = item.get("messageId")
        if message_id is None:
            continue
        ms = _message_id_to_ms(message_id)
        if ms is None:
            continue
        sent_at = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)
        traffic = str(item.get("traffic") or "").strip().lower()
        if traffic not in ("incoming", "outgoing"):
            continue
        reply_to = item.get("replyTo") if isinstance(item.get("replyTo"), dict) else None
        # AC-L6: the quoted EXCERPT is persisted alongside the quoted id. Without
        # it the fallback (local) lane renders a "replying to" block with nothing
        # in it - the id alone cannot be shown to a reader.
        reply_to_text = _respond_item_text(reply_to) if reply_to else None
        rows.append(
            {
                "channel": contact.channel,
                "contact_id": contact.respond_io_id,
                "phone_number": contact.phone_number,
                "message": _respond_item_text(item),
                "sent_at": sent_at,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "type": traffic,
                "message_id": str(message_id),
                "reply_to_message_id": (
                    str(reply_to.get("messageId")) if reply_to and reply_to.get("messageId") else None
                ),
                "reply_to_message": reply_to_text,
                "respond_ts": sent_at,
                "ingest_at": datetime.now(tz=timezone.utc).replace(tzinfo=None),
            }
        )
    if not rows:
        return 0

    existing = {
        str(mid)
        for (mid,) in db.query(ChatHistory.message_id)
        .filter(
            ChatHistory.contact_id == contact.respond_io_id,
            ChatHistory.message_id.in_([r["message_id"] for r in rows]),
        )
        .all()
    }
    fresh = [r for r in rows if r["message_id"] not in existing]
    if not fresh:
        return 0

    insert_sql = text(
        f"""
        INSERT INTO chat_histories (
            channel, contact_id, phone_number, message, sent_at, first_name, last_name,
            type, message_id, reply_to_message_id, reply_to_message, respond_ts, ingest_at
        ) VALUES (
            :channel, :contact_id, :phone_number, :message, :sent_at, :first_name, :last_name,
            :type, :message_id, :reply_to_message_id, :reply_to_message, :respond_ts, :ingest_at
        )
        ON CONFLICT (contact_id, message_id) WHERE {CHAT_HISTORY_DEDUPE_PREDICATE}
        DO NOTHING
        """
    )
    db.execute(insert_sql, fresh)
    return len(fresh)


def _persist_best_effort(db: Session, contact: ThreadContact, items: list[dict]) -> int:
    """A read must never fail because the cache fill did.

    Committed here rather than left pending: the caller is a GET with nothing
    else in flight, and an uncommitted backfill would be rolled back by the
    request teardown, so search would never see it.
    """
    try:
        written = persist_messages(db, contact, items)
        if written:
            db.commit()
        return written
    except Exception:  # noqa: BLE001 - the page is already answerable
        logger.warning(
            "chat history backfill failed for contact %s", contact.respond_io_id, exc_info=True
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_thread_page(
    db: Session,
    contact: ThreadContact,
    *,
    before: Optional[str] = None,
    after: Optional[str] = None,
    around: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    client: Any = None,
) -> dict:
    """One window of a contact's thread, ALWAYS oldest-to-newest.

    At most one of ``before`` / ``after`` / ``around`` is honoured, in that
    precedence order (the route rejects more than one before we get here).
    """
    limit = max(1, min(int(DEFAULT_LIMIT if limit is None else limit), MAX_LIMIT))
    before = str(before).strip() if before else None
    after = str(after).strip() if after else None
    around = str(around).strip() if around else None

    if client is not None:
        try:
            page = _respond_page(
                client, contact, before=before, after=after, around=around, limit=limit
            )
        except Exception:  # noqa: BLE001 - the local lane still answers
            logger.warning(
                "Respond thread page failed for contact %s; serving local history",
                contact.respond_io_id,
                exc_info=True,
            )
        else:
            page["backfilled"] = _persist_best_effort(db, contact, page["items"])
            return page

    page = _local_page(db, contact, before=before, after=after, around=around, limit=limit)
    page["backfilled"] = 0
    return page


def _like_pattern(q: str) -> str:
    """`%`, `_` and the escape character itself are literals in a user query."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _snippet(body: str, needle: str) -> str:
    idx = body.lower().find(needle.lower())
    if idx < 0:
        return body[: SNIPPET_RADIUS * 2].strip()
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(body), idx + len(needle) + SNIPPET_RADIUS)
    out = body[start:end].strip()
    if start > 0:
        out = "…" + out
    if end < len(body):
        out = out + "…"
    return out


def search_thread(
    db: Session,
    contact: ThreadContact,
    *,
    q: str,
    limit: int = SEARCH_DEFAULT_LIMIT,
) -> dict:
    """Newest-first matches for `q` inside ONE contact's stored messages.

    Side-effect free. Rows with no ``message_id`` are skipped: the thread jumps
    to a match by message id, so a match it cannot jump to is not a result.

    Coverage is whatever is in ``chat_histories`` - the live ingest plus every
    page a reader has already scrolled back through (see ``fetch_thread_page``).
    """
    limit = max(1, min(int(SEARCH_DEFAULT_LIMIT if limit is None else limit), SEARCH_MAX_LIMIT))
    needle = (q or "").strip()
    if not needle:
        return {"items": [], "total": 0, "truncated": False, "query": ""}

    rows = (
        _base_query(db, contact)
        .filter(ChatHistory.message_id.isnot(None))
        .filter(ChatHistory.message.ilike(_like_pattern(needle), escape="\\"))
        .order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "message_id": str(row.message_id),
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "direction": row.type,
            "snippet": _snippet(row.message or "", needle),
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "truncated": len(items) == limit,
        "query": needle,
    }
