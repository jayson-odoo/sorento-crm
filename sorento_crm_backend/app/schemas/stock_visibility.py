"""Admin API shapes for the stock visibility policy.

One body for every tier (`{effective, override}`), so the same card serves the
contact page, the access-type admin and the settings default without three
response shapes to keep in step. The full contract, request and response, is
documented at the top of `sorento_crm_frontend/services/stockVisibilityService.ts`.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class StockVisibilityWarehouse(BaseModel):
    """A warehouse RESOLVED, not a bare id: the card renders `CODE - name`, and a
    UUID must never reach the UI."""

    id: str
    code: str
    name: Optional[str] = None


class StockVisibilityPolicyOut(BaseModel):
    mode: Literal["detailed", "compact", "availability"]
    #: null = every active warehouse; [] = none at all.
    warehouses: Optional[List[StockVisibilityWarehouse]] = None
    source: Literal["contact", "access_type", "default"]
    #: The access type's NAME when `source` is `access_type`, so the badge can
    #: read "Access type: Dealer". A name, never the code.
    source_label: Optional[str] = None


class StockVisibilityPolicyResponse(BaseModel):
    effective: StockVisibilityPolicyOut
    #: The row stored AT the requested tier. null = this tier inherits.
    override: Optional[StockVisibilityPolicyOut] = None


class StockVisibilityInput(BaseModel):
    """Upsert body. `warehouse_ids` is REPLACED wholesale, never merged - merging
    would make removing a location impossible from the card."""

    mode: Literal["detailed", "compact", "availability"]
    #: REQUIRED, and nullable rather than defaulted: a PUT replaces the whole row,
    #: so a body that simply omitted the key used to widen the policy to every
    #: location - the one edit an admin can make without meaning to.
    warehouse_ids: Optional[List[str]] = Field(
        ..., description="null = every active warehouse; [] = none."
    )
