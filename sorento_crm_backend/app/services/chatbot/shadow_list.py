"""The shadow window, as the console reads it: rows with their live side, and one summary.

AC-1029, AC-1030. A shadow row is a second parse of a live turn (`shadow_of` names the live
turn's `message_id`). Two questions are asked of it, and they are answered in two different
scopes on purpose:

* per ROW, "did this turn come out differently" - answered by joining the row to its live
  turn and handing both parses' branch and domains to the screen;
* per RANGE, "is the new parser safe yet" - answered by `summarise`, over every filtered
  row rather than the page, because the browser holds one page and the owner is asking
  about the window.

Nothing here decides whether the two DIFFER: the frontend's `shadowDrift.ts` owns that rule
so the badge and the parities cannot disagree about what drift means. This module supplies
the facts both read.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy.orm import Query, Session

from app.models.access import RespondContact
from app.models.chatbot_turn import ChatbotTurn

logger = logging.getLogger(__name__)

# How many shadow rows one summary reads. The window the owner watches is days of turns, not
# months, and a parity computed over the newest few thousand answers the question without an
# unbounded scan of a table that only grows. Stated here rather than tuned by a caller: one
# number, one meaning, and a second one would only ever disagree with this.
SUMMARY_SCAN_LIMIT = 5000


def parse_domains(turn: Any) -> list[str] | None:
    """The domains this turn's parse asked about, off its own trace.

    NULL, not `[]`, when the turn was parsed before v3 or recorded no parse: "we cannot
    tell" and "this parse named no domain" are different findings, and the drift comparison
    must not read the first as a difference.
    """
    for record in getattr(turn, "trace", None) or []:
        if not isinstance(record, dict):
            continue
        raw = record.get("raw")
        parse = raw.get("parser_raw") if isinstance(raw, dict) else None
        derived = raw.get("derived") if isinstance(raw, dict) else None
        for candidate in (derived, parse):
            if not isinstance(candidate, dict):
                continue
            domains = candidate.get("domains")
            if isinstance(domains, list):
                return [str(d) for d in domains if d]
            asks = candidate.get("asks")
            if isinstance(asks, list):
                out: list[str] = []
                for ask in asks:
                    domain = ask.get("domain") if isinstance(ask, dict) else None
                    if domain and str(domain) not in out:
                        out.append(str(domain))
                return out
            hint = candidate.get("domain_hint")
            if hint:
                return [str(hint)]
    return None


# The six columns either side of the comparison is made of. SELECTED BY NAME, never as a
# whole ORM row: `envelope` and `response` are the two biggest columns in the table and a
# summary reads thousands of rows, so fetching them would move megabytes to answer a
# question about a branch kind and a list of domains - and would put every one of those
# rows in the session's identity map on the way past. `trace` is here because it is where
# the parse is, which is what `parse_domains` reads; it is the one JSON column the answer
# actually needs.
_COMPARISON_COLUMNS = (
    ChatbotTurn.id,
    ChatbotTurn.contact_respond_id,
    ChatbotTurn.message_id,
    ChatbotTurn.shadow_of,
    ChatbotTurn.branch_kind,
    ChatbotTurn.created_at,
    ChatbotTurn.trace,
)


def _pair_key(contact_respond_id: Any, message_id: Any) -> tuple[str, str]:
    """WHICH live turn a shadow row is the shadow OF.

    The message id alone is not it. `message_id` is unique per CONTACT, not globally -
    the unique index is `(contact_respond_id, message_id, attempt, is_test)` - so two
    contacts whose upstream handed out the same id would pair with each other's turns and
    the window would report drift that never happened.
    """
    return (str(contact_respond_id), str(message_id))


def _newer(left: Any, right: Any) -> bool:
    """`left.created_at` is strictly newer, with NULL treated as oldest.

    `created_at or 0` compared a datetime with an int the moment either side was null,
    which is a `TypeError` on the one row that has no timestamp rather than a comparison.
    """
    a = getattr(left, "created_at", None)
    b = getattr(right, "created_at", None)
    if a is None:
        return False
    if b is None:
        return True
    return a > b


def _live_rows(db: Session, shadow_rows: Iterable[Any]) -> dict[tuple[str, str], Any]:
    """The live turn each shadow row names, keyed by `(contact, shadow_of)`.

    One query for the page, not one per row, and six columns rather than the whole row.
    A shadow row whose live turn has since been deleted simply has no entry, and every
    reader treats that as "nothing to compare".
    """
    wanted = {row.shadow_of for row in shadow_rows if row.shadow_of}
    contacts = {row.contact_respond_id for row in shadow_rows if row.contact_respond_id}
    if not wanted or not contacts:
        return {}
    rows = (
        db.query(*_COMPARISON_COLUMNS)
        .filter(
            ChatbotTurn.message_id.in_(wanted),
            ChatbotTurn.contact_respond_id.in_(contacts),
            ChatbotTurn.ingress != "shadow",
        )
        .all()
    )
    out: dict[tuple[str, str], Any] = {}
    for row in rows:
        # Newest wins on a message answered twice (a retry writes a second row): the live
        # answer the customer last got is the one the shadow is being judged against.
        key = _pair_key(row.contact_respond_id, row.message_id)
        current = out.get(key)
        if current is None or _newer(row, current):
            out[key] = row
    return out


def _contact_labels(db: Session, shadow_rows: Iterable[ChatbotTurn]) -> dict[str, str]:
    """`respond_io_id` to the name a human reads. Never an id the screen would show."""
    ids = {row.contact_respond_id for row in shadow_rows if row.contact_respond_id}
    if not ids:
        return {}
    rows = (
        db.query(RespondContact)
        .filter(RespondContact.respond_io_id.in_(ids))
        .all()
    )
    return {
        str(row.respond_io_id): (row.name or row.phone_number or str(row.respond_io_id))
        for row in rows
    }


def _message_text(turn: Any) -> str | None:
    """What the customer said, off the stored envelope."""
    envelope = getattr(turn, "envelope", None)
    if not isinstance(envelope, dict):
        return None
    message = envelope.get("message")
    inner = message.get("message") if isinstance(message, dict) else None
    if isinstance(inner, dict):
        text = inner.get("text")
        if text:
            return str(text)
        attachment = inner.get("attachment")
        if isinstance(attachment, dict) and attachment.get("description"):
            return str(attachment["description"])
    return None


def decorate(db: Session, items: list[Any], rows: list[ChatbotTurn]) -> None:
    """Fill each response row's shadow context IN PLACE: domains, contact, message, live.

    Best-effort by construction: every field it writes is optional, and a shadow row whose
    live turn or contact has gone renders with what is there. A promotion watch must not
    500 because one row lost its pair.
    """
    try:
        live_by_message = _live_rows(db, rows)
        labels = _contact_labels(db, rows)
    except Exception:  # noqa: BLE001 - a read-only decoration must never fail the list
        logger.warning("shadow list decoration failed; returning bare rows", exc_info=True)
        return

    from app.schemas.chatbot_turn import ShadowTurnLiveSide

    for item, row in zip(items, rows):
        item.domains = parse_domains(row)
        item.contact_display = labels.get(str(row.contact_respond_id))
        item.message = _message_text(row)
        live = (
            live_by_message.get(_pair_key(row.contact_respond_id, row.shadow_of))
            if row.shadow_of
            else None
        )
        item.live = (
            ShadowTurnLiveSide(
                id=str(live.id),
                branch_kind=live.branch_kind,
                domains=parse_domains(live),
            )
            if live is not None
            else None
        )


def summarise(db: Session, query: Query) -> Any:
    """AC-1030: how many shadow turns the range holds, and how often the two agreed.

    `query` is the WHOLE FILTERED RANGE, never the cursor-narrowed page query: the caller
    asks "is the new parser safe yet", which no single page can answer, and a summary that
    silently shrank as the reader paged would be a different number every screen.

    Parity is over the rows that could be PAIRED with a live turn, not over every shadow
    row: a shadow of a turn whose live row has gone says nothing about the new parser, and
    counting it as a disagreement would make the number worse the older the range gets.
    Null when nothing could be paired, which the screen says in words.

    NEWEST FIRST and capped at `SUMMARY_SCAN_LIMIT`, both explicit. Without the order the
    cap takes whatever rows the plan happened to reach, so a truncated window would answer
    with an arbitrary sample rather than the most recent one; `count` is what the cap
    reached, which is what the screen reports.
    """
    from app.schemas.chatbot_turn import ShadowTurnSummary

    rows = (
        query.with_entities(*_COMPARISON_COLUMNS)
        .order_by(ChatbotTurn.created_at.desc(), ChatbotTurn.id.desc())
        .limit(SUMMARY_SCAN_LIMIT)
        .all()
    )
    if not rows:
        return ShadowTurnSummary(count=0)
    try:
        live_by_message = _live_rows(db, rows)
    except Exception:  # noqa: BLE001 - same rule as `decorate`
        logger.warning("shadow summary join failed; reporting the count only", exc_info=True)
        return ShadowTurnSummary(count=len(rows))

    paired = branch_same = asks_same = 0
    for row in rows:
        live = (
            live_by_message.get(_pair_key(row.contact_respond_id, row.shadow_of))
            if row.shadow_of
            else None
        )
        if live is None:
            continue
        paired += 1
        if live.branch_kind == row.branch_kind:
            branch_same += 1
        live_domains = parse_domains(live)
        shadow_domains = parse_domains(row)
        # An UNKNOWN side is not a disagreement, for the same reason the badge does not
        # treat it as one: a pre-v3 parse has nothing to say about the asks.
        if live_domains is None or shadow_domains is None or live_domains == shadow_domains:
            asks_same += 1
    return ShadowTurnSummary(
        count=len(rows),
        branch_parity=(branch_same / paired) if paired else None,
        asks_parity=(asks_same / paired) if paired else None,
    )
