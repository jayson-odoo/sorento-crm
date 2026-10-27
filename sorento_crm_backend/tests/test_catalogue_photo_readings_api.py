"""Catalogue photo readings: upload, worker task, review lists, PATCH, attach.

Written before the implementation (CATALOG-IMAGES S2, red). Contract:
``documentation/plans/products/PLAN-catalog-image-extract-27oct.md`` ("Build":
Data, API, Worker task) and ``catalog-image-extract-acceptance-criteria.md``
(AC-1 to AC-19). Every test names the AC it traces to.

Postgres only, on a blank scratch schema; every row (company, users, roles,
permissions, products, attachment type, existing photos) is seeded here. Storage
is the in-process fake (``tests/_fake_storage.py``). The queued read runs inline
on the test's own session, as ``tests/_flyer_read.py`` does for flyers: the task
takes a keyword-only ``_db`` seam (``process_catalogue_photo_reading(reading_id,
_db=db)``), and the route reaches the queue only through
``app.services.queue_service.enqueue_job`` (looked up at call time).
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.catalogue_photos import CataloguePhoto, CataloguePhotoReading
from app.services.dealer_kit import flyer_reading_service as flyer_svc
from tests._catalogue_photo_images import encode, pattern, png_of
from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

PREFIX = "/api/v1/master-data/catalogue-photo-readings"
SORENTO = "00000000-0000-0000-0000-000000000001"

EDITOR_ID = "5c1e7a39-2b84-4d60-9f13-8a6d0b4e2c71"
EDITOR_ROLE = "a3f8d205-6c19-4e7b-b842-1d9e5a7c3f60"
VIEWER_ID = "b7d40e82-1a53-4c96-8e27-5f3a9c1d6b04"
VIEWER_ROLE = "e19c6b73-4d28-4a05-9f61-7b2d8e4a1c35"
ATTACHER_ID = "c2a95f14-8e37-4b60-a1d8-3e7c5b9f0d26"
ATTACHER_ROLE = "f40b8d61-7a25-4c93-b5e9-2a6d1c8e3f07"
NOPERM_ID = "d85e3a27-9b41-4f06-8c72-6a1e4d7b5f93"

SEED_A, SEED_B, SEED_C, SEED_OTHER = 1, 2, 3, 9
CODE_A = "SRTWT1906-BL-DIY"
CODE_B = "SRTBF12613"
CODE_W = "SRTW2600"

ROW_FIELDS = {
    "id", "page", "position", "thumbnail_url", "image_url", "printed_code",
    "block_codes", "placeholders", "product", "rung", "confidence", "suggestion",
    "other_block_products", "also_attach_product_ids", "duplicate", "decision",
    "attached_at",
}


# --------------------------------------------------------------------------- #
# Fixture PDFs, built here
# --------------------------------------------------------------------------- #
def _catalogue_pdf() -> bytes:
    """One page: photo over CODE_A, photo over a three-token caption (one a
    placeholder), a photo with no caption, and a 30pt icon."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(50, 100, 250, 300), stream=png_of(SEED_A))
    page.insert_text((50, 320), CODE_A, fontsize=9)
    page.insert_image(pymupdf.Rect(300, 100, 500, 300), stream=png_of(SEED_B))
    page.insert_text((300, 320), f"{CODE_B} SRTWB_____ {CODE_W}", fontsize=9)
    page.insert_image(pymupdf.Rect(50, 450, 250, 650), stream=png_of(SEED_C))
    page.insert_image(pymupdf.Rect(400, 700, 430, 730), stream=png_of(5, (30, 30)))
    data = doc.tobytes()
    doc.close()
    return data


def _locked_pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "SRTJC8041 599")
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
def _seed_roles(db) -> None:
    from app.models.user import (
        User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission,
    )

    roles = {
        EDITOR_ROLE: "zzt_cp_editor",
        VIEWER_ROLE: "zzt_cp_viewer",
        ATTACHER_ROLE: "zzt_cp_attacher",
    }
    for role_id, slug in roles.items():
        db.add(UserRole(id=role_id, slug=slug, name=slug, description="",
                        is_protected=False, is_default=False))
    users = {
        EDITOR_ID: EDITOR_ROLE, VIEWER_ID: VIEWER_ROLE, ATTACHER_ID: ATTACHER_ROLE,
        NOPERM_ID: None,
    }
    for user_id in users:
        db.add(User(id=user_id, email=f"zzt-cp-{user_id[:6]}@test.com",
                    name="CP user", status="ACTIVE"))
    db.flush()
    for user_id, role_id in users.items():
        if role_id:
            db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
    grants = {
        "dealer_kit.page.view": (EDITOR_ROLE, VIEWER_ROLE, ATTACHER_ROLE),
        "dealer_kit.page.edit": (EDITOR_ROLE, ATTACHER_ROLE),
        "master_data.products.edit": (ATTACHER_ROLE,),
    }
    for slug, role_ids in grants.items():
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        for role_id in role_ids:
            db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id,
                                      permission_id=perm_id))
    db.commit()


def _product(db, code: str, *, company_id: str | None = None):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTCP")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT product {code}",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"),
        company_id=company_id,
    )
    db.add(product)
    db.commit()
    return product


def _company(db) -> str:
    from app.models.company import Company

    company = Company(id=str(uuid.uuid4()), name=unique_code("ZZT Other Co"),
                      code=unique_code("ZZTCPC")[:20], is_active=True)
    db.add(company)
    db.commit()
    return company.id


def _photo_type(db):
    from app.models.resources import AttachmentType

    row = AttachmentType(id=str(uuid.uuid4()), type_name="Product Photos",
                         allowed_extensions="jpg,jpeg,png", max_file_size_mb=20)
    db.add(row)
    db.commit()
    return row


def _existing_photo(db, storage, product, seed: int, *, primary: bool | None = None,
                    linked: bool = True):
    """An image already on file for ``product``: bytes AND a stored thumbnail, so
    the look-alike check can read either through storage_router."""
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment
    from app.services.image_thumbnailer import thumbnail_key_for

    key = f"zzt-products/{uuid.uuid4()}/existing-{seed}.jpg"
    main = encode(pattern(seed, (480, 480)), "JPEG", 85)
    thumb = encode(pattern(seed, (240, 240)).resize((120, 120)), "JPEG", 70)
    storage.objects[key] = (main, "image/jpeg")
    storage.objects[thumbnail_key_for(key)] = (thumb, "image/jpeg")
    attachment = Attachment(
        id=str(uuid.uuid4()), original_filename=f"existing-{seed}.jpg",
        stored_filename=f"existing-{seed}.jpg", file_path=key,
        thumbnail_path=f"https://cdn.test/{thumbnail_key_for(key)}",
        file_size_bytes=len(main), mime_type="image/jpeg",
        file_hash=hashlib.sha256(main).hexdigest(), storage_provider="s3",
    )
    db.add(attachment)
    db.flush()
    link = None
    if linked:
        link = ProductAttachment(id=str(uuid.uuid4()), product_id=product.id,
                                 attachment_id=attachment.id, is_primary=primary)
        db.add(link)
    db.commit()
    return attachment, link


def _links(db, product) -> list:
    from app.models.product import ProductAttachment

    db.expire_all()
    return db.query(ProductAttachment).filter(
        ProductAttachment.product_id == product.id).all()


# --------------------------------------------------------------------------- #
# The route stack
# --------------------------------------------------------------------------- #
@pytest.fixture
def api(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services import queue_service
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        storage = patch_storage(monkeypatch)

        queued: list[SimpleNamespace] = []

        def _enqueue(func, *args, queue_name="imports", **kwargs):
            queued.append(SimpleNamespace(func=func, args=args, queue_name=queue_name,
                                          kwargs=kwargs))
            return SimpleNamespace(id=f"zzt-job-{len(queued)}")

        monkeypatch.setattr(queue_service, "enqueue_job", _enqueue)

        # No n8n upload webhook may fire for these files (AC-4): patch the helper
        # wherever it has been imported by name, then assert it stayed silent.
        webhook = MagicMock(name="create_and_send_webhook")
        import app.services.attachment_webhook_helper as helper

        monkeypatch.setattr(helper, "create_and_send_webhook", webhook)
        for module in list(sys.modules.values()):
            if module is not None and getattr(module, "create_and_send_webhook", None) \
                    is not None and module is not helper:
                monkeypatch.setattr(module, "create_and_send_webhook", webhook)

        here = {"company": SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope
        set_company_scope(db, frozenset({SORENTO}))

        def as_user(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        as_user(ATTACHER_ID)
        yield SimpleNamespace(db=db, storage=storage, queued=queued, webhook=webhook,
                              as_user=as_user, in_company=in_company)
        app.dependency_overrides.clear()


def _upload(client, data=None, filename="zzt-catalogue.pdf", ctype="application/pdf"):
    return client.post(PREFIX, files={"file": (
        filename, _catalogue_pdf() if data is None else data, ctype)})


def _run(api, reading_id: str) -> dict:
    from app.tasks.catalogue_photo_tasks import process_catalogue_photo_reading

    return process_catalogue_photo_reading(reading_id, _db=api.db)


def _read(api, client, **kwargs) -> str:
    response = _upload(client, **kwargs)
    assert response.status_code == 201, response.text
    reading_id = response.json()["id"]
    _run(api, reading_id)
    return reading_id


def _detail(client, reading_id: str) -> dict:
    response = client.get(f"{PREFIX}/{reading_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _tab(client, reading_id: str, tab: str, **params) -> dict:
    response = client.get(f"{PREFIX}/{reading_id}/photos",
                          params={"tab": tab, **params})
    assert response.status_code == 200, response.text
    return response.json()


def _by_code(items: list[dict], code: str | None) -> dict:
    found = [item for item in items if item["printed_code"] == code]
    assert len(found) == 1, (code, [i["printed_code"] for i in items])
    return found[0]


def _all_items(client, reading_id: str) -> list[dict]:
    items: list[dict] = []
    for tab in ("ready", "duplicate", "needs_product", "skipped"):
        items += _tab(client, reading_id, tab, limit=50)["data"]
    return items


def _seed_catalogue_products(db) -> dict:
    return {code: _product(db, code) for code in (CODE_A, CODE_B, CODE_W)}


# --------------------------------------------------------------------------- #
# POST upload  (AC-2, AC-18)
# --------------------------------------------------------------------------- #
class TestUpload:
    def _counts(self, db) -> tuple[int, int, int]:
        from app.models.resources import Attachment, AttachmentDirectory

        return (db.query(CataloguePhotoReading).count(),
                db.query(Attachment).count(),
                db.query(AttachmentDirectory).count())

    def test_a_non_pdf_is_refused_and_nothing_is_stored(self, api) -> None:
        before = self._counts(api.db)
        with TestClient(app) as client:
            response = _upload(client, data=b"just some words", filename="notes.txt",
                               ctype="text/plain")

        assert response.status_code == 400, response.text
        assert self._counts(api.db) == before
        assert api.queued == []

    def test_an_encrypted_pdf_is_refused_and_nothing_is_stored(self, api) -> None:
        before = self._counts(api.db)
        with TestClient(app) as client:
            response = _upload(client, data=_locked_pdf())

        assert response.status_code == 400, response.text
        assert self._counts(api.db) == before
        assert api.queued == []

    def test_a_file_over_fifty_megabytes_is_refused_naming_the_limit(self, api) -> None:
        before = self._counts(api.db)
        oversize = b"%PDF-1.4\n" + b"0" * (flyer_svc.MAX_UPLOAD_BYTES + 10 * 1024 * 1024)
        with TestClient(app) as client:
            response = _upload(client, data=oversize, filename="zzt-huge.pdf")

        assert response.status_code == 413, response.text
        assert "50" in response.text
        assert self._counts(api.db) == before
        assert api.queued == []

    def test_a_user_without_dealer_kit_edit_is_forbidden(self, api) -> None:
        before = self._counts(api.db)
        for user_id in (VIEWER_ID, NOPERM_ID):
            api.as_user(user_id)
            with TestClient(app) as client:
                assert _upload(client).status_code == 403
        assert self._counts(api.db) == before

    def test_success_queues_a_reading_and_stores_the_pdf_in_its_folder(self, api) -> None:
        from app.models.resources import Attachment, AttachmentDirectory

        api.as_user(EDITOR_ID)
        with TestClient(app) as client:
            response = _upload(client, filename="zzt-catalogue.pdf")

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "queued"
        assert body["file_name"] == "zzt-catalogue.pdf"
        assert len(api.queued) == 1
        job = api.queued[0]
        assert job.func.__name__ == "process_catalogue_photo_reading"
        assert job.args == (body["id"],)
        assert job.queue_name == "flyer_read"

        root = (api.db.query(AttachmentDirectory)
                .filter(AttachmentDirectory.name == "Catalogue photos",
                        AttachmentDirectory.parent_id.is_(None)).one())
        folder = (api.db.query(AttachmentDirectory)
                  .filter(AttachmentDirectory.parent_id == root.id).one())
        assert folder.name in ("zzt-catalogue", "zzt-catalogue.pdf")
        reading = api.db.query(CataloguePhotoReading).filter_by(id=body["id"]).one()
        assert str(reading.directory_id) == str(folder.id)
        pdf = api.db.query(Attachment).filter_by(id=str(reading.pdf_attachment_id)).one()
        assert str(pdf.directory_id) == str(folder.id)
        assert pdf.original_filename == "zzt-catalogue.pdf"


# --------------------------------------------------------------------------- #
# The worker task  (AC-4, AC-6, AC-7)
# --------------------------------------------------------------------------- #
class TestWorkerTask:
    def _run_all(self, api):
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            detail = _detail(client, reading_id)
            items = _all_items(client, reading_id)
        return reading_id, detail, items, products

    def test_three_photos_are_stored_named_typed_and_the_icon_is_dropped(self, api) -> None:
        from app.models.resources import Attachment

        reading_id, detail, _items, _ = self._run_all(api)

        rows = api.db.query(CataloguePhoto).filter_by(reading_id=reading_id).all()
        assert len(rows) == 3
        reading = api.db.query(CataloguePhotoReading).filter_by(id=reading_id).one()
        attachments = [api.db.query(Attachment).filter_by(id=str(r.attachment_id)).one()
                       for r in rows]
        names = sorted(a.original_filename for a in attachments)
        assert CODE_A + ".jpg" in names and CODE_B + ".jpg" in names
        unnamed = [n for n in names if n not in (CODE_A + ".jpg", CODE_B + ".jpg")]
        assert len(unnamed) == 1 and re.fullmatch(r"p01-photo-0\d\.jpg", unnamed[0])
        for attachment in attachments:
            assert str(attachment.directory_id) == str(reading.directory_id)
            assert attachment.attachment_type is not None
            assert attachment.attachment_type.type_name == "Product Photos"
        assert all(r.dhash and re.fullmatch(r"[0-9a-f]{16}", r.dhash) for r in rows)
        assert all(r.sha256 for r in rows)

    def test_no_n8n_upload_webhook_fires(self, api) -> None:
        self._run_all(api)

        api.webhook.assert_not_called()

    def test_the_reading_is_ready_with_its_counts(self, api) -> None:
        _reading_id, detail, _items, _ = self._run_all(api)

        assert detail["status"] == "ready"
        assert detail["photo_count"] == 3
        assert detail["page_count"] == 1
        assert detail["directory_id"]

    def test_rows_carry_codes_matches_placeholders_and_other_block_products(self, api) -> None:
        _rid, _detail_body, items, products = self._run_all(api)

        assert len(items) == 3
        for item in items:
            assert ROW_FIELDS <= set(item), ROW_FIELDS - set(item)
        a = _by_code(items, CODE_A)
        assert a["product"] == {"id": str(products[CODE_A].id), "product_code": CODE_A}
        assert a["rung"] == "exact" and a["confidence"] == "high"
        assert a["decision"] == "attach" and a["duplicate"] is None
        assert a["attached_at"] is None
        b = _by_code(items, CODE_B)
        assert b["product"]["product_code"] == CODE_B
        assert b["block_codes"] == [CODE_B, CODE_W]
        assert b["placeholders"] == ["SRTWB_____"]
        assert b["other_block_products"] == [
            {"id": str(products[CODE_W].id), "product_code": CODE_W}]
        assert b["also_attach_product_ids"] == []
        c = _by_code(items, None)
        assert c["product"] is None and c["block_codes"] == []

    def test_a_failing_read_marks_the_reading_failed_with_the_reason(self, api, monkeypatch) -> None:
        _photo_type(api.db)
        with TestClient(app) as client:
            response = _upload(client)
            reading_id = response.json()["id"]
            # The stored PDF vanishes before the worker reads it back.
            reading = api.db.query(CataloguePhotoReading).filter_by(id=reading_id).one()
            from app.models.resources import Attachment

            pdf = api.db.query(Attachment).filter_by(id=str(reading.pdf_attachment_id)).one()
            api.storage.objects.pop(pdf.file_path, None)
            _run(api, reading_id)
            detail = _detail(client, reading_id)

        assert detail["status"] == "failed"
        assert detail["error"]


# --------------------------------------------------------------------------- #
# Look-alikes  (AC-9)
# --------------------------------------------------------------------------- #
class TestLookAlike:
    def test_a_reencoded_copy_of_an_existing_photo_is_a_duplicate_defaulting_to_skip(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        existing, _ = _existing_photo(api.db, api.storage, products[CODE_A], SEED_A)
        _existing_photo(api.db, api.storage, products[CODE_B], SEED_OTHER)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            detail = _detail(client, reading_id)
            duplicates = _tab(client, reading_id, "duplicate")["data"]
            ready = _tab(client, reading_id, "ready")["data"]

        assert [d["printed_code"] for d in duplicates] == [CODE_A]
        row = duplicates[0]
        assert row["decision"] == "skip"
        assert row["duplicate"]["attachment_id"] == str(existing.id)
        assert row["duplicate"]["thumbnail_url"]
        assert 0 <= row["duplicate"]["distance"] <= 10
        assert [r["printed_code"] for r in ready] == [CODE_B]
        assert ready[0]["duplicate"] is None
        assert detail["counts"] == {"ready": 1, "duplicate": 1, "needs_product": 1,
                                    "skipped": 0, "to_attach": 1}

    def test_an_unrelated_existing_photo_is_not_a_duplicate(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        _existing_photo(api.db, api.storage, products[CODE_A], SEED_OTHER)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            duplicates = _tab(client, reading_id, "duplicate")["data"]
            ready = _tab(client, reading_id, "ready")["data"]

        assert duplicates == []
        assert {r["printed_code"] for r in ready} == {CODE_A, CODE_B}


# --------------------------------------------------------------------------- #
# GET lists  (AC-5, AC-19)
# --------------------------------------------------------------------------- #
class TestReview:
    def test_counts_match_the_tab_definitions(self, api) -> None:
        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            detail = _detail(client, reading_id)
            totals = {tab: _tab(client, reading_id, tab)["pagination"]["total"]
                      for tab in ("ready", "duplicate", "needs_product", "skipped")}

        assert detail["counts"] == {"ready": 2, "duplicate": 0, "needs_product": 1,
                                    "skipped": 0, "to_attach": 2}
        assert totals == {"ready": 2, "duplicate": 0, "needs_product": 1, "skipped": 0}

    def test_pagination_respects_page_and_limit(self, api) -> None:
        # No products seeded, so all three rows need a product.
        with TestClient(app) as client:
            reading_id = _read(api, client)
            first = _tab(client, reading_id, "needs_product", page=1, limit=2)
            second = _tab(client, reading_id, "needs_product", page=2, limit=2)

        assert first["pagination"]["total"] == 3
        assert len(first["data"]) == 2
        assert len(second["data"]) == 1
        ids = [i["id"] for i in first["data"]] + [i["id"] for i in second["data"]]
        assert len(set(ids)) == 3

    def test_sort_by_printed_code_and_page_both_directions(self, api) -> None:
        with TestClient(app) as client:
            reading_id = _read(api, client)

            def coded(**params):
                data = _tab(client, reading_id, "needs_product", limit=50, **params)["data"]
                return [i["printed_code"] for i in data if i["printed_code"]]

            assert coded(sort="printed_code", dir="asc") == [CODE_B, CODE_A]
            assert coded(sort="printed_code", dir="desc") == [CODE_A, CODE_B]
            by_page_asc = _tab(client, reading_id, "needs_product", limit=50,
                               sort="page", dir="asc")["data"]
            by_page_desc = _tab(client, reading_id, "needs_product", limit=50,
                                sort="page", dir="desc")["data"]
            default = _tab(client, reading_id, "needs_product", limit=50)["data"]

        assert [i["id"] for i in by_page_asc] == [i["id"] for i in default]
        assert [i["id"] for i in by_page_desc] == [i["id"] for i in by_page_asc][::-1]
        positions = [(i["page"], i["position"]) for i in by_page_asc]
        assert positions == sorted(positions)

    def test_another_companys_reading_is_404_everywhere(self, api) -> None:
        other = _company(api.db)
        api.in_company(other)
        with TestClient(app) as client:
            created = _upload(client)
            assert created.status_code == 201, created.text
            reading_id = created.json()["id"]
            api.in_company(SORENTO)
            fake_photo = str(uuid.uuid4())

            assert client.get(f"{PREFIX}/{reading_id}").status_code == 404
            assert client.get(f"{PREFIX}/{reading_id}/photos",
                              params={"tab": "ready"}).status_code == 404
            assert client.patch(f"{PREFIX}/{reading_id}/photos/{fake_photo}",
                                json={"decision": "skip"}).status_code == 404
            assert client.post(f"{PREFIX}/{reading_id}/attach").status_code == 404

    def test_a_user_without_view_is_forbidden(self, api) -> None:
        with TestClient(app) as client:
            reading_id = _read(api, client)
            api.as_user(NOPERM_ID)
            assert client.get(f"{PREFIX}/{reading_id}").status_code == 403
            assert client.get(f"{PREFIX}/{reading_id}/photos",
                              params={"tab": "ready"}).status_code == 403


# --------------------------------------------------------------------------- #
# PATCH  (AC-8, AC-10, AC-19)
# --------------------------------------------------------------------------- #
class TestPatch:
    def _world(self, api, client):
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        reading_id = _read(api, client)
        items = _all_items(client, reading_id)
        return reading_id, items, products

    def test_assigning_a_product_to_a_row_without_a_code_moves_it_to_ready(self, api) -> None:
        with TestClient(app) as client:
            reading_id, items, _ = self._world(api, client)
            pick = _product(api.db, "ZZTPICK1234")
            row = _by_code(items, None)

            response = client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                    json={"product_id": str(pick.id)})
            ready = _tab(client, reading_id, "ready")["data"]
            needs = _tab(client, reading_id, "needs_product")["data"]
            detail = _detail(client, reading_id)

        assert response.status_code == 200, response.text
        moved = [i for i in ready if i["id"] == row["id"]]
        assert moved and moved[0]["product"]["product_code"] == "ZZTPICK1234"
        assert needs == []
        assert detail["counts"]["ready"] == 3 and detail["counts"]["needs_product"] == 0

    def test_a_product_of_another_company_is_404(self, api) -> None:
        other = _company(api.db)
        foreign = _product(api.db, "ZZTFOREIGN99", company_id=other)
        with TestClient(app) as client:
            reading_id, items, _ = self._world(api, client)
            row = _by_code(items, None)

            response = client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                    json={"product_id": str(foreign.id)})

        assert response.status_code == 404, response.text

    @pytest.mark.parametrize("decision", ["keep_both", "replace"])
    def test_keep_both_and_replace_need_a_lookalike(self, api, decision) -> None:
        with TestClient(app) as client:
            reading_id, items, _ = self._world(api, client)
            row = _by_code(items, CODE_A)

            response = client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                    json={"decision": decision})

        assert response.status_code == 422, response.text

    def test_skip_moves_a_row_to_skipped_and_restore_brings_it_back(self, api) -> None:
        with TestClient(app) as client:
            reading_id, items, _ = self._world(api, client)
            row = _by_code(items, CODE_A)
            url = f"{PREFIX}/{reading_id}/photos/{row['id']}"

            assert client.patch(url, json={"decision": "skip"}).status_code == 200
            skipped = _tab(client, reading_id, "skipped")["data"]
            after_skip = _detail(client, reading_id)["counts"]
            assert client.patch(url, json={"decision": "attach"}).status_code == 200
            ready = _tab(client, reading_id, "ready")["data"]
            skipped_again = _tab(client, reading_id, "skipped")["data"]

        assert [i["id"] for i in skipped] == [row["id"]]
        assert after_skip["skipped"] == 1 and after_skip["ready"] == 1
        assert after_skip["to_attach"] == 1
        assert row["id"] in [i["id"] for i in ready] and skipped_again == []

    def test_ticking_an_also_attach_product_is_stored(self, api) -> None:
        with TestClient(app) as client:
            reading_id, items, products = self._world(api, client)
            row = _by_code(items, CODE_B)

            response = client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                    json={"also_attach_product_ids": [str(products[CODE_W].id)]})
            ready = _tab(client, reading_id, "ready")["data"]

        assert response.status_code == 200, response.text
        assert _by_code(ready, CODE_B)["also_attach_product_ids"] == [str(products[CODE_W].id)]

    def test_patching_without_dealer_kit_edit_is_forbidden(self, api) -> None:
        with TestClient(app) as client:
            reading_id, items, _ = self._world(api, client)
            row = _by_code(items, CODE_A)
            api.as_user(VIEWER_ID)

            response = client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                    json={"decision": "skip"})

        assert response.status_code == 403

    def test_an_attached_row_cannot_be_changed(self, api) -> None:
        with TestClient(app) as client:
            reading_id, items, _ = self._world(api, client)
            row = _by_code(items, CODE_A)
            assert client.post(f"{PREFIX}/{reading_id}/attach").status_code == 200

            response = client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                    json={"decision": "skip"})

        assert response.status_code == 409, response.text


# --------------------------------------------------------------------------- #
# POST attach  (AC-13 to AC-18)
# --------------------------------------------------------------------------- #
class TestAttach:
    def _photo(self, api, reading_id, code):
        rows = api.db.query(CataloguePhoto).filter_by(reading_id=reading_id).all()
        return next(r for r in rows if r.printed_code == code)

    def test_attach_needs_both_permissions(self, api) -> None:
        _photo_type(api.db)
        _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            api.as_user(EDITOR_ID)

            response = client.post(f"{PREFIX}/{reading_id}/attach")
            api.as_user(VIEWER_ID)
            viewer = client.post(f"{PREFIX}/{reading_id}/attach")

        assert response.status_code == 403
        assert viewer.status_code == 403
        assert "master_data.products.edit" in response.text

    def test_ready_rows_and_ticked_products_are_linked_with_exact_counts(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            items = _all_items(client, reading_id)
            row_b = _by_code(items, CODE_B)
            row_c = _by_code(items, None)
            pick = _product(api.db, "ZZTPICK1234")
            client.patch(f"{PREFIX}/{reading_id}/photos/{row_b['id']}",
                         json={"also_attach_product_ids": [str(products[CODE_W].id)]})
            client.patch(f"{PREFIX}/{reading_id}/photos/{row_c['id']}",
                         json={"product_id": str(pick.id)})

            response = client.post(f"{PREFIX}/{reading_id}/attach")
            after = _all_items(client, reading_id)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["attached"] == 4  # A->A, B->B, B->W, C->pick
        assert body["replaced"] == 0
        assert body["skipped"] == 0
        assert body["products"] == 4
        photo_a = self._photo(api, reading_id, CODE_A)
        photo_b = self._photo(api, reading_id, CODE_B)
        links_a = _links(api.db, products[CODE_A])
        assert [str(l.attachment_id) for l in links_a] == [str(photo_a.attachment_id)]
        for product in (products[CODE_B], products[CODE_W]):
            assert [str(l.attachment_id) for l in _links(api.db, product)] == [
                str(photo_b.attachment_id)]
        assert len(_links(api.db, pick)) == 1
        api.db.expire_all()
        for row in api.db.query(CataloguePhoto).filter_by(reading_id=reading_id):
            assert row.attached_at is not None
        assert all(i["attached_at"] for i in after)

    def test_a_lone_auto_shown_photo_is_pinned_before_the_new_link(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        old, old_link = _existing_photo(api.db, api.storage, products[CODE_A],
                                        SEED_OTHER, primary=None)
        assert not old_link.is_primary
        with TestClient(app) as client:
            reading_id = _read(api, client)
            assert client.post(f"{PREFIX}/{reading_id}/attach").status_code == 200

        photo_a = self._photo(api, reading_id, CODE_A)
        by_attachment = {str(l.attachment_id): l for l in _links(api.db, products[CODE_A])}
        assert by_attachment[str(old.id)].is_primary is True
        assert not by_attachment[str(photo_a.attachment_id)].is_primary

    def test_replace_unlinks_only_the_lookalike_and_keeps_the_file(self, api) -> None:
        from app.models.resources import Attachment

        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        lookalike, _ = _existing_photo(api.db, api.storage, products[CODE_A], SEED_A)
        other, _ = _existing_photo(api.db, api.storage, products[CODE_A], SEED_OTHER)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            row = _by_code(_tab(client, reading_id, "duplicate")["data"], CODE_A)
            assert client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                json={"decision": "replace"}).status_code == 200

            response = client.post(f"{PREFIX}/{reading_id}/attach")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["replaced"] == 1 and body["attached"] == 1
        photo_a = self._photo(api, reading_id, CODE_A)
        linked = {str(l.attachment_id) for l in _links(api.db, products[CODE_A])}
        assert linked == {str(other.id), str(photo_a.attachment_id)}
        assert api.db.query(Attachment).filter_by(id=str(lookalike.id)).count() == 1

    def test_keep_both_keeps_the_old_link_and_adds_the_new(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        lookalike, _ = _existing_photo(api.db, api.storage, products[CODE_A], SEED_A)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            row = _by_code(_tab(client, reading_id, "duplicate")["data"], CODE_A)
            assert client.patch(f"{PREFIX}/{reading_id}/photos/{row['id']}",
                                json={"decision": "keep_both"}).status_code == 200

            response = client.post(f"{PREFIX}/{reading_id}/attach")

        body = response.json()
        assert response.status_code == 200 and body["replaced"] == 0
        photo_a = self._photo(api, reading_id, CODE_A)
        linked = {str(l.attachment_id) for l in _links(api.db, products[CODE_A])}
        assert linked == {str(lookalike.id), str(photo_a.attachment_id)}

    def test_a_defaulted_skip_and_a_skipped_row_are_not_linked(self, api) -> None:
        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        lookalike, _ = _existing_photo(api.db, api.storage, products[CODE_A], SEED_A)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            row_b = _by_code(_tab(client, reading_id, "ready")["data"], CODE_B)
            client.patch(f"{PREFIX}/{reading_id}/photos/{row_b['id']}",
                         json={"decision": "skip"})

            response = client.post(f"{PREFIX}/{reading_id}/attach")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["attached"] == 0 and body["replaced"] == 0
        assert [str(l.attachment_id) for l in _links(api.db, products[CODE_A])] == [
            str(lookalike.id)]
        assert _links(api.db, products[CODE_B]) == []

    def test_a_photo_already_linked_to_that_product_is_not_linked_twice(self, api) -> None:
        from app.models.product import ProductAttachment
        from app.models.resources import Attachment

        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            photo_a = self._photo(api, reading_id, CODE_A)
            # The same bytes are already on file for the product, as another file.
            twin = Attachment(id=str(uuid.uuid4()), original_filename="twin.jpg",
                              stored_filename="twin.jpg", file_path="zzt/twin.jpg",
                              file_hash=photo_a.sha256, mime_type="image/jpeg",
                              storage_provider="s3")
            api.db.add(twin)
            api.db.flush()
            api.db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=products[CODE_A].id,
                                         attachment_id=twin.id))
            api.db.commit()

            response = client.post(f"{PREFIX}/{reading_id}/attach")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["skipped"] == 1
        assert body["attached"] == 1  # only B
        assert [str(l.attachment_id) for l in _links(api.db, products[CODE_A])] == [
            str(twin.id)]

    def test_attaching_twice_adds_nothing_the_second_time(self, api) -> None:
        from app.models.product import ProductAttachment

        _photo_type(api.db)
        products = _seed_catalogue_products(api.db)
        with TestClient(app) as client:
            reading_id = _read(api, client)
            first = client.post(f"{PREFIX}/{reading_id}/attach")
            api.db.expire_all()
            links_after_first = api.db.query(ProductAttachment).count()

            second = client.post(f"{PREFIX}/{reading_id}/attach")
            api.db.expire_all()

        assert first.status_code == 200 and first.json()["attached"] == 2
        assert second.status_code == 200, second.text
        assert second.json()["attached"] == 0 and second.json()["replaced"] == 0
        assert api.db.query(ProductAttachment).count() == links_after_first
