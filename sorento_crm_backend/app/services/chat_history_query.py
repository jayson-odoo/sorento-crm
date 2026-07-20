"""Admin query layer over `chat_histories`.

The table is high-volume and holds raw customer message content, so:

- **Keyset pagination** on `(sent_at, id)`, not OFFSET. Deep OFFSET scans everything it
  skips; the existing `ix_chat_histories_channel_contact_sent_id` index makes the keyset
  walk cheap at any depth. `id` breaks ties so identical timestamps still paginate
  deterministically instead of repeating or dropping rows.
- **No opaque identifiers surfaced.** `contact_id` is the Respond.io id string, not
  `respond_contacts.id`, and is meaningless to a human — rows carry a rendered
  `contact_display` built from the stored name and phone instead.
- **Latency is attached to the reply**, not the message that triggered it, which is what
  an admin scanning the grid expects to read.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.chat_history import ChatHistory

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DEFAULT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class ChatMessageRow:
    id: int
    channel: str
    contact_id: str
    contact_display: str
    phone_number: str
    type: str
    message: str
    sent_at: datetime
    respond_ts: Optional[datetime]
    delivery_status: Optional[str]
    turn_id: Optional[str]
    message_id: Optional[str]
    latency_seconds: Optional[float]
    webhook_lag_seconds: Optional[float]


def _contact_display(row: ChatHistory) -> str:
    """Human-readable contact label. Never the Respond id."""
    name = " ".join(p for p in (row.first_name, row.last_name) if p).strip()
    phone = (row.phone_number or "").strip()
    if name and phone:
        return f"{name} ({phone})"
    return name or phone or "Unknown contact"


def encode_cursor(sent_at: datetime, row_id: int) -> str:
    return base64.urlsafe_b64encode(f"{sent_at.isoformat()}|{row_id}".encode()).decode()


def decode_cursor(cursor: str) -> Optional[tuple[datetime, int]]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, row_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(ts), int(row_id)
    except Exception:  # noqa: BLE001 - a malformed cursor restarts from the top
        return None


def _latencies_from_rows(rows: list[ChatHistory]) -> dict[str, float]:
    """Turn latency from an already-fetched, respond_ts-ordered row set.

    Computed from `respond_ts` only — a row still awaiting resolution has no honest
    clock, and approximating from `sent_at` would fabricate the number.
    """
    starts: dict[str, datetime] = {}
    replies: dict[str, datetime] = {}
    for row in rows:
        if row.turn_id is None or row.respond_ts is None:
            continue
        key = str(row.turn_id)
        if row.type == "incoming":
            starts.setdefault(key, row.respond_ts)
        else:
            replies.setdefault(key, row.respond_ts)
    return {
        key: (replies[key] - start).total_seconds()
        for key, start in starts.items()
        if key in replies
    }


def _turn_latencies(db: Session, rows: list[ChatHistory]) -> dict[str, float]:
    """Turn latency for the turns present in `rows`, fetching their sibling messages."""
    turn_ids = {r.turn_id for r in rows if r.turn_id}
    if not turn_ids:
        return {}
    related = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.turn_id.in_(turn_ids),
            ChatHistory.respond_ts.isnot(None),
        )
        .order_by(ChatHistory.respond_ts.asc(), ChatHistory.id.asc())
        .all()
    )
    return _latencies_from_rows(related)


def _to_row(row: ChatHistory, latencies: dict[str, float]) -> ChatMessageRow:
    key = str(row.turn_id) if row.turn_id else None
    # Latency belongs to the reply. Showing it on the inbound row would read as
    # "this message took 6s to arrive", which is a different claim entirely.
    latency = latencies.get(key) if (key and row.type == "outgoing") else None
    lag = (
        (row.ingest_at - row.respond_ts).total_seconds()
        if row.ingest_at is not None and row.respond_ts is not None
        else None
    )
    return ChatMessageRow(
        id=row.id,
        channel=row.channel,
        contact_id=row.contact_id,
        contact_display=_contact_display(row),
        phone_number=row.phone_number,
        type=row.type,
        message=row.message,
        sent_at=row.sent_at,
        respond_ts=row.respond_ts,
        delivery_status=row.delivery_status,
        turn_id=row.turn_id,
        message_id=row.message_id,
        latency_seconds=latency,
        webhook_lag_seconds=lag,
    )


def _apply_filters(
    q,
    *,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    contact_id: Optional[str],
    direction: Optional[str],
    search: Optional[str],
):
    if date_from is not None:
        q = q.filter(ChatHistory.sent_at >= date_from)
    if date_to is not None:
        q = q.filter(ChatHistory.sent_at <= date_to)
    if contact_id:
        q = q.filter(ChatHistory.contact_id == contact_id)
    if direction in ("incoming", "outgoing"):
        q = q.filter(ChatHistory.type == direction)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                ChatHistory.message.ilike(like),
                ChatHistory.phone_number.ilike(like),
                ChatHistory.first_name.ilike(like),
                ChatHistory.last_name.ilike(like),
            )
        )
    return q


def _breached_turn_ids(
    db: Session, *, date_from, date_to, contact_id, target_seconds: float
) -> set[str]:
    """Turn ids in the window whose reply exceeded the target.

    Bounded by the date filter, so it is a scan of the window, not the table.
    """
    q = db.query(ChatHistory).filter(
        ChatHistory.turn_id.isnot(None),
        ChatHistory.respond_ts.isnot(None),
    )
    q = _apply_filters(
        q, date_from=date_from, date_to=date_to, contact_id=contact_id,
        direction=None, search=None,
    )
    rows = q.order_by(ChatHistory.respond_ts.asc(), ChatHistory.id.asc()).all()
    latencies = _latencies_from_rows(rows)
    return {k for k, v in latencies.items() if v > target_seconds}


def list_messages_page(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    contact_id: Optional[str] = None,
    direction: Optional[str] = None,
    search: Optional[str] = None,
    breached_only: bool = False,
    target_seconds: float = 10.0,
    page: int = 1,
    limit: int = DEFAULT_LIMIT,
    sort: Optional[str] = None,
    dir_: str = "desc",
    now: Optional[datetime] = None,
) -> tuple[list[ChatMessageRow], int]:
    """Offset page of messages plus the total, for the standard DataGrid.

    Uses offset paging (not keyset) because the DataGrid lets the user jump to an
    arbitrary page and needs a total to render the pager — both of which keyset
    cannot serve. The date filter bounds the scan, so offset is acceptable here;
    the keyset path (`list_messages`) is retained for the unbounded CSV export.
    """
    now = now or datetime.utcnow()
    limit = max(1, min(int(limit), MAX_LIMIT))
    page = max(1, int(page))

    if date_from is None and date_to is None:
        date_from, date_to = now - DEFAULT_WINDOW, now

    q = db.query(ChatHistory)
    q = _apply_filters(
        q, date_from=date_from, date_to=date_to, contact_id=contact_id,
        direction=direction, search=search,
    )

    if breached_only:
        breached = _breached_turn_ids(
            db, date_from=date_from, date_to=date_to, contact_id=contact_id,
            target_seconds=target_seconds,
        )
        if not breached:
            return [], 0
        q = q.filter(ChatHistory.turn_id.in_(breached))

    total = q.count()

    sort_col = {
        "sent_at": ChatHistory.sent_at,
        "contact_display": ChatHistory.first_name,
        "type": ChatHistory.type,
        "message": ChatHistory.message,
    }.get(sort or "sent_at", ChatHistory.sent_at)
    ordering = sort_col.asc() if dir_ == "asc" else sort_col.desc()

    page_rows = (
        q.order_by(ordering, ChatHistory.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    latencies = _turn_latencies(db, page_rows)
    return [_to_row(r, latencies) for r in page_rows], total


def list_messages(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    contact_id: Optional[str] = None,
    direction: Optional[str] = None,
    search: Optional[str] = None,
    breached_only: bool = False,
    target_seconds: float = 10.0,
    limit: int = DEFAULT_LIMIT,
    cursor: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[list[ChatMessageRow], Optional[str]]:
    """Newest-first keyset page of messages plus the cursor for the next page.

    Retained for the CSV export, which walks the whole filtered set with flat memory.
    """
    now = now or datetime.utcnow()
    limit = max(1, min(int(limit), MAX_LIMIT))

    # Default to the last 24h: an unbounded scan of this table is never what was meant.
    if date_from is None and date_to is None:
        date_from, date_to = now - DEFAULT_WINDOW, now

    q = db.query(ChatHistory)
    q = _apply_filters(
        q, date_from=date_from, date_to=date_to, contact_id=contact_id,
        direction=direction, search=search,
    )

    if cursor:
        decoded = decode_cursor(cursor)
        if decoded:
            c_sent, c_id = decoded
            # Strictly after the cursor in (sent_at DESC, id DESC) order.
            q = q.filter(
                or_(
                    ChatHistory.sent_at < c_sent,
                    (ChatHistory.sent_at == c_sent) & (ChatHistory.id < c_id),
                )
            )

    q = q.order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc())

    # Over-fetch by one to learn whether another page exists without a COUNT.
    fetched = q.limit(limit + 1).all()
    has_more = len(fetched) > limit
    page = fetched[:limit]

    latencies = _turn_latencies(db, page)
    rows = [_to_row(row, latencies) for row in page]

    if breached_only:
        breached_turns = {k for k, v in latencies.items() if v > target_seconds}
        rows = [r for r in rows if r.turn_id and str(r.turn_id) in breached_turns]
        # Filtering after the page is fetched means a page can come back short; the
        # cursor still advances correctly, so the caller keeps paging.

    next_cursor = (
        encode_cursor(page[-1].sent_at, page[-1].id) if has_more and page else None
    )
    return rows, next_cursor


def get_thread(
    db: Session,
    *,
    contact_id: str,
    anchor_id: Optional[int] = None,
    before: int = 25,
    after: int = 25,
) -> list[ChatMessageRow]:
    """One contact's transcript around an anchor message, oldest-first.

    Oldest-first because a transcript reads top-down, whereas the grid reads
    newest-first — the two orders are deliberately different.
    """
    anchor = None
    if anchor_id is not None:
        anchor = (
            db.query(ChatHistory)
            .filter(ChatHistory.id == anchor_id, ChatHistory.contact_id == contact_id)
            .first()
        )

    base = db.query(ChatHistory).filter(ChatHistory.contact_id == contact_id)

    if anchor is None:
        rows = base.order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc()).limit(before + after).all()
        rows.reverse()
    else:
        older = (
            base.filter(
                or_(
                    ChatHistory.sent_at < anchor.sent_at,
                    (ChatHistory.sent_at == anchor.sent_at) & (ChatHistory.id < anchor.id),
                )
            )
            .order_by(ChatHistory.sent_at.desc(), ChatHistory.id.desc())
            .limit(before)
            .all()
        )
        newer = (
            base.filter(
                or_(
                    ChatHistory.sent_at > anchor.sent_at,
                    (ChatHistory.sent_at == anchor.sent_at) & (ChatHistory.id > anchor.id),
                )
            )
            .order_by(ChatHistory.sent_at.asc(), ChatHistory.id.asc())
            .limit(after)
            .all()
        )
        rows = list(reversed(older)) + [anchor] + newer

    latencies = _turn_latencies(db, rows)
    return [_to_row(row, latencies) for row in rows]
