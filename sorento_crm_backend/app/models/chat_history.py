"""High-volume chat history model populated by n8n."""
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    channel = Column(String(32), nullable=False)
    contact_id = Column(String(128), nullable=False)
    phone_number = Column(String(32), nullable=False)
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=False), nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    type = Column(String(32), nullable=False)
    # Respond.io message id + the numbered-options result set the bot sent in
    # that message. Lets conversation-variables resolve a result set by the
    # message the user replied to, not only the latest one.
    message_id = Column(String(64), nullable=True)
    result = Column(JSONB, nullable=True)
    # Set on incoming rows when the user quote-replied to an older message.
    # `reply_to_message_id` matches the `message_id` of that earlier outgoing row,
    # so the chatbot can resolve the pick against its stored `result` set.
    reply_to_message_id = Column(String(64), nullable=True)
    reply_to_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    # --- Round-trip latency telemetry -------------------------------------
    # `sent_at` above is whatever n8n supplied. `respond_ts` is the authoritative
    # Respond-side timestamp, resolved via GET /v2/message/{id}. Both ends of the
    # SLA measurement read `respond_ts` so the two timestamps share one clock —
    # mixing Respond's clock with ours would bake skew into the p99.
    respond_ts = Column(DateTime(timezone=False), nullable=True)
    # sent | delivered | read | failed | not_sent. Displayed and alerted on
    # separately, but NOT part of the p99: delivery is owned by the recipient's
    # handset, so an offline user must not be able to breach our SLA.
    delivery_status = Column(String(32), nullable=True)
    delivered_ts = Column(DateTime(timezone=False), nullable=True)
    read_ts = Column(DateTime(timezone=False), nullable=True)
    resolve_attempts = Column(Integer, nullable=True, server_default="0")
    # n8n $execution.id, stamped on both saves of one turn. NULL = proactive send,
    # which is excluded from the SLA denominator rather than paired by guesswork.
    turn_id = Column(String(64), nullable=True)
    # Our clock at ingest. Diagnostic only: ingest_at - respond_ts is webhook lag,
    # which is the thing that silently degrades when Respond's webhook misbehaves.
    ingest_at = Column(DateTime(timezone=False), nullable=True)
    # Per-turn conversation state transition (v1), populated by n8n on INCOMING rows
    # only; NULL on outgoing. Opaque jsonb: {v, before, parser_raw, parser_applied,
    # after}. `after: null` means the turn wrote no state (no-access refusal, LLM
    # fallback) — a real signal, distinct from "field absent". Diagnostic column: read
    # by the admin thread view, deliberately absent from the external read contract.
    state_trace = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_chat_histories_channel_contact_sent_id", "channel", "contact_id", "sent_at", "id"),
        Index("ix_chat_histories_channel_phone_sent", "channel", "phone_number", "sent_at"),
        Index("ix_chat_histories_channel_type_sent", "channel", "type", "sent_at"),
        Index(
            "ix_chat_histories_contact_message_id",
            "contact_id",
            "message_id",
            postgresql_where=message_id.isnot(None),
        ),
        Index(
            "ix_chat_histories_contact_reply_to",
            "contact_id",
            "reply_to_message_id",
            postgresql_where=reply_to_message_id.isnot(None),
        ),
    )
