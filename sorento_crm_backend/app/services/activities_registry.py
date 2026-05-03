"""Per-entity adapters for the generic Activities & Notes panel.

Each consuming module (tickets, leads, complaints, …) registers an
``ActivitiesAdapter`` keyed on its ``entity_type`` string. The activities
service routes permission checks, visibility filters and side-effects
through the matching adapter so the API surface stays generic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session


@dataclass
class ActivitiesAdapter:
    """Hook bundle for one entity_type."""

    entity_type: str
    permission_view: str
    permission_post: str
    get_respond_contacts: Optional[Callable[[Session, str], List[Dict[str, Any]]]] = None
    on_post: Optional[Callable[[Session, str, str, str], None]] = None
    visibility_filter: Optional[Callable[[Session, dict], Any]] = None
    can_view: Optional[Callable[[Session, str, dict], bool]] = None


ACTIVITIES_REGISTRY: Dict[str, ActivitiesAdapter] = {}


def register_activities_adapter(adapter: ActivitiesAdapter) -> None:
    ACTIVITIES_REGISTRY[adapter.entity_type] = adapter


def get_adapter(entity_type: str) -> ActivitiesAdapter:
    a = ACTIVITIES_REGISTRY.get(entity_type)
    if a is None:
        raise KeyError(f"No activities adapter registered for entity_type={entity_type!r}")
    return a


def is_registered(entity_type: str) -> bool:
    return entity_type in ACTIVITIES_REGISTRY
