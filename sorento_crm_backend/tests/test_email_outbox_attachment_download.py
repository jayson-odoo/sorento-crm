"""OUTBOX-ATTACHMENT - an outbox row's attachments can be listed and downloaded.

The Email Outbox detail dialog lists every file the email sends (the row's own column
attachment, then each `metadata_json["extra_attachments"]` entry, in the drainer's order) and
downloads one by its POSITION in that list. There is no storage-key parameter: only a key the
row itself carries can ever be served.

Plan: documentation/plans/_archive/email/PLAN-outbox-attachment-26oct.md
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.services.storage_router as storage_router
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.email_outbox import EmailOutbox
from app.services.user_service import UserPermissionService

BASE = "/api/v1/system/email-outbox"


def _row(**overrides) -> EmailOutbox:
    now = datetime(2026, 10, 26, 10, 0, 0)
    fields = dict(
        id="11111111-1111-1111-1111-111111111111",
        event_key="order_inquiry_handover",
        recipient_email="person1@example.com",
        subject="Order inquiry handover",
        body_text="Body",
        priority=10,
        status="sent",
        scheduled_for=now,
        attempt_count=1,
        max_attempts=5,
        created_at=now,
        updated_at=now,
        metadata_json=None,
    )
    fields.update(overrides)
    return EmailOutbox(**fields)


def _handover_row() -> EmailOutbox:
    return _row(
        attachment_filename="PO-0001.pdf",
        attachment_storage_provider="s3",
        attachment_storage_key="exports/po/PO-0001.pdf",
        metadata_json={
            "extra_attachments": [
                "not-a-dict",
                {"filename": "no-key.xlsx"},
                {
                    "filename": "OI-2609-0042.xlsx",
                    "storage_provider": "r2",
                    "storage_key": "exports/order-inquiry/handover/abc/OI-2609-0042.xlsx",
                    "optional": True,
                },
                {
                    "storage_provider": "r2",
                    "storage_key": "uploads/lines/photo-7.png",
                },
            ]
        },
    )


class _Backend:
    def __init__(self, blobs=None, error=None):
        self.blobs = blobs or {}
        self.error = error
        self.asked = []

    def download_file(self, key):
        self.asked.append(key)
        if self.error is not None:
            raise self.error
        return self.blobs[key]


@pytest.fixture
def setup(monkeypatch):
    state = {"row": _handover_row(), "allowed": True, "slugs": []}
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = lambda: state["row"]

    def _db():
        yield db

    user = {"id": "admin"}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user

    def _has(self, uid, slug):
        state["slugs"].append(slug)
        return state["allowed"]

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _has)

    backend = _Backend(
        blobs={
            "exports/po/PO-0001.pdf": b"%PDF-po",
            "exports/order-inquiry/handover/abc/OI-2609-0042.xlsx": b"PK-xlsx",
            "uploads/lines/photo-7.png": b"png-bytes",
        }
    )
    providers = []

    def _get_backend(provider):
        providers.append(provider)
        return backend

    monkeypatch.setattr(storage_router, "get_backend", _get_backend)
    state.update(client=TestClient(app), backend=backend, providers=providers)
    yield state
    app.dependency_overrides.clear()


def test_detail_lists_every_attachment_in_send_order(setup):
    r = setup["client"].get(f"{BASE}/{setup['row'].id}")
    assert r.status_code == 200, r.text
    assert r.json()["attachments"] == [
        {"index": 0, "filename": "PO-0001.pdf"},
        {"index": 1, "filename": "OI-2609-0042.xlsx"},
        {"index": 2, "filename": "photo-7.png"},
    ]
    assert setup["backend"].asked == [], "listing must not read storage"


def test_detail_row_without_files_lists_none(setup):
    setup["row"] = _row()
    r = setup["client"].get(f"{BASE}/{setup['row'].id}")
    assert r.status_code == 200, r.text
    assert r.json()["attachments"] == []


def test_download_extra_attachment_serves_the_rows_own_key(setup):
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/1")
    assert r.status_code == 200, r.text
    assert r.content == b"PK-xlsx"
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert 'filename="OI-2609-0042.xlsx"' in r.headers["content-disposition"]
    assert setup["backend"].asked == ["exports/order-inquiry/handover/abc/OI-2609-0042.xlsx"]
    assert setup["providers"] == ["r2"]


def test_download_column_attachment_is_index_zero(setup):
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/0")
    assert r.status_code == 200, r.text
    assert r.content == b"%PDF-po"
    assert r.headers["content-type"].startswith("application/pdf")
    assert setup["backend"].asked == ["exports/po/PO-0001.pdf"]
    assert setup["providers"] == ["s3"]


def test_download_index_out_of_range_is_404_without_touching_storage(setup):
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/3")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Attachment not found"
    assert setup["backend"].asked == []


def test_download_unknown_row_is_404(setup):
    setup["row"] = None
    r = setup["client"].get(f"{BASE}/22222222-2222-2222-2222-222222222222/attachments/0")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Outbox row not found"
    assert setup["backend"].asked == []


def test_download_missing_object_is_a_clear_404(setup):
    setup["backend"].error = Exception("File not found in R2: exports/x.xlsx")
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/1")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Attachment file not found in storage"


def test_download_other_storage_failure_is_not_a_404(setup):
    setup["backend"].error = Exception("Failed to connect to R2: timeout")
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/1")
    assert r.status_code == 502, r.text


def test_download_needs_email_outbox_view(setup):
    setup["allowed"] = False
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/1")
    assert r.status_code == 403, r.text
    assert "system.email_outbox.view" in setup["slugs"]
    assert setup["backend"].asked == []


def test_malformed_extra_attachments_do_not_break_the_row(setup):
    # A non-string key or filename is shown as text. Neither may 500 the list or the detail.
    setup["row"] = _row(
        metadata_json={
            "extra_attachments": [
                {"storage_key": 12345, "storage_provider": "r2"},
                {"filename": 7, "storage_provider": "r2", "storage_key": "uploads/lines/photo-7.png"},
            ]
        }
    )
    r = setup["client"].get(f"{BASE}/{setup['row'].id}")
    assert r.status_code == 200, r.text
    assert r.json()["attachments"] == [
        {"index": 0, "filename": "12345"},
        {"index": 1, "filename": "7"},
    ]


def test_drainer_still_fails_the_send_for_a_malformed_required_extra(monkeypatch):
    # The drainer's rule: an email that silently arrives without its document is worse than
    # one that retries. Listing the row for the outbox screen must not change that.
    import app.tasks.email_outbox_tasks as tasks

    asked = []

    class Backend:
        def download_file(self, key):
            asked.append(key)
            raise Exception("bad key")

    monkeypatch.setattr(storage_router, "get_backend", lambda provider: Backend())
    row = _row(metadata_json={"extra_attachments": [{"storage_key": 12345, "storage_provider": "r2"}]})
    with pytest.raises(Exception):
        tasks._attachments_for(row)
    assert asked == [12345]


def test_download_is_never_sniffed_as_another_type(setup):
    r = setup["client"].get(f"{BASE}/{setup['row'].id}/attachments/1")
    assert r.status_code == 200, r.text
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment;")
