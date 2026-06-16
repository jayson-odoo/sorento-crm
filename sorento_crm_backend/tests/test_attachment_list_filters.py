"""Attachment list filter behavior (type, uploaded_by, uploaded_at range)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.audit import AuditLog
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.resources import (
    Attachment,
    AttachmentDirectory,
    AttachmentType,
)
from app.services.resources_service import AttachmentService


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AttachmentDirectory.__table__,
            AttachmentType.__table__,
            Attachment.__table__,
            LookupSet.__table__,
            LookupOption.__table__,
            LookupBinding.__table__,
            AuditLog.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_type(db, type_name: str) -> str:
    att_type = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=type_name,
        allowed_extensions="pdf,jpg",
        max_file_size_mb=10,
    )
    db.add(att_type)
    db.flush()
    return att_type.id


def _seed_attachment(
    db,
    *,
    filename: str,
    type_id: str | None = None,
    uploaded_by: str | None = None,
    uploaded_at: datetime | None = None,
    storage_status: str = "unchecked",
) -> str:
    att = Attachment(
        id=str(uuid.uuid4()),
        attachment_type_id=type_id,
        original_filename=filename,
        stored_filename=filename,
        file_path=f"/tmp/{filename}",
        uploaded_by=uploaded_by,
        uploaded_at=uploaded_at or datetime(2026, 5, 1, 0, 0, 0),
        access_levels=["dealer"],
        storage_status=storage_status,
    )
    db.add(att)
    db.flush()
    return att.id


def test_filter_by_attachment_type_only_returns_matching_rows(db):
    type_a = _seed_type(db, "TypeA")
    type_b = _seed_type(db, "TypeB")
    keep_id = _seed_attachment(db, filename="a.pdf", type_id=type_a)
    _seed_attachment(db, filename="b.pdf", type_id=type_b)
    db.commit()

    result = AttachmentService(db).list_attachments(attachment_type_id=type_a)
    ids = [a.id for a in result["data"]]
    assert ids == [keep_id]


def test_filter_by_uploaded_by(db):
    keep_id = _seed_attachment(db, filename="alice.pdf", uploaded_by="user-alice")
    _seed_attachment(db, filename="bob.pdf", uploaded_by="user-bob")
    db.commit()

    result = AttachmentService(db).list_attachments(uploaded_by="user-alice")
    ids = [a.id for a in result["data"]]
    assert ids == [keep_id]


def test_filter_by_uploaded_at_range(db):
    base = datetime(2026, 5, 10, 0, 0, 0)
    before = _seed_attachment(
        db, filename="old.pdf", uploaded_at=base - timedelta(days=5)
    )
    inside = _seed_attachment(
        db, filename="mid.pdf", uploaded_at=base - timedelta(hours=12)
    )
    after = _seed_attachment(
        db, filename="new.pdf", uploaded_at=base + timedelta(days=2)
    )
    db.commit()

    result = AttachmentService(db).list_attachments(
        uploaded_at_from=base - timedelta(days=1),
        uploaded_at_to=base + timedelta(days=1),
    )
    ids = {a.id for a in result["data"]}
    assert inside in ids
    assert before not in ids
    assert after not in ids


def test_filter_by_storage_status_missing(db):
    missing_id = _seed_attachment(db, filename="gone.jpg", storage_status="missing")
    _seed_attachment(db, filename="ok.jpg", storage_status="accessible")
    _seed_attachment(db, filename="new.jpg", storage_status="unchecked")
    db.commit()

    result = AttachmentService(db).list_attachments(storage_status="missing")
    ids = [a.id for a in result["data"]]
    assert ids == [missing_id]


def test_storage_status_unset_returns_all_states(db):
    a = _seed_attachment(db, filename="gone.jpg", storage_status="missing")
    b = _seed_attachment(db, filename="ok.jpg", storage_status="accessible")
    db.commit()

    result = AttachmentService(db).list_attachments()
    ids = {x.id for x in result["data"]}
    assert {a, b} <= ids
