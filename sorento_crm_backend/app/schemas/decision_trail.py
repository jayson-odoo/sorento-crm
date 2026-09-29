"""AC-DT-10 (`PLAN-oi-decision-trail-ui.md`, round 2): the decision trail behind ONE
core sales-order line - the History icon's own read, shared by the OI worklist/Lines-tab
row and the fulfilment-board line that name the same core line.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DecisionTrailEntryOut(BaseModel):
    """One fact in the trail, newest first. `kind` is `confirmed` / `saved` / `raised` /
    `reconfirmed` / `sheet` / `planning_change`. `actor_name` is always a human name, never
    a UUID (Cursor rules) - `None` when nobody is named (a sheet migration, or a planning
    change nobody attributed)."""

    kind: str
    actor_name: Optional[str] = None
    at: Optional[datetime] = None
    detail: Optional[str] = None


class DecisionTrailResponse(BaseModel):
    entries: List[DecisionTrailEntryOut]
