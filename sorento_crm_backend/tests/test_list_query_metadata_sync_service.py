"""Unit tests for list-query metadata sync service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import String
from sqlalchemy.orm import Session

from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.services.list_query_metadata_sync_service import ListQueryMetadataSyncService
from app.services.list_query_registry import ListQueryResourceAdapter


@dataclass
class _FakeColumn:
    name: str
    type: Any


class _FakeTable:
    def __init__(self, columns: list[_FakeColumn]):
        self.columns = columns


class _FakeModel:
    __table__ = _FakeTable(
        columns=[
            _FakeColumn("id", String()),
            _FakeColumn("name", String()),
            _FakeColumn("created_at", String()),
        ]
    )


class _FakeQuery:
    def __init__(self, rows: list[Any]):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self):
        self.resources: list[ListQueryResource] = []
        self.fields: list[ListQueryField] = []

    def query(self, model):
        if model is ListQueryResource:
            return _FakeQuery(self.resources)
        if model is ListQueryField:
            return _FakeQuery(self.fields)
        raise AssertionError(f"unexpected model query: {model}")

    def add(self, row: Any):
        if isinstance(row, ListQueryResource):
            self.resources.append(row)
        elif isinstance(row, ListQueryField):
            self.fields.append(row)
        else:
            raise AssertionError(f"unexpected row type: {type(row)}")

    def flush(self):
        return None


def test_sync_resource_idempotent_for_generated_fields():
    db = _FakeSession()
    service = ListQueryMetadataSyncService(cast(Session, db))
    adapter = ListQueryResourceAdapter(
        resource_key="fake_items",
        view_slug="x.view",
        export_slug="x.export",
        serializer=lambda rows: list(rows),
        model=_FakeModel,
        compile_prefix="fake",
        display_name="Fake Items",
        description="Test model for metadata sync",
    )

    first = service.sync_resource(adapter)
    second = service.sync_resource(adapter)

    assert first.resources_created == 1
    assert first.fields_created >= 1
    assert second.resources_created == 0
    assert second.fields_created == 0
    assert len(db.fields) == len({f.field_key for f in db.fields})
