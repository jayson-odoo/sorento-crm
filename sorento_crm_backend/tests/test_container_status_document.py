"""Publishing the imported workbook, and keeping exactly one of them.

The sheet is re-uploaded whole on every import, so an older copy is not history -
it is a stale answer wearing the current one's name. Six of them accumulated in
the library, all called "Container Status 2026.xlsx", and nothing downstream
(entity resolution, the MCP document tool, the file list) had any way to choose
between them.

So the invariant is: one live Container Status attachment, and it is the newest.
The tests that matter are the ones about which row survives a re-run, because
naming the WRONG survivor is worse than having six - it answers confidently with
last month's dates.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.services.container_status_document import (
    TYPE_NAME,
    ensure_attachment_type,
    enforce_single_current,
    latest_document,
    publish_import_source,
)
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _workbook(db, *, uploaded_at: datetime, key: str | None = None) -> str:
    """A live Container Status attachment stamped at a given moment."""
    type_id = ensure_attachment_type(db)
    att_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO attachments (
                id, attachment_type_id, original_filename, stored_filename,
                file_path, mime_type, uploaded_at, is_deleted
            ) VALUES (:id, :t, :n, :n, :k, :m, :u, false)
            """
        ),
        {
            "id": att_id,
            "t": type_id,
            "n": "Container Status 2026.xlsx",
            "k": key or f"import-sources/{unique_code('key')}/Container Status 2026.xlsx",
            "m": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "u": uploaded_at,
        },
    )
    db.flush()
    return att_id


def _live_ids(db) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT a.id FROM attachments a
            JOIN attachment_types t ON t.id = a.attachment_type_id
            WHERE t.type_name = :name AND a.is_deleted = false
            """
        ),
        {"name": TYPE_NAME},
    ).fetchall()
    return [str(r[0]) for r in rows]


def _job(**overrides) -> SimpleNamespace:
    fields = {
        "id": uuid.uuid4(),
        "source_file_key": f"import-sources/{unique_code('job')}/Container Status 2026.xlsx",
        "source_filename": "Container Status 2026.xlsx",
        "source_file_size": 1024,
        "source_file_provider": "r2",
        "user_id": None,
        "created_at": datetime(2026, 8, 7, 3, 9, 33),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


# --- the invariant --------------------------------------------------------


def test_only_the_newest_workbook_stays_live(db):
    now = datetime(2026, 8, 7, 10, 0, 0)
    oldest = _workbook(db, uploaded_at=now - timedelta(days=2))
    middle = _workbook(db, uploaded_at=now - timedelta(days=1))
    newest = _workbook(db, uploaded_at=now)

    trashed = enforce_single_current(db)

    assert trashed == 2
    assert _live_ids(db) == [newest]
    assert oldest not in _live_ids(db) and middle not in _live_ids(db)


def test_superseded_rows_are_trashed_not_destroyed(db):
    """Soft delete - the sheet must stay recoverable, and its job untouched."""
    now = datetime(2026, 8, 7, 10, 0, 0)
    old = _workbook(db, uploaded_at=now - timedelta(days=1))
    _workbook(db, uploaded_at=now)

    enforce_single_current(db)

    row = db.execute(
        text("SELECT is_deleted, deleted_at, file_path FROM attachments WHERE id = :id"),
        {"id": old},
    ).fetchone()
    assert row[0] is True
    assert row[1] is not None, "trash must be dated, or the UI cannot order it"
    assert row[2], "the storage key survives - the bytes are still there"


def test_is_idempotent(db):
    now = datetime(2026, 8, 7, 10, 0, 0)
    _workbook(db, uploaded_at=now - timedelta(days=1))
    newest = _workbook(db, uploaded_at=now)

    enforce_single_current(db)
    second_pass = enforce_single_current(db)

    assert second_pass == 0
    assert _live_ids(db) == [newest]


def test_a_single_workbook_is_left_alone(db):
    only = _workbook(db, uploaded_at=datetime(2026, 8, 7, 10, 0, 0))
    assert enforce_single_current(db) == 0
    assert _live_ids(db) == [only]


def test_ties_resolve_deterministically(db):
    """A backfill stamps every row with the same now(); one must still win.

    Without the id tie-breaker the survivor is whichever row the planner emitted
    first, so two runs of the same command can keep different sheets.
    """
    same = datetime(2026, 8, 7, 10, 0, 0)
    ids = [_workbook(db, uploaded_at=same) for _ in range(3)]

    enforce_single_current(db)

    assert _live_ids(db) == [max(ids)]


def test_other_attachment_types_are_untouched(db):
    """It trashes Container Status workbooks, not the library."""
    from app.models.resources import Attachment, AttachmentType

    other_type = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=unique_code("Packing List"),
        allowed_extensions="pdf",
    )
    db.add(other_type)
    db.flush()
    bystander = Attachment(
        id=str(uuid.uuid4()),
        original_filename="pl.pdf",
        stored_filename="pl.pdf",
        file_path="x/pl.pdf",
        attachment_type_id=str(other_type.id),
        is_deleted=False,
    )
    db.add(bystander)
    db.flush()

    now = datetime(2026, 8, 7, 10, 0, 0)
    _workbook(db, uploaded_at=now - timedelta(days=1))
    _workbook(db, uploaded_at=now)

    enforce_single_current(db)

    db.refresh(bystander)
    assert bystander.is_deleted is False


# --- publishing -----------------------------------------------------------


def test_publishing_supersedes_the_previous_one(db):
    # Well in the past: publish stamps now(), and a same-day fixture time is a
    # UTC-vs-local coin flip over which row counts as newer.
    _workbook(db, uploaded_at=datetime(2020, 1, 1, 0, 0, 0))

    published = publish_import_source(db, _job())

    assert published is not None
    assert _live_ids(db) == [published]


def test_publishing_reuses_the_retained_storage_key(db):
    """One set of bytes, two references - never a second upload.

    The stored value is the CDN URL, but the key inside it is the import's own
    retained key: same object, second reference.
    """
    job = _job()
    published = publish_import_source(db, job)

    stored = db.execute(
        text("SELECT file_path FROM attachments WHERE id = :id"), {"id": published}
    ).scalar()
    assert stored.endswith(job.source_file_key)


def test_published_file_path_is_a_url_like_every_other_attachment(db, monkeypatch):
    """`file_path` is an ADDRESS, not a storage key.

    The import retains `source_file_key`, which is a key, but every other
    attachment row holds the full "https://<cdn>/<key>" the upload path writes,
    and consumers read the column without resolving it. Publishing the bare key
    put a domain-less string in the MCP envelope that no client could fetch -
    and it read as a signing bug rather than a shape mismatch.

    The CDN is stubbed rather than read from the environment: CI configures no
    bucket, so asserting the real one would only test the machine.
    """
    monkeypatch.setattr(
        "app.services.storage_router.cdn_base_url",
        lambda provider, key: f"https://cdn.test/{key}",
    )
    job = _job()
    published = publish_import_source(db, job)

    stored = db.execute(
        text("SELECT file_path FROM attachments WHERE id = :id"), {"id": published}
    ).scalar()
    assert stored == f"https://cdn.test/{job.source_file_key}"


def test_publish_survives_an_unconfigured_cdn(db, monkeypatch):
    """Falling back to the key beats losing the document.

    A wrong-looking path is recoverable by a backfill; a publish that raises
    means the workbook is never catalogued and nobody notices until someone
    asks for it.
    """
    def boom(*_a, **_k):
        raise RuntimeError("R2_CDN_DOMAIN is not set")

    monkeypatch.setattr("app.services.storage_router.cdn_base_url", boom)
    job = _job()

    published = publish_import_source(db, job)

    assert published is not None
    stored = db.execute(
        text("SELECT file_path FROM attachments WHERE id = :id"), {"id": published}
    ).scalar()
    assert stored == job.source_file_key


def test_republishing_matches_a_row_stored_as_a_bare_key(db):
    """Rows published before the URL change must not republish as duplicates."""
    job = _job()
    legacy = _workbook(
        db, uploaded_at=datetime(2020, 1, 1, 0, 0, 0), key=job.source_file_key
    )

    assert publish_import_source(db, job) == legacy


def test_republishing_an_older_job_does_not_resurrect_it(db):
    """The regression that would hurt most.

    A retry or a backfill re-run of an OLD job must not promote its sheet over
    the current one. Keeping "whatever the caller named" would do exactly that,
    and the answer would silently revert to last month's dates.
    """
    old_job = _job()
    old_attachment = publish_import_source(db, old_job)
    newest = _workbook(db, uploaded_at=datetime(2030, 1, 1, 0, 0, 0))

    again = publish_import_source(db, old_job)

    assert again == old_attachment, "same key means the same row, not a duplicate"
    assert _live_ids(db) == [newest], "the newer sheet is still the live one"


def test_a_job_with_no_retained_file_publishes_nothing(db):
    assert publish_import_source(db, _job(source_file_key=None)) is None
    assert _live_ids(db) == []


def test_latest_document_reads_the_live_row(db):
    _workbook(db, uploaded_at=datetime(2020, 1, 1, 0, 0, 0))
    published = publish_import_source(db, _job())

    doc = latest_document(db)

    assert doc is not None
    assert doc["id"] == published
    assert doc["filename"] == "Container Status 2026.xlsx"


def test_latest_document_is_none_before_any_import(db):
    assert latest_document(db) is None
