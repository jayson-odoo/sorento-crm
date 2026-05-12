"""External conversation-state schemas: arbitrary JSON state keyed by respond_io_id."""
from typing import Any

from pydantic import BaseModel, Field, RootModel


class ConversationStateResponse(BaseModel):
    respond_io_id: str
    session_vars: dict[str, Any] = Field(default_factory=dict)


class ConversationStateOverwriteRequest(RootModel[dict[str, Any]]):
    """Arbitrary JSON object that replaces `respond_contacts.session_vars` wholesale."""

    root: dict[str, Any] = Field(default_factory=dict)
