"""External conversation-variables schemas (n8n turn-by-turn variable accumulator)."""
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ConversationVariablesUpsertRequest(BaseModel):
    """Per-turn variable submission from n8n.

    `contact_id` maps to `respond_contacts.respond_io_id` (the Respond.io contact ID,
    not the internal CRM UUID). `space_id` is the Respond.io workspace ID — kept for
    audit / scope context, not used for the contact lookup itself. `inquiry_type`
    is a short classifier (e.g. "complaint", "general", "stock_inquiry").
    """

    contact_id: str = Field(..., description="Respond.io contact id (respond_io_id).")
    space_id: str = Field(..., description="Respond.io workspace/space id.")
    inquiry_type: str = Field(..., description="Inquiry classifier, e.g. 'complaint', 'general'.")
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Latest message's extracted variables. null value means delete that key from the "
            "merged rollup; empty string is preserved as a real value."
        ),
    )
    max_turns: int = Field(15, ge=1, le=100, description="Sliding-window cap (global across inquiry_types).")
    clear_inquiry_type: bool = Field(
        False,
        description=(
            "If true, drop all turns + merged state for `inquiry_type` first, then record the "
            "incoming `variables` as the seed of a fresh sub-conversation."
        ),
    )

    @field_validator("contact_id", "space_id", "inquiry_type", mode="before")
    @classmethod
    def _strip_required(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("must be a non-empty string")
        return s


class ConversationVariablesUpsertResponse(BaseModel):
    inquiry_type: str
    variables: dict[str, Any]
    turn_count_total: int
    turn_count_for_inquiry_type: int
    max_turns: int


class ConversationVariableKeysResponse(BaseModel):
    """Distinct variable keys ever recorded across all respond_contacts.session_vars.

    Returned to n8n so the LLM can reuse known keys instead of inventing new ones
    (e.g. avoid 'product' vs 'product_code' duplicates for the same concept).
    """

    keys: list[str]
    count: int
