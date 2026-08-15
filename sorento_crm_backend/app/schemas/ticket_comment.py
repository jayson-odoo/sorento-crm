"""Schemas for internal ticket comments (UAC AC-L1/L2/L3)."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketCommentCreate(BaseModel):
    """A comment written from the ticket drawer's comment mode."""

    body: str = Field(..., min_length=1, max_length=5000)
    # CRM users.id values. The body keeps the readable "@Display Name" inline;
    # these are what the mention notification and the Respond mirror resolve.
    mentioned_user_ids: list[str] = Field(default_factory=list)

    @field_validator("body")
    @classmethod
    def _body_is_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("A comment cannot be empty.")
        return cleaned

    @field_validator("mentioned_user_ids")
    @classmethod
    def _dedupe_mentions(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for raw in value or []:
            uid = str(raw).strip()
            if uid and uid not in seen:
                seen.append(uid)
        return seen


class TicketCommentResponse(BaseModel):
    """One rendered comment. No CRM user ids beyond the row's own id: the UI
    renders names, never uuids (cursor rule)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    # Null on a Respond-ingested (contact-scoped) comment.
    tracking_id: Optional[str] = None
    body: str
    author_name: Optional[str] = None
    mentioned_names: list[str] = Field(default_factory=list)
    source: Literal["crm", "respond"] = "crm"
    created_at: datetime


class TicketCommentIngestRequest(BaseModel):
    """One `comment.created` event forwarded by n8n from Respond.io.

    Respond comments are contact-scoped, so there is no tracking id here: the
    comment is attached to the contact and renders in every open ticket for it.
    """

    # Respond.io contact id (the `respond_io_id` we store), or `phone_number`.
    contact_id: Optional[str] = None
    phone_number: Optional[str] = None
    # Respond's own comment id: the dedupe key for a replayed webhook, and
    # therefore MANDATORY. Typed Optional so a payload without one gets the
    # route's readable 400 rather than a pydantic 422 the forwarder cannot tell
    # apart from a transport fault - but a missing or blank value is refused.
    # Without it there is no way to recognise a replay, and a 201 that is not
    # idempotent is a worse promise than a refusal.
    comment_id: Optional[str] = Field(None, max_length=128)
    text: str = Field(..., min_length=1, max_length=5000)
    author_respond_user_id: Optional[str] = Field(None, max_length=64)
    author_name: Optional[str] = None
    created_at: Optional[int] = Field(None, description="Epoch milliseconds")

    @field_validator("text")
    @classmethod
    def _text_is_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("A comment cannot be empty.")
        return cleaned


class TicketCommentIngestResponse(BaseModel):
    id: str
    # "duplicate" mirrors the chat-message ingest: a replay is a 201 naming the
    # outcome in the body, never an error the forwarder would retry forever.
    status: Literal["created", "duplicate"]
