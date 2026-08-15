"""Uploading a flyer and getting the match report back (S7.3, the routes half).

Written before the routes.

``flyer_extraction`` reads the paper and ``flyer_matching`` says what it means.
This slice is the only part a designer touches: drop the PDF in, read the report.
Everything asserted here is something that decides whether they can trust it.

* **The report is RECOMPUTED on every read, never stored.** The test that proves
  it changes the master between two GETs of the same reading and expects the
  answer to move. A stored report would still pass every other test in this file
  while quietly telling marketing that 213 products are missing from a promotion
  somebody fixed last week.
* **A designer who picked the wrong file is told.** Not a 500, and not an empty
  report that reads as "your flyer has no products in it".
* **A reading belongs to one company.** Another company's reading is absent, not
  forbidden: 403 would confirm the id exists.
* **A malformed ``promotionId`` never reaches the database.** That exact mistake
  produced a 500 in this feature once already.

Postgres only, on a blank scratch schema. Every row is ZZT-scoped except the
product codes, which have to be the ones actually printed on the fixture flyer -
matching a printed code is the whole point, so a ZZT-prefixed code would match
nothing.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# A code printed on page 2 of the fixture, verified in flyer_golden.json. The
# recompute test hangs off it: unmatched on the first read, matched on the second.
PRINTED_CODE = "SRTJC8041"

_SORENTO = "00000000-0000-0000-0000-000000000001"

_ADMIN_ID = "1c6f3b92-77d4-5e08-9a35-4b8e0d2f6c17"
_ADMIN_ROLE = "9e2d5a41-3f86-5c19-b704-6d1a8c3e7b52"
_EDITOR_ID = "4b8a1e37-6c92-5d40-8f13-2a7e9b5c0d68"
_EDITOR_ROLE = "7d3c8f15-2a49-5b67-9e08-1c4b6d3a8f29"
_NOPERM_ID = "6a4d9c28-1b75-5f39-8c02-3e7b1a5d4f60"


def _seed_roles(db) -> None:
    """A superadmin, an editor holding view+edit, and a stranger holding nothing."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

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
        UserRole(
            id=_EDITOR_ROLE,
            slug="zzt_flyer_editor",
            name="ZZT Flyer Editor",
            description="Reads flyers into the Kit",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ADMIN_ID, email="zzt-fr-admin@test.com", name="FR Admin", status="ACTIVE"))
    db.add(User(id=_EDITOR_ID, email="zzt-fr-editor@test.com", name="FR Editor", status="ACTIVE"))
    db.add(User(id=_NOPERM_ID, email="zzt-fr-out@test.com", name="FR Outsider", status="ACTIVE"))
    db.flush()

    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.add(UserRoleAssignment(user_id=_EDITOR_ID, role_id=_EDITOR_ROLE))

    # The blank schema has no permission rows, so the ones a migration seeds in a
    # real database are created here. No NEW slug: reading a flyer is drafting a
    # catalogue, and a fourth slug would need a grant sweep before anybody held it.
    granted = ("dealer_kit.page.view", "dealer_kit.page.edit")
    for slug in granted + ("dealer_kit.page.publish",):
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        if slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=_EDITOR_ROLE, permission_id=perm_id
                )
            )
    db.commit()


@pytest.fixture
def api(monkeypatch):
    """The route stack with a switchable principal AND a switchable company.

    The company has to move because "another company's reading is 404" cannot be
    asserted from a fixture pinned to one - and the pin is necessary, since the
    real resolver reads a bearer token these tests do not send.

    Storage is faked even though nothing here asserts on a stored byte: an upload
    stores the flyer's banners, and unfaked that is a live PUT to the real bucket
    (see tests/_fake_storage.py).
    """
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        patch_storage(monkeypatch)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            # Direct test-level writes and reads run on the same session, so the
            # scope has to move for them too, not only for the next request.
            set_company_scope(db, frozenset({company_id}))

        _as(_ADMIN_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def _pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


def _upload(client: TestClient, *, filename: str = "zzt-flyer.pdf", data: bytes | None = None, **params):
    return client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": (filename, data if data is not None else _pdf_bytes(), "application/pdf")},
        params=params,
    )


def _product(db, code: str):
    """A product carrying a code the fixture flyer actually prints.

    The CODE is real by necessity; everything else about the row is ZZT-scoped.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTFR")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.commit()
    return product


def _company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTFRC")[:20],
        is_active=True,
    )
    db.add(company)
    db.commit()
    return company.id


def _promotion(db, product) -> str:
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(
        id=str(uuid.uuid4()), description=unique_code("ZZT promo"), is_active=True
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name=unique_code("ZZT grp"))
    db.add(group)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion.id,
            promotion_group_id=group.id,
            product_id=product.id,
            promo_selling_price=Decimal("79.00"),
        )
    )
    db.commit()
    return promotion.id


def _codes(entries) -> list[str]:
    return [entry["code"] for entry in entries]


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
class TestUpload:
    def test_uploading_the_real_flyer_returns_a_report(self, api) -> None:
        """The whole slice in one call: a PDF in, something to review out."""
        _db, _as, _scope = api

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-a3-flyer.pdf")

        assert res.status_code == 201, res.text
        body = res.json()
        assert body["id"]
        assert body["filename"] == "zzt-a3-flyer.pdf"
        assert body["pageCount"] == 3
        # Nothing in the master yet, so every printed code is a gap somebody has
        # to close. That IS the report on a fresh database.
        assert body["report"]["matched"] == []
        assert PRINTED_CODE in _codes(body["report"]["unmatched"])

    def test_a_matched_code_names_the_product_beside_what_was_printed(self, api) -> None:
        db, _as, _scope = api
        product = _product(db, PRINTED_CODE)

        with TestClient(app) as c:
            report = _upload(c).json()["report"]

        entry = next(row for row in report["matched"] if row["code"] == PRINTED_CODE)
        assert entry["productId"] == product.id
        assert entry["productName"] == product.product_name
        # Which page to turn to. "It is wrong somewhere" is not a correction.
        assert entry["pages"] == [2]

    def test_a_near_miss_reaches_the_screen_as_a_suggestion_with_its_score(
        self, api
    ) -> None:
        """A suggestion, never a substitution (PLAN D8).

        It has to survive serialisation with BOTH the product it names and the
        score behind it: a guess presented without a number reads as a fact, and
        the reviewer is one click from applying it.
        """
        db, _as, _scope = api
        neighbour = _product(db, "SRTJC8042")  # the flyer prints SRTJC8041

        with TestClient(app) as c:
            report = _upload(c).json()["report"]

        entry = next(row for row in report["unmatched"] if row["code"] == PRINTED_CODE)
        assert entry["suggestion"]["productCode"] == "SRTJC8042"
        assert entry["suggestion"]["productId"] == neighbour.id
        assert 0.4 <= entry["suggestion"]["similarity"] < 1.0
        # No product id on the unmatched entry itself: the gap is the point.
        assert "productId" not in entry

    def test_a_printed_size_reaches_the_review_queue_beside_the_master(
        self, api
    ) -> None:
        """Nothing is written to the product master from a reading (PLAN D9)."""
        db, _as, _scope = api
        product = _product(db, PRINTED_CODE)  # no dimensions on the master row

        with TestClient(app) as c:
            report = _upload(c).json()["report"]

        entry = next(
            row for row in report["dimensionCandidates"] if row["code"] == PRINTED_CODE
        )
        assert entry["productId"] == product.id
        assert (
            entry["printedLengthMm"],
            entry["printedWidthMm"],
            entry["printedHeightMm"],
        ) == (1700, 800, 590)
        assert entry["currentLengthMm"] is None
        assert entry["verdict"] == "missing"

    def test_a_file_that_is_not_a_pdf_is_refused_in_words(self, api) -> None:
        """A designer who picked the wrong file needs telling.

        Not a 500, and not a 201 carrying an empty report - that reads as "your
        flyer has no products on it" and sends them looking for the wrong bug.
        """
        _db, _as, _scope = api

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-notes.docx", data=b"PK\x03\x04 not a pdf at all")

        assert res.status_code == 400, res.text
        assert "pdf" in res.text.lower()

    def test_a_password_protected_flyer_is_told_it_is_the_password(self, api) -> None:
        """A locked PDF IS a PDF, so "export it as a PDF" is the wrong advice.

        Print-ready artwork comes back from an agency locked more often than it
        does corrupt, and the designer who receives it can fix it in a minute if
        anybody tells them what is wrong. Sent the generic message instead, they
        re-export the same locked file and try again. PyMuPDF's own wording is
        "document closed or encrypted", which is worse than useless in front of
        somebody who is looking at an open document.
        """
        _db, _as, _scope = api

        import pymupdf

        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "SRTJC8041 599")
        locked = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u"
        )

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-locked.pdf", data=locked)

        assert res.status_code == 400, res.text
        body = res.text.lower()
        assert "password" in body
        # The generic advice must NOT be what they are told, and PyMuPDF's
        # "document closed" must not reach a human at all.
        assert "word or image file" not in body
        assert "document closed" not in body

    def test_an_empty_upload_is_refused_too(self, api) -> None:
        _db, _as, _scope = api

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-empty.pdf", data=b"")

        assert res.status_code == 400, res.text

    def test_a_flyer_over_the_ceiling_is_refused_and_the_limit_is_named(
        self, api, monkeypatch
    ) -> None:
        """The ceiling is 50 MB; the real flyer is 20 MB.

        Exercised with the limit turned down rather than by posting 50 MB of
        zeroes: what is under test is that the check fires and says what the
        limit is, and a 50 MB multipart body would add half a minute to the run
        to prove the same thing.
        """
        from app.services.dealer_kit import flyer_reading_service as svc

        _db, _as, _scope = api
        monkeypatch.setattr(svc, "MAX_UPLOAD_BYTES", 100 * 1024)

        with TestClient(app) as c:
            res = _upload(c)

        assert res.status_code == 413, res.text
        # Naming the limit is the difference between "try a smaller file" and a
        # designer guessing at what smaller means.
        assert "0.1 MB" in res.text or "0.10 MB" in res.text, res.text

    def test_the_real_ceiling_leaves_headroom_over_the_real_flyer(self) -> None:
        """20 MB printed, 50 MB allowed.

        A designer exporting the same document without compression can double it
        and still get through, while the cap stays inside what one request can
        read and extract without a worker.
        """
        from app.services.dealer_kit import flyer_reading_service as svc

        assert svc.MAX_UPLOAD_BYTES >= 2 * 20 * 1024 * 1024


# --------------------------------------------------------------------------- #
# The design decision: store the reading, derive the report
# --------------------------------------------------------------------------- #
class TestTheReportIsDerived:
    def test_the_report_is_recomputed_on_every_read(self, api) -> None:
        """The test the storage decision rests on.

        A report is only true for the master it was computed against. Products
        are created and promotions change every day, so a report written at
        upload time starts lying immediately - and lies in the one direction
        that costs money, by reporting gaps somebody has already closed.
        """
        db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

            before = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").json()
            assert PRINTED_CODE in _codes(before["report"]["unmatched"])
            assert PRINTED_CODE not in _codes(before["report"]["matched"])

            # The master moves underneath a reading that has not changed.
            product = _product(db, PRINTED_CODE)

            after = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").json()

        assert PRINTED_CODE in _codes(after["report"]["matched"])
        assert PRINTED_CODE not in _codes(after["report"]["unmatched"])
        assert (
            next(row for row in after["report"]["matched"] if row["code"] == PRINTED_CODE)[
                "productId"
            ]
            == product.id
        )

    def test_what_is_stored_is_the_reading_and_not_the_report(self, api) -> None:
        """Pinned so nobody "optimises" the recompute away into a column."""
        db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

        from app.models.dealer_kit import FlyerReadingRecord

        row = db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).one()
        stored = row.reading_json

        assert [page["number"] for page in stored["pages"]] == [1, 2, 3]
        assert PRINTED_CODE in [
            card["code"] for page in stored["pages"] for card in page["cards"]
        ]
        # Nothing derived from the master is in there.
        assert "matched" not in stored
        assert "unmatched" not in stored
        assert "not_promoted" not in stored

    def test_the_stored_reading_round_trips_through_the_database(self, api) -> None:
        """Rows, artwork and headings survive too, because the seeder needs them.

        Only the codes are needed to MATCH, so a serialiser that dropped the
        printed rows would pass every other test here and then seed a catalogue
        with no layout at all.

        Two fields are cleared before comparing, and only two: where each page's
        banner ended up in the asset library, and how it should be laid out. A
        plain extraction cannot know either - they are filled in by the upload,
        once the bytes have actually been stored - so keeping them in would
        assert that the reading equals something it is deliberately richer than.
        Everything the serialiser IS responsible for (cards, printed rows,
        artwork geometry and crop, headings) is still compared whole.
        """
        db, _as, _scope = api

        from app.models.dealer_kit import FlyerReadingRecord
        from app.services.dealer_kit.flyer_extraction import extract_flyer
        from app.services.dealer_kit.flyer_reading_service import to_reading

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

        row = db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).one()
        stored = to_reading(row)

        # The upload really did bind some artwork, or clearing it below would
        # quietly turn this into a weaker test than it looks.
        assert any(page.banner_asset_id for page in stored.pages)
        for page in stored.pages:
            page.banner_asset_id = None
            page.banner_fit = None

        assert stored == extract_flyer(_pdf_bytes())


# --------------------------------------------------------------------------- #
# The promotion parameter
# --------------------------------------------------------------------------- #
class TestPromotion:
    def test_naming_a_promotion_reports_what_it_does_not_carry(self, api) -> None:
        db, _as, _scope = api
        promoted = _product(db, PRINTED_CODE)
        printed_elsewhere = _product(db, "SRTJC2025")  # page 2 of the fixture
        promotion_id = _promotion(db, promoted)

        with TestClient(app) as c:
            body = _upload(c, promotionId=promotion_id).json()

        report = body["report"]
        assert report["promotionId"] == promotion_id
        assert PRINTED_CODE not in _codes(report["notPromoted"])
        assert printed_elsewhere.product_code in _codes(report["notPromoted"])

    def test_without_a_promotion_nothing_is_reported_as_unpromoted(self, api) -> None:
        """A brochure need not be linked to one at all (PLAN D5)."""
        db, _as, _scope = api
        _product(db, PRINTED_CODE)

        with TestClient(app) as c:
            report = _upload(c).json()["report"]

        assert report["promotionId"] is None
        assert report["notPromoted"] == []

    def test_the_promotion_can_be_named_on_the_read_instead(self, api) -> None:
        """It is a question asked of a report, not a property of the upload."""
        db, _as, _scope = api
        product = _product(db, PRINTED_CODE)
        printed_elsewhere = _product(db, "SRTJC2025")  # page 2 of the fixture
        promotion_id = _promotion(db, product)

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]
            plain = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").json()
            asked = c.get(
                f"/api/v1/dealer-kit/flyer-readings/{reading_id}",
                params={"promotionId": promotion_id},
            ).json()

        assert plain["report"]["notPromoted"] == []
        assert asked["report"]["promotionId"] == promotion_id
        assert _codes(asked["report"]["notPromoted"]) == [printed_elsewhere.product_code]

    @pytest.mark.parametrize("bad", ["not-a-uuid", "123", "SRTJC8041", ""])
    def test_a_malformed_promotion_id_never_reaches_the_database(self, api, bad) -> None:
        """422, not a 500 out of the driver.

        A malformed uuid landing in a WHERE clause is how this feature produced
        its one 500, so the shape is refused at the edge on BOTH verbs.
        """
        _db, _as, _scope = api

        with TestClient(app) as c:
            posted = _upload(c, promotionId=bad)
            reading_id = _upload(c).json()["id"]
            got = c.get(
                f"/api/v1/dealer-kit/flyer-readings/{reading_id}",
                params={"promotionId": bad},
            )

        assert posted.status_code == 422, posted.text
        assert got.status_code == 422, got.text

    def test_a_promotion_that_does_not_exist_reports_everything_as_unpromoted(
        self, api
    ) -> None:
        """Loud on purpose.

        A brochure pointing at a promotion somebody deleted must read as "none of
        this is promoted", because silence there looks exactly like a healthy
        flyer.
        """
        db, _as, _scope = api
        _product(db, PRINTED_CODE)

        with TestClient(app) as c:
            report = _upload(c, promotionId=str(uuid.uuid4())).json()["report"]

        assert _codes(report["notPromoted"]) == [PRINTED_CODE]


# --------------------------------------------------------------------------- #
# Reading, listing, deleting
# --------------------------------------------------------------------------- #
class TestLifecycle:
    def test_a_reading_is_read_back_by_id(self, api) -> None:
        _db, _as, _scope = api

        with TestClient(app) as c:
            created = _upload(c, filename="zzt-read-back.pdf").json()
            got = c.get(f"/api/v1/dealer-kit/flyer-readings/{created['id']}")

        assert got.status_code == 200, got.text
        body = got.json()
        assert body["id"] == created["id"]
        assert body["filename"] == "zzt-read-back.pdf"
        assert body["uploadedAt"]
        assert body["report"]["unmatched"]

    def test_an_unknown_reading_is_404(self, api) -> None:
        _db, _as, _scope = api

        with TestClient(app) as c:
            missing = str(uuid.uuid4())
            got = c.get(f"/api/v1/dealer-kit/flyer-readings/{missing}")
            removed = c.delete(f"/api/v1/dealer-kit/flyer-readings/{missing}")

        assert got.status_code == 404, got.text
        assert removed.status_code == 404, removed.text
        # The message matters: an absent ROUTE also answers 404, and this test
        # would then pass while proving nothing.
        assert "reading" in got.text.lower(), got.text
        assert "reading" in removed.text.lower(), removed.text

    def test_deleting_a_reading_removes_it(self, api) -> None:
        """Hard delete, per the repo rule: DELETE means gone."""
        _db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

            assert c.delete(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 204
            assert c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 404
            assert reading_id not in [
                row["id"] for row in c.get("/api/v1/dealer-kit/flyer-readings").json()
            ]

    def test_the_list_is_newest_first(self, api) -> None:
        db, _as, _scope = api

        with TestClient(app) as c:
            first = _upload(c, filename="zzt-older.pdf").json()["id"]
            second = _upload(c, filename="zzt-newer.pdf").json()["id"]

            # Postgres `now()` is TRANSACTION time, and this whole test runs in
            # one, so both rows would otherwise carry the same timestamp and the
            # order would be luck. Stamped apart here so the ORDER BY is what is
            # actually being asserted.
            from datetime import datetime

            from app.models.dealer_kit import FlyerReadingRecord

            db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == first).update(
                {"created_at": datetime(2026, 1, 1, 9, 0, 0)}
            )
            db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == second).update(
                {"created_at": datetime(2026, 1, 2, 9, 0, 0)}
            )
            db.commit()

            listed = c.get("/api/v1/dealer-kit/flyer-readings")

        assert listed.status_code == 200, listed.text
        ids = [row["id"] for row in listed.json()]
        assert ids.index(second) < ids.index(first)

    def test_the_list_does_not_carry_reports(self, api) -> None:
        """One report per row would mean a match run per row, on a screen whose
        only job is to say which flyers have been uploaded."""
        _db, _as, _scope = api

        with TestClient(app) as c:
            _upload(c)
            row = c.get("/api/v1/dealer-kit/flyer-readings").json()[0]

        assert "report" not in row
        assert row["filename"]
        assert row["pageCount"] == 3


# --------------------------------------------------------------------------- #
# Who may do it
# --------------------------------------------------------------------------- #
class TestAccess:
    def test_an_editor_may_upload_read_and_delete(self, api) -> None:
        """Reading a flyer is drafting a catalogue, so page.edit is the gate and
        no new permission slug is invented for it."""
        _db, _as, _scope = api
        _as(_EDITOR_ID)

        with TestClient(app) as c:
            created = _upload(c)
            assert created.status_code == 201, created.text
            reading_id = created.json()["id"]
            assert c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 200
            assert c.delete(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 204

    def test_a_stranger_is_refused_on_every_route(self, api) -> None:
        _db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

        _as(_NOPERM_ID)
        with TestClient(app) as c:
            assert _upload(c).status_code == 403
            assert c.get("/api/v1/dealer-kit/flyer-readings").status_code == 403
            assert c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 403
            assert c.delete(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 403


class TestCompanyScope:
    def test_another_companys_reading_is_absent_not_forbidden(self, api) -> None:
        """404, never 403.

        403 confirms the id exists, which tells one company that another has a
        flyer - and the id is then a thing worth guessing at.
        """
        db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

        elsewhere = _company(db)
        _scope(elsewhere)

        with TestClient(app) as c:
            got = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}")
            removed = c.delete(f"/api/v1/dealer-kit/flyer-readings/{reading_id}")
            listed = c.get("/api/v1/dealer-kit/flyer-readings")

        assert got.status_code == 404, got.text
        assert removed.status_code == 404, removed.text
        assert reading_id not in [row["id"] for row in listed.json()]

        # And it is still there for the company that uploaded it: the 404 above
        # is a scope answer, not a delete that half worked.
        _scope(_SORENTO)
        with TestClient(app) as c:
            assert c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").status_code == 200


# --------------------------------------------------------------------------- #
# Headings
#
# The extractor reads a heading per page and the seed writes it as the section
# name, but the detail response did not carry it - so the review screen could
# say headings are guessed without showing WHICH ones were guessed wrong, and a
# reviewer had to open the builder and compare against the paper by hand.
# --------------------------------------------------------------------------- #
CORRECT_HEADING = "WATER CLOSET"  # fixture page 3, which the heuristic gets right
MISREAD_HEADING = "Transforming Your"  # fixture page 2, headed "BATHTUB COLLECTION"


class TestHeadings:
    def test_every_page_reports_the_heading_the_reader_found(self, api) -> None:
        """One entry per page, in printed order, so it reads beside the paper.

        Page order is the whole ergonomic: a reviewer holds the flyer and goes
        down the list. An arbitrary order would make them search for each page.
        """
        _db, _as, _scope = api

        with TestClient(app) as c:
            body = _upload(c).json()

        headings = body["headings"]
        assert [entry["page"] for entry in headings] == [1, 2, 3]
        assert headings[2]["text"] == CORRECT_HEADING

    def test_a_misread_heading_is_shown_and_not_quietly_repaired(self, api) -> None:
        """Fixture page 2 is headed "BATHTUB COLLECTION" on the paper.

        The heuristic reads "Transforming Your" instead. Surfacing the WRONG
        value is the entire point of the field: a reviewer can only correct what
        they can see, and a response that hid the misread would leave the screen
        saying headings need checking with nothing to check them against.
        """
        _db, _as, _scope = api

        with TestClient(app) as c:
            body = _upload(c).json()

        assert body["headings"][1]["text"] == MISREAD_HEADING

    def test_a_page_with_no_heading_is_still_listed(self, api) -> None:
        """A page that vanishes from the list is a page nobody checks.

        A pure-artwork flyer page yields no heading at all, and the seed names
        that section after its flyer page instead. The review list has to show
        the same page so the reviewer knows it needs a name, rather than seeing
        two entries for a three page flyer and assuming one was merged.
        """
        db, _as, _scope = api

        from app.models.dealer_kit import FlyerReadingRecord

        with TestClient(app) as c:
            reading_id = _upload(c).json()["id"]

            record = (
                db.query(FlyerReadingRecord)
                .filter(FlyerReadingRecord.id == reading_id)
                .one()
            )
            stripped = dict(record.reading_json)
            stripped["pages"] = [dict(page) for page in stripped["pages"]]
            stripped["pages"][0]["heading"] = None
            record.reading_json = stripped
            db.commit()

            body = c.get(f"/api/v1/dealer-kit/flyer-readings/{reading_id}").json()

        headings = body["headings"]
        assert [entry["page"] for entry in headings] == [1, 2, 3]
        assert headings[0]["text"] is None

    def test_the_list_screen_carries_no_headings(self, api) -> None:
        """Same reasoning as the report: the list says which flyers were read.

        Headings are a review concern. Putting them on the row would grow a
        screen nobody reviews from, for a field nobody reads there.
        """
        _db, _as, _scope = api

        with TestClient(app) as c:
            _upload(c, filename="zzt-headings-list.pdf")
            rows = c.get("/api/v1/dealer-kit/flyer-readings").json()

        assert rows
        assert all("headings" not in row for row in rows)
