"""S5 - the one call n8n makes when a dealer's WhatsApp burst closes.

n8n is the pump: it receives every Respond.io message, debounces the burst with a wait node,
and calls this ONCE with everything at once. The CRM neither polls nor subscribes, so there
is no second message pump to keep in step with the first.

Wrapped as the MCP tool `complaint_intake_submit` (AC-C0a). The name matters beyond taste:
`_is_write_tool` keys off the `*_submit` suffix, so the AI-assistant prompt dry-run strips
this tool and a prompt test can never file a real Complaint against a real dealer (AC-C0b).

**Idempotent on `burst_key`** (AC-C0d). n8n retries on timeout, and a retry that created a
second Complaint would put the office back to deduplicating by hand - the exact work this
slice removes. The guarantee is a partial unique index on `complaints.intake_burst_key`, not
a lookup: two retries arriving together both find nothing and both insert.

**Extraction happens here, not in n8n.** The prompt is versioned through `ai_prompt_registry`
and the dealer, product and Kind resolvers already live in the CRM. An LLM node in n8n would
fork the registry and duplicate three resolvers, and the day the copies disagree the WhatsApp
track and the consumer portal name different dealers for the same shop.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user

logger = logging.getLogger(__name__)

router = APIRouter()


class IntakeMessage(BaseModel):
    """One WhatsApp message in the burst, as n8n saw it.

    `text` and `media_ref` are both optional because a message is routinely one or the
    other: photos arrive first and the words that explain them arrive after (AC-C3).
    """

    text: Optional[str] = None
    sent_at: Optional[str] = None
    media_ref: Optional[str] = None


class ComplaintIntakeRequest(BaseModel):
    # The idempotency key. n8n owns it - it knows which burst it debounced - and the same
    # value must come back on a retry or the guarantee is worthless.
    burst_key: str = Field(..., min_length=1, max_length=120)
    contact_id: str = Field(..., min_length=1)
    messages: List[IntakeMessage] = Field(default_factory=list)
    media_refs: List[str] = Field(default_factory=list)
    # Escape hatch for tests and replays: when supplied, the model is not called. Never
    # sent by n8n in normal operation.
    extraction: Optional[Dict[str, Any]] = None


@router.post("/submit")
def complaint_intake_submit(
    payload: ComplaintIntakeRequest,
    _principal: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """One burst in, one Complaint out, and the sentence to send back.

    Returns `complaint_number` and `missing_fields` so n8n can reply in the same
    conversation, asking for ONLY what is absent (AC-C5, AC-C6).
    """
    from app.services.complaint_intake_extractor import extract_burst
    from app.services.complaint_intake_service import submit_intake, transcript_of

    messages = [m.model_dump() for m in payload.messages]

    extraction = payload.extraction
    if extraction is None:
        # The transcript is built here, once, and reused for both the model call and the
        # stored record - so what the extractor read is exactly what a human later reads.
        extraction = extract_burst(db, transcript_of(messages))

    result = submit_intake(
        db,
        burst_key=payload.burst_key,
        contact_id=payload.contact_id,
        messages=messages,
        media_refs=payload.media_refs,
        extraction=extraction,
    )
    return {
        "complaint_id": result.complaint_id,
        "complaint_number": result.complaint_number,
        # n8n must not send the follow-up twice for one retried call.
        "already_submitted": result.already_submitted,
        "dealer_state": result.dealer_state,
        "dealer_name": result.dealer_name,
        "media_count": result.media_count,
        "missing_fields": result.missing_fields,
        "reply": result.reply,
        "prompt_versions": result.prompt_versions,
    }
