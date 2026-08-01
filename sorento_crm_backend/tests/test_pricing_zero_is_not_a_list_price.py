"""A list price of zero is missing master data, not a free product.

Found by opening the published catalogue in a browser. A tile printed

    MYR 0.00

against a real product, on the page a dealer forwards to a customer.

This is the LIST price, so the rule that already guards offers does not reach
it. `_offer_worth_showing` refuses a promotional price of zero because "MYR 0.00
against a water closet is a commercial incident", and then the same figure walks
in through the other door.

Nor is it rare. On the live database 10,370 of 22,805 products carry
`list_price = 0.00`: 46% of Sorento's catalogue and 45% of Mocha's. A collection
built by rule can therefore be half zeroes, and the flyer seed in S7.4 pins
products by printed code without consulting price at all.

Zero is not a price anybody charges. `products.list_price` is NOT NULL with a
zero default, so a product whose price was never imported is indistinguishable
from one deliberately priced at nothing, and the second of those is not a real
category: a genuine giveaway is a promotion line, priced against a promotion,
not a permanent list price of nought.

So zero is read as ABSENT, which is the state the system already knows how to
render: the tile shows no price, exactly as it does for a product with no price
at all. Showing nothing tells the reader we do not have a price. Showing MYR
0.00 tells them the price is nothing, which is a claim, and one somebody could
reasonably act on.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services.dealer_kit.pricing import resolve_prices
from app.services.dealer_kit.viewer import ViewerContext
from tests._pg_fixture import blank_session, unique_code

DEALER = ViewerContext(access_codes=frozenset({"dealer"}))


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _product(db, list_price):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("c")[:20],
        category_name=unique_code("cat"),
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_name=unique_code("uom"), uom_code=unique_code("u")[:10]
    )
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("sku"),
        product_name="Test product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=list_price,
    )
    db.add(product)
    db.flush()
    return product


class TestZeroIsNotAListPrice:
    def test_a_zero_list_price_is_reported_as_absent(self, db) -> None:
        product = _product(db, Decimal("0.00"))

        view = resolve_prices(db, [product], DEALER)[product.id]

        assert view.list_price is None

    def test_a_real_price_is_untouched(self, db) -> None:
        product = _product(db, Decimal("1260.00"))

        view = resolve_prices(db, [product], DEALER)[product.id]

        assert view.list_price == Decimal("1260.00")

    def test_a_negative_list_price_is_absent_too(self, db) -> None:
        """Nobody is owed money for taking a bath away.

        Same door as zero, and one an import can produce from a spreadsheet
        column read with the wrong sign.
        """
        product = _product(db, Decimal("-1.00"))

        view = resolve_prices(db, [product], DEALER)[product.id]

        assert view.list_price is None

    def test_the_smallest_real_price_survives(self, db) -> None:
        """One sen is a price. The rule is "not a positive number", not "small"."""
        product = _product(db, Decimal("0.01"))

        view = resolve_prices(db, [product], DEALER)[product.id]

        assert view.list_price == Decimal("0.01")

    def test_an_offer_still_shows_when_the_list_price_is_missing(self, db) -> None:
        """The two rules must not cancel each other out.

        `_offer_worth_showing` demands an offer beat the list price, and a
        product with no list price has nothing to beat, so the offer stands on
        its own. That path already existed for a NULL list price; a zero one now
        arrives at the same place, and this pins that it does rather than
        falling into "no list price, therefore no offer either" and emptying the
        tile completely.
        """
        from datetime import date, timedelta

        from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

        product = _product(db, Decimal("0.00"))
        promotion = Promotion(
            id=str(uuid.uuid4()),
            description=unique_code("promo"),
            is_active=True,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=30),
            access_levels=["dealer"],
        )
        db.add(promotion)
        db.flush()
        group = PromotionGroup(promotion_id=promotion.id, group_name=unique_code("grp"))
        db.add(group)
        db.flush()
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promotion.id,
                promotion_group_id=group.id,
                product_id=product.id,
                promo_selling_price=Decimal("599.00"),
            )
        )
        db.flush()

        view = resolve_prices(db, [product], DEALER, promotion.id)[product.id]

        assert view.list_price is None
        assert view.offer_price == Decimal("599.00")

    def test_the_invoice_price_is_held_to_the_same_rule(self, db) -> None:
        """Staff read this one, and a zero cost is the same missing import.

        Worth stating rather than leaving to fall out: the invoice price is what
        an internal reader checks margin against, and "MYR 0.00" there reads as
        "this costs us nothing" rather than "we never loaded a cost".

        BOTH gates have to be opened for this to test anything. `is_staff` alone
        leaves `show_invoice_price` at its default of False, so the figure comes
        back absent whatever the rule does, and the test passes green against an
        unchanged implementation. It did exactly that when first written.
        """
        product = _product(db, Decimal("1260.00"))
        product.invoice_price = Decimal("0.00")
        db.flush()

        staff = ViewerContext(
            access_codes=frozenset({"dealer"}), is_staff=True, show_invoice_price=True
        )
        assert staff.invoice_price_visible, "the gates must be open or this proves nothing"

        view = resolve_prices(db, [product], staff)[product.id]

        assert view.invoice_price is None

        # The control: with the rule doing nothing this viewer DOES receive a
        # figure, so the assertion above is about zero and not about the gates.
        priced = _product(db, Decimal("1260.00"))
        priced.invoice_price = Decimal("900.00")
        db.flush()
        assert resolve_prices(db, [priced], staff)[priced.id].invoice_price == Decimal(
            "900.00"
        )
