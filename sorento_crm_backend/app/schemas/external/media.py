"""Chatbot media endpoint schemas (PLAN-chatbot-media-endpoint section 3.2).

The response is always 200 for a well-formed request: **the decision is in the
body, not the status code**, because n8n branches on it and an HTTP error would
send the turn down the failure path when the correct answer is "this contact is
not allowed photos". `decision` answers "may we", `status` answers "did we".
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

MediaModality = Literal["image", "voice"]


class MediaProcessRequest(BaseModel):
    """One inbound media message, as n8n describes it."""

    respond_io_id: str = Field(..., description="Respond.io contact id, not the internal UUID.")
    message_id: str = Field(
        ...,
        description=(
            "Respond.io messageId. Together with modality and media_ordinal this is "
            "the idempotency key, which is what makes n8n's `retryOnFail` free "
            "rather than a second extraction spend."
        ),
    )
    modality: MediaModality
    media_ordinal: int = Field(
        0,
        ge=0,
        description=(
            "0 unless one messageId carries several media items. Present so that "
            "case needs an n8n change rather than a migration."
        ),
    )
    media_url: str = Field(..., description="Respond.io CDN url the worker fetches.")
    mime_type: Optional[str] = None
    caption: Optional[str] = None
    duration_ms: Optional[int] = Field(
        None, ge=0, description="Voice only. Checked against the clip cap before any spend."
    )
    bytes: Optional[int] = Field(None, ge=0)
    turn_id: Optional[str] = Field(None, description="n8n $execution.id.")
    callback_url: Optional[str] = Field(
        None,
        description=(
            "Opaque. The CRM POSTs the result here and assumes nothing about what "
            "consumes it. Omitting it is valid and disables callback delivery."
        ),
    )
    callback_headers: Optional[dict[str, str]] = Field(
        None, description="Opaque; applied verbatim to the callback POST."
    )
    context: Optional[dict[str, Any]] = Field(
        None, description="Opaque turn context, echoed back unchanged."
    )


class MediaQuota(BaseModel):
    used: int
    limit: int
    remaining: int
    period_key: str = Field(..., description="YYYY-MM, computed in Asia/Kuala_Lumpur.")
    resets_on: str = Field(
        ..., description="Already rendered ('1 September'). n8n does no date arithmetic."
    )


class MediaNotice(BaseModel):
    kind: str
    text: str = Field(..., description="Ready to send. The far end formats nothing.")
    append: bool = True


class MediaProcessResponse(BaseModel):
    job_id: Optional[str] = Field(None, description="Null when the decision is a refusal.")
    decision: Literal[
        "accepted", "denied_gate", "denied_burst", "denied_quota", "denied_duration"
    ]
    status: Optional[Literal["completed", "pending", "failed"]] = Field(
        None,
        description=(
            "Accepted decisions only. `pending` is the graceful edge, not an error: "
            "the wait hit media_sync_wait_seconds, the job is still running, and the "
            "result stays retrievable through GET /media/jobs/{job_id} and the callback."
        ),
    )
    idempotent_replay: bool = False
    tier: Optional[Literal["standard", "degraded"]] = None
    quota: MediaQuota
    notices: list[MediaNotice] = Field(default_factory=list)
    language_strategy: Optional[dict[str, Any]] = Field(
        None, description="Voice only."
    )
    result: Optional[dict[str, Any]] = Field(
        None, description="The extraction body. Null unless status == completed."
    )
    error: Optional[str] = None
