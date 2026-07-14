"""Import source-file retention — store helper + download endpoint.

Covers docs/plans/imports/import-source-file-retention-acceptance-criteria.md
AC-1 (store), AC-2 (best-effort never blocks), AC-3/AC-5 (download + ownership),
AC-4 (no file → 404).
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.job import ImportJob, JobStatus
import app.services.import_source_store as store_mod
from app.services.import_source_store import store_import_source_file
import app.api.v1.system.jobs as jobs_api


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ImportJob.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


class _RecordingBackend:
    def __init__(self):
        self.calls = []

    def upload_file(self, content, path, content_type=None, **_):
        self.calls.append((content, path, content_type))
        return (path, f"https://cdn.test/{path}")


class _ExplodingBackend:
    def upload_file(self, *_a, **_k):
        raise RuntimeError("bucket unreachable")


# ---------------------------------------------------------------- store helper

def test_store_uploads_and_stamps_job(monkeypatch):
    """AC-1 / AC-7: original bytes uploaded under import-sources/{id}/name, attrs set."""
    backend = _RecordingBackend()
    monkeypatch.setattr(store_mod, "default_provider", lambda: "r2")
    monkeypatch.setattr(store_mod, "get_backend", lambda _p: backend)

    job = SimpleNamespace(
        id=uuid.uuid4(),
        source_file_key=None,
        source_file_provider=None,
        source_file_size=None,
        source_filename=None,
    )
    ok = store_import_source_file(job, b"raw-excel-bytes", "Order Listing.xlsx", "application/vnd.ms-excel")

    assert ok is True
    assert len(backend.calls) == 1
    content, path, ctype = backend.calls[0]
    assert content == b"raw-excel-bytes"
    assert path == f"import-sources/{job.id}/Order Listing.xlsx"
    assert ctype == "application/vnd.ms-excel"
    assert job.source_file_key == path
    assert job.source_file_provider == "r2"
    assert job.source_file_size == len(b"raw-excel-bytes")
    assert job.source_filename == "Order Listing.xlsx"


def test_store_is_best_effort_on_storage_failure(monkeypatch):
    """AC-2: storage failure must not raise; job stays unstamped."""
    monkeypatch.setattr(store_mod, "default_provider", lambda: "r2")
    monkeypatch.setattr(store_mod, "get_backend", lambda _p: _ExplodingBackend())

    job = SimpleNamespace(id=uuid.uuid4(), source_file_key=None, source_file_provider=None,
                          source_file_size=None, source_filename=None)
    ok = store_import_source_file(job, b"bytes", "x.xlsx", None)

    assert ok is False
    assert job.source_file_key is None
    assert job.source_file_provider is None


def test_store_skips_when_no_bytes(monkeypatch):
    monkeypatch.setattr(store_mod, "get_backend", lambda _p: _ExplodingBackend())
    job = SimpleNamespace(id=uuid.uuid4(), source_file_key=None)
    assert store_import_source_file(job, b"", "x.xlsx") is False
    assert store_import_source_file(job, None, "x.xlsx") is False


# ------------------------------------------------------------- download route

def _make_job(db, *, user_id, key=None, provider="r2"):
    job = ImportJob(
        job_id=str(uuid.uuid4()),
        job_type="delivery_order_detail_import",
        status=JobStatus.FINISHED.value,
        user_id=user_id,
        filename="cleaned.xlsx",
        source_file_key=key,
        source_file_provider=provider if key else None,
        source_file_size=123 if key else None,
        source_filename="Original Upload.xlsx" if key else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_download_returns_signed_url_for_owner(db, monkeypatch):
    """AC-3: owner gets a fresh signed URL + original filename."""
    monkeypatch.setattr(jobs_api.JobService, "sync_job_status", lambda self, _jid: None)
    monkeypatch.setattr(
        "app.services.storage_router.resolve_signed_url",
        lambda key, provider=None, expires_in=3600: f"https://signed.test/{key}?sig=abc",
    )
    job = _make_job(db, user_id="user-1", key="import-sources/abc/Original Upload.xlsx")

    res = asyncio.run(
        jobs_api.download_job_source_file(job.job_id, current_user={"id": "user-1"}, db=db)
    )
    assert res["url"].startswith("https://signed.test/")
    assert res["filename"] == "Original Upload.xlsx"
    assert res["size"] == 123


def test_download_404_when_no_source_file(db):
    """AC-4: a job with no retained file returns 404."""
    job = _make_job(db, user_id="user-1", key=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(jobs_api.download_job_source_file(job.job_id, current_user={"id": "user-1"}, db=db))
    assert exc.value.status_code == 404


def test_download_403_for_non_owner(db, monkeypatch):
    """AC-5: a non-owner is denied."""
    monkeypatch.setattr(jobs_api.JobService, "sync_job_status", lambda self, _jid: None)
    job = _make_job(db, user_id="owner", key="import-sources/abc/f.xlsx")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(jobs_api.download_job_source_file(job.job_id, current_user={"id": "intruder"}, db=db))
    assert exc.value.status_code == 403
