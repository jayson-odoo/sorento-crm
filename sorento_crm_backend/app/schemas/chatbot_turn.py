"""Response shapes for the turn trace admin API (AC-257).

**Every field the screen reads is declared here.** `response_model` silently DROPS an
undeclared field, and the two that would go first - `trace` and `response` - are the whole
point of the screen: a trace list that arrives empty looks like "the engine recorded
nothing", not like "the schema forgot to say the column exists".

`trace` records and `response` stay loosely typed on purpose. Their shape is the ENGINE's
(`app/services/chatbot/trace.py`, `contracts.py`), the turn rows already in the table were
written by earlier versions of it, and a strict model here would drop a field the day the
engine adds one - the exact failure this file exists to prevent, arriving through the back
door.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatbotTurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_respond_id: str
    message_id: str | None = None
    ingress: str
    status: str
    stage: str | None = None
    branch_kind: str | None = None
    error: str | None = None
    attempt: int
    is_test: bool
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_requested_at: datetime | None = None
    # The stage records the timeline renders. `[]` when the engine wrote none.
    trace: list[dict[str, Any]] = []
    # The answer the turn returned: `{ctx, item, actions}` today, `{reply, actions}` from
    # S3. Null on a turn that failed or is still running.
    response: dict[str, Any] | None = None


class ChatbotTurnListResponse(BaseModel):
    items: list[ChatbotTurnResponse]
    # Opaque. Absent (null) when there is no further page.
    next_cursor: str | None = None
    # Whether Retry can work in this environment at all. Rides the list rather than a
    # route of its own: it is one boolean the screen needs at the same moment it needs the
    # turns, and a second endpoint, hook, query and prop hop to deliver it is machinery a
    # single field does not need.
    retry_available: bool = False
    retry_unavailable_reason: str | None = None


class FailedContactRow(BaseModel):
    """One contact with at least one failed turn in the range (AC-255).

    An aggregate rather than a page of turns: the list filter needs "which contacts are
    worth opening", and answering that by pulling every turn and grouping in the frontend
    would move thousands of rows to answer a question about tens.
    """

    contact_respond_id: str
    last_failed_stage: str | None = None
    last_failed_at: datetime | None = None
    count: int


class FailedContactListResponse(BaseModel):
    items: list[FailedContactRow]


class RetryTurnResponse(BaseModel):
    turn_id: str
    # The attempt the RE-INJECTED turn will carry when it arrives as its own row. The row
    # being retried keeps its own attempt: it is a record of what happened.
    attempt: int
