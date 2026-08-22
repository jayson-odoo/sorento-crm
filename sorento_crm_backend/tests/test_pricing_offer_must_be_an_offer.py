"""An offer that is not cheaper is not an offer.

Found by driving a browser, not by reading code. Once tiles started drawing the
promotional price, the treatment is "list price struck through, offer prominent"
- so a promotion line priced ABOVE the product's list price renders as a
crossed-out 285 next to a bold 1,099. The catalogue advertises a price nobody is
charging, and it advertises it as a discount.

That is not a rare data error. On the live database 422 of 1,178 promotion lines
are at or above their product's list price, and 20 are exactly 0.00, which would
print as "MYR 0.00" against a real product.

Those rows are not wrong as records. Promotions carry bundle and free-gift
bookkeeping, and a line priced above list is meaningful inside a group where the
customer is buying several things. What is wrong is treating any of them as
"the price of this product on this tile".

So the rule the CATALOGUE applies is narrow and stated here: an offer shown to a
reader must be strictly cheaper than the list price and must be a real amount.
Anything else falls back to the list price with no offer styling, which is the
same thing that happens when no promotion applies at all.
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


def _promote(db, product, promo_price):
    from datetime import date, timedelta

    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

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
            promo_selling_price=promo_price,
        )
    )
    db.flush()
    return promotion.id


class TestAnOfferHasToBeCheaper:
    def test_a_genuine_discount_is_an_offer(self, db) -> None:
        product = _product(db, Decimal("1260.00"))
        promotion_id = _promote(db, product, Decimal("599.00"))

        view = resolve_prices(db, [product], DEALER, promotion_id)[product.id]

        assert view.offer_price == Decimal("599.00")

    def test_a_price_above_list_is_not_an_offer(self, db) -> None:
        # 422 of 1,178 live rows look like this. Rendered, it is a struck-through
        # 285 beside a bold 1,099.
        product = _product(db, Decimal("285.00"))
        promotion_id = _promote(db, product, Decimal("1099.00"))

        view = resolve_prices(db, [product], DEALER, promotion_id)[product.id]

        assert view.offer_price is None
        assert view.list_price == Decimal("285.00")

    def test_a_price_equal_to_list_is_not_an_offer(self, db) -> None:
        # Nothing is being offered. Striking a number through and reprinting it
        # unchanged is worse than showing it once.
        product = _product(db, Decimal("285.00"))
        promotion_id = _promote(db, product, Decimal("285.00"))

        view = resolve_prices(db, [product], DEALER, promotion_id)[product.id]

        assert view.offer_price is None

    def test_zero_is_not_a_catalogue_price(self, db) -> None:
        # 20 live rows are exactly 0.00. They are free-gift bookkeeping inside a
        # group, not the price of the product on its own tile, and "MYR 0.00"
        # against a water closet is a commercial incident.
        product = _product(db, Decimal("1260.00"))
        promotion_id = _promote(db, product, Decimal("0.00"))

        view = resolve_prices(db, [product], DEALER, promotion_id)[product.id]

        assert view.offer_price is None

    def test_a_negative_price_is_not_an_offer(self, db) -> None:
        product = _product(db, Decimal("1260.00"))
        promotion_id = _promote(db, product, Decimal("-50.00"))

        view = resolve_prices(db, [product], DEALER, promotion_id)[product.id]

        assert view.offer_price is None

    def test_a_product_with_no_list_price_has_nothing_to_beat(self, db) -> None:
        """With no list price there is no discount to claim, so the promotional
        figure stands on its own as the price.

        Stated as a decision rather than left to fall out: the alternative is
        showing nothing at all, which would hide a product that is genuinely on
        offer just because its master data is incomplete.
        """
        product = _product(db, Decimal("500.00"))
        promotion_id = _promote(db, product, Decimal("99.00"))

        # products.list_price is NOT NULL, so a row like this cannot be inserted.
        # The case still has to be covered because callers hand this function
        # part-built rows: bundles pass component views, and the seed will pass
        # products it has only partly resolved. Blanked in memory, with autoflush
        # held off so the session does not try to persist the impossible row.
        product.list_price = None
        with db.no_autoflush:
            view = resolve_prices(db, [product], DEALER, promotion_id)[product.id]

        assert view.offer_price == Decimal("99.00")
        assert view.list_price is None
