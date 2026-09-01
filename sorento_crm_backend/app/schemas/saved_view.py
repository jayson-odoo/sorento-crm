"""Wire shapes for saved views (segments) - S4 of PLAN-scm-reorder-oi-feedback-1sep.md.

`view` is deliberately opaque past its four top-level keys: `filters` is whatever shape
the frontend's `ListQueryFilterGroup` is that day (recursive, and the backend never
evaluates it - the DynamicFilterBuilder does, client-side), and `columns`/`column_order`
are column ids the backend has no catalog of. Typing them further here would just be a
second place for the frontend's own shape to drift from.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
