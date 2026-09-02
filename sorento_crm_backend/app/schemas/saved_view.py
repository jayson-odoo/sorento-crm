"""Wire shapes for saved views (segments) - S4 of PLAN-scm-reorder-oi-feedback-1sep.md.

`view` is deliberately opaque past its five top-level keys: `filters` is whatever shape
the frontend's `ListQueryFilterGroup` is that day (recursive, and the backend never
evaluates it - the DynamicFilterBuilder does, client-side), and `columns`/`column_order`
are column ids the backend has no catalog of. Typing them further here would just be a
second place for the frontend's own shape to drift from.

`quick_filters` (S4 shortfall, PR #489 review round): a listing's own FIXED dropdown
filters (`PlanLinesGrid`'s status/decided/price/action/level) sit beside the recursive
`filters` builder in the SAME Filters popover and are ANDed into what a reader sees - a
segment that omitted them would not be capturing "the full view" G9 promises. Opaque
string map for the same reason `filters` is: the set of fixed filters is a fact about
ONE listing, declared entirely on the frontend.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# S6 (PR #489 review round): the SAME cap `DynamicFilterBuilder.tsx`'s `addGroup`
# enforces client-side. A published default segment auto-applies for every reader
# (AC-4.4), so an unbounded nesting depth saved through some OTHER path (a future
# API client, a hand-edited row) is not just a slow filter - it is a segment nobody
# can turn off without knowing to reach for "No segment" first.
_MAX_FILTER_DEPTH = 5


def _group_depth(node: Any, depth: int = 1) -> int:
    if not isinstance(node, dict):
        return depth
    children = node.get("children")
    if not isinstance(children, list):
        return depth
    deepest = depth
    for child in children:
        if isinstance(child, dict) and "children" in child:
            deepest = max(deepest, _group_depth(child, depth + 1))
    return deepest


class SavedViewSortEntry(BaseModel):
    id: str
    desc: bool = False


class SavedViewConfig(BaseModel):
    # A `ListQueryFilterGroup` (recursive and/or tree of conditions), or null for "no
    # filter". Opaque here on purpose (see module docstring).
    filters: Optional[Dict[str, Any]] = None
    sort: List[SavedViewSortEntry] = Field(default_factory=list)
    # Visible column ids.
    columns: List[str] = Field(default_factory=list)
    column_order: List[str] = Field(default_factory=list)
    # The listing's own fixed dropdown filters - opaque key/value map, see module doc.
    quick_filters: Optional[Dict[str, str]] = None

    @field_validator("filters")
    @classmethod
    def _cap_filter_depth(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if value is not None and _group_depth(value) > _MAX_FILTER_DEPTH:
            raise ValueError(f"Filters may nest at most {_MAX_FILTER_DEPTH} groups deep")
        return value


class SavedView(BaseModel):
    id: str
    name: str
    is_shared: bool
    is_default: bool
    # Display name of the owner, never the user id (no UUID reaches the UI).
    owner_name: Optional[str] = None
    view: SavedViewConfig


class SavedViews(BaseModel):
    """Mine = the views the caller OWNS, published ones included (badged Shared).
    Shared = OTHER users' published views."""

    mine: List[SavedView]
    shared: List[SavedView]


class SavedViewCreate(BaseModel):
    name: str
    view: SavedViewConfig


class SavedViewPublish(BaseModel):
    is_shared: bool = True
