"""Sync list-query metadata from SQLAlchemy model definitions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional
import uuid

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text
from sqlalchemy.orm import Session

from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.services.list_query_registry import ADAPTERS, ListQueryResourceAdapter


def _is_uuid_type(col: Any) -> bool:
    return col.type.__class__.__name__.lower() == "uuid"


def _infer_data_type(col: Any) -> str:
    t = col.type
    if isinstance(t, (Integer, Float, Numeric)):
        return "number"
    if isinstance(t, Boolean):
        return "boolean"
    if isinstance(t, (Date, DateTime)):
        return "date"
    if _is_uuid_type(col):
        return "uuid"
    if isinstance(t, (String, Text)):
        return "string"
    return "string"


def _default_ops(data_type: str) -> list[str]:
    if data_type == "number":
        return ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]
    if data_type == "boolean":
        return ["eq", "is_null"]
    if data_type == "date":
        return ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"]
    if data_type == "uuid":
        return ["eq", "ne", "in", "is_null"]
    return ["eq", "ne", "contains", "starts_with", "in", "is_null"]


def _is_ignored_column(col_name: str) -> bool:
    return col_name in {"deleted_at", "updated_by", "deleted_by", "metadata_"}


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


@dataclass
class SyncResult:
    resources_created: int = 0
    resources_updated: int = 0
    fields_created: int = 0
    fields_updated: int = 0


class ListQueryMetadataSyncService:
    def __init__(self, db: Session):
        self.db = db

    def sync_all(self) -> SyncResult:
        out = SyncResult()
        for adapter in ADAPTERS.values():
            if not adapter.model or not adapter.compile_prefix:
                continue
            partial = self.sync_resource(adapter)
            out.resources_created += partial.resources_created
            out.resources_updated += partial.resources_updated
            out.fields_created += partial.fields_created
            out.fields_updated += partial.fields_updated
        return out

    def sync_resource(self, adapter: ListQueryResourceAdapter) -> SyncResult:
        out = SyncResult()
        resource = self._upsert_resource(adapter)
        if resource is None:
            return out
        if getattr(resource, "_created_now", False):
            out.resources_created += 1
        else:
            out.resources_updated += 1

        existing_fields = (
            self.db.query(ListQueryField)
            .filter(ListQueryField.resource_id == resource.id)
            .all()
        )
        by_key = {f.field_key: f for f in existing_fields}

        for idx, col in enumerate(adapter.model.__table__.columns, start=1):
            col_name = str(col.name)
            if _is_ignored_column(col_name):
                continue
            field_key = col_name
            dtype = _infer_data_type(col)
            compile_key = f"{adapter.compile_prefix}.{col_name}"
            payload = {
                "label": _humanize(col_name),
                "data_type": dtype,
                "compile_key": compile_key,
                "allowed_operators": _default_ops(dtype),
                "filterable": True,
                "exportable": True,
                "export_column_name": field_key,
                "is_line_field": False,
                "sort_order": idx * 10,
            }
            current = by_key.get(field_key)
            if current is None:
                row = ListQueryField(
                    id=str(uuid.uuid4()),
                    resource_id=resource.id,
                    field_key=field_key,
                    **payload,
                )
                self.db.add(row)
                out.fields_created += 1
                continue

            # Only update fields that still follow generated compile-key convention.
            current_ck = str(getattr(current, "compile_key", "") or "")
            if current_ck.startswith(f"{adapter.compile_prefix}."):
                for k, v in payload.items():
                    setattr(current, k, v)
                out.fields_updated += 1

        self.db.flush()
        return out

    def _upsert_resource(self, adapter: ListQueryResourceAdapter) -> Optional[ListQueryResource]:
        row = (
            self.db.query(ListQueryResource)
            .filter(ListQueryResource.resource_key == adapter.resource_key)
            .first()
        )
        if row is None:
            row = ListQueryResource(
                id=str(uuid.uuid4()),
                resource_key=adapter.resource_key,
                display_name=adapter.display_name or adapter.resource_key,
                description=adapter.description,
                is_active=True,
            )
            setattr(row, "_created_now", True)
            self.db.add(row)
            self.db.flush()
            return row

        row.display_name = adapter.display_name or row.display_name
        row.description = adapter.description
        row.is_active = True
        setattr(row, "_created_now", False)
        self.db.flush()
        return row
