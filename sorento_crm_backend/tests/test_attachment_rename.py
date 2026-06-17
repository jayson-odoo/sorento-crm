"""Attachment rename + storage-primitive tests (storage mocked, no real S3/R2).

Rename is DB-only: the object key is uuid-segregated and independent of the
display name (see PLAN-attachment-key-uuid-segregation.md), so renaming must NOT
touch storage. The copy/verify/delete primitives still exist — the key-relocation
migration uses them — so they keep their own tests here.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.resources import Attachment
from app.schemas.resources import AttachmentUpdate
from app.services.error_handler import AppException
from app.services import storage_router
from app.services import resources_service
from app.services.storage_router import (
    copy_object_verified,
    delete_object_best_effort,
    sanitize_storage_filename,
)


class FakeBackend:
    """In-memory stand-in for S3Service/R2Service. ``copy_verifies`` toggles whether
    a copy actually lands (False simulates a silent copy that can't be verified)."""

    def __init__(self, existing=None, copy_verifies=True):
        self.existing = set((k or "").lstrip("/") for k in (existing or []))
        self.copy_verifies = copy_verifies
        self.copied: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def file_exists(self, key: str) -> bool:
        return (key or "").lstrip("/") in self.existing

    def copy_file(self, old_key: str, new_key: str) -> None:
        self.copied.append((old_key.lstrip("/"), new_key.lstrip("/")))
        if self.copy_verifies:
            self.existing.add(new_key.lstrip("/"))

    def delete_file(self, key: str) -> bool:
        self.deleted.append(key.lstrip("/"))
        self.existing.discard(key.lstrip("/"))
        return True

    def get_cdn_base_url(self, key: str) -> str:
        return f"https://cdn.test/{key.lstrip('/')}"


# --------------------------------------------------------------- copy_object_verified

def _patch_backend(monkeypatch, backend):
    monkeypatch.setattr(storage_router, "get_backend", lambda provider: backend)


def test_copy_object_verified_happy(monkeypatch):
    be = FakeBackend(existing=["resource/old.pdf"])
    _patch_backend(monkeypatch, be)
    copy_object_verified("r2", "resource/old.pdf", "resource/new.pdf")
    assert be.copied == [("resource/old.pdf", "resource/new.pdf")]
    # never deletes the old object — caller does that after commit
    assert be.deleted == []


def test_copy_object_verified_collision_409(monkeypatch):
    be = FakeBackend(existing=["resource/old.pdf", "resource/new.pdf"])
    _patch_backend(monkeypatch, be)
    with pytest.raises(AppException) as ei:
        copy_object_verified("r2", "resource/old.pdf", "resource/new.pdf")
    assert ei.value.status_code == 409
    assert be.copied == []  # never clobbered


def test_copy_object_verified_unverified_500(monkeypatch):
    be = FakeBackend(existing=["resource/old.pdf"], copy_verifies=False)
    _patch_backend(monkeypatch, be)
    with pytest.raises(AppException) as ei:
        copy_object_verified("r2", "resource/old.pdf", "resource/new.pdf")
    assert ei.value.status_code == 500


def test_copy_object_verified_noop_same_key(monkeypatch):
    be = FakeBackend(existing=["resource/old.pdf"])
    _patch_backend(monkeypatch, be)
    copy_object_verified("r2", "resource/old.pdf", "resource/old.pdf")
    assert be.copied == [] and be.deleted == []


def test_delete_object_best_effort_swallows(monkeypatch):
    be = FakeBackend()
    be.delete_file = MagicMock(side_effect=Exception("boom"))
    _patch_backend(monkeypatch, be)
    # must not raise
    delete_object_best_effort("r2", "resource/old.pdf")


def test_sanitizer_matches_upload_rules():
    assert sanitize_storage_filename("My File (v2)!.pdf") == "My File v2.pdf"
    assert sanitize_storage_filename("***") == "file"
    assert sanitize_storage_filename("  spaced  .txt ") == "spaced  .txt"


# ------------------------------------------------------------------ update_attachment

def _make_service(monkeypatch, attachment, backend, *, collision_row=None):
    """Build an AttachmentService whose DB + storage are fully mocked."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = collision_row
    svc = resources_service.AttachmentService(db)
    monkeypatch.setattr(svc, "get_attachment", lambda _id: attachment)
    _patch_backend(monkeypatch, backend)
    monkeypatch.setattr(resources_service, "publish_embedding_event", lambda *a, **k: None)
    return svc


def _attachment(**over):
    a = Attachment(
        original_filename="old.pdf",
        stored_filename="old.pdf",
        file_path="https://cdn-sorento.com/resource/old.pdf",
        storage_provider="r2",
    )
    a.id = "att-1"
    from datetime import datetime
    a.created_at = datetime.utcnow()
    for k, v in over.items():
        setattr(a, k, v)
    return a


def test_update_rename_is_db_only(monkeypatch):
    """Rename edits stored_filename (user-facing) only. original_filename + the uuid key are
    immutable. Object never moves — no copy, no delete, file_path untouched."""
    att = _attachment()
    be = FakeBackend(existing=["resource/old.pdf"])
    svc = _make_service(monkeypatch, att, be)
    original_path = att.file_path

    svc.update_attachment("att-1", AttachmentUpdate(stored_filename="new name.pdf"))

    assert be.copied == [] and be.deleted == []      # storage untouched
    assert att.file_path == original_path             # uuid key unchanged
    assert att.original_filename == "old.pdf"         # immutable
    assert att.stored_filename == "new name.pdf"      # the editable label changed


def test_update_non_rename_field_skips_storage(monkeypatch):
    att = _attachment()
    be = FakeBackend(existing=["resource/old.pdf"])
    svc = _make_service(monkeypatch, att, be)

    svc.update_attachment("att-1", AttachmentUpdate(description="hello"))

    assert be.copied == [] and be.deleted == []
    assert att.description == "hello"
    assert att.stored_filename == "old.pdf"
