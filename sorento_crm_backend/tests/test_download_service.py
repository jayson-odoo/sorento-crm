"""Tests for DownloadService source-scoped queries (print-count + per-entity list).

UserDownload has no JSONB / FK / lookup-bound columns, so an isolated sqlite
in-memory table is enough — no listener tables required.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.download import DownloadStatus, UserDownload
from app.services.download_service import DownloadService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[UserDownload.__table__])
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _mk(svc, **kw):
    row = svc.create(kind="complaint_pdf", **kw)
    return row


def test_count_map_scoped_to_user_and_entity(db):
    svc = DownloadService(db)
    # user u1: 2 for complaint c1, 1 for c2
    _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="e03881a9-2c26-59d7-be11-e6eb5aed6f56")
    # other user u2: must NOT leak into u1's counts
    _mk(svc, user_id="ebdb3d1e-acb7-529d-a515-1c38f77c73fa", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    # different entity type with same id: must NOT match
    _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="stock_inquiry", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")

    counts = svc.count_map_for_user("82dce68d-596c-5265-9263-07b67db11d44", "complaint", ["a464017f-adb4-5685-b832-9c6e852318d4", "e03881a9-2c26-59d7-be11-e6eb5aed6f56", "c3"])
    assert counts == {"a464017f-adb4-5685-b832-9c6e852318d4": 2, "e03881a9-2c26-59d7-be11-e6eb5aed6f56": 1}  # c3 absent (zero), u2/stock_inquiry excluded


def test_count_map_empty_inputs(db):
    svc = DownloadService(db)
    assert svc.count_map_for_user("82dce68d-596c-5265-9263-07b67db11d44", "complaint", []) == {}
    assert svc.count_map_for_user(None, "complaint", ["a464017f-adb4-5685-b832-9c6e852318d4"]) == {}


def test_list_for_user_by_source_filters_and_orders_newest_first(db):
    svc = DownloadService(db)
    base = datetime(2026, 6, 1, 8, 0, 0)
    a = _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    b = _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    # noise: other user + other entity
    _mk(svc, user_id="ebdb3d1e-acb7-529d-a515-1c38f77c73fa", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="e03881a9-2c26-59d7-be11-e6eb5aed6f56")
    # sqlite func.now() has 1s resolution -> set distinct created_at explicitly.
    a.created_at = base
    b.created_at = base + timedelta(minutes=5)
    db.commit()

    rows = svc.list_for_user_by_source("82dce68d-596c-5265-9263-07b67db11d44", "complaint", "a464017f-adb4-5685-b832-9c6e852318d4")
    assert [r.id for r in rows] == [b.id, a.id]  # newest first


def test_count_map_reflects_marked_states(db):
    """All states count — print count = times generated, not times ready."""
    svc = DownloadService(db)
    r1 = _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    r2 = _mk(svc, user_id="82dce68d-596c-5265-9263-07b67db11d44", source_entity_type="complaint", source_entity_id="a464017f-adb4-5685-b832-9c6e852318d4")
    svc.mark_ready(r1.id, storage_provider="s3", storage_key="k", filename="f.pdf")
    svc.mark_failed(r2.id, "boom")
    assert svc.count_map_for_user("82dce68d-596c-5265-9263-07b67db11d44", "complaint", ["a464017f-adb4-5685-b832-9c6e852318d4"]) == {"a464017f-adb4-5685-b832-9c6e852318d4": 2}
    assert r1.status == DownloadStatus.READY.value
