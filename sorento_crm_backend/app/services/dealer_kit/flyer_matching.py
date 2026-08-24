"""What a reading of the printed flyer MEANS against the master (S7.3).

``flyer_extraction`` says what is on the paper. This module says what the paper
is talking about, and produces the one artefact the seed is reviewed from: a
report a human reads beside the flyer before anything is created.

Everything in it is something somebody has to act on:

* **Matched codes**, resolved inside the active company. Every code in the real
  flyer resolves to two ``products`` rows, one per company, so the scope filter
  is not incidental here - it is the entire question. Every query below goes
  through the ordinary ORM, never raw SQL, precisely so the filter applies.
* **Unmatched codes**, 38 of the flyer's 998, each with the nearest existing
  code offered as a SUGGESTION. Never applied. Silently seeding ``SRTKS7851``
  where the flyer printed ``SRTKS7850`` puts the wrong product in front of a
  customer, and a wrong product is a worse outcome than a gap somebody can see
  (PLAN D8).
* **Printed but not promoted**, 213 of 998 on the real flyer. This is the list
  that lets marketing close the gap deliberately instead of a dealer finding it.
* **Dimension candidates**, 425 of them, each flagged against what the product
  currently holds. Nothing is written to ``products`` (PLAN D9): a card that
  disagrees with the master is a decision, not a correction to apply on a
  designer's behalf.

**Bulk, not per code.** 998 codes at one query each is not a slow report, it is
a report nobody waits for. Three statements answer the whole reading regardless
of its size: the products, the suggestions for whatever missed, and the
promotion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, cast, column, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.models.marketing import PromotionProduct
from app.models.product import Product
from app.services.dealer_kit.flyer_extraction import FlyerCard, FlyerReading

# How alike the nearest existing code has to be before it is worth showing a
# reviewer at all. Below this there is no suggestion, because "no idea" is a
# useful answer and a bath offered as the replacement for a tap is not.
#
# 0.40 rather than the 0.25 recall floor the entity resolver uses for search:
# search is allowed to be generous because a human is picking from a list, while
# this is a single named guess with an APPLY button next to it. It matches the
# resolver's own substitution floor (``SUGGEST_FLOOR``), which draws the same
# line for the same reason. Real near misses sit far above it - the flyer's
# digit-off codes score around 0.67.
SUGGESTION_FLOOR = Decimal("0.40")

# ``pg_trgm`` is installed into ``public``. Test sessions run on a scratch schema
# with ``public`` deliberately off the search path (so a stray raw query cannot
# reach the production tables), so the function is qualified rather than left to
# resolve. Qualifying is correct in production too, where the extension also
# lives in ``public``.
_TRGM_SCHEMA = "public"

# What a printed size means against the product it matched.
MISSING = "missing"
AGREES = "agrees"
CONFLICTS = "conflicts"


@dataclass(frozen=True)
class CodeSuggestion:
    """The nearest existing code to one the master does not have.

    A suggestion, and only ever a suggestion: it names a product and says how
    confident the guess is, so a reviewer can refuse it. ``similarity`` is
    reported because a suggestion with no number behind it reads as a fact.
    """

    product_id: str
    product_code: str
    product_name: str
    similarity: Decimal


@dataclass(frozen=True)
class MatchedCode:
    """A printed code, and the product in this company that it is.

    ``pages`` holds every page the code was printed on, not just the first. A
    reviewer checking the report is holding the flyer, and "it is wrong
    somewhere" is not a correction anybody can make.
    """

    code: str
    product_id: str
    product_code: str
    product_name: str
    pages: tuple[int, ...]


@dataclass(frozen=True)
class UnmatchedCode:
    """A printed code the master does not have.

    Deliberately carries NO product id. The gap is the point: a reader of this
    object cannot accidentally treat the suggestion as the answer.
    """

    code: str
    pages: tuple[int, ...]
    suggestion: Optional[CodeSuggestion]


@dataclass(frozen=True)
class DimensionCandidate:
    """A size the flyer printed, beside the size the product currently holds.

    A review queue entry and nothing else. ``verdict`` is ``CONFLICTS`` whenever
    the two disagree at all, including when the master is only half filled in -
    calling that "missing" would let a partial row be overwritten without
    anybody looking at it.
    """

    code: str
    product_id: str
    pages: tuple[int, ...]
    printed_length_mm: Decimal
    printed_width_mm: Decimal
    printed_height_mm: Decimal
    current_length_mm: Optional[Decimal]
    current_width_mm: Optional[Decimal]
    current_height_mm: Optional[Decimal]
    verdict: str


@dataclass(frozen=True)
class MatchReport:
    """Everything the review screen needs, and nothing it has to derive."""

    matched: list[MatchedCode] = field(default_factory=list)
    unmatched: list[UnmatchedCode] = field(default_factory=list)
    not_promoted: list[MatchedCode] = field(default_factory=list)
    dimension_candidates: list[DimensionCandidate] = field(default_factory=list)
    promotion_id: Optional[str] = None

    @property
    def duplicates(self) -> dict[str, tuple[int, ...]]:
        """Codes printed on more than one page, and every page each appeared on.

        A code printed twice is one product, so it is reported once above. This
        says where to look when it needs checking.
        """
        return {
            entry.code: entry.pages
            for entry in [*self.matched, *self.unmatched]
            if len(entry.pages) > 1
        }


@dataclass(frozen=True)
class _Printed:
    """One code as the whole document printed it."""

    pages: tuple[int, ...]
    sized_card: Optional[FlyerCard]


def match_reading(
    db: Session,
    reading: FlyerReading,
    promotion_id: Optional[str] = None,
) -> MatchReport:
    """Turn a reading into the report the seed is reviewed from.

    Reads only. Nothing here writes to ``products`` or to the promotion; the
    dimension queue and the suggestions are applied later, one click at a time,
    by somebody with the permission to do it.

    ``promotion_id`` is optional because a brochure need not be linked to one
    (PLAN D5). Given one, the report says which printed products it does not
    carry - including when the promotion does not exist at all, which reports
    every matched product. Loud on purpose: "998 of 998 not promoted" is how a
    reviewer finds out the brochure points at a promotion somebody deleted,
    where silence would read as a healthy flyer.
    """
    printed = _printed_codes(reading)
    if not printed:
        # An empty reading asks the database nothing. The seed screen renders a
        # report for a PDF that is still uploading, and that must not be a query.
        return MatchReport(promotion_id=promotion_id)

    products = _products_by_code(db, list(printed))

    matched: list[MatchedCode] = []
    unmatched_codes: list[str] = []
    for code, where in printed.items():
        product = products.get(code)
        if product is None:
            unmatched_codes.append(code)
            continue
        matched.append(
            MatchedCode(
                code=code,
                product_id=product.id,
                product_code=product.product_code,
                product_name=product.product_name,
                pages=where.pages,
            )
        )

    suggestions = _suggestions(db, unmatched_codes) if unmatched_codes else {}
    unmatched = [
        UnmatchedCode(code=code, pages=printed[code].pages, suggestion=suggestions.get(code))
        for code in unmatched_codes
    ]

    return MatchReport(
        matched=matched,
        unmatched=unmatched,
        not_promoted=_not_promoted(db, matched, promotion_id),
        dimension_candidates=_dimension_candidates(matched, printed, products),
        promotion_id=promotion_id,
    )


def _printed_codes(reading: FlyerReading) -> dict[str, _Printed]:
    """``{code: where it was printed}``, in the order the document prints them.

    A code on two pages is ONE entry carrying both page numbers: it is one
    product, and the flyer shows it twice. The first card that carries a size
    wins, because there is one product to correct and the reviewer reads the
    document top to bottom.
    """
    pages: dict[str, list[int]] = {}
    sized: dict[str, FlyerCard] = {}

    for page in reading.pages:
        for card in page.cards:
            seen = pages.setdefault(card.code, [])
            if page.number not in seen:
                seen.append(page.number)
            if card.code not in sized and _printed_size(card) is not None:
                sized[card.code] = card

    return {
        code: _Printed(pages=tuple(numbers), sized_card=sized.get(code))
        for code, numbers in pages.items()
    }


def _printed_size(card: FlyerCard) -> Optional[tuple[Decimal, Decimal, Decimal]]:
    """The card's ``L x W x H``, as millimetres, or nothing.

    All three or none: a half-read dimension line is the extractor's own miss,
    and offering it for review would put a guess into the master.
    """
    if card.length_mm is None or card.width_mm is None or card.height_mm is None:
        return None
    return (
        Decimal(card.length_mm),
        Decimal(card.width_mm),
        Decimal(card.height_mm),
    )


def _products_by_code(db: Session, codes: list[str]) -> dict[str, Product]:
    """Resolve every printed code at once, inside the active company scope.

    An ordinary ORM query on purpose: ``do_orm_execute`` splices the company
    predicate into it, so a code that exists only under another company comes
    back unmatched rather than silently seeding that company's product id into
    this catalogue. Raw SQL would go round the filter and pass every other test
    in the suite while doing it.

    One statement for the whole reading. A multi-company scope can return the
    same code twice; a brochure belongs to one company, so the first row wins
    and the caller's scope is what decides which.
    """
    rows = (
        db.query(Product)
        .filter(Product.product_code.in_(codes))
        .order_by(Product.product_code, Product.id)
        .all()
    )

    resolved: dict[str, Product] = {}
    for product in rows:
        resolved.setdefault(product.product_code, product)
    return resolved


def _suggestions(db: Session, codes: list[str]) -> dict[str, CodeSuggestion]:
    """The nearest existing code to each miss, when one is near enough.

    ``similarity()`` from ``pg_trgm`` rather than a distance computed here: the
    extension is installed, it is what the rest of the system already uses to
    answer "did you mean", and a hand-rolled metric would disagree with the
    suggestions users see everywhere else.

    One statement for every miss, by unnesting the codes into a derived table
    and joining the products to it. The alternative - a query per unmatched code
  - is invisible on the three-page fixture and 38 round trips on the real one.
    ``Product`` leads the query so the company predicate lands on it, which is
    what keeps a suggestion from naming another company's product.
    """
    wanted = (
        func.unnest(cast(codes, ARRAY(String)))
        .table_valued(column("code", String))
        .render_derived()
    )
    score = getattr(func, _TRGM_SCHEMA).similarity(Product.product_code, wanted.c.code)

    rows = (
        db.query(Product, wanted.c.code.label("printed"), score.label("score"))
        .join(wanted, score >= SUGGESTION_FLOOR)
        .all()
    )

    best: dict[str, CodeSuggestion] = {}
    for product, printed, raw_score in rows:
        # Quantised because the score is shown to a human, who is deciding
        # whether to accept a guess and does not need seven decimal places.
        similarity = Decimal(str(raw_score)).quantize(Decimal("0.0001"))
        current = best.get(printed)
        # Ties broken by code so two runs over the same flyer suggest the same
        # thing. A suggestion that moves between refreshes is not trustworthy.
        if current is None or (similarity, product.product_code) > (
            current.similarity,
            current.product_code,
        ):
            best[printed] = CodeSuggestion(
                product_id=product.id,
                product_code=product.product_code,
                product_name=product.product_name,
                similarity=similarity,
            )
    return best


def _not_promoted(
    db: Session,
    matched: list[MatchedCode],
    promotion_id: Optional[str],
) -> list[MatchedCode]:
    """Matched products the linked promotion does not carry (PLAN D6).

    Only MATCHED codes can be here. An unmatched code is already reported as a
    match gap, and listing it again would inflate the promotion gap with codes
    the master does not even have.

    Membership, not pricing: the dates and the audience belong to
    ``resolve_prices``. A product sitting in an expired promotion is still IN
    that promotion, and telling marketing to add it would be wrong.
    """
    if not promotion_id or not matched:
        return []

    product_ids = [entry.product_id for entry in matched]
    rows = (
        db.query(PromotionProduct)
        .filter(PromotionProduct.promotion_id == promotion_id)
        .filter(PromotionProduct.product_id.in_(product_ids))
        .all()
    )
    promoted = {row.product_id for row in rows}

    return [entry for entry in matched if entry.product_id not in promoted]


def _dimension_candidates(
    matched: list[MatchedCode],
    printed: dict[str, _Printed],
    products: dict[str, Product],
) -> list[DimensionCandidate]:
    """The review queue for the 425 cards that print a size (PLAN D9).

    Matched codes only: an unmatched code has nothing to be reviewed against.
    Nothing is written here, and nothing may be - a size on a flyer is evidence,
    and which of the two records is wrong is a decision for someone with the
    master-data permission.
    """
    candidates: list[DimensionCandidate] = []

    for entry in matched:
        card = printed[entry.code].sized_card
        if card is None:
            continue
        size = _printed_size(card)
        if size is None:  # pragma: no cover - sized_card is chosen by this test
            continue

        product = products[entry.code]
        current = (
            _as_decimal(product.dimensions_length),
            _as_decimal(product.dimensions_width),
            _as_decimal(product.dimensions_height),
        )
        candidates.append(
            DimensionCandidate(
                code=entry.code,
                product_id=entry.product_id,
                pages=entry.pages,
                printed_length_mm=size[0],
                printed_width_mm=size[1],
                printed_height_mm=size[2],
                current_length_mm=current[0],
                current_width_mm=current[1],
                current_height_mm=current[2],
                verdict=_verdict(size, current),
            )
        )

    return candidates


def _verdict(
    printed: tuple[Decimal, Decimal, Decimal],
    current: tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]],
) -> str:
    """Which of the three things this candidate is.

    ``CONFLICTS`` is the interesting one and must not be buried: either the
    printed flyer is wrong, which is a reprint, or the master is, which is a
    wrong box arriving at a customer. A half-filled master counts as a conflict
    rather than as missing, so filling in the blanks is never a silent overwrite
    of the two numbers somebody already entered.
    """
    if all(value is None for value in current):
        return MISSING
    return AGREES if tuple(current) == printed else CONFLICTS


def _as_decimal(value) -> Optional[Decimal]:
    """A millimetre, or nothing. Never a float.

    ``Numeric`` columns already arrive as Decimal; the coercion covers a row a
    caller built by hand, where a float would compare unequal to the identical
    printed figure and turn an agreement into a conflict.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
