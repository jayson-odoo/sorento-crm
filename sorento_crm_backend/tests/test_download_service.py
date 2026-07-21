"""Tests for DownloadService source-scoped queries (print-count + per-entity list).

Runs against a blank copy of the real Postgres schema, so UserDownload's actual
column types and defaults are the ones under test.
"""
from datetime import datetime, timedelta

import pytest

from app.models.download import DownloadStatus
from app.services.download_service import DownloadService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _mk(svc, **kw):
    row = svc.create(kind="complaint_pdf", **kw)
    return row


def test_count_map_scoped_to_user_and_entity(db):
    svc = DownloadService(db)
    # user u1: 2 for complaint c1, 1 for c2
    _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c1")
    _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c1")
    _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c2")
    # other user u2: must NOT leak into u1's counts
    _mk(svc, user_id="u2", source_entity_type="complaint", source_entity_id="c1")
    # different entity type with same id: must NOT match
    _mk(svc, user_id="u1", source_entity_type="stock_inquiry", source_entity_id="c1")

    counts = svc.count_map_for_user("u1", "complaint", ["c1", "c2", "c3"])
    assert counts == {"c1": 2, "c2": 1}  # c3 absent (zero), u2/stock_inquiry excluded


def test_count_map_empty_inputs(db):
    svc = DownloadService(db)
    assert svc.count_map_for_user("u1", "complaint", []) == {}
    assert svc.count_map_for_user(None, "complaint", ["c1"]) == {}


def test_list_for_user_by_source_filters_and_orders_newest_first(db):
    svc = DownloadService(db)
    base = datetime(2026, 6, 1, 8, 0, 0)
    a = _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c1")
    b = _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c1")
    # noise: other user + other entity
    _mk(svc, user_id="u2", source_entity_type="complaint", source_entity_id="c1")
    _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c2")
    # Rows created in the same statement batch share a now(); set distinct
    # created_at explicitly so the ordering assertion is deterministic.
    a.created_at = base
    b.created_at = base + timedelta(minutes=5)
    db.commit()

    rows = svc.list_for_user_by_source("u1", "complaint", "c1")
    assert [r.id for r in rows] == [b.id, a.id]  # newest first


def test_count_map_reflects_marked_states(db):
    """All states count — print count = times generated, not times ready."""
    svc = DownloadService(db)
    r1 = _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c1")
    r2 = _mk(svc, user_id="u1", source_entity_type="complaint", source_entity_id="c1")
    svc.mark_ready(r1.id, storage_provider="s3", storage_key="k", filename="f.pdf")
    svc.mark_failed(r2.id, "boom")
    assert svc.count_map_for_user("u1", "complaint", ["c1"]) == {"c1": 2}
    assert r1.status == DownloadStatus.READY.value
