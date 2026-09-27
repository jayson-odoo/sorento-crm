"""Request shapes for the sales-order-line attachment routes (#1312,
PLAN-oi-line-attachments-27sep.md)."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

#: AC-A5: more than this many ids in one lookup answers 422.
MAX_LOOKUP_IDS = 1000


class SoLineAttachmentLookupRequest(BaseModel):
    line_ids: List[str] = Field(default_factory=list, max_length=MAX_LOOKUP_IDS)
