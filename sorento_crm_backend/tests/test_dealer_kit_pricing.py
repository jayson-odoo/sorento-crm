"""Golden set for the one function that says what a viewer pays (ADR 0008).

Written BEFORE the implementation.

The Kit already turns a price into something a reader sees in four places and
none of them knows promotions exist. ADR 0008 makes that one function, so the
commercial rule - "a dealer sees the promo price while the promotion is live" -
has a single home instead of four that drift.

Two properties carry most of the weight here:

* **A price a viewer may not see is ABSENT, not hidden.** A promotion restricted
  to dealers must not reach a consumer's browser at all, so these tests assert
  ``offer_price is None`` AND ``promotion_id is None`` - the excluded reader must
  not even learn that an offer exists.
* **One query for the whole page.** A forty-product catalogue that resolves per
  tile is forty round trips, which is the difference between a page that opens
  and a page a dealer gives up on. ``TestOneQueryForTheWholePage`` measures it
  rather than trusting the code to stay that way.

Postgres only, on a blank scratch schema, every row prefixed ZZT: the dev
database is a copy of production.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.dealer_kit.pricing import PriceView, business_today, resolve_prices
from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext
from tests._pg_fixture import blank_session, unique_code

STAFF = ViewerContext(is_staff=True, access_codes=frozenset({"end_user"}))
STAFF_SHOWING_INVOICE = ViewerContext(
    is_staff=True, access_codes=frozenset({"end_user"}), show_invoice_price=True
)
DEALER = ViewerContext(access_codes=frozenset({"dealer"}))
CONSUMER = ViewerContext(access_codes=frozenset({"end_user"}))

BOTH_AUDIENCES = ["dealer", "end_user"]


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _product(
    db,
    *,
    list_price: Decimal | None = Decimal("100.00"),
    invoice_price: Decimal | None = Decimal("60.00"),
    currency: str = "MYR",
) -> Product:
    """A saleable product. Postgres enforces the category/UOM FKs."""
    code = unique_code("ZZTP")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code, uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=list_price,
        invoice_price=invoice_price,
        currency=currency,
    )
    db.add(product)
    db.flush()
    return product


def _promotion(
    db,
    prices: dict[Product, Decimal | None],
    *,
    access_levels: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    is_active: bool = True,
    company_id: str | None = None,
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
        is_active=is_active,
        access_levels=BOTH_AUDIENCES if access_levels is None else access_levels,
        company_id=company_id,
    )
    db.add(promotion)
    db.flush()
    _group(db, promotion, prices, company_id=company_id)
    return promotion.id


def _group(
    db,
    promotion: Promotion,
    prices: dict[Product, Decimal | None],
    *,
    company_id: str | None = None,
) -> PromotionGroup:
    group = PromotionGroup(
        promotion_id=promotion.id,
        group_name=unique_code("ZZT grp"),
        company_id=company_id,
    )
    db.add(group)
    db.flush()
    for product, price in prices.items():
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promotion.id,
                promotion_group_id=group.id,
                product_id=product.id,
                promo_selling_price=price,
                company_id=company_id,
            )
        )
    db.flush()
    return group


def _other_company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTOC")[:20],
        is_active=True,
    )
    db.add(company)
    db.flush()
    return company.id


@contextmanager
def _promotion_selects(db):
    """Every SELECT that reads the promotion tables, so they can be counted.

    The ADR's performance rule is a property of the implementation, not of the
    answer: a per-product loop returns exactly the same dict as one query. Only
    a measurement can tell them apart, so the count is asserted rather than
    assumed.
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


class TestWithNoPromotion:
    def test_the_list_price_is_the_price(self, db) -> None:
        product = _product(db, list_price=Decimal("249.90"))

        view = resolve_prices(db, [product], CONSUMER)[product.id]

        assert view.list_price == Decimal("249.90")
        assert view.offer_price is None
        assert view.promotion_id is None

    def test_the_currency_comes_from_the_product(self, db) -> None:
        product = _product(db, currency="SGD")

        assert resolve_prices(db, [product], CONSUMER)[product.id].currency == "SGD"

    def test_every_product_asked_about_is_answered(self, db) -> None:
        # Callers index the result by product id while rendering a grid. A
        # missing key is a KeyError mid-page, so absence is never how this
        # function says "no offer" - a PriceView with no offer_price is.
        products = [_product(db) for _ in range(3)]

        views = resolve_prices(db, products, CONSUMER)

        assert set(views) == {product.id for product in products}
        assert all(isinstance(view, PriceView) for view in views.values())

    def test_an_empty_page_resolves_to_nothing(self, db) -> None:
        assert resolve_prices(db, [], CONSUMER) == {}

    def test_an_empty_page_asks_the_database_nothing(self, db) -> None:
        with _promotion_selects(db) as statements:
            resolve_prices(db, [], CONSUMER, promotion_id=str(uuid.uuid4()))

        assert statements == []


class TestALivePromotion:
    def test_a_dealer_gets_the_promotion_price(self, db) -> None:
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(db, {product: Decimal("79.00")})

        view = resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[product.id]

        assert view.offer_price == Decimal("79.00")

    def test_the_list_price_is_still_reported(self, db) -> None:
        # The tile strikes the list price through beside the offer. Replacing it
        # would leave the page unable to show what the reader is saving.
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(db, {product: Decimal("79.00")})

        view = resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[product.id]

        assert view.list_price == Decimal("100.00")

    def test_the_offer_names_the_promotion_that_produced_it(self, db) -> None:
        # For the support question "why is this customer being quoted 79".
        product = _product(db)
        promotion_id = _promotion(db, {product: Decimal("79.00")})

        view = resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[product.id]

        assert view.promotion_id == promotion_id

    def test_a_product_the_promotion_does_not_cover_keeps_its_list_price(self, db) -> None:
        # A page carries at most one promotion but not every tile on it is in
        # the offer. The uncovered tile is the list price with no offer styling,
        # never a hidden product.
        covered = _product(db, list_price=Decimal("100.00"))
        uncovered = _product(db, list_price=Decimal("55.00"))
        promotion_id = _promotion(db, {covered: Decimal("79.00")})

        views = resolve_prices(db, [covered, uncovered], DEALER, promotion_id=promotion_id)

        assert views[uncovered.id].offer_price is None
        assert views[uncovered.id].promotion_id is None
        assert views[uncovered.id].list_price == Decimal("55.00")


class TestWhenThePromotionIsNotRunning:
    """An expired promotion is simply a promotion with no applicable rows.

    Never a hidden product and never a stale figure: the reader sees the list
    price, styled as an ordinary price.
    """

    def test_a_promotion_that_ended_yesterday_is_no_offer(self, db) -> None:
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(
            db,
            {product: Decimal("79.00")},
            start=business_today() - timedelta(days=30),
            end=business_today() - timedelta(days=1),
        )

        view = resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[product.id]

        assert view.offer_price is None
        assert view.list_price == Decimal("100.00")

    def test_a_promotion_that_starts_tomorrow_is_no_offer(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(
            db,
            {product: Decimal("79.00")},
            start=business_today() + timedelta(days=1),
            end=business_today() + timedelta(days=30),
        )

        assert (
            resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
                product.id
            ].offer_price
            is None
        )

    def test_the_first_day_is_inside_the_promotion(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(
            db,
            {product: Decimal("79.00")},
            start=business_today(),
            end=business_today() + timedelta(days=7),
        )

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_the_last_day_is_inside_the_promotion(self, db) -> None:
        # The window is inclusive at both ends. A promotion advertised as
        # running "until the 31st" that stops honouring its price on the 31st is
        # an argument at a counter.
        product = _product(db)
        promotion_id = _promotion(
            db,
            {product: Decimal("79.00")},
            start=business_today() - timedelta(days=7),
            end=business_today(),
        )

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_no_start_date_means_it_has_always_been_running(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, start=None, end=business_today() + timedelta(days=7)
        )

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_no_end_date_means_it_is_still_running(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, start=business_today() - timedelta(days=7), end=None
        )

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_no_dates_at_all_means_it_is_running(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(db, {product: Decimal("79.00")}, start=None, end=None)

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_a_switched_off_promotion_is_no_offer(self, db) -> None:
        # `is_active` is how somebody pulls a live offer in a hurry, so it wins
        # over a window that still says the promotion is running.
        product = _product(db)
        promotion_id = _promotion(
            db,
            {product: Decimal("79.00")},
            start=business_today() - timedelta(days=1),
            end=business_today() + timedelta(days=1),
            is_active=False,
        )

        assert (
            resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
                product.id
            ].offer_price
            is None
        )

    def test_a_promotion_that_does_not_exist_is_no_offer(self, db) -> None:
        # A page can outlive the promotion it was bound to. It renders as list
        # prices rather than failing, so the catalogue keeps working.
        product = _product(db, list_price=Decimal("100.00"))

        view = resolve_prices(db, [product], DEALER, promotion_id=str(uuid.uuid4()))[
            product.id
        ]

        assert view.offer_price is None
        assert view.list_price == Decimal("100.00")

    def test_the_business_day_is_malaysias(self, db) -> None:
        # The company sells in Malaysia, so a promotion ends at the end of the
        # Malaysian day. Deriving it from the server's clock would end an offer
        # eight hours early on a UTC host.
        expected = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kuala_Lumpur")).date()

        assert business_today() == expected


class TestWhoTheOfferIsFor:
    """The brochure decides WHICH promotion, the viewer decides WHETHER."""

    def test_a_consumer_never_sees_a_dealer_only_price(self, db) -> None:
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, access_levels=["dealer"]
        )

        view = resolve_prices(db, [product], CONSUMER, promotion_id=promotion_id)[product.id]

        assert view.offer_price is None
        assert view.list_price == Decimal("100.00")

    def test_an_excluded_reader_is_not_even_told_a_promotion_exists(self, db) -> None:
        # Absent, not hidden. Naming the promotion to a consumer hands them the
        # id of an offer they may not have, which is a support call at best.
        product = _product(db)
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, access_levels=["dealer"]
        )

        assert (
            resolve_prices(db, [product], CONSUMER, promotion_id=promotion_id)[
                product.id
            ].promotion_id
            is None
        )

    def test_a_dealer_sees_a_dealer_only_price(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, access_levels=["dealer"]
        )

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_a_reader_with_no_access_code_counts_as_a_consumer(self, db) -> None:
        # The public catalogue is the consumer-facing surface, exactly as it is
        # for imagery. An anonymous reader gets the consumer offer and never the
        # trade one.
        product = _product(db)
        consumer_offer = _promotion(
            db, {product: Decimal("89.00")}, access_levels=["end_user"]
        )
        trade_offer = _promotion(db, {product: Decimal("59.00")}, access_levels=["dealer"])

        assert resolve_prices(db, [product], ANONYMOUS, promotion_id=consumer_offer)[
            product.id
        ].offer_price == Decimal("89.00")
        assert (
            resolve_prices(db, [product], ANONYMOUS, promotion_id=trade_offer)[
                product.id
            ].offer_price
            is None
        )

    def test_a_promotion_for_nobody_reaches_nobody(self, db) -> None:
        # `access_levels` is NOT NULL and ships defaulted to both audiences, so
        # an empty list is somebody deliberately emptying it. Fail closed: an
        # untagged promotion is not the same kind of legacy row as an untagged
        # photo, and guessing wrong here prices a sale.
        product = _product(db)
        promotion_id = _promotion(db, {product: Decimal("79.00")}, access_levels=[])

        for viewer in (CONSUMER, DEALER, STAFF):
            assert (
                resolve_prices(db, [product], viewer, promotion_id=promotion_id)[
                    product.id
                ].offer_price
                is None
            )

    def test_staff_previewing_a_consumer_page_see_what_the_consumer_sees(self, db) -> None:
        # `is_staff` is about the INVOICE price and nothing else. Staff checking
        # the page they are about to send a customer must see the customer's
        # price, or the preview is a lie about the page and the quote given over
        # the phone disagrees with the one on screen. Seeing the trade price is
        # what "preview as a dealer" is for: it changes the access codes, which
        # is the one knob that decides an offer.
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, access_levels=["dealer"]
        )

        view = resolve_prices(db, [product], STAFF, promotion_id=promotion_id)[product.id]

        assert view.offer_price is None
        assert view.promotion_id is None

    def test_staff_holding_the_dealer_code_see_the_dealer_price(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, access_levels=["dealer"]
        )
        staff_as_dealer = ViewerContext(is_staff=True, access_codes=frozenset({"dealer"}))

        assert resolve_prices(db, [product], staff_as_dealer, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("79.00")

    def test_another_companys_promotion_is_no_offer(self, db) -> None:
        # Money is the last thing that should cross a company boundary. The
        # ordinary scope filter does it, and this proves the query goes through
        # it rather than around it in raw SQL.
        elsewhere = _other_company(db)
        product = _product(db)
        promotion_id = _promotion(
            db, {product: Decimal("79.00")}, company_id=elsewhere
        )

        assert (
            resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
                product.id
            ].offer_price
            is None
        )


class TestTheInvoicePrice:
    def test_staff_see_it_when_the_document_asks(self, db) -> None:
        product = _product(db, invoice_price=Decimal("60.00"))

        view = resolve_prices(db, [product], STAFF_SHOWING_INVOICE)[product.id]

        assert view.invoice_price == Decimal("60.00")

    def test_staff_do_not_see_it_when_the_document_does_not_ask(self, db) -> None:
        product = _product(db, invoice_price=Decimal("60.00"))

        assert resolve_prices(db, [product], STAFF)[product.id].invoice_price is None

    def test_a_dealer_never_sees_it_however_the_document_is_set(self, db) -> None:
        # A dealer negotiating on price must not read the figure the invoice
        # will be raised at. The document toggle and the viewer entitlement are
        # ANDed, and the dealer fails the second one.
        product = _product(db, invoice_price=Decimal("60.00"))
        dealer_on_a_page_that_asks = ViewerContext(
            access_codes=frozenset({"dealer"}), show_invoice_price=True
        )

        assert (
            resolve_prices(db, [product], dealer_on_a_page_that_asks)[product.id].invoice_price
            is None
        )

    def test_a_consumer_never_sees_it(self, db) -> None:
        product = _product(db, invoice_price=Decimal("60.00"))

        assert resolve_prices(db, [product], CONSUMER)[product.id].invoice_price is None

    def test_a_product_with_no_invoice_price_reports_none_to_staff(self, db) -> None:
        product = _product(db, invoice_price=None)

        assert (
            resolve_prices(db, [product], STAFF_SHOWING_INVOICE)[product.id].invoice_price
            is None
        )


class TestAwkwardData:
    def test_a_product_with_no_list_price_is_answered_not_refused(self, db) -> None:
        # `products.list_price` is NOT NULL, so this row cannot be inserted -
        # it is built unsaved on purpose, which is how a caller holding a
        # part-built or projected product hands us one. The tile shows "price on
        # request"; a raise here would take the whole catalogue down with it.
        priceless = Product(
            id=str(uuid.uuid4()),
            product_code=unique_code("ZZTNP"),
            product_name="ZZT priceless",
            list_price=None,
        )

        view = resolve_prices(db, [priceless], CONSUMER)[priceless.id]

        assert view.list_price is None
        assert view.offer_price is None
        # No currency on the row either, and a tile still has to label a column.
        assert view.currency == "MYR"

    def test_a_promotion_row_with_no_price_is_not_an_offer(self, db) -> None:
        # `promo_selling_price` is nullable and the promotion editor allows a
        # row that only records a discount percent. A row with no price states
        # no price, so the reader gets the list price rather than a blank where
        # a number belongs.
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(db, {product: None})

        view = resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[product.id]

        assert view.offer_price is None
        assert view.promotion_id is None
        assert view.list_price == Decimal("100.00")

    def test_the_same_product_in_two_groups_is_offered_the_lower_price(self, db) -> None:
        # One promotion can list a product in more than one group - a bundle
        # group and a headline group, say. Whichever we pick must be the same
        # every time or two screens quote two prices for one product, which is
        # the failure ADR 0008 exists to prevent. The lower one is chosen
        # because it is the one already published to this reader on this
        # promotion: quoting the higher figure while the lower is advertised on
        # the same offer is indefensible at the counter.
        product = _product(db, list_price=Decimal("100.00"))
        promotion_id = _promotion(db, {product: Decimal("89.00")})
        promotion = db.query(Promotion).filter(Promotion.id == promotion_id).one()
        _group(db, promotion, {product: Decimal("69.00")})

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("69.00")

    def test_a_priced_row_beats_a_priceless_one_in_another_group(self, db) -> None:
        # A row with no price is not a cheaper offer, it is no offer. Sorting it
        # to the front would silence a real published price.
        product = _product(db)
        promotion_id = _promotion(db, {product: None})
        promotion = db.query(Promotion).filter(Promotion.id == promotion_id).one()
        _group(db, promotion, {product: Decimal("69.00")})

        assert resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price == Decimal("69.00")

    def test_the_same_product_asked_about_twice_is_answered_once(self, db) -> None:
        product = _product(db)
        promotion_id = _promotion(db, {product: Decimal("79.00")})

        views = resolve_prices(db, [product, product], DEALER, promotion_id=promotion_id)

        assert list(views) == [product.id]

    def test_every_figure_is_a_decimal(self, db) -> None:
        # Money is Decimal end to end (ADR 0008 rule 3). A float that reaches a
        # caller gets summed into a quote total that is a cent out, and the
        # place that fails is the invoice.
        product = _product(db, list_price=Decimal("100.00"), invoice_price=Decimal("60.00"))
        promotion_id = _promotion(db, {product: Decimal("79.00")})

        view = resolve_prices(db, [product], STAFF_SHOWING_INVOICE, promotion_id=promotion_id)[
            product.id
        ]

        # The dealer offer needs its own resolve: STAFF is deliberately a
        # consumer for access purposes.
        offer = resolve_prices(db, [product], DEALER, promotion_id=promotion_id)[
            product.id
        ].offer_price

        for figure in (view.list_price, view.invoice_price, offer):
            assert isinstance(figure, Decimal), f"{figure!r} is {type(figure)}, not Decimal"

    def test_a_number_that_is_not_a_decimal_is_made_one(self, db) -> None:
        # An unsaved row can carry whatever the caller assigned. Passing it
        # through untouched puts a float into somebody's arithmetic.
        product = Product(
            id=str(uuid.uuid4()),
            product_code=unique_code("ZZTINT"),
            product_name="ZZT int priced",
            list_price=100,
        )

        assert resolve_prices(db, [product], CONSUMER)[product.id].list_price == Decimal("100")
        assert isinstance(
            resolve_prices(db, [product], CONSUMER)[product.id].list_price, Decimal
        )


class TestOneQueryForTheWholePage:
    """Rule: the work does not grow with the number of tiles."""

    def _page(self, db, size: int):
        products = [_product(db) for _ in range(size)]
        promotion_id = _promotion(db, {product: Decimal("79.00") for product in products})
        return products, promotion_id

    def test_a_bigger_page_is_not_more_queries(self, db) -> None:
        small, small_promotion = self._page(db, 2)
        large, large_promotion = self._page(db, 20)
        db.flush()

        with _promotion_selects(db) as for_small:
            resolve_prices(db, small, DEALER, promotion_id=small_promotion)
        with _promotion_selects(db) as for_large:
            views = resolve_prices(db, large, DEALER, promotion_id=large_promotion)

        assert len(views) == 20
        assert all(view.offer_price == Decimal("79.00") for view in views.values())
        assert len(for_large) == len(for_small), (
            f"{len(for_small)} statement(s) for 2 products but {len(for_large)} for 20 - "
            "the resolver is looking up one product at a time"
        )

    def test_it_is_exactly_one_query(self, db) -> None:
        products, promotion_id = self._page(db, 20)
        db.flush()

        with _promotion_selects(db) as statements:
            resolve_prices(db, products, DEALER, promotion_id=promotion_id)

        assert len(statements) == 1, statements

    def test_no_promotion_means_no_query_at_all(self, db) -> None:
        # Most pages carry no promotion. They must not pay for the feature.
        products, _ = self._page(db, 5)
        db.flush()

        with _promotion_selects(db) as statements:
            resolve_prices(db, products, DEALER)

        assert statements == []
