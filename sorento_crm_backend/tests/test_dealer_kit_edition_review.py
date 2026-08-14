"""What changed since the last Edition (S2.5.5, AC-L9).

The load-bearing case is the DROPPED product. `resolve_members` filters
`is_discontinued` and `is_active` out of the candidate set AND repeats the
filter on the pinned path, so a product discontinued since the catalogue was
built does not render struck through - it disappears, and the collection
quietly holds one fewer product. 5,317 live products are discontinued, so this
is the ordinary case.

These tests pin that the pin is reported even though the member is gone,
because the pin is the only place the information still exists.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.dealer_kit import Collection, Edition, Page, PageVersion
from app.models.inventory import Stock
from app.models.product import Product
from app.services.dealer_kit import edition_review_service as review_service
from tests._pg_fixture import blank_session, unique_code

_MIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "318_dealer_kit_edition.py"
)
_spec = importlib.util.spec_from_file_location("mig_318_review", _MIG_PATH)
mig318 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig318)


@pytest.fixture
def db():
    with blank_session() as session:
        mig318._seed_graph(session.connection())
        session.flush()
        yield session


def _reference(db):
    """A category and a UOM, because products carry NOT NULL FKs to both."""
    from app.models.product import ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("ZZTC"),
        category_name=unique_code("ZZT Cat"),
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=unique_code("ZZTU"),
        uom_name=unique_code("ZZT Uom"),
    )
    db.add_all([category, uom])
    db.flush()
    return category, uom


def _product(
    db,
    *,
    discontinued: bool = False,
    active: bool = True,
    created_at: datetime | None = None,
) -> Product:
    category, uom = _reference(db)
    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("ZZTP"),
        product_name=unique_code("ZZT Product"),
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("199.00"),
        currency="MYR",
        is_active=active,
        is_discontinued=discontinued,
    )
    db.add(product)
    db.flush()
    if created_at is not None:
        product.created_at = created_at
        db.flush()
    return product


def _page_with_collection(db, pinned: list[str]) -> tuple[Page, Collection]:
    page = Page(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Page"),
        slug=unique_code("zzt-rev").lower(),
    )
    db.add(page)
    db.flush()

    collection = Collection(
        id=str(uuid.uuid4()),
        page_id=page.id,
        name=unique_code("ZZT Collection"),
        scope="page",
        pinned_product_ids=pinned,
    )
    db.add(collection)
    db.flush()

    db.add(
        PageVersion(
            id=str(uuid.uuid4()),
            page_id=page.id,
            version=1,
            doc={
                "sections": [
                    {
                        "id": "s1",
                        "blocks": [
                            {
                                "id": "b1",
                                "type": "collection",
                                "props": {"collectionId": collection.id},
                            }
                        ],
                    }
                ]
            },
        )
    )
    db.flush()
    return page, collection


def _edition(db, page: Page, previous: Edition | None = None) -> Edition:
    from app.models.status import Status

    draft = (
        db.query(Status)
        .filter(Status.entity_type == "dealer_kit_edition", Status.key == "draft")
        .one()
    )
    edition = Edition(
        id=str(uuid.uuid4()),
        page_id=page.id,
        name=unique_code("ZZT Edition"),
        status_id=draft.id,
        status_key="draft",
        previous_edition_id=previous.id if previous else None,
    )
    db.add(edition)
    db.flush()
    return edition


class TestTheProductsThatVanished:
    def test_a_discontinued_pin_is_reported_even_though_it_renders_nowhere(
        self, db
    ) -> None:
        """The whole reason this service exists.

        The resolver drops it from the members, so without this the catalogue
        silently holds one fewer product and no screen says so.
        """
        alive = _product(db)
        gone = _product(db, discontinued=True)
        page, _ = _page_with_collection(db, [alive.id, gone.id])

        result = review_service.review(db, _edition(db, page))

        assert [m.product_id for m in result.members] == [alive.id]
        assert [(d.product_id, d.reason) for d in result.dropped] == [
            (gone.id, review_service.DISCONTINUED)
        ]

    def test_an_inactive_pin_is_a_different_reason(self, db) -> None:
        """Two ways to disappear, two places to send somebody. A discontinued
        product is a commercial decision to accept; an inactive one is data."""
        gone = _product(db, active=False)
        page, _ = _page_with_collection(db, [gone.id])

        result = review_service.review(db, _edition(db, page))

        assert [d.reason for d in result.dropped] == [review_service.INACTIVE]

    def test_discontinued_wins_when_a_product_is_both(self, db) -> None:
        """"Inactive" would send somebody to reactivate a product that is
        deliberately end-of-life."""
        gone = _product(db, discontinued=True, active=False)
        page, _ = _page_with_collection(db, [gone.id])

        result = review_service.review(db, _edition(db, page))

        assert [d.reason for d in result.dropped] == [review_service.DISCONTINUED]

    def test_a_pin_whose_product_no_longer_exists_is_named_not_skipped(self, db) -> None:
        vanished = str(uuid.uuid4())
        page, _ = _page_with_collection(db, [vanished])

        result = review_service.review(db, _edition(db, page))

        assert [(d.product_id, d.reason) for d in result.dropped] == [
            (vanished, review_service.MISSING)
        ]
        assert result.dropped[0].product_code is None

    def test_nothing_is_dropped_when_everything_still_resolves(self, db) -> None:
        page, _ = _page_with_collection(db, [_product(db).id, _product(db).id])

        result = review_service.review(db, _edition(db, page))

        assert result.dropped == []
        assert len(result.members) == 2


class TestNewSinceTheLastEdition:
    def test_a_product_created_after_the_previous_edition_is_badged(self, db) -> None:
        page, collection = _page_with_collection(db, [])
        previous = _edition(db, page)
        # The previous Edition has to be done, or the partial unique index
        # refuses a second open one against the same page.
        previous.status_key = "done"
        db.flush()

        old = _product(db, created_at=previous.created_at - timedelta(days=30))
        fresh = _product(db, created_at=previous.created_at + timedelta(days=1))
        collection.pinned_product_ids = [old.id, fresh.id]
        db.flush()

        result = review_service.review(db, _edition(db, page, previous=previous))

        badged = {m.product_id: m.is_new_since_previous for m in result.members}
        assert badged[fresh.id] is True
        assert badged[old.id] is False

    def test_a_first_edition_badges_nothing(self, db) -> None:
        """No previous Edition means no window. Badging everything would flag
        the whole catalogue and teach people to ignore the badge."""
        page, _ = _page_with_collection(db, [_product(db).id])

        result = review_service.review(db, _edition(db, page))

        assert all(not m.is_new_since_previous for m in result.members)
        assert result.previous_edition_name is None

    def test_it_names_what_it_compared_against(self, db) -> None:
        page, _ = _page_with_collection(db, [_product(db).id])
        previous = _edition(db, page)
        previous.status_key = "done"
        db.flush()

        result = review_service.review(db, _edition(db, page, previous=previous))

        assert result.previous_edition_name == previous.name


class TestStock:
    def test_stock_is_summed_across_warehouses(self, db) -> None:
        """A catalogue tile is not warehouse-specific, so "is there any of this"
        is answered across all of them."""
        from app.models.inventory import Warehouse

        product = _product(db)
        for quantity in (3, 4):
            warehouse = Warehouse(
                id=str(uuid.uuid4()),
                warehouse_code=unique_code("ZW"),
            )
            db.add(warehouse)
            db.flush()
            db.add(
                Stock(
                    id=str(uuid.uuid4()),
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=quantity,
                )
            )
        db.flush()
        page, _ = _page_with_collection(db, [product.id])

        result = review_service.review(db, _edition(db, page))

        assert [m.stock_on_hand for m in result.members] == [7]

    def test_a_product_with_no_stock_row_reads_as_zero(self, db) -> None:
        page, _ = _page_with_collection(db, [_product(db).id])

        result = review_service.review(db, _edition(db, page))

        assert [m.stock_on_hand for m in result.members] == [0]


class TestWhatItReadsFrom:
    def test_a_collection_not_placed_in_the_document_is_ignored(self, db) -> None:
        """A collection can exist against a page and no longer be placed in the
        current version. Reporting on one sends a Designer hunting for a tile
        that is not there."""
        page, placed = _page_with_collection(db, [_product(db).id])
        orphan_product = _product(db, discontinued=True)
        db.add(
            Collection(
                id=str(uuid.uuid4()),
                page_id=page.id,
                name=unique_code("ZZT Unplaced"),
                scope="page",
                pinned_product_ids=[orphan_product.id],
            )
        )
        db.flush()

        result = review_service.review(db, _edition(db, page))

        assert result.dropped == []

    def test_a_page_with_no_version_reviews_to_nothing(self, db) -> None:
        page = Page(
            id=str(uuid.uuid4()),
            name=unique_code("ZZT Bare"),
            slug=unique_code("zzt-bare").lower(),
        )
        db.add(page)
        db.flush()

        result = review_service.review(db, _edition(db, page))

        assert result.members == []
        assert result.dropped == []
