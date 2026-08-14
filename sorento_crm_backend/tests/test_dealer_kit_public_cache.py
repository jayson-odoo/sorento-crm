"""What the public catalogue costs to serve, and how stale it may get.

The seeded A3 brochure is 341 printed rows, and each one is a collection. The
first version of this route fetched and resolved them ONE AT A TIME: a row per
query for the collection, then two more for its photos and its prices. Around a
thousand round trips for one page view, none of them slow on its own, and it was
most of the thirteen seconds a reader waited.

Two things fix it and each is tested here:

* **Bulk resolution.** Members are decided per collection in Python, then the
  union is priced and photographed once. The query count must stop growing with
  the number of collections, so the assertion is on a COUNT and not on a clock.
* **A short cache.** Bounded by one TTL rather than pinned to the version id,
  because a published page is a version plus two mutable joins (the promotion
  lives on the page, collections resolve at read time). Publishing has to bust
  it, or the button visibly does nothing.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import company_scope
from app.models.company import Company
from app.models.dealer_kit import Collection, Page, PageLabel, PageVersion
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.dealer_kit import collection_service, public_cache
from app.services.dealer_kit import page_service
from app.services.dealer_kit.viewer import ANONYMOUS
from app.services.error_handler import AppException
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


@pytest.fixture(autouse=True)
def _no_carry_over():
    """The cache is process-global, so one test must not answer another's read."""
    public_cache.clear()
    yield
    public_cache.clear()


def _company(db, label: str) -> Company:
    company = Company(
        id=str(uuid.uuid4()),
        name=f"ZZT {label}",
        code=unique_code(f"ZZT{label}")[:20],
        is_active=True,
    )
    db.add(company)
    db.flush()
    return company


def _product(db, index: int) -> Product:
    """Its own category and uom: both are NOT NULL, and CI's database is empty
    so there is nothing to borrow."""
    code = unique_code(f"ZZTP{index}")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        product_code=code,
        product_name=f"ZZT product {index}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("50.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _pins_collection(db, page_id, products) -> Collection:
    collection = Collection(
        scope="page",
        page_id=page_id,
        name=f"ZZT row {unique_code('r')}",
        conditions_json=None,
        pinned_product_ids=[product.id for product in products],
    )
    db.add(collection)
    db.flush()
    return collection


def _published(db, company: Company, slug: str, collection_count: int, per_row: int):
    """A page whose document binds `collection_count` hand-picked rows."""
    with company_scope(db, frozenset({company.id})):
        products = [_product(db, index) for index in range(per_row)]
        page = Page(name="ZZT brochure", slug=slug, print_profile=None)
        db.add(page)
        db.flush()

        blocks = []
        for _ in range(collection_count):
            collection = _pins_collection(db, page.id, products)
            blocks.append(
                {
                    "id": str(uuid.uuid4()),
                    "props": {"kind": "collection", "collectionId": collection.id},
                }
            )

        version = PageVersion(
            page_id=page.id,
            version=1,
            doc={"sections": [{"id": "s1", "name": "ZZT", "blocks": blocks}]},
        )
        db.add(version)
        db.flush()
        db.add(PageLabel(page_id=page.id, label="published", version_id=version.id))
        db.flush()
    return page


def _client(db) -> TestClient:
    from app.database import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


class _Counter:
    """Counts statements issued on one connection, for the duration of a block."""

    def __init__(self, db):
        self._bind = db.get_bind()
        self.count = 0

    def _on_execute(self, *args, **kwargs):
        self.count += 1

    def __enter__(self):
        event.listen(self._bind, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self._bind, "before_cursor_execute", self._on_execute)
        return False


def test_resolving_many_collections_does_not_cost_more_queries_than_resolving_few():
    """The whole point. Ten rows and forty rows must cost the same round trips."""
    with pg_session() as db:
        company = _company(db, "COST")
        with company_scope(db, frozenset({company.id})):
            products = [_product(db, index) for index in range(3)]
            page = Page(name="ZZT cost", slug=unique_code("zzt-cost").lower())
            db.add(page)
            db.flush()
            few = [_pins_collection(db, page.id, products) for _ in range(4)]
            many = [_pins_collection(db, page.id, products) for _ in range(40)]
            db.flush()

            with _Counter(db) as counting_few:
                collection_service.resolve_tiles_bulk(db, few, ANONYMOUS)
            with _Counter(db) as counting_many:
                collection_service.resolve_tiles_bulk(db, many, ANONYMOUS)

        assert counting_many.count == counting_few.count, (
            f"cost grew with collection count: {counting_few.count} -> {counting_many.count}"
        )


def test_bulk_resolution_says_the_same_thing_as_resolving_one_at_a_time():
    """A faster answer that is a different answer is not a fix."""
    with pg_session() as db:
        company = _company(db, "SAME")
        with company_scope(db, frozenset({company.id})):
            products = [_product(db, index) for index in range(4)]
            page = Page(name="ZZT same", slug=unique_code("zzt-same").lower())
            db.add(page)
            db.flush()
            # Deliberately overlapping membership: the union is de-duped, and a
            # product on two rows must still appear on both.
            rows = [
                _pins_collection(db, page.id, products[:2]),
                _pins_collection(db, page.id, products[1:]),
                _pins_collection(db, page.id, []),
            ]
            db.flush()

            bulk = collection_service.resolve_tiles_bulk(db, rows, ANONYMOUS)
            one_at_a_time = {
                row.id: collection_service.resolve_tiles(db, row, ANONYMOUS) for row in rows
            }

        assert bulk == one_at_a_time


def test_a_second_reader_is_served_from_the_cache_without_touching_the_database():
    with pg_session() as db:
        company = _company(db, "WARM")
        slug = unique_code("zzt-warm").lower()
        _published(db, company, slug, collection_count=3, per_row=2)
        try:
            with _client(db) as client:
                first = client.get(f"/api/v1/public/c/{company.code}/{slug}")
                assert first.status_code == 200, first.text

                with _Counter(db) as counting:
                    second = client.get(f"/api/v1/public/c/{company.code}/{slug}")

            assert second.status_code == 200
            assert second.json() == first.json()
            # One query: resolving the company code, which happens before the
            # cache is consulted because the cache is keyed on the company id.
            assert counting.count == 1, f"cache miss: {counting.count} queries"
        finally:
            app.dependency_overrides.clear()


def test_a_reader_who_already_has_this_payload_gets_a_304():
    with pg_session() as db:
        company = _company(db, "ETAG")
        slug = unique_code("zzt-etag").lower()
        _published(db, company, slug, collection_count=2, per_row=1)
        try:
            with _client(db) as client:
                first = client.get(f"/api/v1/public/c/{company.code}/{slug}")
                etag = first.headers.get("etag")
                assert etag, "no ETag was offered, so a reader can never revalidate"

                again = client.get(
                    f"/api/v1/public/c/{company.code}/{slug}",
                    headers={"If-None-Match": etag},
                )
            assert again.status_code == 304
            assert again.content == b""
        finally:
            app.dependency_overrides.clear()


def test_publishing_a_new_version_reaches_the_next_reader_immediately():
    """The one staleness case that is indefensible: somebody pressed Publish."""
    with pg_session() as db:
        company = _company(db, "PUB")
        slug = unique_code("zzt-pub").lower()
        page = _published(db, company, slug, collection_count=1, per_row=1)
        try:
            with _client(db) as client:
                before = client.get(f"/api/v1/public/c/{company.code}/{slug}")
                assert before.status_code == 200

                with company_scope(db, frozenset({company.id})):
                    second = PageVersion(
                        page_id=page.id,
                        version=2,
                        doc={"sections": [{"id": "s2", "name": "ZZT AFTER", "blocks": []}]},
                    )
                    db.add(second)
                    db.flush()
                    page_service.move_label(
                        db, page.id, "published", version_id=second.id, user_id=None
                    )

                after = client.get(f"/api/v1/public/c/{company.code}/{slug}")

            assert after.status_code == 200
            assert after.json()["doc"]["sections"][0]["name"] == "ZZT AFTER"
        finally:
            app.dependency_overrides.clear()


def test_two_companies_holding_the_same_slug_do_not_share_a_cache_entry():
    """The cache is keyed on the company id, not the code and not the slug."""
    with pg_session() as db:
        sorento = _company(db, "CA")
        mocha = _company(db, "CB")
        slug = unique_code("zzt-shared").lower()
        _published(db, sorento, slug, collection_count=1, per_row=1)
        _published(db, mocha, slug, collection_count=2, per_row=1)
        try:
            with _client(db) as client:
                first = client.get(f"/api/v1/public/c/{sorento.code}/{slug}")
                second = client.get(f"/api/v1/public/c/{mocha.code}/{slug}")

            assert first.status_code == 200 and second.status_code == 200
            assert len(first.json()["collections"]) == 1
            assert len(second.json()["collections"]) == 2
        finally:
            app.dependency_overrides.clear()


def _tile_template(db, name: str):
    from app.models.dealer_kit import TileTemplate

    template = TileTemplate(name=name, doc={"fields": ["image", "name", "price"]})
    db.add(template)
    db.flush()
    return template


def test_a_block_that_names_no_design_uses_the_pages():
    """The actual defect behind "I chose a tile design and nothing changed".

    A brochure seeded from the printed flyer is 341 collection blocks that bind
    a design on NONE of them, and the only control was per block.
    """
    with pg_session() as db:
        company = _company(db, "DFLT")
        slug = unique_code("zzt-dflt").lower()
        page = _published(db, company, slug, collection_count=2, per_row=1)
        try:
            with company_scope(db, frozenset({company.id})):
                template = _tile_template(db, f"ZZT compact {unique_code('t')}")
                page_service.set_tile_template(db, page.id, template.id)

            with _client(db) as client:
                res = client.get(f"/api/v1/public/c/{company.code}/{slug}")

            assert res.status_code == 200, res.text
            body = res.json()
            # The document is NOT rewritten on its way to a reader: the blocks
            # genuinely name no design, the page does.
            blocks = body["doc"]["sections"][0]["blocks"]
            assert all(b["props"].get("tileTemplateId") is None for b in blocks)
            assert body["defaultTileTemplateId"] == template.id
            # And its fields are sent, so the renderer has something to resolve
            # the fallback against.
            assert body["tileTemplates"][template.id] == ["image", "name", "price"]
        finally:
            app.dependency_overrides.clear()


def test_applying_a_design_reaches_the_next_reader_immediately():
    """It changes what every tile on the LIVE page looks like."""
    with pg_session() as db:
        company = _company(db, "TAPP")
        slug = unique_code("zzt-tapp").lower()
        page = _published(db, company, slug, collection_count=1, per_row=1)
        try:
            with _client(db) as client:
                before = client.get(f"/api/v1/public/c/{company.code}/{slug}")
                assert before.json()["defaultTileTemplateId"] is None

                with company_scope(db, frozenset({company.id})):
                    template = _tile_template(db, f"ZZT bold {unique_code('t')}")
                    page_service.set_tile_template(db, page.id, template.id)

                after = client.get(f"/api/v1/public/c/{company.code}/{slug}")

            assert after.json()["defaultTileTemplateId"] == template.id
        finally:
            app.dependency_overrides.clear()


def test_clearing_the_design_is_a_finished_state_not_an_error():
    with pg_session() as db:
        company = _company(db, "TCLR")
        slug = unique_code("zzt-tclr").lower()
        page = _published(db, company, slug, collection_count=1, per_row=1)
        try:
            with company_scope(db, frozenset({company.id})):
                template = _tile_template(db, f"ZZT clr {unique_code('t')}")
                page_service.set_tile_template(db, page.id, template.id)
                cleared = page_service.set_tile_template(db, page.id, None)

            assert cleared.tile_template_id is None
        finally:
            app.dependency_overrides.clear()


def test_a_design_that_does_not_exist_is_refused():
    with pg_session() as db:
        company = _company(db, "TMIS")
        slug = unique_code("zzt-tmis").lower()
        page = _published(db, company, slug, collection_count=1, per_row=1)
        with company_scope(db, frozenset({company.id})):
            with pytest.raises(AppException) as caught:
                page_service.set_tile_template(db, page.id, str(uuid.uuid4()))
        assert caught.value.status_code == 404
