"""Response + annotation schemas for AutoCount read-only mirror entities.

Every mirror response carries ``source`` so the frontend gates read-only on one
uniform field (AC-G3). For new mirror tables (credit_terms, tax_codes, ...) only
ingest ever creates a row, so ``source`` is always "autocount"; the field still
ships for a uniform FE contract with the reused tables (orders/SO/PO) where it is
computed from provenance.

Annotation is the ONLY write the UI performs on a mirror: Sorento-only columns the
ingest column-map never touches, so they survive re-sync (AC-G2).

**This file is the meeting point of two branches.** The AutoCount branch ships the
same module with the other mirror entities (credit terms, tax codes, payment methods,
...) in it; SCM S6 ships only the sales-agent pair, because that is the only mirror
this chain has a table for. The three classes below are byte-compatible with that
branch's definitions plus the three named extensions S6 needs, so the merge is an
addition on both sides rather than a contradiction:

1. ``MirrorAnnotationUpdate`` also allows ``person_label`` and ``demand_class``. With
   ``extra="forbid"`` and without them the merged page could not write the two columns
   it exists to write, and would say nothing about why.
2. ``SalesAgentResponse`` declares them too, because ``response_model`` drops any field
   a schema does not name: the values would be held and read as absent.
3. ``_MirrorBase.source`` accepts ``import``. The AutoCount literal is
   ``("autocount", "manual")`` while S1's column carries ``manual`` or ``import`` (a
   row an upload created on meeting an unknown code), and an undeclared value fails
   response validation - a 500 on a list the operator did nothing wrong to reach.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MirrorAnnotationUpdate(BaseModel):
    """PATCH body. Only these columns may be written from the UI.

    ``extra="forbid"`` on purpose: a mistyped key must fail loudly rather than answer
    200 having written nothing, which is the failure that looks exactly like success.
    Omitting a field leaves it alone (the routes read ``model_fields_set``), so sending
    only ``demand_class`` cannot wipe a label.
    """

    model_config = ConfigDict(extra="forbid")
    internal_note: Optional[str] = None
    follow_up: Optional[bool] = None
    #: Who the codes belong to. Free text, and metadata only - it groups codes for
    #: reporting and decides nothing. Bounded to the column's own width: without it a
    #: pasted 120-character name dies in the flush and the user's toast reads
    #: `StringDataRightTruncation`, which tells them nothing they can act on.
    person_label: Optional[str] = Field(None, max_length=100)
    #: What this agent's orders are for. Validated by ``sales_agent_service``, not here:
    #: typing it as a Literal would answer a bad word with a 422 field error instead of
    #: the service's message naming the words the fulfilment policy can weigh.
    demand_class: Optional[str] = None


class _MirrorBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
    internal_note: Optional[str] = None
    follow_up: bool = False
    source: Literal["autocount", "manual", "import"] = "autocount"
    created_at: datetime
    updated_at: Optional[datetime] = None


class SalesAgentResponse(_MirrorBase):
    sales_agent: str
    description: Optional[str] = None
    person_label: Optional[str] = None
    demand_class: Optional[str] = None
