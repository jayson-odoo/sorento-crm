"""The four surfaces that show money, all asking the same function (ADR 0008).

Written BEFORE the migration.

``resolve_prices`` has its own golden set in ``test_dealer_kit_pricing.py``.
What is under test HERE is that the catalogue tile, the quote line, the bundle
allocation and the public page all go THROUGH it, carrying the page's promotion,
rather than each reading ``products.list_price`` and formatting it themselves.

Three properties do most of the work:

* **No promotion means nothing changed.** Most pages carry no offer, so the
  no-promotion path is asserted with exact figures at every surface. A migration
  that quietly moved a list price by a cent would be the worst outcome here.
* **A price a viewer may not see is absent, not hidden.** The figure must not be
  recoverable from the payload, and neither must the promotion's id - naming the
  offer to a reader who cannot have it is the same leak in a different field.
* **One query for the whole page.** A per-tile lookup returns exactly the same
  answer as one query, so only a measurement can tell them apart.

Postgres only, on a blank scratch schema, every row prefixed ZZT: the dev
database is a copy of production.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: F401,E402

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.dealer_kit import (
    bundle_service,
    collection_service,
    selection_service,
)
from app.services.dealer_kit.bundle_pricing import (
    BundleComponentInput,
    allocate_bundle_price,
)
from app.services.dealer_kit.pricing import business_today
from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext
from tests._pg_fixture import blank_session, unique_code

DEALER = ViewerContext(access_codes=frozenset({"dealer"}))
CONSUMER = ViewerContext(access_codes=frozenset({"end_user"}))
STAFF = ViewerContext(is_staff=True)

BOTH_AUDIENCES = ["dealer", "end_user"]

_USER_ID = "3e8a5d61-7c92-4f13-8b06-2c7d9e4a1f58"


@pytest.fixture
def db():
    with blank_session() as session:
        from app.models.user import User

        session.add(
            User(id=_USER_ID, email="zzt-promo-pricing@test.com", name="ZZT", status="ACTIVE")
        )
        session.flush()
        yield session


def _product(db, *, list_price: str = "100.00", **overrides) -> Product:
    code = unique_code("ZZTPP")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
        invoice_price=Decimal("60.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    fields.update(overrides)
    product = Product(**fields)
    db.add(product)
    db.flush()
    return product


def _promotion(
    db,
    prices: dict[Product, str],
    *,
    access_levels: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> str:
    """A promotion offering ``prices`` to ``access_levels``.

    ``promotion_products.promotion_group_id`` is NOT NULL, so every offer needs a
    group even when the promotion has no bundle structure.
    """
    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=unique_code("ZZT promo"),
        start_date=start,
        end_date=end,
        is_active=True,
        access_levels=BOTH_AUDIENCES if access_levels is None else access_levels,
    )
    db.add(promotion)
    db.flush()

    group = PromotionGroup(promotion_id=promotion.id, group_name=unique_code("ZZT grp"))
    db.add(group)
    db.flush()
    for product, price in prices.items():
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promotion.id,
                promotion_group_id=group.id,
                product_id=product.id,
                promo_selling_price=Decimal(price),
            )
        )
    db.flush()
    return promotion.id


def _collection(db, *products):
    return collection_service.create_collection(
        db,
        scope="library",
        name=f"ZZT {unique_code('col')}",
        pinned_product_ids=[product.id for product in products],
        manual_order=[product.id for product in products],
    )


def _selection(db, *lines):
    selection = selection_service.create_selection(db, user_id=_USER_ID, name="ZZT design")
    db.flush()
    for product, quantity in lines:
        selection_service.add_line(db, selection, product.id, Decimal(str(quantity)))
    db.flush()
    return selection


def _bundle(db, price: str, *components):
    return bundle_service.create_bundle(
        db,
        name=f"ZZT {unique_code('bundle')}",
        price=Decimal(price),
        components=[{"product_id": product.id} for product in components],
    )


@contextmanager
def _promotion_selects(db):
    """Every SELECT that reads the promotion tables, so they can be counted.

    The ADR's performance rule is a property of the implementation, not of the
    answer: a per-tile lookup returns the same figures as one query. Only a
    measurement can tell them apart, so the count is asserted rather than
    assumed. Same listener shape as ``test_dealer_kit_pricing.py``.
    """
    from sqlalchemy import event

    statements: list[str] = []
    engine = db.connection().engine

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        text = statement.lstrip()
        if text.upper().startswith("SELECT") and "promotion" in text:
            statements.append(text)

    event.listen(engine, "after_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "after_cursor_execute", _record)


# --------------------------------------------------------------------------
# 1. The catalogue tile
# --------------------------------------------------------------------------


class TestTheCatalogueTile:
    def test_with_no_promotion_the_tile_is_exactly_the_list_price(self, db) -> None:
        # The regression that matters: most pages carry no offer, and this path
        # must be indistinguishable from before the migration.
        product = _product(db, list_price="1290.00")
        collection = _collection(db, product)

        tile = collection_service.resolve_tiles(db, collection, CONSUMER)[0]

        assert tile["price"] == "MYR 1,290.00"
        assert tile["offer_price"] is None

    def test_a_dealer_sees_the_offer_beside_the_list_price(self, db) -> None:
        # Beside, not instead of: the tile strikes the list price through, and a
        # tile handed only the offer could not show what the reader is saving.
        product = _product(db, list_price="100.00")
        collection = _collection(db, product)
        promotion_id = _promotion(db, {product: "79.00"})

        tile = collection_service.resolve_tiles(
            db, collection, DEALER, promotion_id=promotion_id
        )[0]

        assert tile["price"] == "MYR 100.00"
        assert tile["offer_price"] == "MYR 79.00"

    def test_a_consumer_is_never_told_a_dealer_offer_exists(self, db) -> None:
        product = _product(db, list_price="100.00")
        collection = _collection(db, product)
        promotion_id = _promotion(db, {product: "79.00"}, access_levels=["dealer"])

        tile = collection_service.resolve_tiles(
            db, collection, CONSUMER, promotion_id=promotion_id
        )[0]

        assert tile["offer_price"] is None
        assert tile["price"] == "MYR 100.00"
        # Absent, not hidden (AC-G7). Match the FORMATTED figure - bare digits
        # turn up inside uuids, so a substring check on "79" passes by luck.
        assert "MYR 79.00" not in str(tile)
        # And the promotion itself is not named: an id would tell the reader an
        # offer exists that they may not have, which is a support call at best.
        assert promotion_id not in str(tile)

    def test_a_tile_never_carries_a_promotion_uuid_even_for_the_dealer_who_gets_it(
        self, db
    ) -> None:
        # A uuid must never reach a screen. The offer is expressed as a figure.
        product = _product(db)
        collection = _collection(db, product)
        promotion_id = _promotion(db, {product: "79.00"})

        tile = collection_service.resolve_tiles(
            db, collection, DEALER, promotion_id=promotion_id
        )[0]

        assert tile["offer_price"] == "MYR 79.00"
        assert promotion_id not in str(tile)

    def test_an_expired_promotion_is_simply_no_offer(self, db) -> None:
        product = _product(db, list_price="100.00")
        collection = _collection(db, product)
        promotion_id = _promotion(
            db,
            {product: "79.00"},
            start=business_today() - timedelta(days=30),
            end=business_today() - timedelta(days=1),
        )

        tile = collection_service.resolve_tiles(
            db, collection, DEALER, promotion_id=promotion_id
        )[0]

        assert tile["offer_price"] is None
        assert tile["price"] == "MYR 100.00"

    def test_a_product_the_promotion_does_not_cover_keeps_its_list_price(self, db) -> None:
        covered = _product(db, list_price="100.00")
        uncovered = _product(db, list_price="55.00")
        collection = _collection(db, covered, uncovered)
        promotion_id = _promotion(db, {covered: "79.00"})

        tiles = collection_service.resolve_tiles(
            db, collection, DEALER, promotion_id=promotion_id
        )
        by_id = {tile["product_id"]: tile for tile in tiles}

        assert by_id[covered.id]["offer_price"] == "MYR 79.00"
        assert by_id[uncovered.id]["offer_price"] is None
        assert by_id[uncovered.id]["price"] == "MYR 55.00"


class TestOneQueryForTheWholeGrid:
    """Rule: the work does not grow with the number of tiles."""

    def _grid(self, db, size: int):
        products = [_product(db) for _ in range(size)]
        collection = _collection(db, *products)
        promotion_id = _promotion(db, {product: "79.00" for product in products})
        db.flush()
        return collection, promotion_id

    def test_a_bigger_grid_is_not_more_queries(self, db) -> None:
        small, small_promotion = self._grid(db, 2)
        large, large_promotion = self._grid(db, 20)

        with _promotion_selects(db) as for_small:
            collection_service.resolve_tiles(db, small, DEALER, promotion_id=small_promotion)
        with _promotion_selects(db) as for_large:
            tiles = collection_service.resolve_tiles(
                db, large, DEALER, promotion_id=large_promotion
            )

        assert len(tiles) == 20
        assert all(tile["offer_price"] == "MYR 79.00" for tile in tiles)
        assert len(for_large) == len(for_small), (
            f"{len(for_small)} statement(s) for 2 tiles but {len(for_large)} for 20 - "
            "the grid is pricing one tile at a time"
        )

    def test_it_is_exactly_one_query(self, db) -> None:
        collection, promotion_id = self._grid(db, 20)

        with _promotion_selects(db) as statements:
            collection_service.resolve_tiles(db, collection, DEALER, promotion_id=promotion_id)

        assert len(statements) == 1, statements

    def test_a_grid_with_no_promotion_asks_the_promotion_tables_nothing(self, db) -> None:
        # Most pages carry no offer. They must not pay for the feature.
        collection, _ = self._grid(db, 5)

        with _promotion_selects(db) as statements:
            collection_service.resolve_tiles(db, collection, DEALER)

        assert statements == []


# --------------------------------------------------------------------------
# 2. Quote lines, line totals and the subtotal
# --------------------------------------------------------------------------


class TestTheQuote:
    def test_with_no_promotion_the_lines_and_total_are_list_prices(self, db) -> None:
        first = _product(db, list_price="100.00")
        second = _product(db, list_price="250.50")
        selection = _selection(db, (first, 1), (second, 2))

        resolved = selection_service.resolve_selection(db, selection, STAFF)

        assert resolved["total"] == "601.00"
        assert all(line["offer_price"] is None for line in resolved["lines"])

    def test_a_promotion_prices_the_line_and_the_total(self, db) -> None:
        product = _product(db, list_price="100.00")
        selection = _selection(db, (product, 2))
        promotion_id = _promotion(db, {product: "79.00"})

        resolved = selection_service.resolve_selection(
            db, selection, DEALER, promotion_id=promotion_id
        )
        line = resolved["lines"][0]

        # The list price is still reported, so the quote can show the saving.
        assert line["price"] == "100.00"
        assert line["offer_price"] == "79.00"
        # What the customer pays is what the line and the total say.
        assert line["line_total"] == "158.00"
        assert resolved["total"] == "158.00"

    def test_the_subtotal_follows_the_offer(self, db) -> None:
        keep = _product(db, list_price="100.00")
        drop = _product(db, list_price="250.00")
        selection = _selection(db, (keep, 2), (drop, 1))
        promotion_id = _promotion(db, {keep: "79.00", drop: "200.00"})

        quote = selection_service.quote_selection(
            db,
            selection,
            DEALER,
            excluded_product_ids=[drop.id],
            promotion_id=promotion_id,
        )

        assert quote["subtotal"] == "158.00"
        assert quote["excluded_count"] == 1

    def test_a_consumer_quote_carries_neither_the_offer_nor_its_figure(self, db) -> None:
        product = _product(db, list_price="100.00")
        selection = _selection(db, (product, 1))
        promotion_id = _promotion(db, {product: "79.00"}, access_levels=["dealer"])

        quote = selection_service.quote_selection(
            db, selection, CONSUMER, promotion_id=promotion_id
        )

        assert quote["lines"][0]["offer_price"] is None
        assert quote["subtotal"] == "100.00"
        assert "79.00" not in str(quote)
        assert promotion_id not in str(quote)

    def test_the_subtotal_is_exact_money_not_rounded_arithmetic(self, db) -> None:
        # Decimal end to end (ADR 0008 rule 3). Summing formatted strings or
        # floats lands a quote a cent out, and the place that fails is the
        # invoice.
        first = _product(db, list_price="100.00")
        second = _product(db, list_price="100.00")
        selection = _selection(db, (first, 3), (second, 3))
        promotion_id = _promotion(db, {first: "33.33", second: "33.34"})

        quote = selection_service.quote_selection(
            db, selection, DEALER, promotion_id=promotion_id
        )

        assert quote["subtotal"] == "200.01"

    def test_an_unavailable_line_stays_out_of_the_total_even_when_it_is_on_offer(
        self, db
    ) -> None:
        live = _product(db, list_price="100.00")
        dead = _product(db, list_price="500.00", is_discontinued=True)
        selection = _selection(db, (live, 1), (dead, 1))
        promotion_id = _promotion(db, {live: "79.00", dead: "400.00"})

        quote = selection_service.quote_selection(
            db, selection, DEALER, promotion_id=promotion_id
        )

        assert quote["subtotal"] == "79.00"
        line = next(row for row in quote["lines"] if row["product_id"] == dead.id)
        assert line["included"] is False

    def test_the_quote_asks_the_promotion_tables_once(self, db) -> None:
        products = [_product(db) for _ in range(20)]
        selection = _selection(db, *((product, 1) for product in products))
        promotion_id = _promotion(db, {product: "79.00" for product in products})
        db.flush()

        with _promotion_selects(db) as statements:
            selection_service.quote_selection(
                db, selection, DEALER, promotion_id=promotion_id
            )

        assert len(statements) == 1, statements

    def test_a_selection_takes_its_promotion_from_the_page_it_was_built_from(
        self, db
    ) -> None:
        # The dealer designed this from a brochure. If the quote priced at list
        # while the page showed the offer, the two screens would disagree about
        # one product - which is the failure ADR 0008 exists to prevent.
        from app.services.dealer_kit import page_service

        product = _product(db, list_price="100.00")
        promotion_id = _promotion(db, {product: "79.00"})
        slug = unique_code("zzt-source").lower()
        page = page_service.create_page(
            db, name=f"ZZT {slug}", slug=slug, user_id=None, promotion_id=promotion_id
        )
        selection = selection_service.create_selection(
            db, user_id=_USER_ID, name="ZZT from page", source_page_id=page.id
        )
        db.flush()
        selection_service.add_line(db, selection, product.id, Decimal("1"))
        db.flush()

        assert selection_service.promotion_for(db, selection) == promotion_id

    def test_a_selection_with_no_source_page_has_no_promotion(self, db) -> None:
        # Opening the designer cold is a normal way to start, and it is list
        # prices, not an error.
        selection = _selection(db, (_product(db), 1))

        assert selection_service.promotion_for(db, selection) is None


# --------------------------------------------------------------------------
# 3. Bundle component prices
# --------------------------------------------------------------------------


class TestTheBundle:
    def test_with_no_promotion_the_allocation_is_the_list_price_split(self, db) -> None:
        # Exact figures, because this is the path every existing bundle takes.
        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="500.00")
        bundle = _bundle(db, "1000.00", first, second)

        resolved = bundle_service.resolve_bundle(db, bundle.id)
        allocated = {line["product_id"]: line["allocated"] for line in resolved["components"]}

        assert allocated[first.id] == "MYR 666.67"
        assert allocated[second.id] == "MYR 333.33"

    def test_an_offer_reweights_the_allocation(self, db) -> None:
        # The split is pro-rata by what the reader PAYS. Weighting by the list
        # price while quoting the offer would allocate a bundle a dealer buys
        # on promotion as though nothing were discounted.
        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="500.00")
        bundle = _bundle(db, "1000.00", first, second)
        promotion_id = _promotion(db, {first: "500.00"})

        resolved = bundle_service.resolve_bundle(
            db, bundle.id, viewer=DEALER, promotion_id=promotion_id
        )
        allocated = {line["product_id"]: line["allocated"] for line in resolved["components"]}

        assert allocated[first.id] == "MYR 500.00"
        assert allocated[second.id] == "MYR 500.00"

    def test_the_allocation_still_sums_exactly_when_an_offer_applies(self, db) -> None:
        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="500.00")
        third = _product(db, list_price="500.00")
        bundle = _bundle(db, "1000.00", first, second, third)
        promotion_id = _promotion(db, {first: "333.33"})

        resolved = bundle_service.resolve_bundle(
            db, bundle.id, viewer=DEALER, promotion_id=promotion_id
        )
        total = sum(
            Decimal(line["allocated"].replace("MYR", "").replace(",", "").strip())
            for line in resolved["components"]
        )

        assert total == Decimal("1000.00")

    def test_a_consumer_bundle_is_allocated_at_list_prices(self, db) -> None:
        first = _product(db, list_price="1000.00")
        second = _product(db, list_price="500.00")
        bundle = _bundle(db, "1000.00", first, second)
        promotion_id = _promotion(db, {first: "500.00"}, access_levels=["dealer"])

        resolved = bundle_service.resolve_bundle(
            db, bundle.id, viewer=CONSUMER, promotion_id=promotion_id
        )
        allocated = {line["product_id"]: line["allocated"] for line in resolved["components"]}

        assert allocated[first.id] == "MYR 666.67"
        assert promotion_id not in str(resolved)

    def test_the_bundle_asks_the_promotion_tables_once(self, db) -> None:
        products = [_product(db) for _ in range(10)]
        bundle = _bundle(db, "1000.00", *products)
        promotion_id = _promotion(db, {product: "50.00" for product in products})
        db.flush()

        with _promotion_selects(db) as statements:
            bundle_service.resolve_bundle(
                db, bundle.id, viewer=DEALER, promotion_id=promotion_id
            )

        assert len(statements) == 1, statements


class TestTheAllocationArithmetic:
    """The pure part: an offer is a weight, and the lines still sum exactly."""

    def test_the_weight_is_what_the_reader_pays(self) -> None:
        lines = allocate_bundle_price(
            Decimal("1000.00"),
            [
                BundleComponentInput(
                    key="a", list_price=Decimal("1000.00"), offer_price=Decimal("500.00")
                ),
                BundleComponentInput(key="b", list_price=Decimal("500.00")),
            ],
        )

        assert [line.allocated for line in lines] == [Decimal("500.00"), Decimal("500.00")]

    def test_no_offer_leaves_the_list_price_as_the_weight(self) -> None:
        lines = allocate_bundle_price(
            Decimal("1000.00"),
            [
                BundleComponentInput(key="a", list_price=Decimal("1000.00"), offer_price=None),
                BundleComponentInput(key="b", list_price=Decimal("500.00")),
            ],
        )

        assert [line.allocated for line in lines] == [Decimal("666.67"), Decimal("333.33")]

    def test_an_offer_of_zero_is_a_price_not_a_missing_one(self) -> None:
        # A promotion may genuinely price a component at nothing (a free
        # accessory in a bundle). Treating 0 as "no offer" would silently put
        # the list price back and allocate money to a line the customer is not
        # paying for.
        lines = allocate_bundle_price(
            Decimal("900.00"),
            [
                BundleComponentInput(
                    key="free", list_price=Decimal("100.00"), offer_price=Decimal("0")
                ),
                BundleComponentInput(key="paid", list_price=Decimal("900.00")),
            ],
        )

        assert [line.allocated for line in lines] == [Decimal("0.00"), Decimal("900.00")]

    def test_the_lines_still_sum_exactly_with_offers_in_play(self) -> None:
        lines = allocate_bundle_price(
            Decimal("100.00"),
            [
                BundleComponentInput(
                    key=str(index), list_price=Decimal("100.00"), offer_price=Decimal("33.33")
                )
                for index in range(3)
            ],
        )

        assert sum(line.allocated for line in lines) == Decimal("100.00")

    def test_quantity_still_multiplies_the_weight(self) -> None:
        lines = allocate_bundle_price(
            Decimal("300.00"),
            [
                BundleComponentInput(
                    key="two",
                    list_price=Decimal("500.00"),
                    offer_price=Decimal("100.00"),
                    quantity=2,
                ),
                BundleComponentInput(key="one", list_price=Decimal("100.00"), quantity=1),
            ],
        )

        assert [line.allocated for line in lines] == [Decimal("200.00"), Decimal("100.00")]


# --------------------------------------------------------------------------
# 4. The published page: the promotion reaches a real reader
# --------------------------------------------------------------------------


def test_the_pages_promotion_prices_its_public_tiles(db) -> None:
    """End to end: a link shared with a consumer quotes the consumer offer.

    This is the thread the whole migration exists to pull - the page carries the
    binding, and nothing between it and the tile has a price of its own.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.models.company import Company
    from app.models.dealer_kit import PageLabel, PageVersion
    from app.services.dealer_kit import page_service

    company = db.query(Company).filter(Company.code == "SRT").one()

    product = _product(db, list_price="100.00")
    collection = _collection(db, product)
    promotion_id = _promotion(db, {product: "79.00"}, access_levels=["end_user"])

    slug = unique_code("zzt-public").lower()
    page = page_service.create_page(
        db, name=f"ZZT {slug}", slug=slug, user_id=None, promotion_id=promotion_id
    )
    version = PageVersion(
        page_id=page.id,
        version=1,
        doc={
            "sections": [
                {
                    "id": "s1",
                    "blocks": [
                        {"props": {"kind": "collection", "collectionId": collection.id}}
                    ],
                }
            ]
        },
    )
    db.add(version)
    db.flush()
    db.add(PageLabel(page_id=page.id, label="published", version_id=version.id))
    db.flush()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as client:
            res = client.get(f"/api/v1/public/c/{company.code}/{slug}")
        assert res.status_code == 200, res.text
        tile = res.json()["collections"][collection.id][0]
        assert tile["price"] == "MYR 100.00"
        assert tile["offerPrice"] == "MYR 79.00"
    finally:
        app.dependency_overrides.clear()


def test_a_public_page_with_no_promotion_shows_list_prices(db) -> None:
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.models.company import Company
    from app.models.dealer_kit import PageLabel, PageVersion
    from app.services.dealer_kit import page_service

    company = db.query(Company).filter(Company.code == "SRT").one()

    product = _product(db, list_price="100.00")
    collection = _collection(db, product)
    # An offer exists in the database, but no page links it. It must not leak.
    promotion_id = _promotion(db, {product: "79.00"})

    slug = unique_code("zzt-plain").lower()
    page = page_service.create_page(db, name=f"ZZT {slug}", slug=slug, user_id=None)
    version = PageVersion(
        page_id=page.id,
        version=1,
        doc={
            "sections": [
                {
                    "id": "s1",
                    "blocks": [
                        {"props": {"kind": "collection", "collectionId": collection.id}}
                    ],
                }
            ]
        },
    )
    db.add(version)
    db.flush()
    db.add(PageLabel(page_id=page.id, label="published", version_id=version.id))
    db.flush()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as client:
            res = client.get(f"/api/v1/public/c/{company.code}/{slug}")
        assert res.status_code == 200, res.text
        tile = res.json()["collections"][collection.id][0]
        assert tile["price"] == "MYR 100.00"
        assert tile["offerPrice"] is None
        assert promotion_id not in res.text
    finally:
        app.dependency_overrides.clear()


def test_the_printed_copy_quotes_the_same_two_figures_as_the_screen(db) -> None:
    """Parity: the PDF payload and the public page report the same money.

    The user's requirement is one sentence - the PDF and the brochure on screen
    must look the same - and the rendering is genuinely one component. What is
    left to prove is that the two payloads feeding it agree, because a tile can
    only strike a list price through if it is handed BOTH figures.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.models.company import Company
    from app.models.dealer_kit import PageLabel, PageVersion
    from app.services.dealer_kit import export_service, page_service, render_token

    company = db.query(Company).filter(Company.code == "SRT").one()

    product = _product(db, list_price="1260.00")
    collection = _collection(db, product)
    promotion_id = _promotion(db, {product: "599.00"}, access_levels=["end_user"])

    slug = unique_code("zzt-parity").lower()
    page = page_service.create_page(
        db, name=f"ZZT {slug}", slug=slug, user_id=None, promotion_id=promotion_id
    )
    doc = {
        "sections": [
            {
                "id": "s1",
                "blocks": [
                    {"props": {"kind": "collection", "collectionId": collection.id}}
                ],
            }
        ]
    }
    version = PageVersion(page_id=page.id, version=1, doc=doc)
    db.add(version)
    db.flush()
    db.add(PageLabel(page_id=page.id, label="published", version_id=version.id))
    db.flush()

    # A consumer's copy: same audience as the anonymous reader of the link, so
    # the two payloads are directly comparable.
    download = export_service.request_export(
        db, page_id=page.id, audience="consumer", user_id=_USER_ID
    )
    db.flush()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as client:
            on_screen = client.get(f"/api/v1/public/c/{company.code}/{slug}")
            printed = client.get(
                f"/api/v1/public/print/{download.id}",
                params={"token": render_token.issue(download.id)},
            )
        assert on_screen.status_code == 200, on_screen.text
        assert printed.status_code == 200, printed.text

        screen_tile = on_screen.json()["collections"][collection.id][0]
        print_tile = printed.json()["collections"][collection.id][0]

        assert screen_tile["price"] == "MYR 1,260.00"
        assert screen_tile["offerPrice"] == "MYR 599.00"
        # The struck-through figure and the prominent one, identical on paper.
        assert print_tile["price"] == screen_tile["price"]
        assert print_tile["offerPrice"] == screen_tile["offerPrice"]
    finally:
        app.dependency_overrides.clear()


def test_an_anonymous_reader_of_a_collection_still_gets_list_prices(db) -> None:
    # ``resolve_tiles`` keeps its anonymous default, so a caller that knows
    # nothing about promotions behaves exactly as it did.
    product = _product(db, list_price="1290.00")
    collection = _collection(db, product)

    tile = collection_service.resolve_tiles(db, collection, ANONYMOUS)[0]

    assert tile["price"] == "MYR 1,290.00"
    assert tile["offer_price"] is None
