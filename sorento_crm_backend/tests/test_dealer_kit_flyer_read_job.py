"""The read as a background job: the seams the migrated suites do not cover.

`documentation/plans/dealer-kit/PLAN-flyer-read-background-job.md` (2.2, 2.3,
2.7) and `documentation/plans/dealer-kit/flyer-read-background-job-acceptance-
criteria.md` are the contract. `test_dealer_kit_flyer_readings.py` and
`test_dealer_kit_flyer_from_attachment.py` were migrated onto the queue shape
(`tests/_flyer_read.py`) and already prove, exhaustively: 202 + processing for
both routes, the report reachable once the job runs, the exact refusal words
for a non-PDF and a password-protected flyer, permission denial on every
route (`TestAccess` in both files), and company scope (404 never 403).

What they do NOT prove, and what this file is for:

* **AC-J2.1/J2.2/J2.3** - the actual queued entry: that exactly one job is
  queued, carrying the staged provider/key for an upload and `None, None` for
  a library read, and that the staged bytes are really parked in storage
  before the job runs.
* **AC-J2.4** - idempotency, asserted directly: two POSTs of the same source
  while the first is `processing` return the SAME row and queue nothing
  twice; a THIRD POST after the first finishes queues a new one.
* **AC-J2.5** - the seam raising (Redis down): the row still comes back 202,
  now `failed`, naming the queue problem, and the staged object is gone.
* **AC-J3.6** - the job body directly: banners actually land in storage (not
  only a `banner_asset_id` in the JSON), the staged object is deleted after
  BOTH a done and a failed run, and the vanished-row case (AC-J3.4).
* The 502 `FLYER_STAGING_FAILED` path, and that it creates no row.
* **AC-J3.1** - a queued read and `create_reading`'s synchronous convenience
  produce the same reading off the same bytes.

AC-J2.6 (permission denial on both routes) is already exhaustively covered by
`TestAccess` in both migrated files post-migration, so it is not repeated here.

Postgres only, on a blank scratch schema. Storage is the in-process fake
(`tests/_fake_storage.py`); the queue is the recorder in `tests/_flyer_read.py`.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.dealer_kit import flyer_reading_service as svc  # noqa: E402

from tests._fake_storage import patch_storage
from tests._flyer_read import finish_reads, patch_flyer_read
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# The fixture's three pages: two carry a banner, matching
# test_dealer_kit_flyer_artwork_assets.py's PAGES_WITH_A_BANNER.
PAGES_WITH_A_BANNER = 2

# Where a stored banner ends up, per asset_service.STORAGE_ENTITY_TYPE - checked
# against fake storage directly so "a banner was stored" means bytes in the
# bucket, not only a `banner_asset_id` written into the reading JSON.
BANNER_STORAGE_PREFIX = "dealer_kit_asset/"

_SORENTO = "00000000-0000-0000-0000-000000000001"

_ADMIN_ID = "2b6f8e14-9d37-4c5a-8b02-1e6d3a7f9c40"
_ADMIN_ROLE = "7c1d4a92-3e58-4b06-a719-2f8c6d5b3e01"


def _seed_roles(db) -> None:
    """One superadmin. Permission denial is proven elsewhere; this file needs
    only a principal that can reach every route."""
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add(
        UserRole(
            id=_ADMIN_ROLE,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(
        User(id=_ADMIN_ID, email="zzt-frj-admin@test.com", name="FRJ Admin", status="ACTIVE")
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.commit()


@pytest.fixture
def api(monkeypatch):
    """The route stack, a superadmin principal, fake storage, and the queue
    recorder - exposed as `reads` so a test can assert on `.queued` directly."""
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        storage = patch_storage(monkeypatch)
        reads = patch_flyer_read(monkeypatch, db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _ADMIN_ID, "email": "zzt-frj-admin@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        # Direct db calls in a test (svc.create_reading, deleting a row) run
        # outside a request, so they need the scope set here too, exactly as
        # the migrated suites' `_in_company` does for their own direct writes.
        set_company_scope(db, frozenset({_SORENTO}))

        yield db, storage, reads

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def _pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


def _upload(client: TestClient, *, filename: str = "zzt-flyer.pdf", data: bytes | None = None):
    return client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": (filename, data if data is not None else _pdf_bytes(), "application/pdf")},
    )


def _from_attachment(client: TestClient, attachment_id):
    return client.post(
        "/api/v1/dealer-kit/flyer-readings/from-attachment",
        json={"attachmentId": str(attachment_id)},
    )


def _attachment(
    db,
    storage,
    *,
    company_id=_SORENTO,
    filename: str = "zzt-library-flyer.pdf",
    data: bytes | None = None,
):
    from app.models.resources import Attachment

    data = _pdf_bytes() if data is None else data
    key = f"zzt-dealer-kit-attachments/{uuid.uuid4()}/{filename}"
    storage.objects[key] = (data, "application/pdf")

    attachment = Attachment(
        id=str(uuid.uuid4()),
        company_id=company_id,
        original_filename=filename,
        stored_filename=filename,
        file_path=key,
        file_size_bytes=len(data),
        mime_type="application/pdf",
        storage_provider="s3",
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _locked_pdf_bytes() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "SRTJC8041 599")
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")


def _staged_keys(storage) -> list[str]:
    return [key for key in storage.objects if key.startswith(svc.STAGING_PREFIX)]


def _reading_count(db) -> int:
    from app.models.dealer_kit import FlyerReadingRecord

    return db.query(FlyerReadingRecord).count()


def _get(client: TestClient, reading_id: str) -> dict:
    res = client.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}")
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# AC-J2.1 / AC-J2.2 / AC-J2.3 - the actual queued entry
# --------------------------------------------------------------------------- #
class TestQueuedEntry:
    def test_ac_j2_1_2_3_upload_stages_the_bytes_and_queues_one_job(self, api) -> None:
        db, storage, reads = api
        data = _pdf_bytes()

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-queue-upload.pdf", data=data)

        assert res.status_code == 202, res.text
        body = res.json()
        assert body["status"] == "processing"

        assert len(reads.queued) == 1
        reading_id, staged_provider, staged_key = reads.queued[0]
        assert reading_id == body["id"]
        assert staged_provider == "s3"
        assert staged_key is not None
        assert staged_key.startswith(svc.STAGING_PREFIX)

        # The bytes are really parked, not merely a key handed to the seam.
        assert staged_key in storage.objects
        assert storage.objects[staged_key][0] == data

    def test_ac_j2_1_3_from_attachment_stages_nothing_and_queues_one_job(self, api) -> None:
        db, storage, reads = api
        attachment = _attachment(db, storage, filename="zzt-queue-fa.pdf")

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 202, res.text
        body = res.json()
        assert body["status"] == "processing"

        assert len(reads.queued) == 1
        reading_id, staged_provider, staged_key = reads.queued[0]
        assert reading_id == body["id"]
        assert staged_provider is None
        assert staged_key is None

        # Nothing was parked under the staging prefix for this read.
        assert _staged_keys(storage) == []


# --------------------------------------------------------------------------- #
# AC-J2.4 - idempotent re-click
# --------------------------------------------------------------------------- #
class TestIdempotentReClick:
    def test_ac_j2_4_a_second_upload_of_the_same_bytes_returns_the_existing_row(
        self, api
    ) -> None:
        db, storage, reads = api
        data = _pdf_bytes()

        with TestClient(app) as c:
            first = _upload(c, filename="zzt-idem-1.pdf", data=data)
            assert first.status_code == 202, first.text
            first_id = first.json()["id"]
            assert len(reads.queued) == 1

            # Re-click while the first is still processing: same row, nothing
            # new queued or staged.
            second = _upload(c, filename="zzt-idem-1-again.pdf", data=data)
            assert second.status_code == 202, second.text
            assert second.json()["id"] == first_id
            assert second.json()["status"] == "processing"
            assert len(reads.queued) == 1

            assert [job["status"] for job in finish_reads()] == ["done"]

            # A done reading of the same source does not block a new read.
            third = _upload(c, filename="zzt-idem-1-third.pdf", data=data)

        assert third.status_code == 202, third.text
        assert third.json()["id"] != first_id
        assert third.json()["status"] == "processing"
        assert len(reads.queued) == 2

    def test_ac_j2_4_a_second_from_attachment_read_returns_the_existing_row(
        self, api
    ) -> None:
        db, storage, reads = api
        attachment = _attachment(db, storage, filename="zzt-idem-fa.pdf")

        with TestClient(app) as c:
            first = _from_attachment(c, attachment.id)
            assert first.status_code == 202, first.text
            first_id = first.json()["id"]
            assert len(reads.queued) == 1

            second = _from_attachment(c, attachment.id)
            assert second.status_code == 202, second.text
            assert second.json()["id"] == first_id
            assert len(reads.queued) == 1

            assert [job["status"] for job in finish_reads()] == ["done"]

            third = _from_attachment(c, attachment.id)

        assert third.status_code == 202, third.text
        assert third.json()["id"] != first_id
        assert len(reads.queued) == 2


# --------------------------------------------------------------------------- #
# AC-J2.5 - the queue itself is unreachable
# --------------------------------------------------------------------------- #
class TestEnqueueFailure:
    def test_ac_j2_5_upload_enqueue_failure_fails_the_row_and_discards_the_staged_object(
        self, api, monkeypatch
    ) -> None:
        db, storage, _reads = api

        def _boom(record, staged_provider, staged_key):
            raise RuntimeError("Redis is unreachable")

        monkeypatch.setattr(svc, "_enqueue", _boom)

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-enqueue-fail.pdf")

        # Still 202: the ROW carries the failure, not the response status.
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["status"] == "failed"
        assert "queue" in body["errorMessage"].lower(), body["errorMessage"]
        assert body["finishedAt"]

        # The staged upload is not left behind for a job that will never run.
        assert _staged_keys(storage) == []

        from app.models.dealer_kit import FlyerReadingRecord

        record = (
            db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == body["id"]).one()
        )
        assert record.job_id is None

    def test_ac_j2_5_from_attachment_enqueue_failure_fails_the_row(
        self, api, monkeypatch
    ) -> None:
        db, storage, _reads = api
        attachment = _attachment(db, storage, filename="zzt-enqueue-fail-fa.pdf")

        def _boom(record, staged_provider, staged_key):
            raise RuntimeError("Redis is unreachable")

        monkeypatch.setattr(svc, "_enqueue", _boom)

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 202, res.text
        body = res.json()
        assert body["status"] == "failed"
        assert "queue" in body["errorMessage"].lower(), body["errorMessage"]
        # Nothing was ever staged for a library read, so there is nothing to
        # discard - the failure path must not choke on that.
        assert _staged_keys(storage) == []


# --------------------------------------------------------------------------- #
# AC-J3.6 - the job body, end to end
# --------------------------------------------------------------------------- #
class TestJobBody:
    def test_ac_j3_6_done_transition_reaches_get_with_banners_in_storage(self, api) -> None:
        db, storage, reads = api

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-job-done.pdf")
            assert res.status_code == 202, res.text
            reading_id = res.json()["id"]

            _reading_id, _provider, staged_key = reads.queued[0]
            assert staged_key in storage.objects, "the staged bytes must exist before the job runs"

            assert [job["status"] for job in finish_reads()] == ["done"]

            body = _get(c, reading_id)

        assert body["status"] == "done"
        assert body["finishedAt"]
        assert body["pageCount"] == 3

        # The staged copy is gone once the job is done - it is a throwaway
        # parking spot, not a second copy of the file.
        assert staged_key not in storage.objects

        # Banners really reached storage, not only a `banner_asset_id` in the
        # reading JSON.
        banner_objects = [k for k in storage.objects if k.startswith(BANNER_STORAGE_PREFIX)]
        assert len(banner_objects) >= PAGES_WITH_A_BANNER

        from app.models.dealer_kit import Asset

        assert len(db.query(Asset).all()) == PAGES_WITH_A_BANNER

    def test_ac_j3_6_failed_transition_not_a_pdf_names_the_words_and_cleans_up(
        self, api
    ) -> None:
        db, storage, reads = api

        with TestClient(app) as c:
            res = _upload(
                c, filename="zzt-job-garbage.pdf", data=b"PK\x03\x04 not a pdf at all"
            )
            assert res.status_code == 202, res.text
            reading_id = res.json()["id"]
            _reading_id, _provider, staged_key = reads.queued[0]

            assert [job["status"] for job in finish_reads()] == ["failed"]

            body = _get(c, reading_id)

        assert body["status"] == "failed"
        assert "could not be read as a pdf" in body["errorMessage"].lower(), body["errorMessage"]
        assert body["finishedAt"]
        # No report to show for a file that was never read.
        assert body["report"]["matched"] == []
        assert body["report"]["unmatched"] == []
        # The staged object is discarded on a FAILED run too, not only a done one.
        assert staged_key not in storage.objects

    def test_ac_j3_6_failed_transition_password_protected_names_the_words_and_cleans_up(
        self, api
    ) -> None:
        db, storage, reads = api
        locked = _locked_pdf_bytes()

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-job-locked.pdf", data=locked)
            assert res.status_code == 202, res.text
            reading_id = res.json()["id"]
            _reading_id, _provider, staged_key = reads.queued[0]

            assert [job["status"] for job in finish_reads()] == ["failed"]

            body = _get(c, reading_id)

        assert body["status"] == "failed"
        assert body["errorMessage"] == (
            "That PDF is password protected, so its contents cannot be read. "
            "Save an unprotected copy and upload that."
        )
        assert staged_key not in storage.objects

    def test_ac_j3_4_a_reading_deleted_while_the_job_ran_discards_the_result(
        self, api
    ) -> None:
        """The vanished-row case. The designer deleted the row before the
        worker got to it: no banners, no report, the job exits cleanly, and the
        staged copy is still cleaned up (best-effort, regardless of outcome)."""
        db, storage, reads = api

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-job-gone.pdf")
            assert res.status_code == 202, res.text
            reading_id = res.json()["id"]

        _reading_id, _provider, staged_key = reads.queued[0]
        assert _reading_count(db) == 1

        from app.models.dealer_kit import FlyerReadingRecord

        db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).delete()
        db.commit()
        assert _reading_count(db) == 0

        results = finish_reads()
        assert results == [{"reading_id": reading_id, "status": "gone"}]

        from app.models.dealer_kit import Asset

        assert db.query(Asset).all() == []
        assert staged_key not in storage.objects

        with TestClient(app) as c:
            assert c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 404


# --------------------------------------------------------------------------- #
# 502 FLYER_STAGING_FAILED - the one storage failure told in the request
# --------------------------------------------------------------------------- #
class TestStagingFailure:
    def test_a_bucket_that_refuses_the_staging_put_answers_502_and_creates_no_row(
        self, api, monkeypatch
    ) -> None:
        """Inverse of `test_dealer_kit_flyer_artwork_assets.py`'s "a flyer whose
        banners cannot be stored is still read": THERE only the asset PUTs are
        broken and the staging PUT is exempted, so the read still succeeds. HERE
        only the staging PUT (under `STAGING_PREFIX`) is broken - the one PUT
        that happens before any row exists, so a refusal here must leave nothing
        behind at all.
        """
        db, storage, reads = api
        real_upload = storage.upload_file

        def _explode(**kwargs):
            if str(kwargs.get("file_path", "")).startswith(svc.STAGING_PREFIX):
                raise RuntimeError("bucket unreachable")
            return real_upload(**kwargs)

        monkeypatch.setattr(storage, "upload_file", _explode)

        before = _reading_count(db)

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-staging-fail.pdf")

        assert res.status_code == 502, res.text
        assert res.json().get("code") == "FLYER_STAGING_FAILED"
        assert _reading_count(db) == before, "a 502 must not have created a reading"
        assert reads.queued == [], "nothing was enqueued for a read that was never staged"


# --------------------------------------------------------------------------- #
# AC-J3.1 - a queued read and the synchronous convenience are the same reading
# --------------------------------------------------------------------------- #
class TestSameness:
    def test_ac_j3_1_a_queued_read_and_create_reading_produce_the_same_reading(
        self, api
    ) -> None:
        db, storage, reads = api
        data = _pdf_bytes()

        sync_record = svc.create_reading(
            db, filename="zzt-sync.pdf", data=data, user_id=_ADMIN_ID
        )

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-queued.pdf", data=data)
            assert res.status_code == 202, res.text
            queued_id = res.json()["id"]
            assert [job["status"] for job in finish_reads()] == ["done"]

        from app.models.dealer_kit import FlyerReadingRecord

        queued_record = (
            db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == queued_id).one()
        )

        def _banner_count(record) -> int:
            return sum(
                1
                for page in record.reading_json["pages"]
                if page.get("banner_asset_id")
            )

        assert queued_record.sha256 == sync_record.sha256
        assert svc.page_count(queued_record) == svc.page_count(sync_record)
        assert svc.code_count(queued_record) == svc.code_count(sync_record)
        assert _banner_count(queued_record) == _banner_count(sync_record)
        assert queued_record.status == sync_record.status == svc.ReadingStatus.DONE


# --------------------------------------------------------------------------- #
# Commit 2fa98766, case 1 - the unique partial index actually forbids a
# second in-flight row, at the database, not merely at the service's read.
# --------------------------------------------------------------------------- #
class TestUniqueIndexForbidsASecondInFlightRow:
    def test_a_second_processing_row_for_the_same_attachment_is_refused(self, api) -> None:
        db, storage, _reads = api
        attachment = _attachment(db, storage, filename="zzt-index-attachment.pdf")

        first = svc._new_processing_record(
            filename="zzt-index-first.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(first)
        db.commit()

        second = svc._new_processing_record(
            filename="zzt-index-second.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(second)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_a_second_processing_row_for_the_same_sha256_is_refused(self, api) -> None:
        db, _storage, _reads = api
        digest = hashlib.sha256(b"zzt-unique-index-sha256").hexdigest()

        first = svc._new_processing_record(
            filename="zzt-index-first.pdf",
            byte_size=10,
            sha256=digest,
            source_attachment_id=None,
            user_id=_ADMIN_ID,
        )
        db.add(first)
        db.commit()

        second = svc._new_processing_record(
            filename="zzt-index-second.pdf",
            byte_size=10,
            sha256=digest,
            source_attachment_id=None,
            user_id=_ADMIN_ID,
        )
        db.add(second)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# --------------------------------------------------------------------------- #
# Commit 2fa98766, case 2 - the index does NOT block what it must allow.
# --------------------------------------------------------------------------- #
class TestUniqueIndexAllowsWhatItMust:
    def test_a_second_read_of_the_same_attachment_inserts_once_the_first_is_done(
        self, api
    ) -> None:
        db, storage, _reads = api
        attachment = _attachment(db, storage, filename="zzt-allow-done.pdf")

        first = svc._new_processing_record(
            filename="zzt-allow-first.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(first)
        db.commit()

        first.status = svc.ReadingStatus.DONE
        db.add(first)
        db.commit()

        second = svc._new_processing_record(
            filename="zzt-allow-second.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(second)
        db.commit()  # must not raise: only ``processing`` is in the index

        from app.models.dealer_kit import FlyerReadingRecord

        rows = (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.source_attachment_id == str(attachment.id))
            .all()
        )
        assert len(rows) == 2

    def test_a_second_read_of_the_same_attachment_inserts_once_the_first_failed(
        self, api
    ) -> None:
        db, storage, _reads = api
        attachment = _attachment(db, storage, filename="zzt-allow-failed.pdf")

        first = svc._new_processing_record(
            filename="zzt-allow-failed-first.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(first)
        db.commit()

        first.status = svc.ReadingStatus.FAILED
        db.add(first)
        db.commit()

        second = svc._new_processing_record(
            filename="zzt-allow-failed-second.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(second)
        db.commit()  # must not raise: only ``processing`` is in the index

    def test_two_processing_rows_for_different_attachments_coexist(self, api) -> None:
        """Also proves NULLs are distinct on the sha256 index: both rows here
        have ``sha256=None``, and only differ by ``source_attachment_id``."""
        db, storage, _reads = api
        attachment_a = _attachment(db, storage, filename="zzt-diff-a.pdf")
        attachment_b = _attachment(db, storage, filename="zzt-diff-b.pdf")

        row_a = svc._new_processing_record(
            filename="zzt-diff-row-a.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment_a.id),
            user_id=_ADMIN_ID,
        )
        row_b = svc._new_processing_record(
            filename="zzt-diff-row-b.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment_b.id),
            user_id=_ADMIN_ID,
        )
        db.add_all([row_a, row_b])
        db.commit()  # must not raise

    def test_two_processing_upload_rows_coexist_because_source_attachment_id_nulls_are_distinct(
        self, api
    ) -> None:
        """Both rows here have ``source_attachment_id=None`` (an upload has no
        attachment), and only differ by ``sha256``. If Postgres treated the two
        NULLs on ``source_attachment_id`` as equal, this insert would collide on
        the attachment index even though the sha256 index correctly allows it -
        which is exactly why the guard needs two indexes rather than one."""
        db, _storage, _reads = api
        digest_a = hashlib.sha256(b"zzt-null-attach-a").hexdigest()
        digest_b = hashlib.sha256(b"zzt-null-attach-b").hexdigest()

        row_a = svc._new_processing_record(
            filename="zzt-null-attach-row-a.pdf",
            byte_size=10,
            sha256=digest_a,
            source_attachment_id=None,
            user_id=_ADMIN_ID,
        )
        row_b = svc._new_processing_record(
            filename="zzt-null-attach-row-b.pdf",
            byte_size=10,
            sha256=digest_b,
            source_attachment_id=None,
            user_id=_ADMIN_ID,
        )
        db.add_all([row_a, row_b])
        db.commit()  # must not raise


# --------------------------------------------------------------------------- #
# Commit 2fa98766, case 3 - ``_insert_or_join`` returns the winner rather than
# raising. Simulated by making the FIRST ``_reading_in_flight`` call (the
# application-level idempotency read, before staging/insert) answer None while
# a real in-flight row already exists - exactly the window the module's own
# docstring names: two clicks that both see nothing in flight.
# --------------------------------------------------------------------------- #
class TestInsertOrJoinReturnsTheWinner:
    def _patch_first_lookup_blind(self, monkeypatch):
        """Make the NEXT call to ``_reading_in_flight`` answer None, and every
        call after that behave normally. Used to blind only the early,
        application-level check in ``enqueue_reading_from_upload`` /
        ``enqueue_reading_from_attachment`` - the second call, made by
        ``_insert_or_join`` after the refused INSERT, is real and is what
        proves the join."""
        real_in_flight = svc._reading_in_flight
        calls = {"n": 0}

        def _flaky(db_arg, *, sha256=None, attachment_id=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return real_in_flight(db_arg, sha256=sha256, attachment_id=attachment_id)

        monkeypatch.setattr(svc, "_reading_in_flight", _flaky)

    def test_a_raced_upload_answers_202_with_the_winner_and_discards_the_loser_staged_object(
        self, api, monkeypatch
    ) -> None:
        db, storage, reads = api
        data = _pdf_bytes()
        digest = hashlib.sha256(data).hexdigest()

        winner = svc._new_processing_record(
            filename="zzt-race-winner.pdf",
            byte_size=len(data),
            sha256=digest,
            source_attachment_id=None,
            user_id=_ADMIN_ID,
        )
        db.add(winner)
        db.commit()
        db.refresh(winner)

        self._patch_first_lookup_blind(monkeypatch)

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-race-loser.pdf", data=data)

        assert res.status_code == 202, res.text
        assert res.json()["id"] == str(winner.id)
        assert res.json()["status"] == "processing"

        # Nothing was ever queued for the loser: the row it got back is the
        # winner's, already accounted for.
        assert reads.queued == []

        # The loser's bytes were staged (between the blinded first check and
        # the refused insert) and then discarded once the race was lost.
        assert _staged_keys(storage) == []

        from app.models.dealer_kit import FlyerReadingRecord

        assert db.query(FlyerReadingRecord).count() == 1

    def test_a_raced_from_attachment_read_answers_202_with_the_winner_and_enqueues_nothing(
        self, api, monkeypatch
    ) -> None:
        db, storage, reads = api
        attachment = _attachment(db, storage, filename="zzt-race-fa.pdf")

        winner = svc._new_processing_record(
            filename="zzt-race-fa-winner.pdf",
            byte_size=10,
            sha256=None,
            source_attachment_id=str(attachment.id),
            user_id=_ADMIN_ID,
        )
        db.add(winner)
        db.commit()
        db.refresh(winner)

        self._patch_first_lookup_blind(monkeypatch)

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 202, res.text
        assert res.json()["id"] == str(winner.id)
        assert reads.queued == []

        from app.models.dealer_kit import FlyerReadingRecord

        assert (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.source_attachment_id == str(attachment.id))
            .count()
            == 1
        )


# --------------------------------------------------------------------------- #
# Commit 2fa98766, case 4 - staged-object cleanup when the insert fails for a
# reason that is NOT the idempotency race (a real database blip). The bytes
# are staged before the row exists, so any failure to write the row must not
# leave them behind.
# --------------------------------------------------------------------------- #
class TestStagedCleanupWhenTheInsertFails:
    def test_a_failed_insert_discards_the_staged_object_and_the_exception_propagates(
        self, api, monkeypatch
    ) -> None:
        db, storage, reads = api
        data = _pdf_bytes()

        def _boom(*_args, **_kwargs):
            raise RuntimeError("db blip")

        monkeypatch.setattr(svc, "_insert_or_join", _boom)

        with pytest.raises(RuntimeError, match="db blip"):
            svc.enqueue_reading_from_upload(
                db, filename="zzt-insert-blip.pdf", data=data, user_id=_ADMIN_ID
            )

        assert _staged_keys(storage) == []
        assert reads.queued == []

        from app.models.dealer_kit import FlyerReadingRecord

        assert (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.filename == "zzt-insert-blip.pdf")
            .count()
            == 0
        )


# --------------------------------------------------------------------------- #
# Commit 2fa98766, case 5 - ``create_reading`` never strands a row in
# ``processing``: an ``AppException`` refusal and a plain crash both fail the
# row and re-raise, rather than leaving "being read" forever with a job that
# will never finish it (there is no job on this synchronous path at all).
# --------------------------------------------------------------------------- #
class TestCreateReadingNeverStrandsARow:
    def test_an_app_exception_fails_the_row_with_the_refusal_words_and_reraises(
        self, api
    ) -> None:
        from app.models.dealer_kit import FlyerReadingRecord
        from app.services.error_handler import AppException

        db, _storage, _reads = api
        garbage = b"PK\x03\x04 not a pdf at all"

        with pytest.raises(AppException) as raised:
            svc.create_reading(
                db, filename="zzt-create-not-pdf.pdf", data=garbage, user_id=_ADMIN_ID
            )
        assert raised.value.status_code == 400

        record = (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.filename == "zzt-create-not-pdf.pdf")
            .one()
        )
        assert record.status == svc.ReadingStatus.FAILED
        assert "could not be read as a pdf" in record.error_message.lower()
        assert record.finished_at is not None

    def test_a_plain_crash_fails_the_row_with_the_generic_words_and_reraises(
        self, api, monkeypatch
    ) -> None:
        from app.models.dealer_kit import FlyerReadingRecord

        db, _storage, _reads = api
        data = _pdf_bytes()

        def _boom(*_args, **_kwargs):
            raise RuntimeError("PyMuPDF died")

        monkeypatch.setattr(svc, "complete_reading", _boom)

        with pytest.raises(RuntimeError, match="PyMuPDF died"):
            svc.create_reading(
                db, filename="zzt-create-crash.pdf", data=data, user_id=_ADMIN_ID
            )

        record = (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.filename == "zzt-create-crash.pdf")
            .one()
        )
        # Same wording the job's own generic arm writes, so a designer reading
        # the list cannot tell which path a failure came from.
        assert record.status == svc.ReadingStatus.FAILED
        assert record.error_message == "The flyer could not be read: PyMuPDF died"
        assert record.finished_at is not None
