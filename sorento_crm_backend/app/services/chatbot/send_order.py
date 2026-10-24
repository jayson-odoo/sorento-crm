"""A contact's messages are answered in the order they were SENT (issue #1262 round 3).

The per-contact ticket (`dispatch.py`) orders turns by ARRIVAL at `/chat/turn`, and arrival
is not send order: n8n forwards a text at once but runs its own media intake on a photo
first (~20 s), so a text sent after a photo overtakes it. Mr Loo, 26 Sep: photo 14:57:25,
"Stock" 14:57:29; the CRM ran "Stock" first and answered it from yesterday's products.

No timer and no waiting window (owner, 26 Sep: "very fragile"). The rule instead: when a
turn gets its slot, it first answers every EARLIER-sent message of this contact that the
CRM already KNOWS about and has not answered, then itself. The CRM knows about an earlier
message in exactly three ways, and this module reads all of them:

* **a queued turn row.** Its request reached `/chat/turn` after this one and is waiting for
  its ticket; its row sits at stage `queued`. Earlier-sent is decided on the respond.io
  send time both envelopes carry (`message.message.timestamp`, ms). The row is claimed with
  one conditional UPDATE, so the waiting request, when it gets its slot, finds the row
  already answered and replays it as a duplicate (n8n sends nothing).
* **a media ledger row with no turn row.** While n8n still runs `sub-media-intake`
  upstream (plan S6 not yet promoted), its `/external/media/process` call writes
  `contact_media_usage` for the photo seconds before the photo reaches `/chat/turn`, and
  its extraction job is still queued or running while n8n waits on it. The ledger stores
  no send time, so "earlier" is the CRM's first sight of it: written before this turn
  arrived and after this contact's previous turn. Both bounds are states, not clocks: a
  photo whose job already finished is not on its way (it has a turn row, or n8n answered
  it on its own reply arm), and a job stranded before an answered turn is history.

* **a stored media message with no turn row and no ledger row** (CHAT-SEND-ORDER, prod 24
  Oct). The CRM's own respond.io webhook stores every message in `chat_histories` on arrival,
  often before n8n has forwarded the photo or started reading it, so this is the CRM's
  earliest sight of it. Earlier is decided on respond.io's clock (the message id is the send
  time in microseconds). Bounded by states and one staleness line, never a wait: sent at most
  `STORED_LOOKBACK_SECONDS` before this message and after the contact's latest answered turn,
  not yet a turn, and not yet in n8n's media intake (the ledger rule above owns it from then).
  The text never waits for the photo to arrive; the photo is answered from what is stored.

The engine answers a claimed message on its own turn row, with its own trace, and the
earlier message's actions go out ahead of this turn's in the one response n8n executes in
order. Nothing here waits for anything the CRM has not already seen; the only wait is the
existing bounded media poll on an extraction job that already exists.

Bounded (review round 2, S1), by counts and the existing per-item wait, never a clock:
at most `MAX_EARLIER_PER_TURN` earlier messages per turn, and the media waits taken on,
this turn's own included, stay below n8n's `chat-turn` timeout (`within_bounds`).
Whatever is left goes to its own delivery, as it did before this module existed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.chatbot_turn import ChatbotTurn

QUEUED_STAGE = "queued"

# How far before this message a stored-only media message still counts as on its way. The
# same line direct ingress draws for a body too old to start a turn
# (`direct_ingress.STALE_AFTER_SECONDS`): anything older is history, not a message in flight.
STORED_LOOKBACK_SECONDS = 120.0

# A fixed count of earlier messages one turn answers ahead of itself. Each is a full turn
# (an LLM call, maybe a media wait), and they all ride this request.
MAX_EARLIER_PER_TURN = 2
# n8n's HTTP timeout on its `/chat/turn` call. Every media wait the pre-step takes on is
# spent inside it, so their worst-case sum must stay below it. A copy of the n8n node's
# setting: change both together (plan n8n step 3).
N8N_CHAT_TURN_TIMEOUT_SECONDS = 90.0


def sent_at_ms(envelope_message: Any) -> int | None:
    """respond.io's send time for this message (`message.message.timestamp`, ms), or None."""
    if not isinstance(envelope_message, dict):
        return None
    inner = envelope_message.get("message")
    value = inner.get("timestamp") if isinstance(inner, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _message_id_ms(message_id: Any) -> float | None:
    """respond.io's send time off its message id (epoch microseconds), in ms with the
    microseconds kept, or None when the id is not that clock."""
    try:
        raw = int(str(message_id))
    except (TypeError, ValueError):
        return None
    if raw > 1e14:
        return raw / 1000.0
    if raw > 1e11:
        return float(raw)
    return None


def send_key_ms(envelope_message: Any) -> float | None:
    """The send order of this message (`envelope.message`, the webhook body), in ms.

    `timestamp` (ms) is the clock, as before, but it is whole seconds on real envelopes, so
    two messages sent inside one second tie on it (CHAT-SEND-ORDER, the 15 Oct same-second
    case). The message id is respond.io's send time in microseconds; when it falls inside
    the timestamp's second it refines it. With no timestamp, the id alone; with neither, None.
    """
    if not isinstance(envelope_message, dict):
        return None
    inner = envelope_message.get("message")
    from_id = _message_id_ms(inner.get("messageId") if isinstance(inner, dict) else None)
    sent = sent_at_ms(envelope_message)
    if sent is None:
        return from_id
    if from_id is not None and sent <= from_id < sent + 1000:
        return from_id
    return float(sent)


def claim(db: Session, turn_id: str) -> bool:
    """Take a queued row for answering. True for exactly one caller.

    The waiting request claims its own row this way when its ticket comes up, and a
    predecessor claims it this way to answer it first; whichever UPDATE lands second sees
    no `queued` row and gets False.
    """
    result = db.execute(
        update(ChatbotTurn)
        .where(
            ChatbotTurn.id == turn_id,
            ChatbotTurn.status == "processing",
            ChatbotTurn.stage == QUEUED_STAGE,
        )
        .values(stage="received")
    )
    db.commit()
    return bool(result.rowcount)


@dataclass
class Earlier:
    """One earlier-sent, unanswered message this turn answers before itself."""

    order_key: float
    # A queued row to claim (its own request is waiting behind this one) ...
    row_id: str | None = None
    envelope: dict[str, Any] | None = None
    # ... or a media message the CRM has only seen in the ledger so far.
    message_id: str | None = None
    modality: str | None = None
    media_url: str | None = None
    mime_type: str | None = None
    caption: str | None = None
    job_id: str | None = None
    # Whether answering it can sit in the media poll (a photo or voice note).
    carries_media: bool = False
    # ... or a media message the CRM has only STORED so far (`chat_histories`): its
    # respond.io attachment type and file name, to rebuild it (`stored_envelope`).
    attachment_type: str | None = None
    file_name: str | None = None


def _epoch_ms(value: datetime | None) -> float:
    """`contact_media_usage.created_at` is a naive UTC timestamp (the app's sessions run
    in UTC), so it is marked UTC before conversion, never read as the process's zone."""
    if not isinstance(value, datetime):
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp() * 1000


def earlier_unanswered(db: Session, *, contact_respond_id: str, me: ChatbotTurn) -> list[Earlier]:
    """Every earlier-sent message of this contact the CRM knows about and has not answered,
    oldest first. Live turns only: a test turn never answers or claims a customer's message."""
    if me.is_test:
        return []
    my_sent = send_key_ms(me.envelope.get("message") if isinstance(me.envelope, dict) else None)
    found: list[Earlier] = []

    if my_sent is not None:
        query = db.query(ChatbotTurn).filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.is_test.is_(False),
            ChatbotTurn.status == "processing",
            ChatbotTurn.stage == QUEUED_STAGE,
            ChatbotTurn.id != me.id,
        )
        # A row whose request died while it waited (a deploy killed the process) stays
        # `processing / queued` for good. It arrived before a turn that has since been
        # answered, so it is history, never a message on its way. State, not a clock.
        last_answered = _latest_finished_arrival(db, contact_respond_id=contact_respond_id, me=me)
        if last_answered is not None:
            query = query.filter(ChatbotTurn.started_at > last_answered)
        queued = query.all()
        for row in queued:
            if row.message_id is not None and row.message_id == me.message_id:
                continue
            envelope = row.envelope if isinstance(row.envelope, dict) else {}
            sent = send_key_ms(envelope.get("message"))
            if sent is not None and sent < my_sent:
                found.append(
                    Earlier(
                        order_key=float(sent),
                        row_id=str(row.id),
                        envelope=envelope,
                        carries_media=_envelope_carries_media(envelope),
                    )
                )

    found.extend(_ledger_only_media(db, contact_respond_id=contact_respond_id, me=me))
    if my_sent is not None:
        found.extend(_stored_only_media(db, contact_respond_id=contact_respond_id, me=me, my_sent=my_sent))
    return sorted(found, key=lambda e: e.order_key)


def _envelope_carries_media(envelope: dict[str, Any]) -> bool:
    from app.services.chatbot import media_intake

    body = envelope.get("message") if isinstance(envelope.get("message"), dict) else {}
    inner = body.get("message") if isinstance(body.get("message"), dict) else {}
    return media_intake.detect(inner) is not None


def within_bounds(
    earlier: list[Earlier],
    *,
    media_wait_seconds: float,
    own_carries_media: bool,
    budget_seconds: float = N8N_CHAT_TURN_TIMEOUT_SECONDS,
) -> tuple[list[Earlier], list[Earlier], list[str]]:
    """Split `earlier` (oldest first) into what this turn answers and what it leaves.

    Two bounds, both counts: `MAX_EARLIER_PER_TURN`, and the worst-case media waits (this
    turn's own included) staying below `budget_seconds`. A queued row that does not fit
    ends the take, so nothing later is answered ahead of one whose own request comes
    first. A ledger-only photo that does not fit is only skipped: it reaches `/chat/turn`
    after every queued row, or never, so stopping there gains it nothing (review round 3,
    S1). Returns (taken, left, reasons), `reasons` naming each bound that left something.
    """
    spent = media_wait_seconds if own_carries_media else 0.0
    taken: list[Earlier] = []
    left: list[Earlier] = []
    reasons: list[str] = []
    for index, item in enumerate(earlier):
        if len(taken) >= MAX_EARLIER_PER_TURN:
            return taken, left + earlier[index:], reasons + ["count_bound"]
        cost = media_wait_seconds if item.carries_media else 0.0
        if cost and spent + cost >= budget_seconds:
            if "media_wait_budget" not in reasons:
                reasons.append("media_wait_budget")
            if item.row_id is None:
                left.append(item)
                continue
            return taken, left + earlier[index:], reasons
        spent += cost
        taken.append(item)
    return taken, left, reasons


def _latest_finished_arrival(db: Session, *, contact_respond_id: str, me: ChatbotTurn) -> datetime | None:
    """When the latest ANSWERED turn of this contact arrived (its `started_at`)."""
    row = (
        db.query(ChatbotTurn.started_at)
        .filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.is_test.is_(False),
            ChatbotTurn.id != me.id,
            ChatbotTurn.finished_at.isnot(None),
        )
        .order_by(ChatbotTurn.started_at.desc())
        .first()
    )
    return row[0] if row is not None else None


def _ledger_only_media(
    db: Session, *, contact_respond_id: str, me: ChatbotTurn
) -> list[Earlier]:
    from app.models.media import ContactMediaUsage, MediaExtractionJob

    # This turn's own first sight: its arrival, or n8n's earlier media call for it.
    first_seen = me.started_at or me.created_at
    own = (
        db.query(ContactMediaUsage.created_at)
        .filter(
            ContactMediaUsage.respond_io_id == contact_respond_id,
            ContactMediaUsage.message_id == me.message_id,
        )
        .order_by(ContactMediaUsage.created_at.asc())
        .first()
        if me.message_id
        else None
    )
    previous = (
        db.query(ChatbotTurn.started_at)
        .filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.is_test.is_(False),
            ChatbotTurn.id != me.id,
            ChatbotTurn.started_at < first_seen,
        )
        .order_by(ChatbotTurn.started_at.desc())
        .first()
    )

    query = (
        db.query(ContactMediaUsage, MediaExtractionJob)
        .join(MediaExtractionJob, MediaExtractionJob.usage_id == ContactMediaUsage.id)
        .filter(
            ContactMediaUsage.respond_io_id == contact_respond_id,
            ContactMediaUsage.outcome == "accepted",
            ContactMediaUsage.created_at <= first_seen,
            # Still being read. A finished job's photo either reached `/chat/turn`
            # already (it has a turn row) or never will (n8n answered it on its own reply
            # arm), so only an unfinished one is "on its way".
            MediaExtractionJob.status.in_(("queued", "running")),
        )
    )
    if own is not None:
        query = query.filter(ContactMediaUsage.created_at < own[0])
    if previous is not None:
        query = query.filter(ContactMediaUsage.created_at > previous[0])
    if me.message_id:
        query = query.filter(ContactMediaUsage.message_id != me.message_id)

    found: list[Earlier] = []
    for usage, job in query.order_by(ContactMediaUsage.created_at.asc()).all():
        answered = (
            db.query(ChatbotTurn.id)
            .filter(
                ChatbotTurn.contact_respond_id == contact_respond_id,
                ChatbotTurn.message_id == usage.message_id,
                ChatbotTurn.is_test.is_(False),
            )
            .first()
        )
        if answered is not None or not job.media_url:
            continue
        found.append(
            Earlier(
                order_key=_epoch_ms(usage.created_at),
                message_id=str(usage.message_id),
                modality=str(usage.modality),
                media_url=job.media_url,
                mime_type=job.mime_type,
                caption=job.caption,
                job_id=str(job.id),
                carries_media=True,
            )
        )
    return found


def ledger_envelope(my_envelope: dict[str, Any], earlier: Earlier) -> dict[str, Any]:
    """The earlier media message as the envelope its own delivery will carry.

    Built from THIS turn's envelope (same contact, channel and workspace) with the message
    swapped for the attachment the ledger recorded. Its intake then replays the SAME ledger
    row and job (the idempotency key is contact, message id, modality), so nothing is
    extracted or charged twice. No send time: respond.io's is not in the ledger.
    """
    envelope = copy.deepcopy(my_envelope)
    envelope["media"] = None
    body = envelope.setdefault("message", {})
    inner = copy.deepcopy(body.get("message")) if isinstance(body.get("message"), dict) else {}
    inner.pop("timestamp", None)
    # The text's quote (if it quoted something) is not the photo's.
    inner.pop("replyTo", None)
    inner.pop("reply_to", None)
    inner["messageId"] = earlier.message_id
    attachment: dict[str, Any] = {
        "type": "image" if earlier.modality == "image" else "audio",
        "url": earlier.media_url,
    }
    if earlier.mime_type:
        attachment["mimeType"] = earlier.mime_type
    if earlier.caption:
        attachment["description"] = earlier.caption
    inner["message"] = {"type": "attachment", "attachment": attachment}
    body["message"] = inner
    return envelope


def _latest_answered_send_ms(db: Session, *, contact_respond_id: str, me: ChatbotTurn) -> float | None:
    """The send time of this contact's latest ANSWERED turn (by arrival), or None."""
    row = (
        db.query(ChatbotTurn.message_id, ChatbotTurn.envelope)
        .filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.is_test.is_(False),
            ChatbotTurn.id != me.id,
            ChatbotTurn.finished_at.isnot(None),
        )
        .order_by(ChatbotTurn.started_at.desc())
        .first()
    )
    if row is None:
        return None
    from_id = _message_id_ms(row[0])
    if from_id is not None:
        return from_id
    envelope = row[1] if isinstance(row[1], dict) else {}
    return send_key_ms(envelope.get("message"))


def _stored_only_media(
    db: Session, *, contact_respond_id: str, me: ChatbotTurn, my_sent: float
) -> list[Earlier]:
    """Media messages the CRM's webhook stored before this one was sent, that are not a
    turn yet and that n8n's media intake has not touched (CHAT-SEND-ORDER)."""
    from app.models.chat_history import ChatHistory
    from app.models.media import ContactMediaUsage
    from app.services.chatbot import media_intake

    floor = my_sent - STORED_LOOKBACK_SECONDS * 1000
    answered = _latest_answered_send_ms(db, contact_respond_id=contact_respond_id, me=me)
    if answered is not None:
        floor = max(floor, answered)

    def _naive_utc(ms: float) -> datetime:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)

    # `sent_at` is the id's send time cut to ms, so the SQL window is a ms either side and
    # the exact comparison runs on the id below.
    query = db.query(ChatHistory).filter(
        ChatHistory.contact_id == contact_respond_id,
        ChatHistory.type == "incoming",
        ChatHistory.message_id.isnot(None),
        ChatHistory.media_type.isnot(None),
        ChatHistory.media_url.isnot(None),
        ChatHistory.sent_at >= _naive_utc(floor - 1),
        ChatHistory.sent_at <= _naive_utc(my_sent + 1),
    )
    if me.message_id:
        query = query.filter(ChatHistory.message_id != me.message_id)

    found: list[Earlier] = []
    seen: set[str] = set()
    for row in query.order_by(ChatHistory.sent_at.asc(), ChatHistory.id.asc()).all():
        message_id = str(row.message_id)
        if message_id in seen:
            continue
        seen.add(message_id)
        key = _message_id_ms(message_id)
        if key is None:
            key = _epoch_ms(row.sent_at)
        if not floor < key < my_sent:
            continue
        has_turn = (
            db.query(ChatbotTurn.id)
            .filter(
                ChatbotTurn.contact_respond_id == contact_respond_id,
                ChatbotTurn.message_id == message_id,
                ChatbotTurn.is_test.is_(False),
            )
            .first()
        )
        if has_turn is not None:
            continue
        in_ledger = (
            db.query(ContactMediaUsage.id)
            .filter(
                ContactMediaUsage.respond_io_id == contact_respond_id,
                ContactMediaUsage.message_id == message_id,
            )
            .first()
        )
        if in_ledger is not None:
            continue
        attachment_type = str(row.media_type)
        found.append(
            Earlier(
                order_key=key,
                message_id=message_id,
                media_url=row.media_url,
                caption=row.message or None,
                attachment_type=attachment_type,
                file_name=row.media_file_name,
                carries_media=media_intake.detect({"attachment": {"type": attachment_type}}) is not None,
            )
        )
    return found


def stored_envelope(my_envelope: dict[str, Any], earlier: Earlier) -> dict[str, Any]:
    """A stored-only media message as the envelope its own delivery will carry.

    Built from THIS turn's envelope (same contact, channel and workspace), with the message
    swapped for the attachment the webhook stored, its own id and its send time. The
    engine's own media intake then reads a photo or voice note under the ledger key n8n's
    intake uses too (contact, message id, modality), so nothing is read or charged twice.
    """
    envelope = copy.deepcopy(my_envelope)
    envelope["media"] = None
    body = envelope.setdefault("message", {})
    inner = copy.deepcopy(body.get("message")) if isinstance(body.get("message"), dict) else {}
    # The text's quote (if it quoted something) is not the photo's.
    inner.pop("replyTo", None)
    inner.pop("reply_to", None)
    inner["messageId"] = earlier.message_id
    inner["timestamp"] = int(earlier.order_key)
    attachment: dict[str, Any] = {"type": earlier.attachment_type, "url": earlier.media_url}
    if earlier.file_name:
        attachment["fileName"] = earlier.file_name
    if earlier.caption:
        attachment["description"] = earlier.caption
    inner["message"] = {"type": "attachment", "attachment": attachment}
    body["message"] = inner
    return envelope
