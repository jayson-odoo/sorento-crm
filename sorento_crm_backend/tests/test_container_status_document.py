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

import logging
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.container_status_document import (
    TYPE_NAME,
    ensure_attachment_type,
    enforce_single_current,
    latest_document,
    publish_import_source,
)
from tests._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"
SORENTO_ID = DEFAULT_COMPANY_ID


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _mocha(db) -> None:
    """Seed the Mocha company. Idempotent per test - each test gets its own
    blank schema, so this only ever runs once per db fixture instance."""
    if db.get(Company, MOCHA_ID) is None:
        db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        db.flush()


def _workbook(db, *, uploaded_at: datetime, key: str | None = None, company_id: str | None = None) -> str:
    """A live Container Status attachment stamped at a given moment.

    ``company_id=None`` is the legacy pre-stamping shape (AC-A5) - never pass
    the string "null", it must be the Python ``None`` so the column is a real
    SQL NULL.
    """
    type_id = ensure_attachment_type(db)
    att_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO attachments (
                id, attachment_type_id, original_filename, stored_filename,
                file_path, mime_type, uploaded_at, is_deleted, company_id
            ) VALUES (:id, :t, :n, :n, :k, :m, :u, false, :c)
            """
        ),
        {
            "id": att_id,
            "t": type_id,
            "n": "Container Status 2026.xlsx",
            "k": key or f"import-sources/{unique_code('key')}/Container Status 2026.xlsx",
            "m": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "u": uploaded_at,
            "c": company_id,
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


def _live_ids_for(db, company_id: str | None) -> list[str]:
    """Live Container Status ids restricted to one company (``None`` = the
    legacy/NULL partition)."""
    clause = "a.company_id IS NULL" if company_id is None else "a.company_id = :c"
    rows = db.execute(
        text(
            f"""
            SELECT a.id FROM attachments a
            JOIN attachment_types t ON t.id = a.attachment_type_id
            WHERE t.type_name = :name AND a.is_deleted = false AND {clause}
            """
        ),
        {"name": TYPE_NAME, "c": company_id},
    ).fetchall()
    return [str(r[0]) for r in rows]


def _is_deleted(db, att_id: str) -> bool:
    return bool(
        db.execute(
            text("SELECT is_deleted FROM attachments WHERE id = :id"), {"id": att_id}
        ).scalar()
    )


def _row_count_for_key(db, key: str) -> int:
    """How many attachments rows point at ``key`` - the duplicate-insert detector."""
    return db.execute(
        text(
            "SELECT count(*) FROM attachments WHERE file_path = :key OR file_path LIKE :suffix"
        ),
        {"key": key, "suffix": f"%/{key}"},
    ).scalar()


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


def _real_import_job(db, *, company_id: str) -> SimpleNamespace:
    """A REAL ``import_jobs`` row stamped with ``company_id``, for the one test
    that must exercise `publish_import_source`'s INSERT subquery
    (``SELECT company_id FROM import_jobs WHERE id = :job_id``) rather than
    just asserting the invariant function in isolation.

    ``import_jobs`` is deliberately NOT a ``CompanyScopedMixin`` (job-tracking
    infra, never auto-filtered/auto-stamped), so it is seeded by raw INSERT
    rather than the ORM. Returns a ``SimpleNamespace`` with the SAME attribute
    shape ``_job()`` returns, so ``publish_import_source`` reads it identically
  - the difference is that THIS job's ``id`` actually resolves a row in
    ``import_jobs``, so the subquery has something real to read instead of
    always returning NULL.
    """
    job_id = uuid.uuid4()
    key = f"import-sources/{unique_code('key')}/Container Status 2026.xlsx"
    created_at = datetime(2026, 8, 7, 3, 9, 33)
    db.execute(
        text(
            """
            INSERT INTO import_jobs (
                id, job_id, job_type, status, user_id, company_id,
                source_filename, source_file_key, source_file_provider,
                source_file_size, created_at
            ) VALUES (
                :id, :rq_id, :job_type, :status, :user_id, :company_id,
                :source_filename, :source_file_key, :source_file_provider,
                :source_file_size, :created_at
            )
            """
        ),
        {
            "id": str(job_id),
            "rq_id": unique_code("rq"),
            "job_type": "container_status_import",
            "status": "finished",
            "user_id": str(uuid.uuid4()),
            "company_id": company_id,
            "source_filename": "Container Status 2026.xlsx",
            "source_file_key": key,
            "source_file_provider": "r2",
            "source_file_size": 1024,
            "created_at": created_at,
        },
    )
    db.flush()
    return SimpleNamespace(
        id=job_id,
        source_file_key=key,
        source_filename="Container Status 2026.xlsx",
        source_file_size=1024,
        source_file_provider="r2",
        user_id=None,
        created_at=created_at,
    )


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
    # Sorento, because that is where publication lands: `_job()` is not a real
    # `import_jobs` row, so the company subquery finds nothing and COALESCEs onto
    # the incumbent company. A NULL seed here would be a different partition and
    # would correctly survive (AC-A5), which is not what this test is about.
    _workbook(db, uploaded_at=datetime(2020, 1, 1, 0, 0, 0), company_id=SORENTO_ID)

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
    # Same company as the published row - publication COALESCEs onto the
    # incumbent company, and "does not resurrect" is a within-company claim.
    newest = _workbook(
        db, uploaded_at=datetime(2030, 1, 1, 0, 0, 0), company_id=SORENTO_ID
    )

    again = publish_import_source(db, old_job)

    assert again == old_attachment, "same key means the same row, not a duplicate"
    assert _live_ids(db) == [newest], "the newer sheet is still the live one"


# --- AC-A9: republishing a TRASHED row must not duplicate or resurrect -----


def test_a9_republishing_a_superseded_job_does_not_duplicate_or_resurrect(db):
    """The regression this fixes: the "already published" probe used to carry
    `AND is_deleted = false`, so once `enforce_single_current` trashed a
    published row, re-running its job found nothing, fell through to the
    INSERT, and wrote a SECOND row for the same storage key stamped
    `uploaded_at = now()` - which then outranked the company's genuine
    current workbook and trashed IT. The row-count assertion below is the one
    that catches the duplicate insert; the rest confirm the trashed row is
    returned as-is, never restored.
    """
    job = _real_import_job(db, company_id=SORENTO_ID)
    first = publish_import_source(db, job)
    assert first is not None

    newer = _workbook(db, uploaded_at=datetime(2030, 1, 1, 0, 0, 0), company_id=SORENTO_ID)
    enforce_single_current(db)

    # Sanity: the supersession actually happened before we republish into it.
    assert _is_deleted(db, first) is True
    assert _live_ids_for(db, SORENTO_ID) == [newer]

    again = publish_import_source(db, job)

    assert again == first, "the same storage key must resolve to the same row"
    assert _is_deleted(db, again) is True, "a trashed match must stay trashed, not be restored"
    assert _row_count_for_key(db, job.source_file_key) == 1, (
        "exactly one attachments row for this storage key - a second insert "
        "here is the defect this test exists to catch"
    )
    assert _live_ids_for(db, SORENTO_ID) == [newer], (
        "the company's genuine current workbook must still be the one live row"
    )


def test_a9_republishing_a_deliberately_trashed_job_stays_trashed(db):
    """A row trashed by hand (not by supersession) also stays trashed on
    republish, and no second row appears - the invariant is not "trashed
    because a newer sheet exists", it is "trashed, full stop"."""
    job = _real_import_job(db, company_id=SORENTO_ID)
    first = publish_import_source(db, job)
    assert first is not None

    db.execute(
        text("UPDATE attachments SET is_deleted = true, deleted_at = :now WHERE id = :id"),
        {"now": datetime(2026, 8, 8, 0, 0, 0), "id": first},
    )
    db.commit()

    again = publish_import_source(db, job)

    assert again == first
    assert _is_deleted(db, again) is True
    assert _row_count_for_key(db, job.source_file_key) == 1
    assert _live_ids_for(db, SORENTO_ID) == [], "nothing was resurrected"


def test_a9_republishing_mochas_trashed_sheet_leaves_sorento_untouched(db):
    """Cross-company: the republish-probe fix must not become a new way for
    one company's retry to reach another's workbook."""
    _mocha(db)
    sorento_current = _workbook(
        db, uploaded_at=datetime(2026, 8, 7, 9, 0, 0), company_id=SORENTO_ID
    )
    mocha_job = _real_import_job(db, company_id=MOCHA_ID)
    mocha_first = publish_import_source(db, mocha_job)
    assert mocha_first is not None

    mocha_newer = _workbook(
        db, uploaded_at=datetime(2030, 1, 1, 0, 0, 0), company_id=MOCHA_ID
    )
    enforce_single_current(db)
    assert _is_deleted(db, mocha_first) is True

    again = publish_import_source(db, mocha_job)

    assert again == mocha_first
    assert _is_deleted(db, again) is True
    assert _row_count_for_key(db, mocha_job.source_file_key) == 1
    assert sorento_current in _live_ids(db), "Sorento's current workbook must survive Mocha's retry"
    assert _live_ids_for(db, SORENTO_ID) == [sorento_current]
    assert _live_ids_for(db, MOCHA_ID) == [mocha_newer]


# --- the two log changes ----------------------------------------------------


def test_a9_warns_when_the_jobs_company_snapshot_is_null(db, caplog):
    """The only diagnosability for a mis-attributed workbook: a NULL job
    snapshot must log a WARNING naming the job, the attachment and the
    incumbent company it fell back to, and the success INFO line must carry
    that company id too."""
    caplog.set_level(logging.INFO, logger="app.services.container_status_document")
    job = _real_import_job(db, company_id=None)

    published = publish_import_source(db, job)

    assert published is not None
    # Scoped to the company-snapshot warning: publish also tolerates an
    # unconfigured CDN with a separate warning (falls back to the raw key),
    # which fires on hosts without R2/CloudFront env and is not under test.
    warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "carried no company snapshot" in r.getMessage()
    ]
    assert len(warnings) == 1
    warning_msg = warnings[0].getMessage()
    assert str(job.id) in warning_msg
    assert published in warning_msg
    assert SORENTO_ID in warning_msg

    infos = [
        r for r in caplog.records
        if r.levelname == "INFO" and "Published container status workbook" in r.getMessage()
    ]
    assert len(infos) == 1
    assert SORENTO_ID in infos[0].getMessage()


def test_a9_no_warning_when_the_job_carries_a_real_company(db, caplog):
    """The warning is for the fallback case only - a job with a real company
    snapshot must not log it, even though the info line still names the
    company."""
    caplog.set_level(logging.INFO, logger="app.services.container_status_document")
    job = _real_import_job(db, company_id=SORENTO_ID)

    published = publish_import_source(db, job)

    assert published is not None
    warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "carried no company snapshot" in r.getMessage()
    ]
    assert warnings == [], "a job with a real company snapshot must not warn"

    infos = [
        r for r in caplog.records
        if r.levelname == "INFO" and "Published container status workbook" in r.getMessage()
    ]
    assert len(infos) == 1
    assert SORENTO_ID in infos[0].getMessage()


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


# --- per-company invariant (AC-A1..A6) -------------------------------------


def test_a1_mocha_publish_leaves_sorento_current_live(db):
    """A Mocha import must never touch Sorento's current workbook."""
    _mocha(db)
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_current = _workbook(db, uploaded_at=now - timedelta(days=1), company_id=SORENTO_ID)

    mocha_new = _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    trashed = enforce_single_current(db)

    assert trashed == 0, "each company had exactly one live row, nothing to collapse"
    assert sorento_current in _live_ids(db)
    assert mocha_new in _live_ids(db)
    assert _live_ids_for(db, SORENTO_ID) == [sorento_current]
    assert _live_ids_for(db, MOCHA_ID) == [mocha_new]


def test_a1_a_real_mocha_upload_through_publish_import_source_leaves_sorento_untouched(db):
    """AC-A1, through the REAL upload path, not just the invariant function.

    `publish_import_source` stamps `company_id` on the new attachment by
    reading it off the `import_jobs` row via an INSERT subquery
    (`SELECT company_id FROM import_jobs WHERE id = :job_id`). Testing only
    `enforce_single_current` in isolation would leave that subquery unpinned:
    if the job's company snapshot ever stopped reaching the attachment, every
    other Group A test would still pass while production trashed across
    companies again.
    """
    _mocha(db)
    sorento_current = _workbook(
        db, uploaded_at=datetime(2026, 8, 7, 9, 0, 0), company_id=SORENTO_ID
    )
    mocha_job = _real_import_job(db, company_id=MOCHA_ID)

    published = publish_import_source(db, mocha_job)

    assert published is not None
    row = db.execute(
        text("SELECT company_id FROM attachments WHERE id = :id"), {"id": published}
    ).scalar()
    assert str(row) == MOCHA_ID, "the published row must carry the JOB's company, not Sorento's"

    assert sorento_current in _live_ids(db), "Sorento's current workbook must survive the Mocha upload"
    assert published in _live_ids(db)
    assert _live_ids_for(db, SORENTO_ID) == [sorento_current]
    assert _live_ids_for(db, MOCHA_ID) == [published]


def test_a7_a_null_company_job_stamps_the_incumbent_not_null(db):
    """AC-A7. An import enqueued under a `None` / `UNSET` scope (the n8n /
    X-API-Key path) snapshots a NULL `company_id` on its `import_jobs` row.
    The published attachment must never inherit that NULL: `Attachment` is
    company-SHARED, so a live NULL row is visible to every company at once,
    and `PARTITION BY company_id` in `enforce_single_current` ranks NULLs only
    against each other, so no future import - from ANY company - could ever
    supersede it.
    """
    _mocha(db)
    null_scope_job = _real_import_job(db, company_id=None)

    published = publish_import_source(db, null_scope_job)

    assert published is not None
    row = db.execute(
        text("SELECT company_id FROM attachments WHERE id = :id"), {"id": published}
    ).scalar()
    assert row is not None, "a published workbook must never be company-less"
    assert str(row) == SORENTO_ID, "a NULL job snapshot coalesces onto the incumbent company"


def test_a2_three_live_workbooks_in_one_company_collapse_to_the_newest(db):
    """The other company's single row is untouched by a different company's
    collapse, and the losers are soft-deleted with their bytes intact."""
    _mocha(db)
    now = datetime(2026, 8, 7, 10, 0, 0)
    mocha_oldest = _workbook(db, uploaded_at=now - timedelta(days=2), company_id=MOCHA_ID)
    mocha_middle = _workbook(db, uploaded_at=now - timedelta(days=1), company_id=MOCHA_ID)
    mocha_newest = _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    sorento_only = _workbook(db, uploaded_at=now - timedelta(days=5), company_id=SORENTO_ID)

    trashed = enforce_single_current(db)

    assert trashed == 2
    assert _live_ids_for(db, MOCHA_ID) == [mocha_newest]
    assert _live_ids_for(db, SORENTO_ID) == [sorento_only]

    for loser in (mocha_oldest, mocha_middle):
        row = db.execute(
            text("SELECT is_deleted, deleted_at, file_path FROM attachments WHERE id = :id"),
            {"id": loser},
        ).fetchone()
        assert row[0] is True
        assert row[1] is not None
        assert row[2]


def test_a3_ties_within_one_company_resolve_by_id_other_company_unaffected(db):
    """Two Mocha workbooks sharing `uploaded_at` to the microsecond - the higher
    id survives - while Sorento's own survivor is untouched."""
    _mocha(db)
    same = datetime(2026, 8, 7, 10, 0, 0)
    mocha_ids = [_workbook(db, uploaded_at=same, company_id=MOCHA_ID) for _ in range(2)]
    sorento_current = _workbook(db, uploaded_at=same, company_id=SORENTO_ID)

    enforce_single_current(db)

    assert _live_ids_for(db, MOCHA_ID) == [max(mocha_ids)]
    assert _live_ids_for(db, SORENTO_ID) == [sorento_current]


def test_a4_a_second_run_is_a_noop_across_two_companies(db):
    _mocha(db)
    now = datetime(2026, 8, 7, 10, 0, 0)
    _workbook(db, uploaded_at=now - timedelta(days=1), company_id=SORENTO_ID)
    sorento_newest = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    _workbook(db, uploaded_at=now - timedelta(days=1), company_id=MOCHA_ID)
    mocha_newest = _workbook(db, uploaded_at=now, company_id=MOCHA_ID)

    first_pass = enforce_single_current(db)
    second_pass = enforce_single_current(db)

    assert first_pass == 2
    assert second_pass == 0
    assert _live_ids_for(db, SORENTO_ID) == [sorento_newest]
    assert _live_ids_for(db, MOCHA_ID) == [mocha_newest]


def test_a5_legacy_null_company_rows_rank_only_against_each_other(db):
    """Legacy pre-stamping rows are their own partition: the newest of them
    survives, and a company's own upload never touches it."""
    now = datetime(2026, 8, 7, 10, 0, 0)
    legacy_old = _workbook(db, uploaded_at=now - timedelta(days=2), company_id=None)
    legacy_newest = _workbook(db, uploaded_at=now - timedelta(days=1), company_id=None)
    sorento_new = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)

    trashed = enforce_single_current(db)

    assert trashed == 1, "only the older legacy row is collapsed"
    assert _live_ids_for(db, None) == [legacy_newest]
    assert legacy_old not in _live_ids(db)
    assert _live_ids_for(db, SORENTO_ID) == [sorento_new]


def test_a6_an_already_trashed_row_is_never_resurrected(db):
    """Rows the OLD global rule already soft-deleted must stay soft-deleted."""
    now = datetime(2026, 8, 7, 10, 0, 0)
    already_trashed = _workbook(db, uploaded_at=now - timedelta(days=10), company_id=SORENTO_ID)
    db.execute(
        text("UPDATE attachments SET is_deleted = true, deleted_at = :now WHERE id = :id"),
        {"now": now - timedelta(days=9), "id": already_trashed},
    )
    survivor = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)

    trashed = enforce_single_current(db)

    assert trashed == 0, "the pre-trashed row was already gone, nothing new to collapse"
    row = db.execute(
        text("SELECT is_deleted FROM attachments WHERE id = :id"), {"id": already_trashed}
    ).fetchone()
    assert row[0] is True, "a superseded rule run must never resurrect a trashed row"
    assert _live_ids_for(db, SORENTO_ID) == [survivor]


# --- the "latest" download link is company-aware (AC-B1/B3/B4) -------------


def test_b1_latest_document_under_mocha_scope_returns_mochas_row(db):
    _mocha(db)
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_doc = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    mocha_doc = _workbook(db, uploaded_at=now - timedelta(days=1), company_id=MOCHA_ID)

    set_company_scope(db, frozenset({MOCHA_ID}))
    doc = latest_document(db)

    assert doc is not None
    assert doc["id"] == mocha_doc
    assert doc["id"] != sorento_doc
    assert doc["company_id"] == MOCHA_ID
    assert doc["company_name"] == "Mocha"


def test_b1_latest_document_under_sorento_scope_returns_sorentos_row(db):
    _mocha(db)
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_doc = _workbook(db, uploaded_at=now - timedelta(days=1), company_id=SORENTO_ID)
    _workbook(db, uploaded_at=now, company_id=MOCHA_ID)

    set_company_scope(db, frozenset({SORENTO_ID}))
    doc = latest_document(db)

    assert doc is not None
    assert doc["id"] == sorento_doc
    assert doc["company_id"] == SORENTO_ID
    assert doc["company_name"] == "Sorento"


def test_b3_latest_document_is_none_when_the_companys_scope_has_nothing(db):
    """Neither an owned workbook nor a legacy NULL-company row exists for the
    caller's company."""
    _mocha(db)
    _workbook(db, uploaded_at=datetime(2026, 8, 7, 10, 0, 0), company_id=MOCHA_ID)

    set_company_scope(db, frozenset({SORENTO_ID}))

    assert latest_document(db) is None


def test_b4_an_owned_row_beats_a_newer_legacy_null_row(db):
    """A workbook the caller's company actually owns wins over a legacy
    unstamped one, even when the legacy row is the newer of the two."""
    now = datetime(2026, 8, 7, 10, 0, 0)
    owned = _workbook(db, uploaded_at=now - timedelta(days=5), company_id=SORENTO_ID)
    _workbook(db, uploaded_at=now, company_id=None)  # newer, but unowned

    set_company_scope(db, frozenset({SORENTO_ID}))
    doc = latest_document(db)

    assert doc is not None
    assert doc["id"] == owned
    assert doc["company_id"] == SORENTO_ID
