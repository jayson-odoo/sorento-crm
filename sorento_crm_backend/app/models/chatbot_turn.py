"""`chatbot.turns` - the turn inbox and its human-readable trace (D12, D13).

One table, in the module's own Postgres schema, so an uninstall drops the module's data
and nothing else. `respond_contacts.session_vars` stays in `public`: it is shared with
ideation and with n8n during the migration window.

**It is a RECORD and a TRACE, never a queue.** The n8n dispatcher is the queue until S7,
and from S7 the per-contact ordering is a redis ticket inside the request. A row is
created by `POST /chat/turn` and closed either by that same call (when the CRM finished
the turn) or by `POST /chat/turn/{id}/complete`; `delegated` is the state in between.

Two columns carry the whole idempotency story (D15, AC-712): `message_id` plus the unique
index on `(contact_respond_id, message_id)`. The webhook producer and the failover poller
are two injectors of one envelope shape, so the same respond message can legitimately
arrive twice. The SELECT-then-INSERT dedup in the engine is a TOCTOU window, so the
unique index is the real backstop: the collision is caught, the winner's row is read, and
its stored `response` is replayed with `duplicate: true` so the caller sends nothing.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ChatbotTurn(Base):
    """One inbound message's journey through the engine."""

    __tablename__ = "turns"
    __table_args__ = (
        # The list the trace screen pages (S2b): one contact, filtered by status, newest
        # first.
        Index("ix_chatbot_turns_contact_status_created", "contact_respond_id", "status", "created_at"),
        # D15: idempotency per respond message. A NULL message_id (a console turn with no
        # respond message behind it) does not participate, which is Postgres's own
        # NULL-distinct behaviour and exactly what is wanted.
        UniqueConstraint("contact_respond_id", "message_id", name="uq_chatbot_turns_contact_message"),
        {"schema": "chatbot"},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)

    # The respond.io contact id, the same value `respond_contacts.respond_io_id` holds.
    # Deliberately not an FK: a turn is a log line and must survive the contact row.
    contact_respond_id = Column(String(64), nullable=False)
    # The respond.io message id (D15). Nullable for a console-driven turn.
    message_id = Column(String(128), nullable=True)
    # Which injector delivered it: webhook | poller | retry | console. Recorded so a
    # duplicate can be explained, never branched on.
    ingress = Column(String(32), nullable=False, server_default="webhook")

    envelope = Column(JSONB, nullable=False)
    # D14: a test envelope does ZERO writes outside this table.
    is_test = Column(Boolean, nullable=False, server_default="false", default=False)

    # queued | processing | delegated | done | failed
    status = Column(String(20), nullable=False, server_default="processing")
    # Where the turn stopped: a TurnStage, or intake / queued / casual_llm.
    stage = Column(String(32), nullable=True)
    branch_kind = Column(String(32), nullable=True)
    error = Column(Text, nullable=True)
    # R4: no automatic retry. This counts MANUAL retries from the trace screen.
    attempt = Column(Integer, nullable=False, server_default="1")

    # An ordered array of stage records, each {stage, status, started_at, ms, summary,
    # why, facts, error, raw}. `summary` and `why` are sentences the engine writes from
    # structured state (D11: never from the customer's text), so the screen renders words.
    trace = Column(JSONB, nullable=True)

    # The answer this turn returned: `{ctx, item, actions}` today, `{reply, actions}` from
    # S3. D15 needs it - a duplicate delivery must replay the ORIGINAL answer, and n8n's
    # `build-ctx` / `route-turn` re-emitters throw on a null `ctx`. It is also what S2b's
    # Retry reads to show the operator what was actually sent.
    response = Column(JSONB, nullable=True)

    # Gate 4 (shadow mode): the n8n turn id this row shadows, when the live spine also
    # called us with is_test and kept its own reply.
    shadow_of = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
