"""What THIS viewer pays for these products. The only answer to that question.

ADR 0008. The Kit turns a price into something a reader sees on a catalogue
tile, in a quote line, in a bundle heading and in a bundle's saving against
list. Four readers, none of which knew promotions existed, and adding "a dealer
sees the promo price while the promotion is live" to each of them separately
means four commercial rules drifting apart until two screens quote one product
at two prices. So it lives here, once, and every surface calls it.

Three things this owes its callers:

* **Decimal end to end.** No float arithmetic anywhere in here, and nothing
  formatted: a caller receives numbers it renders, never numbers it computes.
  Formatting happens at the edge, once.
* **A price a viewer may not see is ABSENT, not hidden.** A dealer-only offer
  resolves to ``offer_price=None`` AND ``promotion_id=None`` for a consumer, so
  neither the figure nor the fact that an offer exists can be recovered from the
  payload.
* **One query for the whole page.** ``resolve_prices`` takes a LIST for the same
  reason ``primary_image_urls`` does - a per-tile lookup turns a forty product
  catalogue into forty round trips.

The brochure decides WHICH promotion (a page carries at most one, an editorial
choice). The viewer decides WHETHER it applies: access levels plus the date
window, resolved here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.marketing import Promotion, PromotionProduct
from app.models.product import Product
from app.services.dealer_kit.product_images import PUBLIC_ACCESS_CODE
from app.services.dealer_kit.viewer import ViewerContext

# The company sells in Malaysia, so a promotion advertised as running "until the
# 31st" ends at the end of the Malaysian day. Deriving the day from the server's
# clock would end every offer eight hours early on a UTC host.
_MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# Every product row carries a currency (NOT NULL, defaulted), but an unsaved or
# part-built row handed in by a caller may not, and a tile still has to label a
# column. Matches the fallback the tile and quote resolvers already use.
DEFAULT_CURRENCY = "MYR"


@dataclass(frozen=True)
class PriceView:
    """What one product costs this reader, and why.

    ``list_price`` is reported alongside ``offer_price`` rather than replaced by
    it: the tile strikes the list price through beside the offer, and a caller
    that only received the offer could not show what the reader is saving.

    ``promotion_id`` is present only when an offer is - it answers the support
    question "why is this customer being quoted 79", and naming a promotion to a
    reader who does not get it would hand them the id of an offer they cannot
    have.
    """

    currency: str
    list_price: Optional[Decimal]
    offer_price: Optional[Decimal]
    invoice_price: Optional[Decimal]
    promotion_id: Optional[str]


def business_today() -> date:
    """The calendar day a promotion window is measured against."""
    return datetime.now(timezone.utc).astimezone(_MY_TZ).date()


def _as_decimal(value) -> Optional[Decimal]:
    """Money, or nothing. Never a float.

    Numeric columns already arrive as Decimal; the coercion is for rows a caller
    built by hand, where an int or a float would otherwise pass straight through
    into somebody's arithmetic and land a quote total a cent out.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _may_see_offer(levels: Optional[Sequence[str]], viewer: ViewerContext) -> bool:
    """Whether this viewer is one of the audiences the promotion is priced for.

    Two deliberate readings, both differing from how imagery is gated:

    **An empty ``access_levels`` reaches nobody.** ``promotions.access_levels``
    is NOT NULL and ships defaulted to both audiences, so an empty list is
    somebody deliberately emptying it rather than a legacy row that predates
    tagging. Guessing wrong here prices a sale, so it fails closed.
    ``product_attachments.access_levels`` is treated the opposite way for the
    opposite reason: untagged photos there are legacy, and hiding all of them
    would empty the catalogue to protect nothing.

    **Staff do not bypass it.** ``is_staff`` decides the invoice price and
    nothing else. Staff checking the page they are about to send a customer must
    see the customer's price, or the preview is a lie about the page and the
    quote given over the phone disagrees with the one on screen. Seeing the
    trade price is what previewing AS a dealer is for: it changes the access
    codes, which is the one knob that decides an offer.
    """
    if not levels:
        return False

    # An INTERNAL COPY is the brochure, so it carries the brochure's own offers
    # whoever they were aimed at. An office PDF that dropped them would be
    # printed, read, and quoted from, and the figure would disagree with the page
    # the customer is looking at. Deliberately NOT keyed on is_staff: staff
    # previewing what a consumer will see must still see the consumer's price.
    if viewer.is_internal_copy:
        return True

    # The public catalogue is the consumer-facing surface, so a reader who
    # brought no code counts as a consumer - exactly as they do for imagery.
    codes = set(viewer.access_codes) or {PUBLIC_ACCESS_CODE}
    return bool(codes & set(levels))


def _offer_prices(
    db: Session,
    product_ids: Sequence[str],
    viewer: ViewerContext,
    promotion_id: str,
) -> dict[str, Decimal]:
    """``{product_id: promo price}`` for the products this offer covers today.

    ONE statement for the whole page. An expired, switched-off, unknown or
    wrong-audience promotion simply yields nothing, which is what makes "no
    applicable offer" and "the promotion ended mid-session" the same code path:
    the list price, with no offer styling.
    """
    today = business_today()

    rows = (
        db.query(PromotionProduct, Promotion)
        .join(Promotion, Promotion.id == PromotionProduct.promotion_id)
        .filter(PromotionProduct.promotion_id == promotion_id)
        .filter(PromotionProduct.product_id.in_(list(product_ids)))
        # Switched off wins over a window that still says the promotion runs:
        # `is_active` is how somebody pulls a live offer in a hurry.
        .filter(Promotion.is_active.is_(True))
        # Inclusive at both ends, unbounded on whichever side has no date. A
        # promotion advertised as running "until the 31st" that stops honouring
        # its price on the 31st is an argument at a counter.
        .filter(or_(Promotion.start_date.is_(None), Promotion.start_date <= today))
        .filter(or_(Promotion.end_date.is_(None), Promotion.end_date >= today))
        .all()
    )

    offers: dict[str, Decimal] = {}
    for offer, promotion in rows:
        # Same promotion on every row, so this drops all of them or none. Kept
        # per row rather than hoisted because the invariant is then enforced
        # rather than assumed.
        if not _may_see_offer(promotion.access_levels, viewer):
            continue

        # A row with no price states no price. The promotion editor allows one
        # that records only a discount percent, and treating that as an offer
        # would leave a blank where a number belongs.
        price = _as_decimal(offer.promo_selling_price)
        if price is None:
            continue

        # One promotion can list a product in more than one group - a bundle
        # group and a headline group, say - and whichever we pick has to be the
        # same every time, or two screens quote two prices for one product. The
        # lower one wins: it is already published to this reader on this
        # promotion, so quoting the higher figure is indefensible at the
        # counter. Equal prices are the same number, so ties do not matter.
        current = offers.get(offer.product_id)
        if current is None or price < current:
            offers[offer.product_id] = price

    return offers


def resolve_prices(
    db: Session,
    products: Iterable[Product],
    viewer: ViewerContext,
    promotion_id: Optional[str] = None,
) -> dict[str, PriceView]:
    """``{product_id: PriceView}`` for every product asked about.

    ``products`` are already company-scoped by the caller; the promotion lookup
    goes through the ordinary ORM scope filter, so another company's offer
    cannot price this company's page.

    Every product asked about is answered. Callers index the result while
    rendering a grid, so a missing key would be a KeyError mid-page: "no offer"
    is a PriceView with no ``offer_price``, never an absent entry.
    """
    products = list(products)
    if not products:
        return {}

    offers: dict[str, Decimal] = {}
    if promotion_id:
        # Deduplicated: the same product can legitimately appear twice on a page
        # (two tiles, or a quote listing it on two lines).
        product_ids = list({product.id for product in products})
        offers = _offer_prices(db, product_ids, viewer, promotion_id)

    # Both gates ANDed, resolved once: the DOCUMENT asks for the invoice price
    # and the VIEWER is entitled to it. The losing case omits the number rather
    # than sending it to be hidden.
    show_invoice = viewer.invoice_price_visible

    views: dict[str, PriceView] = {}
    for product in products:
        if product.id in views:
            continue
        list_price = _a_real_price(product.list_price)
        offer = _offer_worth_showing(offers.get(product.id), list_price)
        views[product.id] = PriceView(
            currency=product.currency or DEFAULT_CURRENCY,
            list_price=list_price,
            offer_price=offer,
            invoice_price=_a_real_price(product.invoice_price) if show_invoice else None,
            promotion_id=promotion_id if offer is not None else None,
        )

    return views


def _a_real_price(value) -> Optional[Decimal]:
    """The figure, unless it is the absence of one wearing a number's clothes.

    ``products.list_price`` is NOT NULL and defaults to zero, so a product whose
    price was never imported is stored identically to one deliberately priced at
    nothing. Those are not both real categories: a genuine giveaway is a
    promotion line priced against a promotion, not a permanent list price of
    nought. So zero means "we do not have a price for this", and the honest
    rendering of that is the one the system already has for a product with no
    price at all: nothing.

    The alternative was found by opening the published catalogue in a browser,
    where a tile on the page a dealer forwards to a customer printed MYR 0.00
    against a real product. Nothing is a statement about our data. MYR 0.00 is a
    claim about the price, and one somebody could reasonably act on.

    Not a rare shape either: 10,370 of 22,805 live products carry
    ``list_price = 0.00``, 46% of one company's catalogue and 45% of the other's.

    Negatives go the same way. Nobody is owed money for taking a bath away, and
    an import reading a spreadsheet column with the wrong sign produces them.
    """
    price = _as_decimal(value)
    if price is None or price <= 0:
        return None
    return price


def _offer_worth_showing(
    offer: Optional[Decimal], list_price: Optional[Decimal]
) -> Optional[Decimal]:
    """The promotional figure, but only when it is actually an offer.

    A tile draws an offer as "list price struck through, offer prominent", so a
    promotion line priced at or above list renders as a crossed-out 285 beside a
    bold 1,099: the catalogue advertising a price nobody charges, presented as a
    discount. On the live database 422 of 1,178 promotion lines are at or above
    their product's list price and 20 are exactly zero.

    Those rows are not wrong as RECORDS. Promotions carry bundle and free-gift
    bookkeeping, and a line priced above list is meaningful inside a group where
    somebody is buying several things together. What is wrong is reading one of
    them as "the price of this product, alone, on its own tile", which is the
    only question this module answers.

    A product with no list price has nothing to be cheaper than, so the
    promotional figure stands on its own. The alternative would hide a product
    that is genuinely on offer because its master data is incomplete.
    """
    if offer is None or offer <= 0:
        return None
    if list_price is not None and offer >= list_price:
        return None
    return offer
