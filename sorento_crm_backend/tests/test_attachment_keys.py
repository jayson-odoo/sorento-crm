"""Tests for uuid-segregated attachment keys + the relocate migration (storage mocked).

See PLAN-attachment-key-uuid-segregation.md. Covers the new-key derivation and the
copy-only / idempotent migration classifier. The upload-path key shape is exercised
end-to-end against staging in the browser flow.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

from app.models.resources import Attachment
from app.services import storage_router
from app.services.storage_router import cdn_base_url

# Load the migration script as a module (it lives under scripts/, not a package).
_MIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "scripts", "migrate_attachment_keys_to_uuid.py")
_spec = importlib.util.spec_from_file_location("mig_keys", _MIG_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


class FakeBackend:
    def __init__(self, existing=None):
        self.existing = set((k or "").lstrip("/") for k in (existing or []))
        self.copied = []

    def file_exists(self, key):
        return (key or "").lstrip("/") in self.existing

    def copy_file(self, old, new):
        self.copied.append((old.lstrip("/"), new.lstrip("/")))
        self.existing.add(new.lstrip("/"))

    def get_cdn_base_url(self, key):
        return f"https://cdn.test/{key.lstrip('/')}"


# --------------------------------------------------------------- _new_key_for

def test_new_key_injects_uuid_for_flat():
    assert mig._new_key_for("direct_access/x.pdf", "ID") == "direct_access/ID/x.pdf"
    assert mig._new_key_for("product_photos/A B.jpg", "ID") == "product_photos/ID/A B.jpg"


def test_new_key_skips_already_scoped():
    assert mig._new_key_for("product_photos/ID/x.jpg", "OTHER") is None   # already uuid-scoped
    assert mig._new_key_for("promotion/entity-1/x.pdf", "ID") is None     # promotion scoped
    assert mig._new_key_for("portal/contact/uuid.bin", "ID") is None      # portal
    assert mig._new_key_for("nofolder", "ID") is None                     # no prefix


# --------------------------------------------------------------- _migrate_one

def _att(provider="r2", key="direct_access/x.pdf"):
    a = Attachment(original_filename="x.pdf", stored_filename="x.pdf",
                   file_path=f"https://cdn-sorento.com/{key}", storage_provider=provider)
    a.id = "11111111-2222-3333-4444-555555555555"
    return a


def _patch(monkeypatch, be):
    # _migrate_one resolves get_backend from the migration module's namespace; cdn_base_url
    # (also imported there) reaches back into storage_router.get_backend. Patch both.
    monkeypatch.setattr(storage_router, "get_backend", lambda provider: be)
    monkeypatch.setattr(mig, "get_backend", lambda provider: be)


def test_migrate_dry_run_no_write(monkeypatch):
    be = FakeBackend(existing=["direct_access/x.pdf"])
    _patch(monkeypatch, be)
    a = _att()
    before = a.file_path
    assert mig._migrate_one(a, apply=False, counts={}) == "WOULD_MIGRATE"
    assert a.file_path == before and be.copied == []


def test_migrate_apply_copies_and_repoints_keeping_old(monkeypatch):
    be = FakeBackend(existing=["direct_access/x.pdf"])
    _patch(monkeypatch, be)
    a = _att()
    assert mig._migrate_one(a, apply=True, counts={}) == "MIGRATED"
    new_key = f"direct_access/{a.id}/x.pdf"
    assert be.copied == [("direct_access/x.pdf", new_key)]
    assert a.file_path == f"https://cdn.test/{new_key}"
    assert be.file_exists("direct_access/x.pdf")   # OLD kept — never deleted


def test_migrate_source_missing(monkeypatch):
    be = FakeBackend(existing=[])  # neither old nor new present
    _patch(monkeypatch, be)
    a = _att()
    assert mig._migrate_one(a, apply=True, counts={}) == "SOURCE_MISSING"
    assert be.copied == []


def test_migrate_idempotent_skips_already_scoped(monkeypatch):
    be = FakeBackend(existing=[f"direct_access/SOMEID/x.pdf"])
    _patch(monkeypatch, be)
    a = _att(key="direct_access/SOMEID/x.pdf")  # already uuid-scoped (3 segs)
    assert mig._migrate_one(a, apply=True, counts={}) == "SKIP_NOT_FLAT"


def test_migrate_repoints_when_new_exists_but_path_stale(monkeypatch):
    a = _att()
    new_key = f"direct_access/{a.id}/x.pdf"
    be = FakeBackend(existing=["direct_access/x.pdf", new_key])  # new already copied in a prior run
    _patch(monkeypatch, be)
    status = mig._migrate_one(a, apply=True, counts={})
    assert status == "REPOINTED"
    assert a.file_path == f"https://cdn.test/{new_key}"
    assert be.copied == []  # no re-copy
