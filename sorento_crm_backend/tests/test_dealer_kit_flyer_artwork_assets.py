"""The banner reaches storage, the document, and the reader (S7.5, group F).

``test_dealer_kit_flyer_artwork.py`` proves what the extractor READS. This proves
what the system DOES with it, which is where two of the criteria actually land:

* **AC-F1** the bytes that reach STORAGE are RGB. The extractor handing back an
  RGB image is necessary but not sufficient - the assertion the criterion makes
  is about what a browser will eventually fetch, so it is made against the bytes
  the storage backend was handed.
* **AC-F3** (backend half) the banner becomes the section BACKGROUND and the
  heading stays a text block over it. Baking the heading into the bitmap would
  be easier and is the thing to refuse: the extractor is known to misread
  headings - fixture page 2 reads "Transforming Your" where the paper says
  "BATHTUB COLLECTION" - and a heading burned into a picture cannot be
  corrected, found by search, or translated.

The library must not fill up with product shots either, so the asset count is
asserted, not just its contents: one row per flyer page that HAS a banner, and
none for the page whose header is typeset rather than placed.

Postgres only, on a blank scratch schema. Storage is a fake that keeps the bytes
it was handed, because the assertion IS the bytes.
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.dealer_kit import flyer_reading_service as svc  # noqa: E402

from tests._fake_storage import patch_storage
from tests._flyer_read import finish_reads, patch_flyer_read
from tests._flyer_pdf import BANNER_RECT, cmyk_jpeg, flyer_pdf
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# The fixture's three pages: the cover carries a full-bleed background, the
# bathtub spread's header is a vector rectangle, the water closet spread has a
# real image band. So two of the three seed a background.
PAGES_WITH_A_BANNER = 2

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ADMIN_ID = "3f8a1d67-92b4-5c08-a731-6e4d2b9f5c14"
_ADMIN_ROLE = "6b2f9c04-51d8-5a37-b4e6-9c1a3f7d2e58"


def _seed_roles(db) -> None:
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
        User(id=_ADMIN_ID, email="zzt-art-admin@test.com", name="Art Admin", status="ACTIVE")
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.commit()


@pytest.fixture
def api(monkeypatch):
    """The route stack, a superadmin principal, and storage that keeps its bytes."""
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
        patch_flyer_read(monkeypatch, db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _ADMIN_ID, "email": "zzt-art-admin@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, storage

        app.dependency_overrides.clear()


def _upload(client: TestClient, data: bytes, *, filename: str = "zzt-flyer.pdf") -> str:
    res = client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": (filename, data, "application/pdf")},
    )
    # The read is a background job now: the POST answers 202 with the row in
    # `processing`, and the extraction happens when the worker runs the job.
    # `finish_reads` is that worker, on this test's own session.
    assert res.status_code == 202, res.text
    assert [job["status"] for job in finish_reads()] == ["done"]
    return res.json()["id"]


def _seed(client: TestClient, reading_id: str) -> dict:
    res = client.post(
        f"/api/v1/dealer-kit/flyer-readings/{reading_id}/seed",
        json={"name": unique_code("ZZT Brochure"), "slug": unique_code("zzt-bro").lower()},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _latest_doc(db, page_id: str) -> dict:
    from app.models.dealer_kit import PageVersion

    row = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page_id)
        .order_by(PageVersion.version.desc())
        .first()
    )
    assert row is not None
    return row.doc


def _assets(db):
    from app.models.dealer_kit import Asset

    return db.query(Asset).all()


def _cmyk_flyer() -> bytes:
    """One A3 page with a CMYK banner across the top and one product code."""
    return flyer_pdf(
        image=cmyk_jpeg(1755, 445),
        image_size=(1755, 445),
        rect=BANNER_RECT,
        codes=[("SRTZZ9001", 60.0, 600.0)],
    )


# --------------------------------------------------------------------------- #
# AC-F1 - the bytes that reach storage are RGB
# --------------------------------------------------------------------------- #
class TestStoredBytes:
    def test_a_cmyk_banner_is_stored_as_rgb(self, api) -> None:
        """The assertion the criterion actually makes.

        A CMYK JPEG renders unreliably in browsers and is rejected outright by
        Meta's media validator, so what matters is not what the extractor
        returned but what a reader will fetch. Read straight out of the storage
        backend, which is the last place the bytes exist before a CDN.
        """
        from PIL import Image

        from app.services.image_normalizer import needs_rgb_conversion

        _db, storage = api
        source = _cmyk_flyer()

        with TestClient(app) as client:
            _upload(client, source)

        images = [
            content
            for key, (content, _mime) in storage.objects.items()
            if not key.endswith(".thumb.jpg")
        ]
        assert images, "the banner never reached storage"
        for content in images:
            assert Image.open(io.BytesIO(content)).mode == "RGB"
            assert needs_rgb_conversion(content, "image/jpeg") is False

    def test_the_stored_banner_is_an_asset_in_the_library(self, api) -> None:
        """Bytes in ``public.attachments``, library semantics in ``dealer_kit.asset``.

        The Kit does not grow a second file store: an asset row points at an
        attachment like every other file in the system, so the storage router,
        the provider column and the signing path all apply unchanged.
        """
        from app.models.resources import Attachment

        db, _storage = api

        with TestClient(app) as client:
            _upload(client, _cmyk_flyer())

        assets = _assets(db)
        assert len(assets) == 1
        attachment = (
            db.query(Attachment).filter(Attachment.id == assets[0].attachment_id).one()
        )
        assert (attachment.mime_type or "").startswith("image/")
        assert attachment.file_path

    def test_only_pages_with_a_banner_add_a_row_to_the_library(self, api) -> None:
        """Two of the fixture's three pages, not one row per picture on the paper.

        The real flyer places 68 images on a single page. An extractor that
        called them all artwork would put hundreds of product shots in a library
        a human is supposed to browse.
        """
        db, _storage = api

        with TestClient(app) as client:
            _upload(client, FIXTURE_PDF.read_bytes())

        assert len(_assets(db)) == PAGES_WITH_A_BANNER

    def test_a_flyer_whose_banners_cannot_be_stored_is_still_read(
        self, api, monkeypatch
    ) -> None:
        """A storage outage costs the backgrounds, never the reading.

        The reading is what the seed is built from; the banners are decoration
        on top of it. Failing the read would throw away a 36 page extraction
        because a bucket was briefly unreachable.

        The failure is aimed at the ASSET writes only, and it has to be aimed
        now: since the read became a background job, the upload's own bytes are
        parked in the same bucket first (`STAGING_PREFIX`) so the worker can
        reach them. Breaking every PUT would break the staging too, which is a
        different failure with a different answer - the request says so in words
        and no reading is created at all - and it would leave this test asserting
        that instead of what it is named for.
        """
        db, storage = api

        real_upload = storage.upload_file

        def _explode(**kwargs):
            if str(kwargs.get("file_path", "")).startswith(svc.STAGING_PREFIX):
                # Parking the flyer for the worker still works. Only the asset
                # library is out.
                return real_upload(**kwargs)
            raise RuntimeError("bucket unreachable")

        monkeypatch.setattr(storage, "upload_file", _explode)

        with TestClient(app) as client:
            reading_id = _upload(client, _cmyk_flyer())

        assert _assets(db) == []
        res_body = TestClient(app).get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}")
        assert res_body.status_code == 200
        assert res_body.json()["status"] == "done"


# --------------------------------------------------------------------------- #
# AC-F3 (backend half) - background binding, heading still a block
# --------------------------------------------------------------------------- #
class TestSeededSections:
    def test_the_banner_becomes_the_sections_background(self, api) -> None:
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

        doc = _latest_doc(db, result["pageId"])
        asset_ids = {asset.id for asset in _assets(db)}

        bound = [
            section["style"]["backgroundAssetId"]
            for section in doc["sections"]
            if section["style"].get("backgroundAssetId")
        ]
        assert len(bound) == PAGES_WITH_A_BANNER
        assert set(bound) <= asset_ids

    def test_the_document_binds_an_asset_id_and_never_a_url(self, api) -> None:
        """Renaming or re-signing a file must not break a published page (AC-D3)."""
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

        doc = _latest_doc(db, result["pageId"])
        for section in doc["sections"]:
            background = section["style"].get("backgroundAssetId")
            if background is None:
                continue
            assert "http" not in background
            assert ".jpg" not in background and ".png" not in background

    def test_the_heading_is_a_block_over_the_background_not_part_of_it(
        self, api
    ) -> None:
        """The heading stays editable, searchable and translatable.

        Fixture page 3's heading reads correctly; fixture page 2's is the known
        misread. Both must be TEXT in the document, because a heading burned
        into a bitmap cannot be corrected by the reviewer this whole slice
        exists to serve.
        """
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

        doc = _latest_doc(db, result["pageId"])
        water_closet = next(
            section
            for section in doc["sections"]
            if section["style"].get("backgroundAssetId")
            and "WATER CLOSET" in section["name"].upper()
        )

        headings = [
            block["props"]["text"]
            for block in water_closet["blocks"]
            if block["type"] == "heading"
        ]
        assert headings == ["WATER CLOSET"]

    def test_a_page_with_no_banner_keeps_its_plain_background(self, api) -> None:
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

        doc = _latest_doc(db, result["pageId"])
        plain = [
            section
            for section in doc["sections"]
            if not section["style"].get("backgroundAssetId")
        ]
        assert len(plain) == len(doc["sections"]) - PAGES_WITH_A_BANNER
        for section in plain:
            assert section["style"]["background"] == "transparent"

    def test_a_band_lies_across_the_top_and_a_cover_fills_the_section(
        self, api
    ) -> None:
        """How the background is laid out is carried too, or every banner zooms.

        A section is as tall as its content, so a 4:1 header band told to
        "cover" is magnified until only a smear of it is visible. The cover
        page's full-page artwork is the opposite case and does want covering.
        """
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

        doc = _latest_doc(db, result["pageId"])
        fits = {
            section["name"]: section["style"].get("backgroundFit")
            for section in doc["sections"]
            if section["style"].get("backgroundAssetId")
        }
        assert set(fits.values()) == {"cover", "width"}


# --------------------------------------------------------------------------- #
# The reader gets a URL, or nothing at all
# --------------------------------------------------------------------------- #
class TestPublicPayload:
    def _publish(self, db, page_id: str) -> None:
        from app.models.dealer_kit import PageLabel, PageVersion

        version = (
            db.query(PageVersion)
            .filter(PageVersion.page_id == page_id)
            .order_by(PageVersion.version.desc())
            .first()
        )
        db.add(PageLabel(page_id=page_id, label="published", version_id=version.id))
        db.commit()

    def test_a_published_catalogue_carries_a_signed_url_per_background(
        self, api
    ) -> None:
        """The document holds ids; the payload holds the URLs they resolve to.

        Sent with the page rather than fetched per section: the print page is
        rendered by headless Chromium, which declares itself finished the moment
        the network is idle, and a background that arrives after that is a blank
        band in a PDF nobody re-checks.
        """
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)
        self._publish(db, result["pageId"])

        with TestClient(app) as client:
            res = client.get(f"/api/v1/public/c/SRT/{result['slug']}")

        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["assets"]) == PAGES_WITH_A_BANNER
        for url in body["assets"].values():
            assert url.startswith("https://")

    def test_a_background_that_cannot_be_signed_is_absent_rather_than_broken(
        self, api
    ) -> None:
        """An image URL that cannot be signed comes back 403 from the CDN.

        ``resolve_signed_url`` fails OPEN by default, which is right for a
        download link and wrong for a picture: the reader gets a broken image
        where the section has a perfectly good plain background to fall back on.
        181 of 2,472 product images could not be signed on one environment and
        every one of them rendered as a broken tile.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)
        self._publish(db, result["pageId"])

        storage.signing_fails = True
        with TestClient(app) as client:
            res = client.get(f"/api/v1/public/c/SRT/{result['slug']}")

        assert res.status_code == 200, res.text
        assert res.json()["assets"] == {}


# --------------------------------------------------------------------------- #
# The designer gets the same URLs the reader does
# --------------------------------------------------------------------------- #
class TestEditorPayload:
    """The builder needs the signed URLs too, and by the same contract.

    A background is bound as an id, so the editor cannot resolve one on its own
    without becoming a second signer with a second opinion about strictness. It
    is handed the same ``{assetId: url}`` map the public page and the print
    payload carry, from the same ``asset_service.background_urls`` call - which
    is what lets the builder paint through the SAME renderer code as the
    catalogue.

    Without this the person reviewing a freshly seeded draft is the only one who
    cannot see the artwork, and they are the one being asked to approve it.
    """

    def test_the_editor_payload_carries_a_signed_url_per_background(self, api) -> None:
        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

            res = client.get(f"/api/v1/dealer-kit/pages/{result['pageId']}")

        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["assets"]) == PAGES_WITH_A_BANNER
        for url in body["assets"].values():
            assert url.startswith("https://")

        # The same ids the document binds, so the renderer can look them up.
        doc = _latest_doc(db, result["pageId"])
        bound = {
            section["style"]["backgroundAssetId"]
            for section in doc["sections"]
            if section["style"].get("backgroundAssetId")
        }
        assert set(body["assets"]) == bound

    def test_a_background_that_cannot_be_signed_is_absent_rather_than_broken(
        self, api
    ) -> None:
        """Strict signing, exactly as on the public payload.

        A URL the CDN answers 403 to is a broken image on the canvas, and the
        section has a designed state for "no picture" and none at all for that.
        """
        _db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client, FIXTURE_PDF.read_bytes())
            result = _seed(client, reading_id)

            storage.signing_fails = True
            res = client.get(f"/api/v1/dealer-kit/pages/{result['pageId']}")

        assert res.status_code == 200, res.text
        assert res.json()["assets"] == {}

    def test_a_page_with_no_artwork_carries_an_empty_map(self, api) -> None:
        """Absent artwork is an empty map, never a missing key.

        The editor reads ``assets`` unconditionally; a key that only appears
        when something is bound would be a null nobody remembered to guard.
        """
        with TestClient(app) as client:
            res = client.post(
                "/api/v1/dealer-kit/pages",
                json={
                    "name": unique_code("ZZT Plain"),
                    "slug": unique_code("zzt-plain").lower(),
                },
            )
            assert res.status_code == 201, res.text
            page_id = res.json()["id"]

            res = client.get(f"/api/v1/dealer-kit/pages/{page_id}")

        assert res.status_code == 200, res.text
        assert res.json()["assets"] == {}


# --------------------------------------------------------------------------- #
# The stored reading still round-trips
# --------------------------------------------------------------------------- #
def test_the_asset_ids_survive_a_round_trip_through_the_database(api) -> None:
    """The seed reads them back out of JSONB, so a dropped field is a blank page."""
    from app.models.dealer_kit import FlyerReadingRecord
    from app.services.dealer_kit.flyer_reading_service import to_reading

    db, _storage = api

    with TestClient(app) as client:
        reading_id = _upload(client, FIXTURE_PDF.read_bytes())

    record = (
        db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).one()
    )
    reading = to_reading(record)

    bound = [page.banner_asset_id for page in reading.pages if page.banner_asset_id]
    assert len(bound) == PAGES_WITH_A_BANNER
    assert all(uuid.UUID(value) for value in bound)


# --------------------------------------------------------------------------- #
# Whose transaction is it
# --------------------------------------------------------------------------- #
class TestTheCallersTransaction:
    """Storing artwork must not decide the fate of the caller's own work.

    Both of these are about the same mistake wearing two hats. Storing a banner
    is a SIDE EFFECT of reading a flyer: it is explicitly best-effort, the
    service says so, and the whole argument for that is that a bucket being
    briefly unreachable is not worth throwing away a 36 page extraction. A side
    effect that commits its caller's half-built work, or rolls it back, has
    exactly the power the "best-effort" framing promises it does not.

    The failure this prevents is not theoretical and not loud: the reading is
    built page by page, and a rollback in the middle of that leaves a request
    that returns 201 having silently discarded rows it had already written.
    """

    def _fake_page(self, image: bytes = b"not really a jpeg"):
        from app.services.dealer_kit.flyer_extraction import (
            FlyerArtwork,
            FlyerBanner,
            FlyerPage,
        )

        page = FlyerPage(number=1, width=841.89, height=1190.55)
        page.banner = FlyerBanner(
            artwork=FlyerArtwork(x_pct=0.0, y_pct=0.0, width_pct=1.0, height_pct=0.2, xref=7),
            image=image,
            mime="image/jpeg",
            fit="width",
        )
        return page

    def _marker(self, db):
        """An unrelated row the caller has written but not committed."""
        from app.models.dealer_kit import Page

        page = Page(name=unique_code("ZZT Pending"), slug=unique_code("zzt-pend").lower())
        db.add(page)
        db.flush()
        return page.id

    def test_storing_a_banner_leaves_the_transaction_to_the_caller(self, api) -> None:
        """The asset is written, not committed: the caller can still undo it all.

        ``create_from_bytes`` used to commit, on the argument that an attachment
        row must not exist without the asset row that makes it reachable. Both
        rows are written in ONE flush, so the caller's commit gives that
        invariant just as well - and without giving a helper the power to commit
        whatever else its caller happened to have pending.
        """
        from app.models.dealer_kit import Asset, Page
        from app.services.dealer_kit import asset_service

        db, _storage = api

        page_id = self._marker(db)
        asset = asset_service.create_from_bytes(
            db, content=b"bytes", name=unique_code("ZZT art"), mime="image/jpeg"
        )
        asset_id = asset.id

        db.rollback()

        assert db.query(Asset).filter(Asset.id == asset_id).first() is None
        assert db.query(Page).filter(Page.id == page_id).first() is None

    def test_a_failed_banner_does_not_discard_the_callers_work(self, api) -> None:
        """A storage outage costs the artwork and nothing else.

        The old handler called ``db.rollback()`` on the caller's session, which
        is the opposite of best-effort: it discards whatever the caller had
        pending. A SAVEPOINT undoes only the half-written asset.
        """
        from app.models.dealer_kit import Page
        from app.services.dealer_kit import flyer_reading_service
        from app.services.dealer_kit.flyer_extraction import FlyerReading

        db, storage = api

        def _explode(**kwargs):
            raise RuntimeError("the bucket is unreachable")

        storage.upload_file = _explode

        reading = FlyerReading()
        reading.pages = [self._fake_page()]

        page_id = self._marker(db)
        flyer_reading_service._store_banners(
            db, reading, filename="zzt-flyer.pdf", user_id=None
        )

        assert reading.pages[0].banner_asset_id is None
        assert db.query(Page).filter(Page.id == page_id).first() is not None

    def test_one_unstorable_banner_does_not_cost_the_others(self, api) -> None:
        """Per page, so page 2 failing does not take page 3 down with it."""
        from app.services.dealer_kit import flyer_reading_service
        from app.services.dealer_kit.flyer_extraction import FlyerReading

        db, storage = api

        real_upload = storage.upload_file
        calls = {"n": 0}

        def _explode_once(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("the bucket blinked")
            return real_upload(**kwargs)

        storage.upload_file = _explode_once

        first = self._fake_page()
        second = self._fake_page()
        second.number = 2
        reading = FlyerReading()
        reading.pages = [first, second]

        flyer_reading_service._store_banners(
            db, reading, filename="zzt-flyer.pdf", user_id=None
        )

        assert reading.pages[0].banner_asset_id is None
        assert reading.pages[1].banner_asset_id is not None
