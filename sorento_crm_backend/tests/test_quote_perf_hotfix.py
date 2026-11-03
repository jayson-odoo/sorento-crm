"""QUOTE-PERF-HOTFIX (3 Nov): the spec sheet preview, its PDF export and the customer's sign page
must not load full-size originals or hold a DB connection while pictures are fetched.

Red first. Postgres only via ``blank_session``; helpers are the spec sheet and PDF suites' own.
"""
from __future__ import annotations

import io
import json

import pytest

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import _FakeBackend, _attachment, _photo_bytes
from .test_project_spec_sheet import _chain, _templates


# ------------------------------------------------------------------ spec sheet


def _with_line_media(db, c):
    from app.models.projects import ProjectQuotationLine

    photo = _attachment(db, c["company_id"], "basin.png")
    photo.thumbnail_path = "https://cdn.zzt.test/products/zzt/basin-thumb.jpg"
    drawing = _attachment(db, c["company_id"], "basin-drawing.png")
    line = (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.product_id == c["basin"].id)
        .one()
    )
    line.image_attachment_id = photo.id
    line.drawing_attachment_id = drawing.id
    db.flush()
    return photo, drawing


def _settings(db, c):
    from app.services import project_spec_sheet_service as spec

    t = _templates(db, c)
    spec.save_settings(
        db, c["document"], {"cover_template_id": t["cover"].id, "page_template_id": t["page"].id}
    )


def test_the_on_screen_preview_signs_thumbnails_not_originals(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec

    asked = []

    def fake_preview_urls(db, ids, full=False):
        asked.append(full)
        return {i: f"https://signed.zzt.test/{'full' if full else 'thumb'}/{i}" for i in ids if i}

    monkeypatch.setattr(images, "preview_urls", fake_preview_urls)
    with blank_session() as db:
        c = _chain(db)
        photo, _drawing = _with_line_media(db, c)
        _settings(db, c)

        payload = spec.build_print_payload(db, c["document"], c["issue"])

        assert asked and not any(asked)
        assert payload["images"][photo.id].startswith("https://signed.zzt.test/thumb/")


def test_export_cap_is_the_page_long_edge_at_200_dpi():
    from app.services import project_spec_sheet_service as spec

    assert spec.export_cap_px((420, 297)) == 3308
    assert spec.export_cap_px((338.7, 190.5)) == 2667


def _download(db, c):
    from app.models.download import UserDownload
    from app.services import project_spec_sheet_service as spec

    row = UserDownload(
        user_id=c["owner"],
        kind=spec.KIND,
        source_entity_type="quotation_issue",
        source_entity_id=c["issue"].id,
        status="pending",
        filename="spec-sheet-x.pdf",
    )
    db.add(row)
    db.flush()
    return row


class _Store:
    """Storage stand-in: originals by key, and what the export uploads."""

    def __init__(self, originals):
        self.originals = originals
        self.uploads = {}
        self.downloads = []

    def download_file(self, key):
        self.downloads.append(key)
        if key in self.uploads:
            return self.uploads[key]
        if key not in self.originals:
            raise RuntimeError("gone")
        return self.originals[key]

    def upload_file(self, file_content, file_path, content_type=None, **_kw):
        self.uploads[file_path] = file_content
        return file_path, f"https://signed.zzt.test/{file_path}"


def test_export_downscales_big_originals_to_the_cap_and_the_print_payload_uses_them(monkeypatch):
    from PIL import Image

    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    with blank_session() as db:
        c = _chain(db)
        photo, drawing = _with_line_media(db, c)
        _settings(db, c)
        download = _download(db, c)

        store = _Store(
            {
                extract_key(photo.file_path): _photo_bytes(4000, 2000),
                extract_key(drawing.file_path): _photo_bytes(800, 600, seed=1),
            }
        )
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")
        signed = []

        def fake_sign(source, *, provider=None, expires_in=3600, strict=False):
            signed.append(source)
            return f"https://signed.zzt.test/{source}"

        monkeypatch.setattr(spec, "resolve_signed_url", fake_sign)
        monkeypatch.setattr(
            images,
            "preview_urls",
            lambda db, ids, full=False: {i: f"https://fallback/{full}/{i}" for i in ids if i},
        )

        manifest = spec.prepare_export_images(db, download)

        # The 4000 px photo is downscaled to the 200 dpi cap of a 338.7 mm page; the small
        # drawing is printed from its own original, untouched.
        cap = spec.export_cap_px((338.7, 190.5))
        capped_key = manifest[photo.id]["key"]
        with Image.open(io.BytesIO(store.uploads[capped_key])) as im:
            assert max(im.size) == cap
        assert manifest[drawing.id]["key"] == drawing.file_path

        payload = spec.print_payload_for_download(db, download)
        assert payload["images"][photo.id] == f"https://signed.zzt.test/{capped_key}"
        assert payload["images"][drawing.id] == f"https://signed.zzt.test/{drawing.file_path}"


def test_an_export_without_a_manifest_still_prints_originals(monkeypatch):
    """A render queued before this shipped, or a failed prep, prints exactly as before."""
    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        photo, _drawing = _with_line_media(db, c)
        _settings(db, c)
        download = _download(db, c)
        monkeypatch.setattr(spec, "_storage", lambda provider=None: _Store({}))
        monkeypatch.setattr(
            images,
            "preview_urls",
            lambda db, ids, full=False: {i: f"https://x/{'full' if full else 'thumb'}/{i}" for i in ids if i},
        )

        payload = spec.print_payload_for_download(db, download)
        assert payload["images"][photo.id] == f"https://x/full/{photo.id}"


def test_the_export_task_prepares_capped_images_before_rendering(monkeypatch):
    from app.tasks import dealer_kit_export_tasks as tasks

    src = open(tasks.__file__).read()
    body = src[src.index("def generate_spec_sheet_pdf") :]
    body = body[: body.index("\ndef ", 10)]
    assert body.index("prepare_export_images") < body.index("_render_pdf(")


def test_renders_run_one_at_a_time_on_the_batch_worker_only():
    import worker

    roles = [role for name, role in worker.QUEUES if name == "catalogue_render"]
    assert roles == ["batch"]


# ------------------------------------------------------------------ sign page


def _sign_issue(db, monkeypatch, *, photos=1, thumbnails=True):
    """One scope, ``photos`` lines each with a distinct photo and drawing."""
    from app.models.projects import ProjectQuotationLine
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    from .test_project_quotation_pdf import MARKER, _issue, _product, _setup

    env = _setup(db)
    owner = env["owner"]
    document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
    scope = qdocs.add_scope(db, document=document, scope_label=f"{MARKER} A", actor_user_id=owner)
    version = quotes.current_version(db, scope.id)
    for n in range(photos):
        product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} item {n}")
        made = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "10.00", "quantity": 1},
        )
        photo = _attachment(db, env["company_id"], f"p{n}.png")
        drawing = _attachment(db, env["company_id"], f"d{n}.png")
        if thumbnails:
            photo.thumbnail_path = f"https://cdn.zzt.test/thumbs/p{n}.jpg"
            drawing.thumbnail_path = f"https://cdn.zzt.test/thumbs/d{n}.jpg"
        line = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == made.id).one()
        line.image_attachment_id = photo.id
        line.drawing_attachment_id = drawing.id
    db.flush()
    return _issue(db, document, owner)


@pytest.fixture(autouse=True)
def _fresh_sign_cache():
    from app.services import project_quotation_document_service as qdocs

    qdocs._SIGN_PICTURES.clear()
    yield
    qdocs._SIGN_PICTURES.clear()


def test_the_sign_page_reads_thumbnails_when_they_exist(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=2)
        backend = _FakeBackend(_photo_bytes(320, 320))
        monkeypatch.setattr(images, "get_backend", lambda provider: backend)

        page = qdocs.serialize_sign_page(db, issued)

        assert page["scopes"][0]["lines"][0]["image_url"].startswith("data:image/jpeg;base64,")
        assert backend.keys and all("thumbs/" in key for key in backend.keys)


def test_the_sign_page_inlines_at_most_60_pictures(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=35)  # 70 pictures
        backend = _FakeBackend(_photo_bytes(64, 64))
        monkeypatch.setattr(images, "get_backend", lambda provider: backend)

        page = qdocs.serialize_sign_page(db, issued)
        lines = page["scopes"][0]["lines"]
        shown = [
            v for line in lines for v in (line["image_url"], line["drawing_url"]) if v
        ]

        assert len(shown) == qdocs.SIGN_PICTURES_PER_PAGE == 60
        assert len(backend.keys) == 60
        # In page order: the first lines carry theirs, the tail does not.
        assert lines[0]["image_url"] and lines[0]["drawing_url"]
        assert lines[-1]["image_url"] is None and lines[-1]["drawing_url"] is None


def test_a_failed_picture_is_not_refetched_within_ten_minutes(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    class Broken(_FakeBackend):
        def download_file(self, key):
            self.keys.append(key)
            raise RuntimeError("storage down")

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=1)
        backend = Broken()
        monkeypatch.setattr(images, "get_backend", lambda provider: backend)
        clock = [1000.0]
        monkeypatch.setattr(qdocs, "_sign_clock", lambda: clock[0])

        qdocs.serialize_sign_page(db, issued)
        assert len(backend.keys) == 2
        clock[0] += 9 * 60
        qdocs.serialize_sign_page(db, issued)
        assert len(backend.keys) == 2  # cached miss
        clock[0] += 2 * 60
        qdocs.serialize_sign_page(db, issued)
        assert len(backend.keys) == 4  # retried after ~10 min


def test_no_picture_is_fetched_for_a_column_the_page_does_not_show(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs
    from app.services import quotation_columns

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=1)
        backend = _FakeBackend(_photo_bytes(64, 64))
        monkeypatch.setattr(images, "get_backend", lambda provider: backend)
        # The page shows no image column at all (a future column set that drops it).
        monkeypatch.setattr(
            quotation_columns,
            "for_lines",
            lambda lines: [c for c in quotation_columns.COLUMNS if c[0] not in ("image", "spec")],
        )

        page = qdocs.serialize_sign_page(db, issued)
        line = page["scopes"][0]["lines"][0]

        assert line["image_url"] is None and line["drawing_url"] is None
        assert backend.keys == []


def test_the_db_connection_is_released_before_any_picture_is_fetched(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    events = []

    class Recording(_FakeBackend):
        def download_file(self, key):
            events.append("fetch")
            return super().download_file(key)

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=1)
        monkeypatch.setattr(
            images, "get_backend", lambda provider: Recording(_photo_bytes(64, 64))
        )

        page = qdocs.serialize_sign_page(db, issued, release=lambda: events.append("release"))

        assert events[0] == "release" and events.count("fetch") == 2
        assert page["scopes"][0]["lines"][0]["image_url"].startswith("data:")


def test_the_public_route_releases_its_session_before_pictures(monkeypatch):
    from app.api.v1.public import quotation_sign

    src = open(quotation_sign.__file__).read()
    body = src[src.index("def read_quotation_for_signing") :]
    body = body[: body.index("\n@router")]
    assert "release=db.close" in body
