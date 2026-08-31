"""Turning a stored flyer reading into a DRAFT brochure (S7.4, group E).

Written before the route and the service exist.

The seed is the payoff of the whole slice: 36 A3 pages somebody spent weeks
laying out become a catalogue in the builder, which a human then corrects. Every
assertion here is something that decides whether that draft can be trusted.

* **AC-E1** one page, one section per flyer page, each ``printMode:
  breakBefore``. One page and not 36, so there is one publish, one label and one
  rollback (PLAN D2).
* **AC-E2** a version is written and NO label moves. A draft is a draft BY
  CONSTRUCTION - there is no draft flag anywhere, the absence of a label IS the
  draft, and approving it is the publish that already exists.
* **AC-E3** a printed row becomes one page-scoped collection: the cards in
  ``pinned_product_ids`` and the printed left-to-right order in ``manual_order``.
* **AC-E4** re-seeding writes a NEW version and NEW collections and mutates no
  existing one. This is the load-bearing one. A collection reused between two
  versions would make an older PUBLISHED version silently start rendering
  something else, which is the single thing versioning exists to prevent, so the
  test is written to fail the moment anybody "optimises" by reusing a row.
* **AC-E5** is `[E2E]` and is deliberately NOT attempted here. It asks that a
  dealer and a consumer see their own prices from one published document, which
  is a browser assertion against the review screen and the public page. A
  backend test that stopped at "the seeded doc holds no price" would look like
  E5 while proving something weaker, so E5 stays open and belongs with the FE
  slice.

Postgres only, on a blank scratch schema. Every row a test creates is ZZT-scoped
EXCEPT the product codes, which have to be the codes actually printed on the
fixture flyer - matching a printed code is the entire point, and a ZZT-prefixed
code would match nothing. Seeding runs off a REAL reading of the committed three
page fixture rather than a synthetic one, because the parts most likely to be
wrong (row splits, a misread heading, a code the master does not have) only
exist in the real document.
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
from tests._flyer_read import finish_reads, patch_flyer_read
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# What the fixture prints, verified in flyer_golden.json and re-confirmed against
# the extractor. Named here so a failing assertion reads as a flyer page rather
# than as a list of SKUs.
#
# Fixture page 2 is flyer page 3, the bathtub spread. Its middle row of three is
# printed 8037, 8030, 8041 - which is NOT alphabetical order, so asserting it
# proves the seed took the order off the paper rather than off the master.
BATHTUB_ROW = ["SRTJC8037", "SRTJC8030", "SRTJC8041"]
# The cover prints these two 6pt apart, so they are one printed row: this is the
# "two products under one photo" pattern the plan names as a real risk.
COVER_PAIR = ["SRTBF11102", "SRTWT51012"]

# Heading detection is a KNOWN heuristic and is KNOWN wrong here: fixture page 2
# is headed "BATHTUB COLLECTION" on the paper and reads as "Transforming Your".
# The seed carries the reading through verbatim and does not pretend otherwise -
# see TestHeading.
MISREAD_HEADING = "Transforming Your"
CORRECT_HEADING = "WATER CLOSET"  # fixture page 3, which the heuristic gets right
COVER_HEADING = "Inspiring Designs, Exciting Promotions"  # fixture page 1

_SORENTO = "00000000-0000-0000-0000-000000000001"

_ADMIN_ID = "2d7e4c03-88a5-5f19-b046-5c9f1e3a7d28"
_ADMIN_ROLE = "af3e6b52-4097-5d2a-c815-7e2b9d4f8c63"
_EDITOR_ID = "5c9b2f48-7da3-5e51-9024-3b8fac6d1e79"
_EDITOR_ROLE = "8e4d9026-3b5a-5c78-af19-2d5c7e4b9f3a"
_NOPERM_ID = "7b5ead39-2c86-5a4b-9d13-4f8c2b6e5a71"


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
            slug="zzt_seed_editor",
            name="ZZT Seed Editor",
            description="Seeds flyers into the Kit",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ADMIN_ID, email="zzt-fs-admin@test.com", name="FS Admin", status="ACTIVE"))
    db.add(User(id=_EDITOR_ID, email="zzt-fs-editor@test.com", name="FS Editor", status="ACTIVE"))
    db.add(User(id=_NOPERM_ID, email="zzt-fs-out@test.com", name="FS Outsider", status="ACTIVE"))
    db.flush()

    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.add(UserRoleAssignment(user_id=_EDITOR_ID, role_id=_EDITOR_ROLE))

    # The blank schema carries no permission rows, so the ones a migration seeds
    # in a real database are created here. The editor deliberately does NOT hold
    # `page.publish`: seeding a draft must never need it (AC-E2).
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

    Storage is faked even though nothing here asserts on a stored byte: seeding
    starts with an upload, an upload stores the flyer's banners, and unfaked that
    is a live PUT to the real bucket (see tests/_fake_storage.py).
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
        patch_flyer_read(monkeypatch, db)
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
            set_company_scope(db, frozenset({company_id}))

        _as(_ADMIN_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def _pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


def _upload(client: TestClient, *, filename: str = "zzt-flyer.pdf") -> str:
    res = client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": (filename, _pdf_bytes(), "application/pdf")},
    )
    # The read is a background job now: the POST answers 202 with the row in
    # `processing`, and the extraction happens when the worker runs the job.
    # `finish_reads` is that worker, on this test's own session.
    assert res.status_code == 202, res.text
    assert [job["status"] for job in finish_reads()] == ["done"]
    return res.json()["id"]


def _product(db, code: str):
    """A product carrying a code the fixture flyer actually prints.

    The CODE is real by necessity; everything else about the row is ZZT-scoped.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTFS")
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


def _products(db, codes) -> dict:
    return {code: _product(db, code) for code in codes}


def _company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTFSC")[:20],
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


def _seed(client: TestClient, reading_id: str, **body):
    """POST the seed.

    A body with no ``page_id`` gets a fresh ZZT name and address, which is the
    common case; a re-seed names its page and nothing else, because saying both
    is the ambiguity the route refuses.
    """
    if not body.get("page_id"):
        body.setdefault("name", unique_code("ZZT Catalogue"))
        body.setdefault("slug", unique_code("zzt-cat").lower())
    return client.post(f"/api/v1/dealer-kit/flyer-readings/{reading_id}/seed", json=body)


def _doc(db, page_id: str, version: int | None = None) -> dict:
    """The stored document of a page's version. Read from the DATABASE.

    The response is asserted separately; what a reader eventually renders is the
    stored doc, so the structural assertions read it rather than the summary.
    """
    from app.models.dealer_kit import PageVersion

    query = db.query(PageVersion).filter(PageVersion.page_id == page_id)
    if version is not None:
        query = query.filter(PageVersion.version == version)
    row = query.order_by(PageVersion.version.desc()).first()
    assert row is not None, "no version was written"
    return row.doc


def _collection_blocks(section: dict) -> list[dict]:
    return [block for block in section["blocks"] if block["type"] == "collection"]


def _collection_ids(section: dict) -> list[str]:
    return [block["props"]["collectionId"] for block in _collection_blocks(section)]


def _collection(db, collection_id: str):
    from app.models.dealer_kit import Collection

    return db.query(Collection).filter(Collection.id == collection_id).one()


def _codes(entries) -> list[str]:
    return [entry["code"] for entry in entries]


# --------------------------------------------------------------------------- #
# AC-E1 - one page, one section per flyer page, breakBefore on each
# --------------------------------------------------------------------------- #
class TestSectionsPerFlyerPage:
    def test_one_section_per_flyer_page_each_breaking_before(self, api) -> None:
        """Three fixture pages in, three sections out, in printed order.

        `breakBefore` on every section is what keeps the PDF export coming out
        as the same number of pages as the flyer (PLAN D2). The paginator
        already ignores a break on the first section, so applying it uniformly
        costs nothing and removes a special case nobody would remember.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _seed(c, reading_id)

        assert res.status_code == 201, res.text
        body = res.json()
        assert body["sectionCount"] == 3

        doc = _doc(db, body["pageId"])
        assert len(doc["sections"]) == 3
        assert [section["printMode"] for section in doc["sections"]] == [
            "breakBefore"
        ] * 3

    def test_one_page_and_not_one_per_flyer_page(self, api) -> None:
        """A reader scrolls ONE catalogue, not 36 URLs (PLAN D2).

        One page is also one publish, one label and one rollback. Thirty six
        pages would mean thirty six of each, and a partial publish nobody can
        see.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        pages = db.query(Page).filter(Page.id == body["pageId"]).all()
        assert len(pages) == 1
        assert db.query(Page).count() == 1

    def test_a_page_whose_codes_all_missed_is_still_a_section(self, api) -> None:
        """An empty master seeds three sections and no collections.

        Dropping the section would silently renumber every page after it, and a
        reviewer holding the flyer could no longer line the draft up against the
        paper. The section carries its heading and waits.
        """
        db, _as, _scope = api  # no products created at all

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        assert body["sectionCount"] == 3
        assert body["collectionCount"] == 0
        assert body["seededProductCount"] == 0

        doc = _doc(db, body["pageId"])
        assert [_collection_blocks(section) for section in doc["sections"]] == [[], [], []]

    def test_the_page_takes_the_flyers_paper(self, api) -> None:
        """The fixture is A3 portrait, so the brochure is.

        The PDF export reads the PAGE row's print profile, so a seed that left
        it at the A4 default would render an A3 layout onto A4 and overflow
        every section - which is the visible half of "the export still comes out
        as 36 pages" (PLAN D2).
        """
        db, _as, _scope = api

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        page = db.query(Page).filter(Page.id == body["pageId"]).one()
        assert page.print_profile["pageSize"] == "A3"
        assert page.print_profile["orientation"] == "portrait"
        # No generated cover: the flyer's own first page IS the cover, and
        # reserving another one puts a blank leading sheet in front of it.
        assert page.print_profile["cover"] is False
        # The document agrees with the row: the editor reads the doc, the PDF
        # reads the row, and a disagreement is a brochure that prints one way
        # and edits another.
        assert _doc(db, page.id)["printProfile"] == page.print_profile


# --------------------------------------------------------------------------- #
# AC-E2 - a version, and no label moves
# --------------------------------------------------------------------------- #
class TestDraftByConstruction:
    def test_the_seed_writes_a_version_and_moves_no_label(self, api) -> None:
        """No draft flag exists anywhere. The ABSENCE of a label is the draft."""
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.models.dealer_kit import PageLabel, PageVersion

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        assert body["version"] == 1
        versions = db.query(PageVersion).filter(PageVersion.page_id == body["pageId"]).all()
        assert len(versions) == 1
        assert versions[0].id == body["versionId"]

        labels = db.query(PageLabel).filter(PageLabel.page_id == body["pageId"]).all()
        assert labels == []

    def test_a_seeded_brochure_is_not_readable_by_the_public(self, api) -> None:
        """The consequence of no label, asserted where a reader would see it.

        ``published_doc`` deliberately does not fall back to the latest version,
        so an unapproved seed reaching a customer is impossible rather than
        unlikely.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.services.dealer_kit import page_service
        from app.services.error_handler import AppException

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        with pytest.raises(AppException) as raised:
            page_service.published_doc(db, body["slug"])
        assert raised.value.status_code == 404

    def test_seeding_does_not_need_the_publish_permission(self, api) -> None:
        """Drafting a catalogue and putting it in front of every dealer are two
        different levels of trust, and the seed is the first one."""
        _db, _as, _scope = api
        _as(_EDITOR_ID)  # holds page.view + page.edit, deliberately not publish

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _seed(c, reading_id)

        assert res.status_code == 201, res.text


# --------------------------------------------------------------------------- #
# AC-E3 - a printed row is a pinned, page-scoped collection
# --------------------------------------------------------------------------- #
class TestPrintedRows:
    def test_each_printed_row_becomes_one_page_scoped_collection(self, api) -> None:
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        # Fixture page 2 prints five rows; only the one this test created
        # products for can be seeded, so exactly one collection block lands.
        bathtub = doc["sections"][1]
        ids = _collection_ids(bathtub)
        assert len(ids) == 1

        collection = _collection(db, ids[0])
        assert collection.scope == "page"
        assert collection.page_id == body["pageId"]
        # Page-scoped and unnamed: it is an editor implementation detail that
        # dies with its page, and naming it would put it in the reusable library.
        assert collection.name is None

    def test_the_printed_order_survives_into_manual_order(self, api) -> None:
        """The paper decides the order, not the master.

        The row is printed 8037, 8030, 8041, which is not the order the codes
        sort in - so an implementation that sorted, or that used whatever order
        the product query returned, fails here.
        """
        db, _as, _scope = api
        products = _products(db, BATHTUB_ROW)
        printed = [products[code].id for code in BATHTUB_ROW]

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        collection = _collection(db, _collection_ids(doc["sections"][1])[0])

        assert collection.pinned_product_ids == printed
        assert collection.manual_order == printed

        # And it survives RESOLUTION, which is what a reader actually sees. A
        # manual_order the resolver ignores would pass the two asserts above and
        # still print the row in the wrong order.
        from app.services.dealer_kit import collection_service

        members = collection_service.resolve_members(db, collection)
        assert [member.id for member in members] == printed

    def test_a_row_carries_no_rule_only_its_pins(self, api) -> None:
        """A printed row is a hand-picked list, not a query (PLAN D3).

        Only 193 of the flyer's 347 printed rows sit wholly inside one promotion
        group, so a rule would quietly add and drop products the flyer never
        printed on that row. It also keeps resolution cheap: a pinned collection
        never scans the catalogue.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        collection = _collection(db, _collection_ids(doc["sections"][1])[0])
        assert collection.conditions_json is None
        assert collection.excluded_product_ids == []

    def test_two_products_printed_under_one_photo_both_get_a_tile(self, api) -> None:
        """A real pattern in this flyer, named in the plan's risks.

        The extractor emits both codes and does not decide which owns the
        picture, and neither does the seed: both are pinned, in printed order,
        and each resolves its own photo from the master. Collapsing them into
        one tile would drop a product from the catalogue on a guess.
        """
        db, _as, _scope = api
        products = _products(db, COVER_PAIR)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        collection = _collection(db, _collection_ids(doc["sections"][0])[0])
        assert collection.pinned_product_ids == [products[code].id for code in COVER_PAIR]

    def test_the_block_asks_for_as_many_columns_as_the_row_printed(self, api) -> None:
        """Column count comes from the paper, on desktop only.

        Six across on A3 is not six across on a phone, so the narrower
        breakpoints follow the builder's own defaults rather than the flyer's.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        block = _collection_blocks(doc["sections"][1])[0]
        assert block["props"]["columns"]["desktop"] == len(BATHTUB_ROW)
        assert block["props"]["columns"]["mobile"] == 1
        # No design is invented for the tile: null renders the builder's default
        # field set, and choosing one is a decision for the review screen.
        assert block["props"]["tileTemplateId"] is None

    def test_the_document_holds_bindings_and_never_a_price(self, api) -> None:
        """The rule a well-meaning change breaks first (AC-Z5, AC-G1).

        A price baked into a document freezes one number for every audience and
        breaks the one thing the Kit exists to do: serve staff, dealers and
        consumers the price each is allowed to see, from one published page.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        import json

        blob = json.dumps(_doc(db, body["pageId"]))
        assert "RM" not in blob
        assert "price" not in blob.lower()
        # Nor a product code or name: a tile binds a product ID and resolves the
        # rest per reader, so a snapshot here would go stale silently.
        for code in BATHTUB_ROW:
            assert code not in blob


# --------------------------------------------------------------------------- #
# Codes the master does not have
# --------------------------------------------------------------------------- #
class TestUnmatchedCodes:
    def test_a_code_with_no_product_is_left_out_and_named_in_the_response(
        self, api
    ) -> None:
        """38 of the real flyer's 998 codes resolve to nothing.

        They cannot be pinned - a collection pins product ids - and inventing a
        product for one would put a SKU nobody stocks in front of a customer
        (PLAN D8). So they are dropped from the document and listed in the
        response, because the difference between a gap and a silent loss is
        whether the person reviewing the seed can see it.
        """
        db, _as, _scope = api
        products = _products(db, ["SRTJC8037", "SRTJC8030"])  # 8041 is NOT created

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        assert "SRTJC8041" in _codes(body["skipped"])

        doc = _doc(db, body["pageId"])
        collection = _collection(db, _collection_ids(doc["sections"][1])[0])
        assert collection.pinned_product_ids == [
            products["SRTJC8037"].id,
            products["SRTJC8030"].id,
        ]

    def test_a_skipped_code_carries_the_page_and_the_nearest_match(self, api) -> None:
        """What did not make it, and what to do about it, in one list.

        The nearest existing code is a SUGGESTION and never applied (PLAN D8),
        and the page number is what lets a reviewer holding the flyer check it.
        """
        db, _as, _scope = api
        _product(db, "SRTJC8042")  # the flyer prints SRTJC8041

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        entry = next(row for row in body["skipped"] if row["code"] == "SRTJC8041")
        assert entry["pages"] == [2]
        assert entry["suggestion"]["productCode"] == "SRTJC8042"
        # No product id on the entry itself: nothing downstream can mistake the
        # suggestion for the answer.
        assert "productId" not in entry

    def test_a_row_where_nothing_matched_produces_no_collection(self, api) -> None:
        """An empty pinned collection renders a blank grid a designer can do
        nothing with, and hides the loss inside a page that looks complete. The
        row is dropped and its codes are in `skipped`, which says the same thing
        where somebody is reading."""
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)  # nothing on the cover or the WC spread

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        assert _collection_blocks(doc["sections"][0]) == []
        assert _collection_blocks(doc["sections"][2]) == []
        assert body["collectionCount"] == 1
        assert "SRTWC286-SH" in _codes(body["skipped"])


# --------------------------------------------------------------------------- #
# Headings
# --------------------------------------------------------------------------- #
class TestHeading:
    def test_a_misread_heading_is_carried_through_and_not_repaired(self, api) -> None:
        """Fixture page 2 is headed "BATHTUB COLLECTION" on the paper.

        The extractor's heuristic - largest non-card text in the top band -
        reads "Transforming Your" instead, and this is KNOWN (PLAN risks). The
        seed carries the reading through verbatim rather than guessing at a
        better answer, because a draft that quietly invents a heading is a draft
        nobody can check against the flyer. Correcting it is a five second edit
        on the review screen, which is exactly why heading carries the smallest
        fidelity weight.
        """
        db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        sections = _doc(db, body["pageId"])["sections"]
        headings = [
            block["props"]["text"]
            for section in sections
            for block in section["blocks"]
            if block["type"] == "heading"
        ]
        assert MISREAD_HEADING in headings
        assert CORRECT_HEADING in headings
        # And the section is NAMED the same thing, so the editor's own list
        # lines up against the flyer page by page.
        assert sections[1]["name"] == MISREAD_HEADING
        assert sections[2]["name"] == CORRECT_HEADING

    def test_a_page_with_no_heading_is_still_named_after_its_flyer_page(
        self, api
    ) -> None:
        """A section a reviewer cannot place is worse than an unnamed one.

        The heading is dropped from the stored reading first, so this is the
        real seed path over a real reading with one field missing - which is
        what a pure-artwork flyer page produces.
        """
        db, _as, _scope = api

        from app.models.dealer_kit import FlyerReadingRecord

        with TestClient(app) as c:
            reading_id = _upload(c)

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

            body = _seed(c, reading_id).json()

        section = _doc(db, body["pageId"])["sections"][0]
        assert section["name"] == "Page 1"
        assert [block for block in section["blocks"] if block["type"] == "heading"] == []


# --------------------------------------------------------------------------- #
# AC-E4 - re-seeding never touches what an older version renders
# --------------------------------------------------------------------------- #
class TestReseed:
    def test_reseeding_writes_a_new_version_and_brand_new_collections(self, api) -> None:
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _seed(c, reading_id).json()
            second = _seed(c, reading_id, page_id=first["pageId"]).json()

        assert second["pageId"] == first["pageId"]
        assert second["version"] == 2

        before = set(_collection_ids(_doc(db, first["pageId"], version=1)["sections"][1]))
        after = set(_collection_ids(_doc(db, first["pageId"], version=2)["sections"][1]))
        assert before and after
        assert before.isdisjoint(after)

    def test_an_older_version_still_renders_exactly_what_it_did(self, api) -> None:
        """The reason AC-E4 exists, exercised rather than described.

        Between the two seeds the master gains a product the first seed could
        not resolve. If the seed reused the first version's collection, version
        1 would silently start rendering a THIRD tile it was never approved
        with - and if that version were published, a customer would see it. So
        this asserts the old row's membership, not just the id.
        """
        db, _as, _scope = api
        products = _products(db, ["SRTJC8037", "SRTJC8030"])

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _seed(c, reading_id).json()

            old_id = _collection_ids(_doc(db, first["pageId"], version=1)["sections"][1])[0]
            old_pins = list(_collection(db, old_id).pinned_product_ids)

            # The master moves: the code the first seed had to skip now exists.
            late = _product(db, "SRTJC8041")

            second = _seed(c, reading_id, page_id=first["pageId"]).json()

        new_id = _collection_ids(_doc(db, first["pageId"], version=2)["sections"][1])[0]

        # The HARM first, before the id: what version 1 renders has not moved.
        # Asserted in this order deliberately, so a reuse fails on the damage it
        # does rather than only on a bookkeeping difference.
        old = _collection(db, old_id)
        assert old.pinned_product_ids == old_pins
        assert old.manual_order == old_pins
        assert late.id not in old.pinned_product_ids

        # And what it RESOLVES to has not moved either, which is what a reader
        # of the older version would actually receive.
        from app.services.dealer_kit import collection_service

        assert [member.id for member in collection_service.resolve_members(db, old)] == old_pins

        assert new_id != old_id
        assert late.id in _collection(db, new_id).pinned_product_ids
        assert "SRTJC8041" in _codes(first["skipped"])
        assert "SRTJC8041" not in _codes(second["skipped"])

    def test_reseeding_leaves_a_published_label_where_it_was(self, api) -> None:
        """Approving a draft is the publish that already exists (AC-E2).

        A seed that moved the label would put an unreviewed document in front of
        every reader the moment somebody re-read the flyer.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.services.dealer_kit import page_service

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _seed(c, reading_id).json()

            page_service.move_label(
                db, first["pageId"], "published", version_id=first["versionId"], user_id=None
            )

            second = _seed(c, reading_id, page_id=first["pageId"]).json()

        live = page_service.published_doc(db, first["slug"])
        assert live["version"] == 1
        assert live["doc"] == _doc(db, first["pageId"], version=1)
        assert second["version"] == 2

    def test_seeding_a_second_page_at_the_same_address_is_refused_in_words(
        self, api
    ) -> None:
        """A re-seed says which page it is re-seeding.

        Nothing links a reading to a page it seeded earlier, deliberately: a
        reading is a working artefact and one flyer may legitimately seed a
        dealer brochure and a consumer one. So the address collides, and the
        answer names the address rather than a constraint.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        with TestClient(app) as c:
            reading_id = _upload(c)
            slug = unique_code("zzt-cat").lower()
            first = _seed(c, reading_id, slug=slug)
            again = _seed(c, reading_id, slug=slug)

        assert first.status_code == 201, first.text
        assert again.status_code == 409, again.text
        assert slug in again.text

    def test_a_seed_into_an_unknown_page_is_404(self, api) -> None:
        _db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _seed(c, reading_id, page_id=str(uuid.uuid4()))

        assert res.status_code == 404, res.text
        # The message matters: an absent ROUTE answers 404 too, and this test
        # would then pass while proving nothing.
        assert "page" in res.text.lower()

    def test_a_seed_must_say_where_it_is_going(self, api) -> None:
        """Neither a target page nor a name and address is a 422 that names both
        ways out. Guessing (creating a page called "Flyer") leaves a designer
        hunting for a catalogue they did not name."""
        _db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c)
            nothing = c.post(
                f"/api/v1/dealer-kit/flyer-readings/{reading_id}/seed", json={}
            )
            both = c.post(
                f"/api/v1/dealer-kit/flyer-readings/{reading_id}/seed",
                json={
                    "page_id": str(uuid.uuid4()),
                    "name": unique_code("ZZT Catalogue"),
                    "slug": unique_code("zzt-cat").lower(),
                },
            )

        assert nothing.status_code == 422, nothing.text
        assert "name" in nothing.text.lower() and "address" in nothing.text.lower()
        # Both a target page AND a new name is ambiguous, and the ambiguity
        # resolves into the wrong one half the time.
        assert both.status_code == 422, both.text


# --------------------------------------------------------------------------- #
# The promotion the flyer IS
# --------------------------------------------------------------------------- #
class TestPromotion:
    def test_the_promotion_is_applied_when_the_seed_is_given_one(self, api) -> None:
        """A brochure links to exactly ONE promotion, explicitly (PLAN D5).

        The seed takes it as a parameter because the review screen is where a
        human is already answering that question - it is the screen that reports
        what the promotion does not carry - so the click that approves the seed
        IS the explicit act D5 requires. It is never inferred from the filename.
        """
        db, _as, _scope = api
        products = _products(db, BATHTUB_ROW)
        promotion_id = _promotion(db, products["SRTJC8037"])

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id, promotion_id=promotion_id).json()

        assert db.query(Page).filter(Page.id == body["pageId"]).one().promotion_id == promotion_id

    def test_a_seed_with_no_promotion_links_nothing(self, api) -> None:
        """No link means list prices, which is a normal end state (PLAN D6).

        Nothing is inferred from the uploaded filename here, even though the
        real flyer's filename IS a promotion's description.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c, filename="zzt-flyer.pdf")
            body = _seed(c, reading_id).json()

        assert db.query(Page).filter(Page.id == body["pageId"]).one().promotion_id is None

    def test_reseeding_without_one_does_not_unlink_the_page(self, api) -> None:
        """Silently dropping a live brochure's offer is the worse failure.

        Clearing the link is the existing PUT on the page, which says so out
        loud. An omitted field on a re-seed means "leave it alone".
        """
        db, _as, _scope = api
        products = _products(db, BATHTUB_ROW)
        promotion_id = _promotion(db, products["SRTJC8037"])

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _seed(c, reading_id, promotion_id=promotion_id).json()
            _seed(c, reading_id, page_id=first["pageId"])

        assert db.query(Page).filter(Page.id == first["pageId"]).one().promotion_id == promotion_id

    def test_reseeding_with_one_does_not_reprice_the_live_brochure(self, api) -> None:
        """The promotion lives on the PAGE, and `published_doc` reads it from
        there - so changing it changes what readers see RIGHT NOW, before
        anybody publishes the new version.

        The review screen always sends its header promotion (that select drives
        the "not in this promotion" report), so a reviewer comparing a reading
        against a different offer used to re-price the live catalogue just by
        clicking Seed. The panel promised the opposite three lines from the
        button: "The live version N is untouched until somebody publishes the
        new one."

        Same rule as the print profile directly above it in `_target_page`:
        applied on CREATION, never on a re-seed. Changing a live brochure's
        offer is the page's own PUT, which says so out loud.
        """
        db, _as, _scope = api
        products = _products(db, BATHTUB_ROW)
        original = _promotion(db, products["SRTJC8037"])
        other = _promotion(db, products["SRTJC8037"])

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _seed(c, reading_id, promotion_id=original).json()
            _seed(c, reading_id, page_id=first["pageId"], promotion_id=other)

        assert (
            db.query(Page).filter(Page.id == first["pageId"]).one().promotion_id
            == original
        )

    def test_an_unknown_promotion_is_still_refused_on_a_reseed(self, api) -> None:
        """Ignored is not unvalidated. A bad id in the payload is still a 404,
        so a typo is reported rather than quietly dropped."""
        db, _as, _scope = api
        products = _products(db, BATHTUB_ROW)
        promotion_id = _promotion(db, products["SRTJC8037"])

        with TestClient(app) as c:
            reading_id = _upload(c)
            first = _seed(c, reading_id, promotion_id=promotion_id).json()
            res = _seed(
                c, reading_id, page_id=first["pageId"], promotion_id=str(uuid.uuid4())
            )

        assert res.status_code == 404, res.text

    def test_an_unknown_promotion_is_refused_and_no_page_is_left_behind(
        self, api
    ) -> None:
        """Validated before anything is written, so a bad link cannot leave a
        half-made catalogue for somebody to find later."""
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _seed(c, reading_id, promotion_id=str(uuid.uuid4()))

        assert res.status_code == 404, res.text
        assert "promotion" in res.text.lower()
        assert db.query(Page).count() == 0

    @pytest.mark.parametrize("bad", ["not-a-uuid", "123", "SRTJC8041"])
    def test_a_malformed_promotion_id_never_reaches_the_database(self, api, bad) -> None:
        """422 at the edge, not a 500 out of the driver. This feature has
        produced that 500 once already."""
        _db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c)
            res = _seed(c, reading_id, promotion_id=bad)

        assert res.status_code == 422, res.text


# --------------------------------------------------------------------------- #
# Who may seed, and whose flyer
# --------------------------------------------------------------------------- #
class TestAccess:
    def test_a_stranger_may_not_seed(self, api) -> None:
        _db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c)

        _as(_NOPERM_ID)
        with TestClient(app) as c:
            assert _seed(c, reading_id).status_code == 403


class TestCompanyScope:
    def test_another_companys_reading_cannot_be_seeded(self, api) -> None:
        """404, never 403: 403 confirms the id exists.

        And nothing is written. A seed that 404'd after creating the page would
        leave one company's catalogue sitting in another's list.
        """
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.models.dealer_kit import Page

        with TestClient(app) as c:
            reading_id = _upload(c)

        _scope(_company(db))
        with TestClient(app) as c:
            res = _seed(c, reading_id)

        assert res.status_code == 404, res.text
        assert "reading" in res.text.lower()
        assert db.query(Page).count() == 0

    def test_the_seeded_catalogue_belongs_to_the_readings_company(self, api) -> None:
        """A reading is only reachable inside its own company, so the active
        scope IS that company - and page and collections are stamped with it."""
        db, _as, _scope = api
        _products(db, BATHTUB_ROW)

        from app.models.dealer_kit import Collection, Page

        with TestClient(app) as c:
            reading_id = _upload(c)
            body = _seed(c, reading_id).json()

        assert db.query(Page).filter(Page.id == body["pageId"]).one().company_id == _SORENTO
        collections = db.query(Collection).filter(Collection.page_id == body["pageId"]).all()
        assert collections
        assert {row.company_id for row in collections} == {_SORENTO}


class TestTheReviewedHeadingIsTheSeededHeading:
    """The cross-check that makes the review screen's heading list worth having.

    The reading detail reports headings so a reviewer can compare them against
    the paper BEFORE seeding. That is only useful if what they were shown is
    what the seed actually writes - two independent readers of
    ``page["heading"]`` could drift apart and the review would quietly be of
    something else.
    """

    def test_what_the_review_reports_is_what_the_sections_are_named(
        self, api
    ) -> None:
        db, _as, _scope = api

        with TestClient(app) as c:
            reading_id = _upload(c)
            reported = [
                entry["text"]
                for entry in c.get(
                    f"/api/v1/dealer-kit/flyer-readings/{reading_id}"
                ).json()["headings"]
            ]
            body = _seed(c, reading_id).json()

        sections = _doc(db, body["pageId"])["sections"]
        assert reported == [COVER_HEADING, MISREAD_HEADING, CORRECT_HEADING]
        assert [section["name"] for section in sections] == reported

    def test_a_page_with_no_heading_reports_null_and_seeds_its_page_number(
        self, api
    ) -> None:
        """The two sides answer the SAME gap differently, and both are right.

        The review says null, because "the reader found nothing here" is the
        thing a reviewer needs to know. The seed names the section after its
        flyer page, because an unnamed section cannot be placed in the editor's
        list. Pinned together so neither is changed to match the other by
        somebody who sees only one of them.
        """
        db, _as, _scope = api

        from app.models.dealer_kit import FlyerReadingRecord

        with TestClient(app) as c:
            reading_id = _upload(c)

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

            reported = c.get(
                f"/api/v1/dealer-kit/flyer-readings/{reading_id}"
            ).json()["headings"]
            body = _seed(c, reading_id).json()

        assert reported[0]["text"] is None
        sections = _doc(db, body["pageId"])["sections"]
        assert sections[0]["name"] != ""
        assert "1" in sections[0]["name"]


# --------------------------------------------------------------------------- #
# An adopted code is a matched code, seeding included (PLAN-flyer-code-adopt.md)
# --------------------------------------------------------------------------- #
class TestAdoptedCodesAreSeeded:
    """AC-A.2. ``flyer_seed_service.product_by_code`` is built straight off
    ``report.matched`` (S1's design note), so an adopted code needs no change
    there to be placed - this pins that it actually is, on the real fixture,
    rather than trusting the claim.
    """

    def test_an_adopted_code_is_placed_in_its_printed_row(self, api) -> None:
        # BATHTUB_ROW is 8037, 8030, 8041 in PRINTED order. Products are made
        # for two of the three; the third is adopted onto a product with an
        # unrelated code, so only the adoption can be why it is placed at all.
        db, _as, _scope = api
        products = _products(db, ["SRTJC8030", "SRTJC8041"])
        adopted = _product(db, "ZZTFSADOPTED")

        with TestClient(app) as c:
            reading_id = _upload(c)
            put = c.put(
                f"/api/v1/dealer-kit/flyer-readings/{reading_id}"
                "/code-overrides/SRTJC8037",
                json={"productId": adopted.id},
            )
            assert put.status_code == 200, put.text
            body = _seed(c, reading_id).json()

        doc = _doc(db, body["pageId"])
        collection = _collection(db, _collection_ids(doc["sections"][1])[0])

        assert collection.pinned_product_ids == [
            adopted.id,
            products["SRTJC8030"].id,
            products["SRTJC8041"].id,
        ]
