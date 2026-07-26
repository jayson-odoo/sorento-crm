"""Status engine schemas (ADR-0001)."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StatusEntityResponse(BaseModel):
    """One engine-managed entity, as offered to the graph admin."""

    entity_type: str
    label: str
    module: str
    supports_scoped_graphs: bool
    scope_label: str = ""
    required_flags: List[str] = Field(default_factory=list)


class StatusBase(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    # Cosmetic only. Behaviour branches on the trait flags, never on this.
    category: Optional[str] = Field(default=None, max_length=64)
    color_hex: Optional[str] = Field(default=None, max_length=7)
    description: Optional[str] = None
    sort_order: int = 0
    is_initial: bool = False
    is_terminal: bool = False
    is_active: bool = True
    is_archived: bool = False
    is_default: bool = False
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class StatusCreate(StatusBase):
    entity_type: str = Field(min_length=1, max_length=64)
    # NULL = the entity's default graph.
    scope_id: Optional[str] = None


class StatusUpdate(BaseModel):
    """Only provided fields are applied. ``key`` is immutable on system rows."""

    key: Optional[str] = Field(default=None, min_length=1, max_length=64)
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, max_length=64)
    color_hex: Optional[str] = Field(default=None, max_length=7)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_initial: Optional[bool] = None
    is_terminal: Optional[bool] = None
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None
    is_default: Optional[bool] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class StatusResponse(StatusBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    scope_id: Optional[str] = None
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # How many live records hold this status. Drives the delete guard in the UI so
    # the user learns why before clicking rather than after.
    record_count: Optional[int] = None


class StatusTransitionBase(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    sort_order: int = 0
    trigger_mode: str = "manual"
    conditions_json: Optional[Dict[str, Any]] = None


class StatusTransitionCreate(StatusTransitionBase):
    entity_type: str = Field(min_length=1, max_length=64)
    from_status_id: str
    to_status_id: str


class StatusTransitionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    sort_order: Optional[int] = None
    trigger_mode: Optional[str] = None
    conditions_json: Optional[Dict[str, Any]] = None


class StatusTransitionResponse(StatusTransitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    scope_id: Optional[str] = None
    from_status_id: str
    to_status_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StatusGraphResponse(BaseModel):
    """A resolved graph.

    ``resolved_scope_id`` and ``is_fork`` are not decoration: an admin editing a
    template's graph must be able to tell whether they are looking at that
    template's own fork or at the inherited default, because editing the default
    changes every template that inherits it.
    """

    entity_type: str
    requested_scope_id: Optional[str] = None
    resolved_scope_id: Optional[str] = None
    is_fork: bool
    statuses: List[StatusResponse]
    transitions: List[StatusTransitionResponse]


class StatusMigrateRequest(BaseModel):
    to_status_id: str


class StatusMigrateResponse(BaseModel):
    migrated: int
    from_status_id: str
    to_status_id: str
