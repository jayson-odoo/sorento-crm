"""External ideation brain-path schemas (ideate turn endpoint, §5.1/§5.2)."""
from typing import Any

from pydantic import BaseModel, Field


class IdeationTurnRequest(BaseModel):
    """Body n8n posts for an `ideate`-classified WhatsApp turn."""

    respond_io_id: str = Field(..., description="Respond.io contact id (not internal UUID).")
    message_text: str = Field(..., description="The user's latest raw turn.")
    audio_attachment_ref: str | None = Field(
        None, description="Optional reference to a transcribed voice note (D9)."
    )
    session_vars: dict[str, Any] | None = Field(
        None,
        description=(
            "Caller-supplied session state. The ideation pointer is read from "
            "session_vars.ideation (or session_vars.variables.ideation). n8n owns/writes "
            "session_vars, so the endpoint trusts this over its own (possibly stale) DB "
            "copy — this is what makes the draft accumulate across turns."
        ),
    )


class IdeationTurnResponse(BaseModel):
    """What n8n relays: the tool's reply, an optional deep link, and the full
    updated session_vars blob."""

    status: str
    reply_text: str
    link: str | None = None
    session_vars: dict[str, Any] = Field(default_factory=dict)
