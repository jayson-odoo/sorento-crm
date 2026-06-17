"""attachment_storage_audit handler: flags accessible vs missing per provider."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
import app.services.attachment_storage_audit_service as audit


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
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed(db, *, key: str, provider: str = "r2", is_deleted: bool = False) -> str:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=key.split("/")[-1],
        stored_filename=key.split("/")[-1],
        file_path=f"https://cdn-sorento.com/{key}",
        storage_provider=provider,
        access_levels=["dealer"],
        is_deleted=is_deleted,
    )
    db.add(att)
    db.flush()
    return att.id


def _patch_backends(monkeypatch, present_keys_by_provider: dict[str, set[str]]):
    """Make get_backend('r2'/'s3') return a fake whose bucket lists the given keys."""
    class _FakePaginator:
        def __init__(self, keys):
            self._keys = keys

        def paginate(self, Bucket=None):
            yield {"Contents": [{"Key": k} for k in self._keys]}

    class _FakeClient:
        def __init__(self, keys):
            self._keys = keys

        def get_paginator(self, _name):
            return _FakePaginator(self._keys)

    class _FakeBackend:
        def __init__(self, keys):
            self.client = _FakeClient(keys)
            self.bucket_name = "fake-bucket"

    def fake_get_backend(provider):
        keys = present_keys_by_provider.get(provider, set())
        return _FakeBackend(keys)

    monkeypatch.setattr(audit, "get_backend", fake_get_backend)


def test_audit_marks_accessible_and_missing(db, monkeypatch):
    ok = _seed(db, key="product_photos/HERE.jpg")
    gone = _seed(db, key="product_photos/GONE.jpg")
    db.commit()

    _patch_backends(monkeypatch, {"r2": {"product_photos/HERE.jpg"}})
    summary = audit.run_attachment_storage_audit(db)

    db.expire_all()
    assert db.get(Attachment, ok).storage_status == "accessible"
    assert db.get(Attachment, gone).storage_status == "missing"
    assert db.get(Attachment, ok).storage_checked_at is not None
    assert summary["scanned"] == 2
    assert summary["accessible"] == 1
    assert summary["missing"] == 1


def test_audit_skips_deleted_rows(db, monkeypatch):
    trashed = _seed(db, key="product_photos/TRASH.jpg", is_deleted=True)
    db.commit()

    _patch_backends(monkeypatch, {"r2": set()})
    summary = audit.run_attachment_storage_audit(db)

    db.expire_all()
    # untouched: deleted rows are not audited
    assert db.get(Attachment, trashed).storage_status == "unchecked"
    assert summary["scanned"] == 0


def test_audit_leaves_status_when_provider_list_fails(db, monkeypatch):
    a = _seed(db, key="product_photos/X.jpg", provider="r2")
    db.commit()

    def boom(_provider):
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(audit, "get_backend", boom)
    summary = audit.run_attachment_storage_audit(db)

    db.expire_all()
    assert db.get(Attachment, a).storage_status == "unchecked"  # not overwritten
    assert "r2" in summary["providers_failed"]
