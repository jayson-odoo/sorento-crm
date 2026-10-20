"""OI-LINE-SPLIT: the whole-SO split view's wire shapes.

Contract: `documentation/plans/scm/PLAN-oi-line-split-16oct.md` ("Build design (final)",
API) and the frontend fixture `project-sales/_shared/__mocks__/lineSplits.ts`, which reads
quantities as JSON numbers. The server owns `base_qty` / `base_date`; the client never
sends them.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, condecimal


class LineSplitViewRowOut(BaseModel):
    """One row of a line's split popup (OI-SPLIT-VIEW, UAC B2): a saved split, or the
    AutoCount extra (`sits_on` "extra"). Quantities and dates are plain strings, the same on
    every read that carries the view."""

    qty: str
    delivery_date: Optional[str] = None
    #: The email's REMARK word (`remark_for_row`): ADVANCE / REMAIN / DELAY / CANCEL BALANCE /
    #: ORDER n.
    change: str
    #: "own" / "line" / "new" / "extra"; `sits_on_line_no` is the AutoCount line number.
    sits_on: str
    sits_on_line_no: Optional[int] = None
    remark: str = ""
    is_cancel: bool = False
    #: Not in the applied plan while the edit waits (UAC B4); `was_*` only when exact.
    changed: bool = False
    was_qty: Optional[str] = None
    was_date: Optional[str] = None


class LineSplitViewOut(BaseModel):
    """A split line as the split popup reads it (OI-SPLIT-VIEW, UAC B2 to B4), built by the one
    serializer `LineSplitService.split_views`; null on a line with no splits."""

    #: "confirmed" / "saved" / "autocount_changed" (UAC B3).
    status: str
    revision_no: Optional[int] = None
    confirmed_on: Optional[str] = None
    base_qty: str
    base_date: Optional[str] = None
    now_qty: str
    now_date: Optional[str] = None
    total_qty: str
    rows: List[LineSplitViewRowOut] = []


class LineSplitOut(BaseModel):
    id: str
    qty: float
    delivery_date: Optional[date] = None
    is_cancel: bool = False
    #: The line this split sits on; `None` = a new line not in AutoCount yet (also what a
    #: split reads once the line it sat on is cancelled, UAC C2).
    sits_on_line_id: Optional[str] = None
    remark: str = ""
    #: The REMARK the email and the Excel print for this split while `remark` is empty
    #: (`remark_for_row`, UAC AC-G5).
    remark_generated: str = ""


class LineSplitLineOut(BaseModel):
    line_id: str
    line_no: Optional[int] = None
    item_code: str = ""
    location: str = ""
    base_qty: float
    base_date: Optional[date] = None
    now_qty: float
    now_date: Optional[date] = None
    #: What AutoCount moved the line to, as the handover email reads it: set only when it
    #: differs from the base (`handover_moves`), else null = blank.
    new_qty: Optional[float] = None
    new_date: Optional[date] = None
    #: The line carries a pending AutoCount change (it is inside Confirm).
    pending_change: bool = False
    #: The saved splits still act on Confirm: false once AutoCount moved on from the base
    #: they were made against (the view then warns "AutoCount changed").
    acting: bool = True
    #: `acting` / `applied` / `stale` (`LineFacts.split_state`): only a stale line warns
    #: "AutoCount changed" and reads its current base.
    split_state: str = "acting"
    delivered_qty: float = 0
    #: AutoCount delivered the whole line (nothing open, no splits, nothing sitting on it):
    #: listed read-only, never split and never a sits-on target (UAC A3).
    delivered_in_full: bool = False
    #: AutoCount qty less the splits sitting on the line (UAC AC-G3), when positive: one
    #: more row under the line, never stored. `None` = no extra.
    extra_qty: Optional[float] = None
    extra_remark: Optional[str] = None
    #: The REMARK the email prints for the line's own row (`remark_for_row`, AC-G9).
    remark_generated: str = ""
    splits: List[LineSplitOut] = []
    #: OI-SPLIT-VIEW (UAC D1): the line's split popup, the same value the SO and OI reads
    #: carry; null on a line with no splits.
    split_view: Optional[LineSplitViewOut] = None


class LineSplitsOut(BaseModel):
    pso_id: str
    so_number: Optional[str] = None
    #: The AutoCount SO document date (the sheet's SO DATE column); `None` when unknown.
    so_date: Optional[date] = None
    customer: Optional[str] = None
    project: Optional[str] = None
    #: The last Confirm's date while no AutoCount change is pending (UAC AC-G1); `None`
    #: while one is pending or when the order was never confirmed.
    confirmed_at: Optional[date] = None
    lines: List[LineSplitLineOut] = []


#: Caps on one save (review round 1): a malformed or oversized body is a 422, never a 500.
MAX_SPLITS_PER_LINE = 50
MAX_LINES_PER_SAVE = 500
MAX_REMARK_LENGTH = 500


class LineSplitIn(BaseModel):
    # The column's own precision. "Above 0" is checked by the service, so its 422 names the
    # line (UAC B3).
    qty: condecimal(max_digits=15, decimal_places=4)  # type: ignore[valid-type]
    delivery_date: Optional[date] = None
    is_cancel: bool = False
    sits_on_line_id: Optional[str] = None
    remark: Optional[str] = Field(default=None, max_length=MAX_REMARK_LENGTH)


class LineSplitLineIn(BaseModel):
    line_id: str
    splits: List[LineSplitIn] = Field(default_factory=list, max_length=MAX_SPLITS_PER_LINE)


class LineSplitsBody(BaseModel):
    lines: List[LineSplitLineIn] = Field(default_factory=list, max_length=MAX_LINES_PER_SAVE)
