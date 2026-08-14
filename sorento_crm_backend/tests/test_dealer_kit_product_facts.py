"""The ``product`` fact source, evaluated through the SHARED rule engine (AC-F3).

What is under test is not "does a filter work" but "does a collection rule go
through the same evaluator as a promo-expiry rule". A bespoke product filter
would have its own operator semantics and its own null handling, and the two
would disagree the first time either was touched.

Also pinned here: the whitelist. `cost_price` and `invoice_price` are NOT facts.
Anyone who can build a collection could otherwise read margin off the rule
builder's own field list.
"""
from __future__ import annotations

import os

import pytest

from app.rule_engine.evaluator import evaluate
from app.rule_engine.registry import fact_map
from app.services.dealer_kit.product_facts import (
    product_facts,
    register_product_facts,
)
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _condition(fact: str, operator: str, value=None):
    """A one-condition tree in the engine's own node shape: a group carries
    `rules`, and a nested group is marked `kind: "group"`."""
    return {
        "combinator": "and",
        "rules": [{"fact": fact, "operator": operator, "value": value}],
    }


def _product(db, **overrides):
    """A real product row. Category and UOM are NOT NULL FKs, so they are seeded
    for real - Postgres enforces what a mock would have let through."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTP")
    category = ProductCategory(
        category_code=code, category_name=f"ZZT category {code}"
    )
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=100,
        is_active=True,
        is_discontinued=False,
    )
    fields.update(overrides)
    product = Product(**fields)
    db.add(product)
    db.flush()
    return product


def test_the_source_is_registered_on_the_shared_registry():
    register_product_facts()
    keys = fact_map(["product"])
    assert "product.listPrice" in keys
    assert "product.isDiscontinued" in keys
    # Registered alongside the core source rather than replacing it.
    assert "promotion.isActive" in fact_map(["product", "promotion"])


def test_internal_prices_are_not_facts():
    register_product_facts()
    keys = fact_map(["product"])
    assert not any("cost" in key.lower() for key in keys)
    assert not any("invoice" in key.lower() for key in keys)


def test_a_rule_matches_a_real_product_through_the_shared_evaluator():
    with pg_session() as db:
        cheap = _product(db, list_price=50)
        dear = _product(db, list_price=500)

        rule = _condition("product.listPrice", "gt", 100)
        assert evaluate(rule, product_facts(dear, db)) is True
        assert evaluate(rule, product_facts(cheap, db)) is False


def test_a_discontinued_product_is_distinguishable_by_rule():
    with pg_session() as db:
        live = _product(db)
        dead = _product(db, is_discontinued=True)

        rule = _condition("product.isDiscontinued", "is_false")
        assert evaluate(rule, product_facts(live, db)) is True
        assert evaluate(rule, product_facts(dead, db)) is False


def test_category_resolves_to_a_name_not_an_id():
    with pg_session() as db:
        product = _product(db)
        facts = product_facts(product, db)
        # A UUID in a condition would be unreadable to whoever maintains the rule.
        assert facts["product.category"] == product.category.category_name
        assert facts["product.category"].startswith("ZZT category")


def test_an_empty_rule_matches_everything():
    # A collection with no conditions is "every product", which is what a
    # Designer means by leaving the rule builder untouched.
    with pg_session() as db:
        product = _product(db)
        assert evaluate(None, product_facts(product, db)) is True


def test_a_rule_naming_an_unknown_fact_does_not_explode():
    # Fields change; a rule authored against an older shape must degrade rather
    # than take the page down (the registry's fail-closed contract).
    with pg_session() as db:
        product = _product(db)
        rule = _condition("product.somethingRemoved", "eq", "x")
        assert evaluate(rule, product_facts(product, db)) is False
