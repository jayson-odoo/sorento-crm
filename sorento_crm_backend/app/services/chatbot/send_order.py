"""A contact's messages are answered in the order they were SENT (issue #1262 round 3).

The per-contact ticket (`dispatch.py`) orders turns by ARRIVAL at `/chat/turn`, and arrival
is not send order: n8n forwards a text at once but runs its own media intake on a photo
first (~20 s), so a text sent after a photo overtakes it. Mr Loo, 26 Sep: photo 14:57:25,
"Stock" 14:57:29; the CRM ran "Stock" first and answered it from yesterday's products.

No timer and no waiting window (owner, 26 Sep: "very fragile"). The rule instead: when a
turn gets its slot, it first answers every EARLIER-sent message of this contact that the
CRM already KNOWS about and has not answered, then itself. The CRM knows about an earlier
message in exactly two ways, and this module reads both:

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
    my_sent = sent_at_ms(me.envelope.get("message") if isinstance(me.envelope, dict) else None)
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
            sent = sent_at_ms(envelope.get("message"))
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
