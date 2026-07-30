"""The quote view of a Selection.

The summary screen lets somebody take lines OUT before they hand the figure to
a customer - "not the mirror this time". The subtotal therefore has to change,
and it is computed HERE rather than in the browser: a frontend that adds up
prices is a second price list nobody knows they are maintaining, and it is the
one the customer ends up seeing.

Excluding is not deleting. The line stays in the design, because the dealer is
answering "what do I quote today", not "what did we choose".
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: F401,E402

from app.services.dealer_kit import selection_service
from app.services.dealer_kit.viewer import ViewerContext
from tests._pg_fixture import blank_session

_USER_ID = "2d9f4c73-6b81-5e42-9c07-1a5e8f3b7d26"
_SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        from app.models.user import User

        session.add(User(id=_USER_ID, email="zzt-quote@test.com", name="Quote", status="ACTIVE"))
        session.flush()
        yield session


def _product(session: Session, price: str, **overrides):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = f"ZZTQ{uuid.uuid4().hex[:6]}"
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    session.add_all([category, uom])
    session.flush()

    fields = dict(
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal(price),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
        company_id=_SORENTO,
    )
    fields.update(overrides)
    product = Product(**fields)
    session.add(product)
    session.flush()
    return product


def _selection_with(session: Session, *lines):
    selection = selection_service.create_selection(session, user_id=_USER_ID, name="ZZT quote")
    session.flush()
    for product, quantity in lines:
        selection_service.add_line(session, selection, product.id, Decimal(str(quantity)))
    session.flush()
    return selection


def test_the_subtotal_is_the_included_lines_only(db):
    keep = _product(db, "100.00")
    drop = _product(db, "250.00")
    selection = _selection_with(db, (keep, 2), (drop, 1))

    quote = selection_service.quote_selection(
        db, selection, ViewerContext(is_staff=True), excluded_product_ids=[drop.id]
    )

    assert quote["subtotal"] == "200.00"
    assert quote["excluded_count"] == 1
    # Excluding is not deleting: the line is still there, marked.
    assert len(quote["lines"]) == 2
    excluded = next(line for line in quote["lines"] if line["product_id"] == drop.id)
    assert excluded["included"] is False


def test_excluding_nothing_matches_the_selection_total(db):
    first = _product(db, "100.00")
    second = _product(db, "250.50")
    selection = _selection_with(db, (first, 1), (second, 2))

    quote = selection_service.quote_selection(db, selection, ViewerContext(is_staff=True))
    resolved = selection_service.resolve_selection(db, selection, ViewerContext(is_staff=True))

    assert quote["subtotal"] == resolved["total"] == "601.00"
    assert quote["excluded_count"] == 0


def test_a_discontinued_line_is_excluded_and_says_why(db):
    """It cannot be quoted, so it cannot be in the figure - and it cannot be
    quietly dropped either, or the dealer never learns why the number moved."""
    live = _product(db, "100.00")
    dead = _product(db, "500.00", is_discontinued=True)
    selection = _selection_with(db, (live, 1), (dead, 1))

    quote = selection_service.quote_selection(db, selection, ViewerContext(is_staff=True))

    assert quote["subtotal"] == "100.00"
    line = next(row for row in quote["lines"] if row["product_id"] == dead.id)
    assert line["included"] is False
    assert line["is_available"] is False
    assert line["unavailable_reason"]


def test_excluding_everything_is_a_zero_quote_not_an_error(db):
    product = _product(db, "100.00")
    selection = _selection_with(db, (product, 1))

    quote = selection_service.quote_selection(
        db, selection, ViewerContext(is_staff=True), excluded_product_ids=[product.id]
    )

    assert quote["subtotal"] == "0.00"
    assert quote["excluded_count"] == 1


def test_an_unknown_exclusion_changes_nothing(db):
    """A stale id from a screen somebody left open must not silently drop a
    different line, and must not 500."""
    product = _product(db, "100.00")
    selection = _selection_with(db, (product, 1))

    quote = selection_service.quote_selection(
        db, selection, ViewerContext(is_staff=True), excluded_product_ids=[str(uuid.uuid4())]
    )

    assert quote["subtotal"] == "100.00"
    assert quote["excluded_count"] == 0


def test_a_consumer_sees_no_invoice_price_anywhere_in_the_quote(db):
    product = _product(db, "100.00", invoice_price=Decimal("60.00"))
    selection = _selection_with(db, (product, 1))

    quote = selection_service.quote_selection(db, selection, ViewerContext(is_staff=False))

    assert quote["lines"][0]["invoice_price"] is None
    # And the number is ABSENT from the payload, not merely flagged.
    assert "60.00" not in str(quote)
