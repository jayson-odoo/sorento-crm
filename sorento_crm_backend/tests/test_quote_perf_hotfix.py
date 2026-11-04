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
from .test_project_spec_sheet import _chain, _sheet, _template, _templates


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


def _image_layer(slot, width, height, part=None, layer_id=None):
    props = {"kind": "image", "fit": "contain"}
    if part is not None:
        props["subjectPart"] = part
    return {
        "id": layer_id or f"img-{slot}-{part}",
        "type": "image",
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": width,
        "height_mm": height,
        "rotation_deg": 0,
        "z_index": 0,
        "slot_binding": slot,
        "props": props,
    }


def _boxed_templates(db, c, photo_mm=100, drawing_mm=60, extra=()):
    """Page templates whose photo slot is a photo_mm x 0.8 photo_mm box and drawing slot a
    drawing_mm box: the designed boxes the export caps each picture to."""
    layers = [
        _image_layer("product_image", photo_mm, photo_mm * 0.8),
        _image_layer("drawing", drawing_mm, drawing_mm * 0.6),
        *extra,
    ]
    return {
        "cover": _template(db, c["company_id"], "spec_cover"),
        "page": _template(db, c["company_id"], "spec_page", layers=layers),
        "single": _template(db, c["company_id"], "spec_page", layers=layers),
    }


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
        sheet = _sheet(db, c)

        payload = spec.build_print_payload(db, sheet)

        assert asked and not any(asked)
        assert payload["images"][photo.id].startswith("https://signed.zzt.test/thumb/")


def test_export_pixel_caps_are_the_layer_box_at_300_dpi():
    from app.services import project_spec_sheet_service as spec

    assert spec.EXPORT_DPI == 300
    assert spec.px_for_mm(100) == 1182
    assert spec.px_for_mm(25.4) == 300
    # The fallback for a picture no image layer is found for: the page's long edge.
    assert spec.export_cap_px((420, 297)) == 4961
    assert spec.export_cap_px((338.7, 190.5)) == 4001


def _download(db, c, sheet):
    from app.models.download import UserDownload
    from app.services import project_spec_sheet_service as spec

    row = UserDownload(
        user_id=c["owner"],
        kind=spec.KIND,
        source_entity_type="quotation_spec_sheet",
        source_entity_id=sheet.id,
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


def _fake_sign(monkeypatch, spec):
    signed = []

    def fake_sign(source, *, provider=None, expires_in=3600, strict=False):
        signed.append(source)
        return f"https://signed.zzt.test/{source}"

    monkeypatch.setattr(spec, "resolve_signed_url", fake_sign)
    return signed


def test_export_downscales_each_picture_to_its_own_box_and_the_print_payload_uses_the_copies(monkeypatch):
    from PIL import Image

    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    with blank_session() as db:
        c = _chain(db)
        photo, drawing = _with_line_media(db, c)
        sheet = _sheet(db, c, templates=_boxed_templates(db, c))  # photo box 100 mm, drawing 60 mm
        download = _download(db, c, sheet)
        store = _Store(
            {
                extract_key(photo.file_path): _photo_bytes(4000, 2000),
                extract_key(drawing.file_path): _photo_bytes(600, 400, seed=1),
            }
        )
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")
        _fake_sign(monkeypatch, spec)
        monkeypatch.setattr(
            images,
            "preview_urls",
            lambda db, ids, full=False: {i: f"https://fallback/{full}/{i}" for i in ids if i},
        )

        manifest = spec.prepare_export_images(db, download)

        # The photo is capped to its 100 mm box at 300 dpi; the 600 px drawing is already under
        # its 60 mm cap (709 px), so it prints from its original and is never upscaled.
        capped_key = manifest[photo.id]["key"]
        with Image.open(io.BytesIO(store.uploads[capped_key])) as im:
            assert max(im.size) == spec.px_for_mm(100) == 1182
        assert manifest[drawing.id]["key"] == drawing.file_path

        payload = spec.print_payload_for_download(db, download)
        assert payload["images"][photo.id] == f"https://signed.zzt.test/{capped_key}"
        assert payload["images"][drawing.id] == f"https://signed.zzt.test/{drawing.file_path}"


def test_a_41_page_sheet_of_4000_by_3000_pictures_gets_a_copy_within_each_box_never_upscaled(monkeypatch):
    from PIL import Image

    from app.models.projects import ProjectQuotationLine
    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    from .test_project_quotation_pdf import _issue, _product, _setup
    from .test_project_spec_sheet import MARKER, _document, _line, _scope

    def flat(width, height):
        buffer = io.BytesIO()
        Image.new("RGB", (width, height), (90, 120, 160)).save(buffer, format="JPEG", quality=60)
        return buffer.getvalue()

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        scope = _scope(db, env, document)
        originals, photos = {}, []
        big, small = flat(4000, 3000), flat(500, 300)
        for n in range(41):
            product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} p{n}")
            line = _line(db, env, scope, {"product_id": product.id})
            att = _attachment(db, env["company_id"], f"p{n}.jpg")
            db.get(ProjectQuotationLine, line.id).image_attachment_id = att.id
            originals[extract_key(att.file_path)] = small if n == 40 else big
            photos.append(att)
        db.flush()
        issue = _issue(db, document, env["owner"])
        c = {**env, "document": document, "issue": issue}
        sheet = _sheet(db, c, templates=_boxed_templates(db, c))
        assert sheet.page_count == 42
        download = _download(db, c, sheet)
        store = _Store(originals)
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")
        _fake_sign(monkeypatch, spec)

        manifest = spec.prepare_export_images(db, download)

        cap = spec.px_for_mm(100)
        assert len(manifest) == 41
        for n, att in enumerate(photos):
            entry = manifest[att.id]
            if n == 40:
                assert entry["key"] == att.file_path  # 500 px: under its cap, kept as is
                continue
            with Image.open(io.BytesIO(store.uploads[entry["key"]])) as im:
                assert max(im.size) == cap
                assert im.width >= im.height  # the 4:3 shape is kept

        payload = spec.print_payload_for_download(db, download)
        for att in photos[:3]:
            assert payload["images"][att.id] == f"https://signed.zzt.test/{manifest[att.id]['key']}"


def test_with_no_image_layer_found_a_picture_falls_back_to_the_page_long_edge_at_300_dpi(monkeypatch):
    from PIL import Image

    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    with blank_session() as db:
        c = _chain(db)
        photo, drawing = _with_line_media(db, c)
        sheet = _sheet(db, c)  # the standard templates carry no image layer
        download = _download(db, c, sheet)
        store = _Store(
            {
                extract_key(photo.file_path): _big_jpeg(),
                extract_key(drawing.file_path): _photo_bytes(800, 600, seed=1),
            }
        )
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")

        manifest = spec.prepare_export_images(db, download)

        with Image.open(io.BytesIO(store.uploads[manifest[photo.id]["key"]])) as im:
            assert max(im.size) == spec.export_cap_px((338.7, 190.5)) == 4001
        assert manifest[drawing.id]["key"] == drawing.file_path


def test_an_accessory_part_slot_sets_the_cap_of_its_own_picture(monkeypatch):
    """subjectPart N draws accessory N's picture: a big part slot lifts that picture's cap only."""
    from PIL import Image

    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    with blank_session() as db:
        c = _chain(db)
        photo, _drawing = _with_line_media(db, c)
        part_photo = _attachment(db, c["company_id"], "valve.png")
        sheet = _sheet(
            db,
            c,
            templates=_boxed_templates(
                db, c, photo_mm=50, extra=[_image_layer("product_image", 200, 150, part=0, layer_id="part0")]
            ),
        )
        # The WC set's first accessory (the valve) has this picture; its page is the set page.
        monkeypatch.setattr(
            spec,
            "_files",
            lambda db_, ids: {str(i): {"photo": part_photo.id, "drawing": None} for i in ids if str(i) == str(c["valve"].id)},
        )
        download = _download(db, c, sheet)
        store = _Store(
            {
                extract_key(photo.file_path): _photo_bytes(3000, 2000),
                extract_key(part_photo.file_path): _photo_bytes(3000, 2000, seed=2),
            }
        )
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")

        manifest = spec.prepare_export_images(db, download)

        with Image.open(io.BytesIO(store.uploads[manifest[photo.id]["key"]])) as im:
            assert max(im.size) == spec.px_for_mm(50)
        with Image.open(io.BytesIO(store.uploads[manifest[part_photo.id]["key"]])) as im:
            assert max(im.size) == spec.px_for_mm(200)


def test_an_export_without_a_manifest_still_prints_originals(monkeypatch):
    """A render queued before this shipped, or a failed prep, prints exactly as before."""
    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        photo, _drawing = _with_line_media(db, c)
        sheet = _sheet(db, c)
        download = _download(db, c, sheet)
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


class _MediumStore(_Store):
    def file_exists(self, key):
        return key in self.uploads


def _open_page_env(db, monkeypatch, original: bytes):
    from app.services import product_image_service as images
    from app.services.storage_router import extract_key

    c = _chain(db)
    photo, drawing = _with_line_media(db, c)
    sheet = _sheet(db, c)
    store = _MediumStore(
        {
            extract_key(photo.file_path): original,
            extract_key(drawing.file_path): _photo_bytes(800, 600, seed=1),
        }
    )
    monkeypatch.setattr(images, "get_backend", lambda provider: store)
    signed = []

    def fake_sign(source, *, provider=None, expires_in=3600, strict=False):
        signed.append(source)
        return f"https://signed.zzt.test/{source}"

    monkeypatch.setattr(images, "resolve_signed_url", fake_sign)
    images._medium_cache.clear()
    return c, sheet, photo, drawing, store, signed


def test_a_pasted_asset_is_never_signed_as_its_original_on_screen(monkeypatch):
    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment
    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    from .test_project_spec_sheets_v2 import _asset, _asset_layer

    with blank_session() as db:
        c, sheet, _photo, _drawing, store, signed = _open_page_env(db, monkeypatch, _photo_bytes(600, 600))
        logo = _asset(db, c["company_id"])
        attachment = db.get(Attachment, db.get(Asset, logo.id).attachment_id)
        store.originals[extract_key(attachment.file_path)] = _big_jpeg(4000, 3000)
        spec.save_page_edit(db, sheet, c["basin"].id, [_asset_layer(logo.id)])

        payload = spec.build_print_payload(db, sheet, keys=[c["basin"].id])
        design = spec.design(db, sheet, c["basin"].id)

        assert ".medium.jpg" in payload["assets"][logo.id]
        assert ".medium.jpg" in design["assets"][logo.id]
        assert attachment.file_path not in signed


def test_a_library_asset_is_capped_to_its_layer_box_in_the_export(monkeypatch):
    from PIL import Image

    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment
    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    from .test_project_spec_sheets_v2 import _asset

    with blank_session() as db:
        c = _chain(db)
        logo = _asset(db, c["company_id"])
        attachment = db.get(Attachment, db.get(Asset, logo.id).attachment_id)
        art = {
            "id": "logo-layer",
            "type": "image",
            "x_mm": 0,
            "y_mm": 0,
            "width_mm": 50,
            "height_mm": 30,
            "props": {"kind": "image", "source": {"type": "asset", "assetId": logo.id}},
        }
        sheet = _sheet(db, c, templates=_boxed_templates(db, c, extra=[art]))
        download = _download(db, c, sheet)
        store = _Store({extract_key(attachment.file_path): _photo_bytes(4000, 3000)})
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")
        _fake_sign(monkeypatch, spec)

        manifest = spec.prepare_export_images(db, download)

        with Image.open(io.BytesIO(store.uploads[manifest[attachment.id]["key"]])) as im:
            assert max(im.size) == spec.px_for_mm(50)
        payload = spec.print_payload_for_download(db, download)
        assert payload["assets"][logo.id] == f"https://signed.zzt.test/{manifest[attachment.id]['key']}"


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


def test_a_picture_with_no_thumbnail_reads_its_original_once_and_saves_a_thumbnail(monkeypatch):
    """Crew ruling (b): no visible change. The original is read once, a thumbnail is stored the
    way the upload path stores one, and every later render reads that thumbnail."""
    from app.models.resources import Attachment
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    class Store(_FakeBackend):
        def __init__(self, payload):
            super().__init__(payload)
            self.uploads = {}

        def download_file(self, key):
            self.keys.append(key)
            return self.uploads.get(key, self.payload)

        def upload_file(self, file_content, file_path, content_type=None, **_kw):
            self.uploads[file_path] = file_content
            return file_path, file_path

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=1, thumbnails=False)
        from app.services import storage_router

        store = Store(_photo_bytes(1200, 1200))
        monkeypatch.setattr(images, "get_backend", lambda provider: store)
        monkeypatch.setattr(
            storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.zzt.test/{key}"
        )

        first = qdocs.serialize_sign_page(db, issued)
        assert first["scopes"][0]["lines"][0]["image_url"].startswith("data:image/jpeg;base64,")
        assert store.keys and not any("thumb" in k for k in store.keys)
        assert len(store.uploads) == 2

        line = first["scopes"][0]["lines"][0]
        assert line["drawing_url"]
        saved = (
            db.query(Attachment)
            .filter(Attachment.original_filename.like("%zzt%"), Attachment.thumbnail_path.isnot(None))
            .count()
        )
        assert saved == 2

        qdocs._SIGN_PICTURES.clear()
        store.keys.clear()
        qdocs.serialize_sign_page(db, issued)
        assert len(store.keys) == 2
        assert all(k in store.uploads for k in store.keys)  # the stored thumbnails, not originals


# ------------------------------------------------------------------ review round 1


def _rotated_jpeg(width=4000, height=3000) -> bytes:
    """A landscape-stored JPEG tagged "rotate 90 CW" (EXIF 6): it displays as portrait."""
    from PIL import Image

    image = Image.new("RGB", (width, height), (200, 30, 30))
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def test_a_made_thumbnail_is_upright_and_flattened_on_white():
    from PIL import Image

    from app.services.image_thumbnailer import generate_thumbnail

    clear = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    buffer = io.BytesIO()
    clear.save(buffer, format="PNG")
    with Image.open(io.BytesIO(generate_thumbnail(buffer.getvalue(), "image/png"))) as thumb:
        assert thumb.getpixel((0, 0)) == (255, 255, 255)

    with Image.open(io.BytesIO(generate_thumbnail(_rotated_jpeg(), "image/jpeg"))) as thumb:
        assert thumb.height > thumb.width  # portrait, as the original displays


def test_an_export_copy_of_a_phone_photo_stays_upright(monkeypatch):
    from PIL import Image

    from app.services import project_spec_sheet_service as spec
    from app.services.storage_router import extract_key

    with blank_session() as db:
        c = _chain(db)
        photo, drawing = _with_line_media(db, c)
        sheet = _sheet(db, c, templates=_boxed_templates(db, c))
        download = _download(db, c, sheet)
        store = _Store(
            {
                extract_key(photo.file_path): _rotated_jpeg(),
                extract_key(drawing.file_path): _photo_bytes(800, 600, seed=1),
            }
        )
        monkeypatch.setattr(spec, "_storage", lambda provider=None: store)
        monkeypatch.setattr(spec, "_default_provider", lambda: "s3")

        manifest = spec.prepare_export_images(db, download)

        with Image.open(io.BytesIO(store.uploads[manifest[photo.id]["key"]])) as im:
            assert im.height > im.width
            assert max(im.size) == spec.px_for_mm(100)


def test_the_export_worker_holds_no_db_connection_during_the_render(monkeypatch):
    from app.services import project_spec_sheet_service as spec
    from app.tasks import dealer_kit_export_tasks as tasks

    events = []

    class Session:
        """A worker session stand-in that records whether it is open at render time."""

        def __init__(self):
            self.open = True

        def query(self, *_a, **_k):
            self.open = True
            return self

        def filter(self, *_a, **_k):
            return self

        def first(self):
            return type("D", (), {"filename": "x.pdf", "id": "d1", "kind": spec.KIND})()

        def close(self):
            self.open = False
            events.append("close")

        info: dict = {}

    session = Session()

    class Downloads:
        def __init__(self, _db):
            pass

        def mark_processing(self, _id):
            pass

        def mark_ready(self, *_a, **_k):
            pass

        def mark_failed(self, *_a, **_k):
            events.append("failed")

    def render(*_a, **_k):
        events.append("render-open" if session.open else "render-closed")
        return b"%PDF"

    class Backend:
        def upload_file(self, **_k):
            return "k", "u"

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "DownloadService", Downloads)
    monkeypatch.setattr(tasks, "_render_pdf", render)
    monkeypatch.setattr(tasks, "get_backend", lambda _p: Backend())
    monkeypatch.setattr(tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(spec, "page_size_for_download", lambda db, d: (338.7, 190.5))
    monkeypatch.setattr(spec, "prepare_export_images", lambda db, d: events.append("prep"))

    result = tasks.generate_spec_sheet_pdf("d1")

    assert result["status"] == "ready", result
    assert events[:3] == ["prep", "close", "render-closed"]


def test_a_thumbnail_made_after_release_is_saved_through_its_own_session_pinned_to_the_company(
    monkeypatch,
):
    import app.database as database
    from app.models.base import _SCOPE_KEY
    from app.models.resources import Attachment
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs
    from app.services import storage_router

    class Store(_FakeBackend):
        def upload_file(self, file_content, file_path, content_type=None, **_kw):
            return file_path, file_path

    with blank_session() as db:
        issued = _sign_issue(db, monkeypatch, photos=1, thumbnails=False)
        monkeypatch.setattr(images, "get_backend", lambda provider: Store(_photo_bytes(600, 600)))
        monkeypatch.setattr(
            storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.zzt.test/{key}"
        )
        scopes = []

        class Own:
            """The test session behind the service's own SessionLocal()."""

            info = db.info

            def query(self, *a, **k):
                scopes.append(db.info.get(_SCOPE_KEY))
                return db.query(*a, **k)

            def commit(self):
                db.flush()

            def rollback(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(database, "SessionLocal", lambda: Own())
        from app.models.projects import ProjectQuotationDocument

        company_id = (
            db.query(ProjectQuotationDocument)
            .filter(ProjectQuotationDocument.id == issued.document_id)
            .one()
            .company_id
        )

        qdocs.serialize_sign_page(db, issued, release=lambda: None)

        assert scopes and all(s == frozenset({str(company_id)}) for s in scopes)
        saved = (
            db.query(Attachment)
            .filter(Attachment.original_filename.like("%zzt%"), Attachment.thumbnail_path.isnot(None))
            .count()
        )
        assert saved == 2


# ------------------------------------------------------------------ crew round 2


def _big_jpeg(width=8000, height=6000) -> bytes:
    """A 48 MP photograph, over the 40 MP decode ceiling."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (40, 90, 160)).save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def test_the_open_page_gets_a_1024_px_rendition_never_the_original(monkeypatch):
    from PIL import Image

    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c, sheet, photo, drawing, store, signed = _open_page_env(db, monkeypatch, _big_jpeg())

        out = spec.page_images(db, sheet, c["basin"].id)

        assert set(out["images"]) == {photo.id, drawing.id}
        assert all(".medium.jpg" in url for url in out["images"].values())
        assert not any(s in (photo.file_path, drawing.file_path) for s in signed)
        medium = next(k for k in store.uploads if k.startswith("products/") and "basin.png" in k)
        with Image.open(io.BytesIO(store.uploads[medium])) as im:
            assert max(im.size) == images.MEDIUM_BOX == 1024

        # Made once: a later open signs the stored rendition without reading the original.
        images._medium_cache.clear()
        store.downloads.clear()
        spec.page_images(db, sheet, c["basin"].id)
        assert store.downloads == []


def test_the_cover_asks_for_no_picture_and_an_unknown_page_is_a_404(monkeypatch):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c, sheet, _photo, _drawing, store, _signed = _open_page_env(db, monkeypatch, _photo_bytes(600, 600))

        assert spec.page_images(db, sheet, "cover") == {"images": {}, "assets": {}}
        with pytest.raises(AppException) as raised:
            spec.page_images(db, sheet, "no-such-page")
        assert raised.value.status_code == 404
        assert store.downloads == []


def test_the_page_images_route_answers_the_open_pages_renditions(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    from .test_project_spec_sheet import _client, _restore, _url

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        monkeypatch.setattr(
            spec,
            "page_images",
            lambda db_, sheet_, key, release=None: {"images": {"a": f"u-{key}"}, "assets": {}},
        )
        client, originals = _client(db, c["owner"])
        try:
            response = client.get(_url(c, f"/{sheet.id}/page-images"), params={"key": c["basin"].id})
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        assert response.json() == {"images": {"a": f"u-{c['basin'].id}"}, "assets": {}}


def test_the_page_images_route_refuses_a_page_the_sheet_does_not_have_and_needs_a_key():
    from .test_project_spec_sheet import _client, _restore, _url

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        client, originals = _client(db, c["owner"], slugs=["projects.projects.view"])
        try:
            assert client.get(_url(c, f"/{sheet.id}/page-images"), params={"key": "set:nope"}).status_code == 404
            assert client.get(_url(c, f"/{sheet.id}/page-images")).status_code == 422
            assert client.get(_url(c, f"/{sheet.id}/page-images"), params={"key": "cover"}).status_code == 200
        finally:
            _restore(originals)


def test_the_designer_binds_the_open_page_to_medium_pictures_not_thumbnails_or_originals(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c, sheet, photo, drawing, store, _signed = _open_page_env(db, monkeypatch, _big_jpeg())

        design = spec.design(db, sheet, c["basin"].id)

        bound = design["bound"]
        assert ".medium.jpg" in bound["images"][0]["url"]
        assert ".medium.jpg" in bound["drawing"]["url"]
        assert bound["images"][0]["url"] != photo.file_path and bound["drawing"]["url"] != drawing.file_path


def test_the_asset_list_carries_a_thumb_url_that_is_never_the_original(monkeypatch):
    from app.models.base import company_scope
    from app.models.dealer_kit import Asset
    from app.models.resources import Attachment
    from app.services import product_image_service as images
    from app.services.storage_router import extract_key

    from .test_project_spec_sheet import _client, _restore
    from .test_project_spec_sheets_v2 import _asset

    with blank_session() as db:
        c = _chain(db)
        plain = _asset(db, c["company_id"])
        thumbed = _asset(db, c["company_id"])
        plain_att = db.get(Attachment, db.get(Asset, plain.id).attachment_id)
        thumbed_att = db.get(Attachment, db.get(Asset, thumbed.id).attachment_id)
        thumbed_att.thumbnail_path = "https://cdn.zzt.test/library/logo-thumb.jpg"
        store = _MediumStore({extract_key(plain_att.file_path): _big_jpeg(4000, 3000)})
        monkeypatch.setattr(images, "get_backend", lambda provider: store)
        monkeypatch.setattr(
            images,
            "resolve_signed_url",
            lambda source, *, provider=None, expires_in=3600, strict=False: f"https://signed.zzt.test/{source}",
        )
        from app.services.dealer_kit import asset_service

        monkeypatch.setattr(
            asset_service,
            "resolve_signed_url",
            lambda source, *, provider=None, expires_in=3600, strict=False: f"https://signed.zzt.test/ORIGINAL/{source}",
        )
        images._medium_cache.clear()
        images._url_cache.clear()
        db.commit()
        with company_scope(db, frozenset({c["company_id"]})):
            client, originals = _client(db, c["owner"], slugs=["dealer_kit.library.manage"])
            try:
                got = client.get("/api/v1/dealer-kit/assets", params={"limit": 50})
            finally:
                _restore(originals)

        assert got.status_code == 200, got.text
        rows = {row["id"]: row for row in got.json()}
        assert rows[plain.id]["url"] == f"https://signed.zzt.test/ORIGINAL/{plain_att.file_path}"  # unchanged
        assert ".medium.jpg" in rows[plain.id]["thumb_url"]
        assert rows[thumbed.id]["thumb_url"] == "https://signed.zzt.test/https://cdn.zzt.test/library/logo-thumb.jpg"
        for row in rows.values():
            assert row["thumb_url"] != row["url"]
