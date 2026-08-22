"""What resolution is allowed to READ, not just what it returns.

A correctness suite cannot see this: a collection of four hand-picked products
resolves to exactly the right four whether the resolver looked at four rows or
at every product in the catalogue. The difference only shows up in production,
on the public page, under load.

The live catalogue has 17,402 sellable products. Loading all of them - with
category and brand joined - to answer "show these four" is the kind of cost that
looks free on a developer's laptop with a seeded database and is not free on the
one surface anonymous strangers can hit.

So the rule is expressed as a test: a collection with NO rule must resolve
without touching the candidate scan at all.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.services.dealer_kit import collection_service
from app.services.dealer_kit.viewer import ANONYMOUS
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"
SCOPE = frozenset({SORENTO})


def _product(db, **overrides):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTQ")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("50.00"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    fields.update(overrides)
    product = Product(**fields)
    db.add(product)
    db.flush()
    return product


def _pins_only_collection(db, product_ids):
    return collection_service.create_collection(
        db,
        scope="library",
        name=f"ZZT {unique_code('pins')}",
        pinned_product_ids=list(product_ids),
    )


def test_a_pinned_collection_resolves_without_scanning_the_catalogue(monkeypatch):
    """The guard. If resolution reaches for the full candidate set to answer a
    hand-picked collection, this fails loudly instead of quietly costing a
    catalogue scan on every public page view."""
    with pg_session() as db, company_scope(db, SCOPE):
        products = [_product(db) for _ in range(3)]
        collection = _pins_only_collection(db, [p.id for p in products])
        db.flush()

        def _forbidden(*args, **kwargs):
            raise AssertionError(
                "resolve_members loaded the whole catalogue for a collection "
                "that only has pins"
            )

        monkeypatch.setattr(collection_service, "_sellable_products", _forbidden)

        members = collection_service.resolve_members(db, collection)
        assert [m.id for m in members] == [p.id for p in products]


def test_a_pinned_collection_still_drops_a_discontinued_pin(monkeypatch):
    """The cheap path must keep the guarantee the expensive one gave.

    A pin pointing at something unsellable was previously filtered out because
    it simply was not in the candidate set. Loading pins directly could
    reintroduce it, which would put an unbuyable product on a public page.
    """
    with pg_session() as db, company_scope(db, SCOPE):
        good = _product(db)
        gone = _product(db, is_discontinued=True)
        inactive = _product(db, is_active=False)
        collection = _pins_only_collection(db, [good.id, gone.id, inactive.id])
        db.flush()

        members = collection_service.resolve_members(db, collection)
        assert [m.id for m in members] == [good.id]


def test_an_exclusion_still_beats_a_pin_on_the_cheap_path(monkeypatch):
    with pg_session() as db, company_scope(db, SCOPE):
        kept = _product(db)
        removed = _product(db)
        collection = collection_service.create_collection(
            db,
            scope="library",
            name=f"ZZT {unique_code('excl')}",
            pinned_product_ids=[kept.id, removed.id],
            excluded_product_ids=[removed.id],
        )
        db.flush()

        members = collection_service.resolve_members(db, collection)
        assert [m.id for m in members] == [kept.id]


def test_a_rule_backed_collection_still_gets_the_candidate_set():
    """The optimisation must not silently break rules: a rule has to be
    evaluated against the catalogue, and there is no cheaper way."""
    with pg_session() as db, company_scope(db, SCOPE):
        product = _product(db)
        collection = collection_service.create_collection(
            db,
            scope="library",
            name=f"ZZT {unique_code('rule')}",
            conditions={
                "combinator": "and",
                "rules": [
                    {"fact": "product.productCode", "operator": "eq", "value": product.product_code}
                ],
            },
        )
        db.flush()

        members = collection_service.resolve_members(db, collection)
        assert [m.id for m in members] == [product.id]


def test_an_empty_collection_resolves_to_nothing_and_reads_nothing(monkeypatch):
    with pg_session() as db, company_scope(db, SCOPE):
        collection = _pins_only_collection(db, [])
        db.flush()

        def _forbidden(*args, **kwargs):
            raise AssertionError("an empty collection must not scan the catalogue")

        monkeypatch.setattr(collection_service, "_sellable_products", _forbidden)

        assert collection_service.resolve_members(db, collection) == []
        assert collection_service.resolve_tiles(db, collection, ANONYMOUS) == []
