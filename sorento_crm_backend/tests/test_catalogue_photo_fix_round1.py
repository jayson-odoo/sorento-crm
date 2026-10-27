"""Fix round 1 for CATALOG-IMAGES: red tests, one class per group of FR items.

Plan: ``documentation/plans/products/PLAN-catalog-image-extract-27oct.md`` "Fix round 1".
Reuses the seeding, route stack and fixture PDF of ``test_catalogue_photo_readings_api.py``.
Module constants the plan names are patched with ``raising=False`` so a missing constant
fails on the behaviour assertion, not on an AttributeError.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: F401  (first app import)
from app.models.catalogue_photos import CataloguePhoto, CataloguePhotoReading
from app.services import catalogue_photo_service as svc
from tests._catalogue_photo_images import png_of
from tests.test_catalogue_photo_readings_api import (  # noqa: F401  (api is a fixture)
    ATTACHER_ID, CODE_A, CODE_B, CODE_W, PREFIX, SEED_A, SEED_B, SEED_OTHER, SORENTO,
    _all_items, _by_code, _catalogue_pdf, _company, _detail, _existing_photo, _links,
    _photo_type, _product, _read, _run, _seed_catalogue_products, _tab, _upload, api,
)


def _pdf(width: float, photos: list[tuple[tuple, int, tuple[float, float, str]]], pages: int = 1) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page(width=width, height=842)
        if number == 0:
            for rect, seed, (x, y, text) in photos:
                page.insert_image(pymupdf.Rect(*rect), stream=png_of(seed))
                page.insert_text((x, y), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def _two_with_one_code() -> bytes:
    return _pdf(595, [((50, 100, 250, 300), SEED_A, (50, 320, CODE_A)),
                      ((300, 100, 500, 300), SEED_B, (300, 320, CODE_A))])


# --------------------------------------------------------------------------- #
# FR-1, FR-5, FR-8: company, fail closed, PDF folder
# --------------------------------------------------------------------------- #
class TestCompany:
    def test_fr1_folder_pdf_and_photos_carry_the_readings_company(self, api) -> None:
        from app.models.resources import Attachment, AttachmentDirectory

        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _read(api, client)
        reading = api.db.query(CataloguePhotoReading).filter_by(id=rid).one()
        directories = api.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.id == reading.directory_id).all()
        attachments = api.db.query(Attachment).filter(
            Attachment.directory_id.in_([reading.directory_id])).all()
        pdf = api.db.query(Attachment).filter_by(id=str(reading.pdf_attachment_id)).one()
        assert directories and attachments
        assert {str(d.company_id) for d in directories} == {SORENTO}
        assert {str(a.company_id) for a in attachments} == {SORENTO}
        assert str(pdf.company_id) == SORENTO

    def test_fr1_another_company_cannot_see_the_folder_or_files(self, api) -> None:
        from app.models.resources import Attachment, AttachmentDirectory

        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _read(api, client)
        reading = api.db.query(CataloguePhotoReading).filter_by(id=rid).one()
        folder_id, pdf_id = str(reading.directory_id), str(reading.pdf_attachment_id)
        photo_ids = [str(p.attachment_id) for p in
                     api.db.query(CataloguePhoto).filter_by(reading_id=rid)]
        other = _company(api.db)
        api.in_company(other)
        api.db.expire_all()
        assert api.db.query(AttachmentDirectory).filter_by(id=folder_id).first() is None
        assert api.db.query(Attachment).filter(
            Attachment.id.in_(photo_ids + [pdf_id])).count() == 0

    def test_fr5_the_company_column_is_not_null(self) -> None:
        assert CataloguePhotoReading.__table__.c.company_id.nullable is False

    def test_fr5_the_worker_fails_closed_on_a_reading_without_a_company(self, api) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _upload(client).json()["id"]
        try:
            with api.db.begin_nested():
                api.db.execute(text("UPDATE catalogue_photo_readings SET company_id = NULL "
                                    "WHERE id = :i"), {"i": rid})
        except IntegrityError:
            return  # the column refuses NULL: nothing to fail closed on
        _run(api, rid)
        status = api.db.execute(text("SELECT status FROM catalogue_photo_readings WHERE id = :i"),
                                {"i": rid}).scalar()
        stored = api.db.execute(text("SELECT count(*) FROM catalogue_photos WHERE reading_id = :i"),
                                {"i": rid}).scalar()
        assert status == "failed"
        assert stored == 0

    def test_fr8_the_pdf_is_stored_in_the_root_folder_not_the_catalogue_folder(self, api) -> None:
        from app.models.resources import Attachment, AttachmentDirectory

        with TestClient(app) as client:
            rid = _upload(client).json()["id"]
        reading = api.db.query(CataloguePhotoReading).filter_by(id=rid).one()
        pdf = api.db.query(Attachment).filter_by(id=str(reading.pdf_attachment_id)).one()
        root = api.db.query(AttachmentDirectory).filter(
            AttachmentDirectory.name == "Catalogue photos",
            AttachmentDirectory.parent_id.is_(None)).one()
        assert str(pdf.directory_id) == str(root.id)
        assert str(pdf.directory_id) != str(reading.directory_id)


# --------------------------------------------------------------------------- #
# FR-2: caps
# --------------------------------------------------------------------------- #
class TestCaps:
    def test_fr2_a_placement_over_the_pixel_cap_is_skipped(self, monkeypatch) -> None:
        from app.services.dealer_kit import catalog_photos as cp

        monkeypatch.setattr(cp, "CATALOGUE_MAX_PIXELS", 10_000, raising=False)
        photos = cp.extract_catalog_photos(_catalogue_pdf())  # 240x240 = 57,600 px each

        assert photos == []

    def test_fr2_a_pdf_over_the_page_cap_is_refused(self, api, monkeypatch) -> None:
        from app.services.dealer_kit import catalog_photos as cp

        for module in (cp, svc):
            monkeypatch.setattr(module, "CATALOGUE_MAX_PAGES", 1, raising=False)
        _photo_type(api.db)
        data = _pdf(595, [((50, 100, 250, 300), SEED_A, (50, 320, CODE_A))], pages=2)
        with TestClient(app) as client:
            response = _upload(client, data=data)
            if response.status_code != 201:
                assert response.status_code in (400, 413, 422)
                return
            rid = response.json()["id"]
            _run(api, rid)
            detail = _detail(client, rid)
        assert detail["status"] == "failed"
        assert api.db.query(CataloguePhoto).filter_by(reading_id=rid).count() == 0

    def test_fr2_more_photos_than_the_cap_fails_the_reading_with_a_fixed_message(
        self, api, monkeypatch
    ) -> None:
        monkeypatch.setattr(svc, "CATALOGUE_MAX_PHOTOS", 2, raising=False)
        _photo_type(api.db)
        with TestClient(app) as client:
            rid = _upload(client).json()["id"]  # three photos
            _run(api, rid)
            detail = _detail(client, rid)
        assert detail["status"] == "failed"
        assert detail["error"]
        assert "Traceback" not in detail["error"]


# --------------------------------------------------------------------------- #
# FR-3, FR-7: errors, truncation, urls, names
# --------------------------------------------------------------------------- #
class TestErrorsAndNames:
    def test_fr3_a_caption_code_over_120_characters_does_not_fail_the_read(self, api) -> None:
        code = "SRTW" + "1" * 146
        data = _pdf(1500, [((50, 100, 250, 300), SEED_A, (50, 320, code))])
        _photo_type(api.db)
        with TestClient(app) as client:
            rid = _read(api, client, data=data)
            detail = _detail(client, rid)
        assert detail["status"] == "ready", detail["error"]
        row = api.db.query(CataloguePhoto).filter_by(reading_id=rid).one()
        assert row.printed_code == code[:120]

    def test_fr3_a_forced_exception_leaves_a_fixed_message_without_its_text(
        self, api, monkeypatch
    ) -> None:
        def boom(*_a, **_k):
            raise RuntimeError("secret-internal-host:5432 refused")

        monkeypatch.setattr(svc, "process_reading", boom)
        with TestClient(app) as client:
            rid = _upload(client).json()["id"]
            _run(api, rid)
            detail = _detail(client, rid)
        assert detail["status"] == "failed"
        assert detail["error"]
        assert "secret-internal-host" not in detail["error"]

    def test_fr3_the_queue_failure_message_names_no_host(self, api, monkeypatch) -> None:
        from app.services import queue_service

        def down(*_a, **_k):
            raise ConnectionError("Error 111 connecting to secret-redis-host:6379")

        monkeypatch.setattr(queue_service, "enqueue_job", down)
        with TestClient(app) as client:
            response = _upload(client)
            assert response.status_code == 201, response.text
            detail = _detail(client, response.json()["id"])
        assert detail["status"] == "failed"
        assert "secret-redis-host" not in (detail["error"] or "")

    def test_fr7_urls_are_signed_or_null_never_the_stored_path(self, api) -> None:
        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _read(api, client)
            api.storage.signing_fails = True
            response = client.get(f"{PREFIX}/{rid}/photos", params={"tab": "ready"})
        assert response.status_code == 200, response.text
        for item in response.json()["data"]:
            for key in ("thumbnail_url", "image_url"):
                assert item[key] is None, item[key]

    def test_fr7_a_300_character_file_name_is_stored_within_255(self, api) -> None:
        from app.models.resources import Attachment

        with TestClient(app) as client:
            response = _upload(client, filename="a" * 300 + ".pdf")
        assert response.status_code == 201, response.text
        reading = api.db.query(CataloguePhotoReading).filter_by(id=response.json()["id"]).one()
        pdf = api.db.query(Attachment).filter_by(id=str(reading.pdf_attachment_id)).one()
        assert len(pdf.stored_filename) <= 255

    def test_fr7_the_folder_name_has_no_arrow(self, api) -> None:
        from app.models.resources import AttachmentDirectory

        with TestClient(app) as client:
            response = _upload(client, filename="a --> b.pdf")
        assert response.status_code == 201, response.text
        reading = api.db.query(CataloguePhotoReading).filter_by(id=response.json()["id"]).one()
        folder = api.db.query(AttachmentDirectory).filter_by(id=str(reading.directory_id)).one()
        assert "-->" not in folder.name


# --------------------------------------------------------------------------- #
# FR-4, FR-6, FR-11: PATCH and attach rules
# --------------------------------------------------------------------------- #
class TestReviewRules:
    def _dup_world(self, api):
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        existing, _ = _existing_photo(api.db, api.storage, products[CODE_A], SEED_A)
        return products, existing

    def test_fr4_changing_the_product_clears_a_lookalike_the_new_product_lacks(self, api) -> None:
        products, _existing = self._dup_world(api)
        pick = _product(api.db, "ZZTPICK1234")
        with TestClient(app) as client:
            rid = _read(api, client)
            row = _by_code(_tab(client, rid, "duplicate")["data"], CODE_A)
            response = client.patch(f"{PREFIX}/{rid}/photos/{row['id']}",
                                    json={"product_id": str(pick.id)})
            ready = _tab(client, rid, "ready")["data"]
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["duplicate"] is None
        assert body["decision"] == "attach"
        assert row["id"] in [r["id"] for r in ready]

    def test_fr4_changing_the_product_recomputes_the_lookalike(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        target = _product(api.db, "ZZTTARGET5678")
        existing, _ = _existing_photo(api.db, api.storage, target, SEED_A)
        with TestClient(app) as client:
            rid = _read(api, client)
            row = _by_code(_tab(client, rid, "ready")["data"], CODE_A)
            response = client.patch(f"{PREFIX}/{rid}/photos/{row['id']}",
                                    json={"product_id": str(target.id)})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["duplicate"] and body["duplicate"]["attachment_id"] == str(existing.id)
        assert body["decision"] == "skip"

    def test_fr4_replace_counts_zero_when_no_link_was_deleted(self, api) -> None:
        from app.models.product import ProductAttachment

        products, existing = self._dup_world(api)
        with TestClient(app) as client:
            rid = _read(api, client)
            row = _by_code(_tab(client, rid, "duplicate")["data"], CODE_A)
            client.patch(f"{PREFIX}/{rid}/photos/{row['id']}", json={"decision": "replace"})
            api.db.query(ProductAttachment).filter_by(attachment_id=str(existing.id)).delete()
            api.db.commit()
            response = client.post(f"{PREFIX}/{rid}/attach")
        assert response.status_code == 200, response.text
        assert response.json()["replaced"] == 0

    def test_fr6_more_than_50_also_attach_ids_is_422(self, api) -> None:
        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _read(api, client)
            row = _by_code(_tab(client, rid, "ready")["data"], CODE_A)
            response = client.patch(
                f"{PREFIX}/{rid}/photos/{row['id']}",
                json={"also_attach_product_ids": [str(uuid.uuid4()) for _ in range(51)]})
        assert response.status_code == 422, response.text

    def test_fr11_replacing_the_primary_photo_leaves_the_new_link_primary(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        old, old_link = _existing_photo(api.db, api.storage, products[CODE_A], SEED_A,
                                        primary=True)
        with TestClient(app) as client:
            rid = _read(api, client)
            row = _by_code(_tab(client, rid, "duplicate")["data"], CODE_A)
            client.patch(f"{PREFIX}/{rid}/photos/{row['id']}", json={"decision": "replace"})
            assert client.post(f"{PREFIX}/{rid}/attach").status_code == 200
        photo = api.db.query(CataloguePhoto).filter_by(reading_id=rid, printed_code=CODE_A).one()
        links = {str(l.attachment_id): l for l in _links(api.db, products[CODE_A])}
        assert str(old.id) not in links
        assert links[str(photo.attachment_id)].is_primary is True


# --------------------------------------------------------------------------- #
# FR-9: upload activity
# --------------------------------------------------------------------------- #
class TestUploadActivity:
    def test_fr9_the_reading_is_one_entry_and_its_photos_are_not_listed(self, api) -> None:
        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            _read(api, client)
            response = client.get("/api/v1/resource-management/upload-activity", params={"scope": "me"})
        assert response.status_code == 200, response.text
        titles = [s["title"] for s in response.json()["sessions"]]
        assert len(titles) == 1, titles
        assert "zzt-catalogue" in titles[0]


# --------------------------------------------------------------------------- #
# FR-12, FR-13: worker behaviour
# --------------------------------------------------------------------------- #
class TestWorker:
    def test_fr12_each_existing_attachment_is_downloaded_at_most_once_per_run(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        _existing_photo(api.db, api.storage, products[CODE_A], SEED_OTHER)
        calls: list[str] = []
        original = api.storage.download_file

        def spy(key: str) -> bytes:
            calls.append(key)
            return original(key)

        api.storage.download_file = spy
        with TestClient(app) as client:
            _read(api, client, data=_two_with_one_code())
        existing = [k for k in calls if k.startswith("zzt-products/")]
        assert existing, "the look-alike check never read the existing photo"
        assert max(existing.count(k) for k in set(existing)) == 1, existing

    def test_fr13_a_failed_read_deletes_the_files_it_uploaded(self, api, monkeypatch) -> None:
        def boom(*_a, **_k):
            raise RuntimeError("lookalike broke")

        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        monkeypatch.setattr(svc, "_lookalike", boom)
        with TestClient(app) as client:
            rid = _upload(client).json()["id"]
            before = set(api.storage.objects)
            _run(api, rid)
            detail = _detail(client, rid)
        assert detail["status"] == "failed"
        assert set(api.storage.objects) == before

    def test_fr13_a_reading_that_is_not_queued_is_not_read_again(self, api) -> None:
        from app.models.resources import Attachment

        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _read(api, client)
            photos = api.db.query(CataloguePhoto).filter_by(reading_id=rid).count()
            files = api.db.query(Attachment).count()
            _run(api, rid)
        assert api.db.query(CataloguePhoto).filter_by(reading_id=rid).count() == photos
        assert api.db.query(Attachment).count() == files


# --------------------------------------------------------------------------- #
# FR-15, FR-16: matching and indexes
# --------------------------------------------------------------------------- #
class TestMatchingAndSchema:
    def test_fr15_already_on_file_ignores_deleted_attachments(self, api) -> None:
        from app.models.product import ProductAttachment
        from app.models.resources import Attachment
        from app.services.dealer_kit.catalog_photo_matching import already_on_file

        product = _product(api.db, CODE_A)
        gone = Attachment(id=str(uuid.uuid4()), original_filename="gone.jpg",
                          stored_filename="gone.jpg", file_path="zzt/gone.jpg",
                          file_hash="ab" * 32, is_deleted=True, storage_provider="s3")
        api.db.add(gone)
        api.db.flush()
        api.db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=product.id,
                                     attachment_id=gone.id))
        api.db.commit()

        assert already_on_file(api.db, str(product.id), "ab" * 32) is False

    def test_fr16_a_placeholder_is_on_the_needs_product_item(self, api) -> None:
        _photo_type(api.db)
        # No products seeded: the placeholder caption's photo has no product.
        with TestClient(app) as client:
            rid = _read(api, client)
            items = _tab(client, rid, "needs_product", limit=50)["data"]
        assert [i["placeholders"] for i in items if i["placeholders"]] == [["SRTWB_____"]]

    def test_fr16_the_foreign_keys_are_indexed(self, api) -> None:
        from sqlalchemy import inspect

        indexed = {tuple(i["column_names"])
                   for i in inspect(api.db.connection()).get_indexes("catalogue_photos")}
        for column in ("attachment_id", "product_id", "duplicate_of_attachment_id"):
            assert (column,) in indexed, column


# --------------------------------------------------------------------------- #
# Fix round 2: FR-19, FR-20
# --------------------------------------------------------------------------- #
def _repeated_pdf(times: int, *, rgba: bool = False) -> bytes:
    """One image placed ``times`` times, fully visible, so every crop is the same."""
    import io
    import pymupdf
    from PIL import Image

    if rgba:
        picture = Image.new("RGBA", (200, 200), (10, 120, 200, 255))
        picture.paste((0, 0, 0, 0), (0, 0, 100, 100))
        out = io.BytesIO()
        picture.save(out, format="PNG")
        stream = out.getvalue()
    else:
        stream = png_of(SEED_A)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for n in range(times):
        x, y = 20 + 110 * (n % 5), 100 + 150 * (n // 5)
        page.insert_image(pymupdf.Rect(x, y, x + 100, y + 100), stream=stream)
    data = doc.tobytes()
    doc.close()
    return data


class TestExtractionCaps:
    def _spy(self, monkeypatch):
        from app.services.dealer_kit import catalog_photos as cp

        calls: list[int] = []
        original = cp._encode

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(cp, "_encode", counting)
        return calls

    def test_fr19_extraction_stops_decoding_at_the_photo_limit(self, api, monkeypatch) -> None:
        calls = self._spy(monkeypatch)
        monkeypatch.setattr(svc, "CATALOGUE_MAX_PHOTOS", 3, raising=False)
        _photo_type(api.db)
        with TestClient(app) as client:
            rid = _upload(client, data=_repeated_pdf(10)).json()["id"]
            _run(api, rid)
            detail = _detail(client, rid)
        assert detail["status"] == "failed"
        assert detail["error"]
        assert len(calls) <= 4, f"{len(calls)} photos were decoded for a limit of 3"

    def test_fr19_one_image_placed_five_times_is_re_encoded_once(self, monkeypatch) -> None:
        from app.services.dealer_kit import catalog_photos as cp

        calls = self._spy(monkeypatch)
        photos = cp.extract_catalog_photos(_repeated_pdf(5))
        assert len(photos) == 5
        assert len(calls) == 1, f"{len(calls)} re-encodes for one (image, crop)"

    def test_fr19_a_soft_mask_with_no_readable_size_is_skipped(self, monkeypatch) -> None:
        import pymupdf
        from app.services.dealer_kit import catalog_photos as cp

        original = pymupdf.Document.xref_get_key

        def unreadable(self, xref, key):
            if key in ("Width", "Height"):
                raise RuntimeError("no size")
            return original(self, xref, key)

        data = _repeated_pdf(1, rgba=True)
        assert len(cp.extract_catalog_photos(data)) == 1  # control: readable mask is kept
        monkeypatch.setattr(pymupdf.Document, "xref_get_key", unreadable)
        assert cp.extract_catalog_photos(data) == []


class TestFinalCommit:
    def test_fr20_a_failed_final_commit_deletes_the_uploaded_files(self, api, monkeypatch) -> None:
        import sys

        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            rid = _upload(client).json()["id"]
            before = set(api.storage.objects)
            original = api.db.commit

            def failing_commit():
                if sys._getframe(1).f_code.co_name == "process_reading":
                    raise RuntimeError("commit refused")
                return original()

            monkeypatch.setattr(api.db, "commit", failing_commit)
            _run(api, rid)
            monkeypatch.setattr(api.db, "commit", original)
            detail = _detail(client, rid)
        assert detail["status"] == "failed"
        assert set(api.storage.objects) == before
