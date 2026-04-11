"""Generic filter compiler orchestrator (resource logic lives in adapters)."""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import ColumnElement

from app.schemas.list_query import FilterGroup
from app.services.list_query_registry import require_adapter
from app.services.query.filter_compiler_adapters import RESOURCE_COMPILERS


def compile_filter(
    resource: str,
    root: FilterGroup,
    field_by_key: Dict[str, Any],
) -> ColumnElement:
    require_adapter(resource)
    compiler = RESOURCE_COMPILERS.get(resource)
    if not compiler:
        raise ValueError(f"unsupported resource: {resource}")
    return compiler(root, field_by_key)


def compile_optional_filter(
    resource: str,
    root: FilterGroup | None,
    field_by_key: Dict[str, Any],
) -> ColumnElement | None:
    if root is None:
        return None
    return compile_filter(resource, root, field_by_key)
