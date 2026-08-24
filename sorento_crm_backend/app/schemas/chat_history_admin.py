"""Admin-facing chat history schemas.

`contact_id` is the Respond.io id and is included only so the UI can filter and
deep-link by it - never for display. `contact_display` is what gets rendered.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChatMessageRowResponse(BaseModel):
    id: int
    channel: str
    contact_id: str
    contact_display: str
    phone_number: str
    type: str
    message: str
    sent_at: datetime
    # Authoritative Respond-side timestamp. Null until the resolver fills it, which is
    # also why `latency_seconds` can be null on an otherwise complete-looking turn.
    respond_ts: Optional[datetime] = None
    delivery_status: Optional[str] = None
    turn_id: Optional[str] = None
    message_id: Optional[str] = None
    # Present on outgoing rows only: seconds from the incoming message of the same turn.
    latency_seconds: Optional[float] = None
    webhook_lag_seconds: Optional[float] = None
    # Per-turn conversation state transition, populated on INCOMING rows only and only
    # on the thread (transcript) path - the diagnosis surface. Opaque by design:
    # {v, before, parser_raw, parser_applied, after}. NULL on the grid list and on
    # every outgoing row. The FE derives the entities-lost/gained + cause-flags summary
    # from this (mirroring the v_turn_state_transition view) and offers the raw document
    # in a searchable JSON viewer.
    state_trace: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class ChatMessagePagination(BaseModel):
    total: int
    page: int


class ChatMessageListResponse(BaseModel):
    data: list[ChatMessageRowResponse]
    # Offset pagination, to fit the shared DataGrid contract (arbitrary page jumps +
    # a total for the pager). The date filter bounds the scan. The CSV export path
    # still walks by keyset for flat memory over the unbounded set.
    pagination: ChatMessagePagination
    empty: bool = False


class ChatThreadResponse(BaseModel):
    data: list[ChatMessageRowResponse]
    contact_display: str
    empty: bool = False


class ChatHistoryExportRequest(BaseModel):
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    contact_id: Optional[str] = None
    direction: Optional[str] = None
    search: Optional[str] = None
    breached_only: bool = False
