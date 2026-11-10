"""STANDARD-HISTORY wave 1: one order inquiry's History tab (AC-SH-B1).

The same event shape as the SO History drawer (`planning_history_service.py`): each event
lists the lines it touched, so a batch press is ONE event naming every row. `actor` is a
human name or "Automatic", never a UUID. No IP, user agent or raw audit values (AC-SH-B6).
"""
from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel


class OrderInquiryHistoryLineOut(BaseModel):
    row_id: str
    so_line_no: Optional[int] = None
    item_code: Optional[str] = None
    qty: Optional[Union[int, float]] = None
    change: str


class OrderInquiryHistoryEventOut(BaseModel):
    """`kind`: raised / reconfirmed / confirmed / unconfirmed / cancelled / linked /
    unlinked / rejected / reserved / unreserved."""

    id: str
    kind: str
    at: Optional[str] = None
    actor: Optional[str] = None
    title: str
    lines: List[OrderInquiryHistoryLineOut]


class OrderInquiryHistoryResponse(BaseModel):
    events: List[OrderInquiryHistoryEventOut]
