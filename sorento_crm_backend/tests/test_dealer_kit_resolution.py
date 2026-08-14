"""Collection and bundle resolution against real rows.

The pure parts have their own golden sets. What is under test HERE is the
wiring: that company scope runs before the rule, that a discontinued product
cannot become a tile, that a bundle's availability is worked out from its
components every time, and that a price a viewer may not see is absent from the
payload rather than merely hidden.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.services.dealer_kit import bundle_service, collection_service
from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


def _product(db, **overrides):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTR")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        invoice_price=Decimal("70.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    fields.update(overrides)
    product = Product(**fields)
    db.add(product)
    db.flush()
    return product


def _collection(db, **overrides):
    return collection_service.create_collection(
        db, scope="library", name=f"ZZT {unique_code('col')}", **overrides
    )


def _brand(db, access_levels=None):
    """A brand, company-scoped like the fixture's other rows.

    ``access_levels`` left ``None`` means "never assigned" - the ORM then omits
    the column from the INSERT and Postgres applies its server default
    (``["dealer","end_user"]``), which is the overwhelming real-world case.
    """
    from app.models.product import Brand

    code = unique_code("ZZTB")
    fields = dict(brand_code=code[:50], brand_name=f"ZZT brand {code}")
    if access_levels is not None:
        fields["access_levels"] = access_levels
    brand = Brand(**fields)
    db.add(brand)
    db.flush()
    return brand


def _rule(fact: str, operator: str, value=None):
    return {"combinator": "and", "rules": [{"fact": fact, "operator": operator, "value": value}]}


# --------------------------------------------------------------------------
# Membership against real products
# --------------------------------------------------------------------------


def test_a_rule_selects_products_through_the_shared_engine():
    with pg_session() as db:
        cheap = _product(db, list_price=Decimal("50.00"))
        dear = _product(db, list_price=Decimal("500.00"))
        collection = _collection(db, conditions=_rule("product.listPrice", "gt", 400))

        members = {p.id for p in collection_service.resolve_members(db, collection)}
        assert dear.id in members
        assert cheap.id not in members


def test_a_collection_with_no_rule_has_only_its_pins():
    # The engine treats an empty tree as unconditional, which is right for
    # "may this promotion run" and catastrophic here: it would put the entire
    # catalogue on the page.
    with pg_session() as db:
        pinned = _product(db)
        _product(db)
        collection = _collection(db, conditions=None, pinned_product_ids=[pinned.id])

        members = [p.id for p in collection_service.resolve_members(db, collection)]
        assert members == [pinned.id]


def test_a_discontinued_product_never_becomes_a_member():
    with pg_session() as db:
        dead = _product(db, is_discontinued=True)
        collection = _collection(db, pinned_product_ids=[dead.id])

        assert collection_service.resolve_members(db, collection) == []


def test_an_inactive_product_never_becomes_a_member():
    with pg_session() as db:
        off = _product(db, is_active=False)
        collection = _collection(db, pinned_product_ids=[off.id])

        assert collection_service.resolve_members(db, collection) == []


def test_an_exclusion_beats_the_rule_on_real_rows():
    with pg_session() as db:
        keep = _product(db, list_price=Decimal("500.00"))
        drop = _product(db, list_price=Decimal("600.00"))
        collection = _collection(
            db,
            conditions=_rule("product.listPrice", "gt", 400),
            excluded_product_ids=[drop.id],
        )

        # The local database is a copy of production, so a price rule matches
        # real products too. Assert on MY two rows, never on the whole set.
        members = {p.id for p in collection_service.resolve_members(db, collection)}
        assert keep.id in members
        assert drop.id not in members


def test_a_pin_naming_a_product_from_another_company_resolves_to_nothing():
    """Company scope runs BEFORE the rule, so a foreign id cannot become a tile
    even when it is pinned by id (AC-F8)."""
    with pg_session() as db:
        other = Company(
            id=str(uuid.uuid4()), name="ZZT Other Co", code=unique_code("ZZTO")[:20]
        )
        db.add(other)
        db.flush()

        with company_scope(db, frozenset({other.id})):
            foreign = _product(db)
            foreign_id = foreign.id

        with company_scope(db, frozenset({SORENTO})):
            collection = _collection(db, pinned_product_ids=[foreign_id])
            assert collection_service.resolve_members(db, collection) == []


def test_manual_order_drives_the_rendered_order():
    with pg_session() as db:
        first = _product(db)
        second = _product(db)
        collection = _collection(
            db,
            pinned_product_ids=[first.id, second.id],
            manual_order=[second.id, first.id],
        )

        members = [p.id for p in collection_service.resolve_members(db, collection)]
        assert members == [second.id, first.id]


# --------------------------------------------------------------------------
# Viewer-resolved pricing
# --------------------------------------------------------------------------


def test_invoice_price_needs_the_toggle_AND_the_viewer():
    with pg_session() as db:
        product = _product(db)
        collection = _collection(db, pinned_product_ids=[product.id])

        staff_on = ViewerContext(is_staff=True, show_invoice_price=True)
        staff_off = ViewerContext(is_staff=True, show_invoice_price=False)
        consumer_on = ViewerContext(is_staff=False, show_invoice_price=True)

        assert collection_service.resolve_tiles(db, collection, staff_on)[0]["invoice_price"]
        # Toggle off: the number is gone even for staff.
        assert collection_service.resolve_tiles(db, collection, staff_off)[0]["invoice_price"] is None
        # The gate that matters: toggle ON, viewer not entitled -> still absent.
        assert collection_service.resolve_tiles(db, collection, consumer_on)[0]["invoice_price"] is None


def test_a_denied_invoice_price_is_absent_from_the_payload_not_hidden():
    with pg_session() as db:
        product = _product(db, invoice_price=Decimal("70.00"))
        collection = _collection(db, pinned_product_ids=[product.id])

        tile = collection_service.resolve_tiles(
            db, collection, ViewerContext(is_staff=False, show_invoice_price=True)
        )[0]
        # Nothing to reveal by inspecting the response (AC-G7). Match the
        # FORMATTED price - bare digits turn up inside UUIDs, so a substring
        # check on "70" passes or fails by luck.
        assert tile["invoice_price"] is None
        assert "MYR 70.00" not in str(tile)


def test_list_price_is_shown_to_everyone_including_an_anonymous_reader():
    with pg_session() as db:
        product = _product(db, list_price=Decimal("1290.00"))
        collection = _collection(db, pinned_product_ids=[product.id])

        tile = collection_service.resolve_tiles(db, collection)[0]
        assert tile["price"] == "MYR 1,290.00"


# --------------------------------------------------------------------------
# Brand-gated visibility (AC-G3)
# --------------------------------------------------------------------------


def test_a_dealer_only_brand_product_is_absent_for_anonymous_and_end_user_readers():
    """Presence, not just price. A brand nobody authorised this viewer for must
    not put a tile on the page at all - not hidden, ABSENT (AC-G3)."""
    with pg_session() as db:
        brand = _brand(db, access_levels=["dealer"])
        product = _product(db, brand_id=brand.id)
        collection = _collection(db, pinned_product_ids=[product.id])

        anon_ids = {
            tile["product_id"] for tile in collection_service.resolve_tiles(db, collection, ANONYMOUS)
        }
        end_user_ids = {
            tile["product_id"]
            for tile in collection_service.resolve_tiles(
                db, collection, ViewerContext(access_codes=frozenset({"end_user"}))
            )
        }
        assert product.id not in anon_ids
        assert product.id not in end_user_ids


def test_a_dealer_only_brand_product_is_present_for_a_dealer_viewer():
    with pg_session() as db:
        brand = _brand(db, access_levels=["dealer"])
        product = _product(db, brand_id=brand.id)
        collection = _collection(db, pinned_product_ids=[product.id])

        dealer_ids = {
            tile["product_id"]
            for tile in collection_service.resolve_tiles(
                db, collection, ViewerContext(access_codes=frozenset({"dealer"}))
            )
        }
        assert product.id in dealer_ids


def test_a_dealer_only_brand_product_is_present_for_staff_with_no_codes():
    """Staff - the internal builder and the office copy - see everything,
    mirroring how staff see trade imagery (product_images._may_see)."""
    with pg_session() as db:
        brand = _brand(db, access_levels=["dealer"])
        product = _product(db, brand_id=brand.id)
        collection = _collection(db, pinned_product_ids=[product.id])

        staff_ids = {
            tile["product_id"]
            for tile in collection_service.resolve_tiles(db, collection, ViewerContext(is_staff=True))
        }
        assert product.id in staff_ids


def test_a_brandless_product_is_visible_to_everyone():
    """Nothing restricts a product with no brand at all."""
    with pg_session() as db:
        product = _product(db, brand_id=None)
        collection = _collection(db, pinned_product_ids=[product.id])

        anon_ids = {
            tile["product_id"] for tile in collection_service.resolve_tiles(db, collection, ANONYMOUS)
        }
        assert product.id in anon_ids


def test_the_default_brand_access_levels_stay_visible_to_everyone():
    """The overwhelming real-world case: a brand's default `access_levels` is
    `["dealer","end_user"]`, and a filter that hid it would blank the
    catalogue."""
    with pg_session() as db:
        brand = _brand(db)  # server default: ["dealer", "end_user"]
        product = _product(db, brand_id=brand.id)
        collection = _collection(db, pinned_product_ids=[product.id])

        anon_ids = {
            tile["product_id"] for tile in collection_service.resolve_tiles(db, collection, ANONYMOUS)
        }
        dealer_ids = {
            tile["product_id"]
            for tile in collection_service.resolve_tiles(
                db, collection, ViewerContext(access_codes=frozenset({"dealer"}))
            )
        }
        end_user_ids = {
            tile["product_id"]
            for tile in collection_service.resolve_tiles(
                db, collection, ViewerContext(access_codes=frozenset({"end_user"}))
            )
        }
        assert product.id in anon_ids
        assert product.id in dealer_ids
        assert product.id in end_user_ids


# --------------------------------------------------------------------------
# Library scope
# --------------------------------------------------------------------------


def test_a_page_scoped_collection_stays_out_of_the_library():
    with pg_session() as db:
        from app.services.dealer_kit import page_service

        page = page_service.create_page(
            db, name="ZZT holder", slug=unique_code("zzt-holder").lower(), user_id=None
        )
        hidden = collection_service.create_collection(db, scope="page", page_id=page.id)

        assert hidden.id not in {row.id for row in collection_service.list_library(db)}


def test_saving_as_reusable_keeps_the_same_row_so_the_page_stays_bound():
    with pg_session() as db:
        from app.services.dealer_kit import page_service

        page = page_service.create_page(
            db, name="ZZT promote", slug=unique_code("zzt-promote").lower(), user_id=None
        )
        collection = collection_service.create_collection(db, scope="page", page_id=page.id)
        promoted = collection_service.save_as_library(db, collection.id, "ZZT Named set")

        assert promoted.id == collection.id
        assert promoted.scope == "library"
        assert promoted.id in {row.id for row in collection_service.list_library(db)}


def test_a_reusable_collection_needs_a_name():
    with pg_session() as db:
        from app.services.error_handler import AppException

        with pytest.raises(AppException):
            collection_service.create_collection(db, scope="library", name="  ")


# --------------------------------------------------------------------------
# Bundles
# --------------------------------------------------------------------------


def test_a_bundle_allocates_its_price_across_components_summing_exactly():
    with pg_session() as db:
        a = _product(db, list_price=Decimal("1000.00"))
        b = _product(db, list_price=Decimal("500.00"))
        bundle = bundle_service.create_bundle(
            db,
            name="ZZT bundle",
            price=Decimal("1000.00"),
            components=[{"product_id": a.id}, {"product_id": b.id}],
        )

        resolved = bundle_service.resolve_bundle(db, bundle.id)
        allocated = [
            Decimal(line["allocated"].replace("MYR", "").replace(",", "").strip())
            for line in resolved["components"]
        ]
        assert sum(allocated) == Decimal("1000.00")


def test_a_bundle_is_unavailable_when_any_component_is_discontinued():
    with pg_session() as db:
        good = _product(db)
        bad = _product(db, is_discontinued=True)
        bundle = bundle_service.create_bundle(
            db,
            name="ZZT broken bundle",
            price=Decimal("500.00"),
            components=[{"product_id": good.id}, {"product_id": bad.id}],
        )

        resolved = bundle_service.resolve_bundle(db, bundle.id)
        assert resolved["available"] is False
        assert bad.product_name in resolved["unavailable_reason"]


def test_bundle_availability_follows_the_component_with_no_write():
    """Derived at read time, never stored - discontinuing a product must change
    the answer without anyone touching the bundle."""
    with pg_session() as db:
        product = _product(db)
        bundle = bundle_service.create_bundle(
            db,
            name="ZZT live bundle",
            price=Decimal("100.00"),
            components=[{"product_id": product.id}],
        )
        assert bundle_service.resolve_bundle(db, bundle.id)["available"] is True

        product.is_discontinued = True
        db.flush()

        assert bundle_service.resolve_bundle(db, bundle.id)["available"] is False


def test_a_bundle_renders_every_component_even_the_unavailable_one():
    with pg_session() as db:
        good = _product(db)
        bad = _product(db, is_discontinued=True)
        bundle = bundle_service.create_bundle(
            db,
            name="ZZT mixed",
            price=Decimal("300.00"),
            components=[{"product_id": good.id}, {"product_id": bad.id}],
        )

        resolved = bundle_service.resolve_bundle(db, bundle.id)
        assert len(resolved["components"]) == 2
        assert [line["available"] for line in resolved["components"]] == [True, False]


def test_a_bundle_needs_at_least_one_component():
    with pg_session() as db:
        from app.services.error_handler import AppException

        with pytest.raises(AppException):
            bundle_service.create_bundle(
                db, name="ZZT empty", price=Decimal("10.00"), components=[]
            )


# --------------------------------------------------------------------------
# Cost of resolving several collections at once
# --------------------------------------------------------------------------


def test_resolving_many_collections_scans_the_catalogue_once():
    """The candidate load is the expensive part and is identical for every
    collection in the same company scope, so listing N collections must not
    mean N catalogue scans."""
    from sqlalchemy import event

    with pg_session() as db:
        product = _product(db)
        collections = [_collection(db, pinned_product_ids=[product.id]) for _ in range(4)]

        scans = []

        def _count(conn, cursor, statement, params, context, executemany):
            if "FROM products" in statement:
                scans.append(statement)

        event.listen(db.bind, "before_cursor_execute", _count)
        try:
            candidates = collection_service.sellable_products(db)
            for collection in collections:
                collection_service.resolve_members(db, collection, candidates)
        finally:
            event.remove(db.bind, "before_cursor_execute", _count)

        # One load, shared across all four - not one per collection.
        assert len(scans) == 1, f"expected 1 catalogue scan, got {len(scans)}"
