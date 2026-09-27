"""Request shapes for the sales-order-line attachment routes (#1312,
PLAN-oi-line-attachments-27sep.md)."""
from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

#: AC-A5: more than this many ids in one lookup answers 422.
MAX_LOOKUP_IDS = 1000


class SoLineAttachmentLookupRequest(BaseModel):
    # security L3: `UUID`, not `str` - a malformed entry answers 422 through
    # FastAPI's own validation handler rather than reaching the DB layer.
    line_ids: List[UUID] = Field(default_factory=list, max_length=MAX_LOOKUP_IDS)
