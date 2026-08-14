"""Turning a reading of the printed flyer into a REVIEW REPORT (UAC group D).

Written before the matcher.

The extractor already says what is printed. This slice says what the printed
document means against the master, and everything it produces is something a
human is meant to act on:

* **A code resolves inside ONE company.** Every code in the real flyer resolves
  to two ``products`` rows, one per company, so scoping is not a detail here -
  it is the whole question. These tests seed the same code in two companies on
  purpose, because a matcher that reached around the scope filter would still
  pass every other test in this file.
* **A near miss is a SUGGESTION, never a substitution** (PLAN D8). Silently
  seeding ``SRTKS7851`` where the flyer printed ``SRTKS7850`` puts the wrong
  product in front of a customer, which is worse than a gap somebody can see.
* **Nothing is written to the product master** (PLAN D9). Dimensions printed on
  a card are a queue for review, and a card disagreeing with the master is the
  interesting row rather than one to bury.

Postgres only, on a blank scratch schema, because the whole point is behaviour
the ORM scope filter and ``pg_trgm`` provide and sqlite does not.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.dealer_kit.flyer_extraction import (
    FlyerCard,
    FlyerPage,
    FlyerReading,
    extract_flyer,
)
from app.services.dealer_kit.flyer_matching import (
    SUGGESTION_FLOOR,
    AGREES,
    CONFLICTS,
    MISSING,
    match_reading,
)
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = (
    Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# --------------------------------------------------------------------------- #
# Building a reading by hand. The extractor is tested elsewhere; what matters
# here is only what a reading SAYS, so these are plain dataclasses.
# --------------------------------------------------------------------------- #
def _card(code: str, *, dims: tuple[int, int, int] | None = None, x: float = 0.0) -> FlyerCard:
    length, width, height = dims or (None, None, None)
    return FlyerCard(
        code=code,
        lines=[f"{code} name"],
        x=x,
        y=100.0,
        length_mm=length,
        width_mm=width,
        height_mm=height,
    )


def _page(number: int, *cards: FlyerCard) -> FlyerPage:
    page = FlyerPage(number=number, width=842.0, height=1191.0)
    page.cards = list(cards)
    return page


def _reading(*pages: FlyerPage) -> FlyerReading:
    return FlyerReading(pages=list(pages))


def _printed(*codes: str) -> FlyerReading:
    """The simplest reading: one page, one card per code."""
    return _reading(_page(1, *[_card(code, x=float(index)) for index, code in enumerate(codes)]))


# --------------------------------------------------------------------------- #
# Rows. Every one is ZZT-scoped: the blank schema is throwaway, but the habit is
# what keeps a stray fixture off the production copy.
# --------------------------------------------------------------------------- #
def _product(
    db,
    code: str,
    *,
    dims: tuple[Decimal | None, Decimal | None, Decimal | None] | None = None,
    company_id: str | None = None,
    name: str | None = None,
) -> Product:
    stem = unique_code("ZZTFM")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()

    length, width, height = dims or (None, None, None)
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=name or f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
        dimensions_length=length,
        dimensions_width=width,
        dimensions_height=height,
        company_id=company_id,
    )
    db.add(product)
    db.flush()
    return product


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


def _promotion(db, *products: Product, company_id: str | None = None) -> str:
    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=unique_code("ZZT promo"),
        is_active=True,
        access_levels=["dealer", "end_user"],
        company_id=company_id,
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(
        promotion_id=promotion.id,
        group_name=unique_code("ZZT grp"),
        company_id=company_id,
    )
    db.add(group)
    db.flush()
    for product in products:
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promotion.id,
                promotion_group_id=group.id,
                product_id=product.id,
                promo_selling_price=Decimal("79.00"),
                company_id=company_id,
            )
        )
    db.flush()
    return promotion.id


@contextmanager
def _selects(db):
    """Every SELECT the matcher issues, so the bulk rule can be measured.

    A per-code loop returns exactly the same report as a bulk resolve, so only a
    count can tell them apart. 998 codes at one query each is not a slow report,
    it is a report nobody waits for.
    """
    from sqlalchemy import event

    statements: list[str] = []
    engine = db.connection().engine

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        text = statement.lstrip()
        if text.upper().startswith("SELECT"):
            statements.append(text)

    event.listen(engine, "after_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "after_cursor_execute", _record)


def _by_code(entries):
    return {entry.code: entry for entry in entries}


class TestMatchingCodes:
    def test_a_printed_code_resolves_to_its_product(self, db) -> None:
        product = _product(db, "ZZTWC8100")

        report = match_reading(db, _printed("ZZTWC8100"))

        assert [entry.product_id for entry in report.matched] == [product.id]

    def test_the_matched_entry_names_the_product_a_reviewer_will_read(self, db) -> None:
        # The review screen lists what the flyer printed beside what it matched.
        # A row of ids is not something a human can check.
        _product(db, "ZZTWC8100", name="ZZT Rimless Water Closet")

        entry = report_of(db, "ZZTWC8100").matched[0]

        assert entry.code == "ZZTWC8100"
        assert entry.product_name == "ZZT Rimless Water Closet"

    def test_a_code_the_master_does_not_have_is_unmatched(self, db) -> None:
        report = match_reading(db, _printed("ZZTNOSUCH1"))

        assert [entry.code for entry in report.unmatched] == ["ZZTNOSUCH1"]
        assert report.matched == []

    def test_every_printed_code_is_accounted_for_exactly_once(self, db) -> None:
        # A code that fell out of both lists is a product silently dropped from
        # the catalogue, which is the failure the report exists to prevent.
        _product(db, "ZZTWC8100")
        reading = _printed("ZZTWC8100", "ZZTNOSUCH1", "ZZTNOSUCH2")

        report = match_reading(db, reading)

        seen = [entry.code for entry in report.matched] + [
            entry.code for entry in report.unmatched
        ]
        assert sorted(seen) == ["ZZTNOSUCH1", "ZZTNOSUCH2", "ZZTWC8100"]

    def test_the_printed_order_is_kept(self, db) -> None:
        # The report is read next to the flyer, page by page.
        for code in ("ZZTWC8100", "ZZTWC8200", "ZZTWC8300"):
            _product(db, code)

        report = match_reading(db, _printed("ZZTWC8300", "ZZTWC8100", "ZZTWC8200"))

        assert [entry.code for entry in report.matched] == [
            "ZZTWC8300",
            "ZZTWC8100",
            "ZZTWC8200",
        ]

    def test_an_empty_reading_is_an_empty_report(self, db) -> None:
        report = match_reading(db, FlyerReading())

        assert report.matched == []
        assert report.unmatched == []
        assert report.not_promoted == []
        assert report.dimension_candidates == []

    def test_an_empty_reading_asks_the_database_nothing(self, db) -> None:
        with _selects(db) as statements:
            match_reading(db, FlyerReading(), promotion_id=str(uuid.uuid4()))

        assert statements == []


class TestCompanyScope:
    """Every code in the real flyer resolves to two rows, one per company."""

    def test_the_product_in_this_company_is_the_one_matched(self, db) -> None:
        elsewhere = _other_company(db)
        mine = _product(db, "ZZTWC8100")
        _product(db, "ZZTWC8100", company_id=elsewhere)

        report = match_reading(db, _printed("ZZTWC8100"))

        assert [entry.product_id for entry in report.matched] == [mine.id]

    def test_a_code_only_another_company_has_is_unmatched(self, db) -> None:
        # Never silently matched. Seeding a catalogue with another company's
        # product id is a cross-company leak that renders as a normal tile.
        elsewhere = _other_company(db)
        _product(db, "ZZTWC8100", company_id=elsewhere)

        report = match_reading(db, _printed("ZZTWC8100"))

        assert report.matched == []
        assert [entry.code for entry in report.unmatched] == ["ZZTWC8100"]

    def test_a_suggestion_never_crosses_a_company_boundary(self, db) -> None:
        # The nearest code by similarity belongs to another company, so there is
        # no suggestion at all rather than one nobody here can act on.
        elsewhere = _other_company(db)
        _product(db, "ZZTKS7851", company_id=elsewhere)

        report = match_reading(db, _printed("ZZTKS7850"))

        assert report.unmatched[0].suggestion is None


class TestSuggestions:
    def test_a_near_miss_gets_the_nearest_code_as_a_suggestion(self, db) -> None:
        neighbour = _product(db, "ZZTKS7851")

        suggestion = report_of(db, "ZZTKS7850").unmatched[0].suggestion

        assert suggestion is not None
        assert suggestion.product_code == "ZZTKS7851"
        assert suggestion.product_id == neighbour.id

    def test_the_suggestion_carries_its_score(self, db) -> None:
        # A reviewer clicking "apply" is entitled to see how confident the guess
        # is. A suggestion with no number behind it reads as a fact.
        _product(db, "ZZTKS7851")

        suggestion = report_of(db, "ZZTKS7850").unmatched[0].suggestion

        assert suggestion is not None
        assert SUGGESTION_FLOOR <= suggestion.similarity <= Decimal("1")

    def test_the_score_is_a_decimal(self, db) -> None:
        _product(db, "ZZTKS7851")

        suggestion = report_of(db, "ZZTKS7850").unmatched[0].suggestion

        assert suggestion is not None
        assert isinstance(suggestion.similarity, Decimal)

    def test_a_suggestion_is_never_applied(self, db) -> None:
        # PLAN D8. The entry stays UNMATCHED and keeps the code the flyer
        # printed, so the seed leaves a gap rather than the wrong product.
        _product(db, "ZZTKS7851")

        report = report_of(db, "ZZTKS7850")

        assert report.matched == []
        assert report.unmatched[0].code == "ZZTKS7850"
        assert not hasattr(report.unmatched[0], "product_id")

    def test_an_unrelated_code_is_no_suggestion_at_all(self, db) -> None:
        # Returning the nearest row whatever its score would offer a bath as the
        # replacement for a tap. Below the floor there is no answer.
        _product(db, "ZZTAB1")

        assert report_of(db, "ZZTKS7850").unmatched[0].suggestion is None

    def test_the_closest_of_several_candidates_wins(self, db) -> None:
        _product(db, "ZZTKS7851")
        _product(db, "ZZTKS7860")
        _product(db, "ZZTKS7900")

        suggestion = report_of(db, "ZZTKS7850").unmatched[0].suggestion

        assert suggestion is not None
        assert suggestion.product_code == "ZZTKS7851"

    def test_a_matched_code_carries_no_suggestion(self, db) -> None:
        _product(db, "ZZTKS7850")
        _product(db, "ZZTKS7851")

        assert report_of(db, "ZZTKS7850").unmatched == []


class TestPrintedButNotPromoted:
    """The 213 of 998 that marketing has to close deliberately (PLAN D6)."""

    def test_a_printed_product_absent_from_the_promotion_is_reported(self, db) -> None:
        promoted = _product(db, "ZZTWC8100")
        gap = _product(db, "ZZTWC8200")
        promotion_id = _promotion(db, promoted)

        report = match_reading(db, _printed("ZZTWC8100", "ZZTWC8200"), promotion_id=promotion_id)

        assert [entry.code for entry in report.not_promoted] == ["ZZTWC8200"]
        assert [entry.product_id for entry in report.not_promoted] == [gap.id]

    def test_a_promoted_product_is_not_reported(self, db) -> None:
        promoted = _product(db, "ZZTWC8100")
        promotion_id = _promotion(db, promoted)

        report = match_reading(db, _printed("ZZTWC8100"), promotion_id=promotion_id)

        assert report.not_promoted == []

    def test_no_promotion_asked_about_means_no_gap_list(self, db) -> None:
        # A brochure with no linked promotion has no gap to close: it prices at
        # list by design (PLAN D6), so listing every product would be noise.
        _product(db, "ZZTWC8100")

        report = match_reading(db, _printed("ZZTWC8100"))

        assert report.not_promoted == []
        assert report.promotion_id is None

    def test_a_promotion_that_does_not_exist_makes_every_product_a_gap(self, db) -> None:
        # Loud on purpose. "998 of 998 not promoted" is how a reviewer finds out
        # the brochure is pointed at a promotion that has been deleted; silence
        # would read as a healthy flyer.
        _product(db, "ZZTWC8100")

        report = match_reading(db, _printed("ZZTWC8100"), promotion_id=str(uuid.uuid4()))

        assert [entry.code for entry in report.not_promoted] == ["ZZTWC8100"]

    def test_another_companys_promotion_row_does_not_close_the_gap(self, db) -> None:
        elsewhere = _other_company(db)
        product = _product(db, "ZZTWC8100")
        promotion_id = _promotion(db, product, company_id=elsewhere)

        report = match_reading(db, _printed("ZZTWC8100"), promotion_id=promotion_id)

        assert [entry.code for entry in report.not_promoted] == ["ZZTWC8100"]

    def test_an_unmatched_code_is_not_also_a_promotion_gap(self, db) -> None:
        # It is reported once, as a match gap. Listing it twice would inflate the
        # promotion gap with codes the master does not even have.
        product = _product(db, "ZZTWC8100")
        promotion_id = _promotion(db, product)

        report = match_reading(
            db, _printed("ZZTWC8100", "ZZTNOSUCH1"), promotion_id=promotion_id
        )

        assert report.not_promoted == []
        assert [entry.code for entry in report.unmatched] == ["ZZTNOSUCH1"]

    def test_the_report_names_the_promotion_it_was_measured_against(self, db) -> None:
        product = _product(db, "ZZTWC8100")
        promotion_id = _promotion(db, product)

        report = match_reading(db, _printed("ZZTWC8100"), promotion_id=promotion_id)

        assert report.promotion_id == promotion_id


class TestDimensionCandidates:
    """A review queue, never a write (PLAN D9)."""

    def test_a_product_with_no_dimensions_gets_a_missing_candidate(self, db) -> None:
        _product(db, "ZZTJC2023")
        reading = _reading(_page(1, _card("ZZTJC2023", dims=(1700, 850, 600))))

        candidate = match_reading(db, reading).dimension_candidates[0]

        assert candidate.code == "ZZTJC2023"
        assert candidate.verdict == MISSING
        assert candidate.printed_length_mm == Decimal("1700")
        assert candidate.printed_width_mm == Decimal("850")
        assert candidate.printed_height_mm == Decimal("600")

    def test_matching_dimensions_agree(self, db) -> None:
        _product(
            db,
            "ZZTJC2023",
            dims=(Decimal("1700"), Decimal("850"), Decimal("600")),
        )
        reading = _reading(_page(1, _card("ZZTJC2023", dims=(1700, 850, 600))))

        assert match_reading(db, reading).dimension_candidates[0].verdict == AGREES

    def test_different_dimensions_conflict(self, db) -> None:
        # The interesting one. Either the flyer is wrong or the master is, and
        # somebody has to decide which.
        _product(
            db,
            "ZZTJC2023",
            dims=(Decimal("1700"), Decimal("800"), Decimal("600")),
        )
        reading = _reading(_page(1, _card("ZZTJC2023", dims=(1700, 850, 600))))

        candidate = match_reading(db, reading).dimension_candidates[0]

        assert candidate.verdict == CONFLICTS
        assert candidate.current_width_mm == Decimal("800")
        assert candidate.printed_width_mm == Decimal("850")

    def test_a_half_filled_product_conflicts_rather_than_agrees(self, db) -> None:
        # Two of three matching is not agreement, and calling it "missing" would
        # let a partial row be overwritten without anybody looking at it.
        _product(db, "ZZTJC2023", dims=(Decimal("1700"), None, None))
        reading = _reading(_page(1, _card("ZZTJC2023", dims=(1700, 850, 600))))

        assert match_reading(db, reading).dimension_candidates[0].verdict == CONFLICTS

    def test_a_card_with_no_dimensions_is_not_a_candidate(self, db) -> None:
        _product(db, "ZZTJC2023")

        assert match_reading(db, _printed("ZZTJC2023")).dimension_candidates == []

    def test_an_unmatched_code_is_not_a_candidate(self, db) -> None:
        # There is nothing to review it against, and the code is already
        # reported as a match gap.
        reading = _reading(_page(1, _card("ZZTNOSUCH1", dims=(1700, 850, 600))))

        assert match_reading(db, reading).dimension_candidates == []

    def test_nothing_is_written_to_the_product(self, db) -> None:
        # AC-D4. The seed never touches the master; a dimension is applied only
        # by someone with the master-data permission clicking on it.
        product = _product(db, "ZZTJC2023")
        reading = _reading(_page(1, _card("ZZTJC2023", dims=(1700, 850, 600))))

        match_reading(db, reading)
        db.expire_all()
        fresh = db.query(Product).filter(Product.id == product.id).one()

        assert fresh.dimensions_length is None
        assert fresh.dimensions_width is None
        assert fresh.dimensions_height is None

    def test_every_measurement_is_a_decimal(self, db) -> None:
        # A float millimetre reaching the master is a dimension that will not
        # compare equal to the one beside it.
        _product(db, "ZZTJC2023", dims=(Decimal("1700"), Decimal("850"), Decimal("600")))
        reading = _reading(_page(1, _card("ZZTJC2023", dims=(1700, 850, 600))))

        candidate = match_reading(db, reading).dimension_candidates[0]

        for figure in (
            candidate.printed_length_mm,
            candidate.printed_width_mm,
            candidate.printed_height_mm,
            candidate.current_length_mm,
            candidate.current_width_mm,
            candidate.current_height_mm,
        ):
            assert isinstance(figure, Decimal), f"{figure!r} is {type(figure)}, not Decimal"


class TestACodePrintedOnTwoPages:
    """One product, one entry, every page kept."""

    def test_it_is_one_matched_entry(self, db) -> None:
        _product(db, "ZZTWC8100")
        reading = _reading(_page(1, _card("ZZTWC8100")), _page(7, _card("ZZTWC8100")))

        report = match_reading(db, reading)

        assert [entry.code for entry in report.matched] == ["ZZTWC8100"]

    def test_every_page_it_appeared_on_is_kept(self, db) -> None:
        # A reviewer checking the report is holding the flyer. "It is wrong
        # somewhere" is not a correction anybody can make.
        _product(db, "ZZTWC8100")
        reading = _reading(_page(1, _card("ZZTWC8100")), _page(7, _card("ZZTWC8100")))

        assert match_reading(db, reading).matched[0].pages == (1, 7)

    def test_the_duplicates_are_named(self, db) -> None:
        _product(db, "ZZTWC8100")
        _product(db, "ZZTWC8200")
        reading = _reading(
            _page(1, _card("ZZTWC8100"), _card("ZZTWC8200", x=10.0)),
            _page(7, _card("ZZTWC8100")),
        )

        assert match_reading(db, reading).duplicates == {"ZZTWC8100": (1, 7)}

    def test_an_unmatched_code_printed_twice_is_reported_once(self, db) -> None:
        reading = _reading(_page(1, _card("ZZTNOSUCH1")), _page(7, _card("ZZTNOSUCH1")))

        report = match_reading(db, reading)

        assert [entry.code for entry in report.unmatched] == ["ZZTNOSUCH1"]
        assert report.unmatched[0].pages == (1, 7)

    def test_a_promotion_gap_is_reported_once_however_often_it_is_printed(self, db) -> None:
        _product(db, "ZZTWC8100")
        promotion_id = _promotion(db)
        reading = _reading(_page(1, _card("ZZTWC8100")), _page(7, _card("ZZTWC8100")))

        report = match_reading(db, reading, promotion_id=promotion_id)

        assert [entry.code for entry in report.not_promoted] == ["ZZTWC8100"]

    def test_the_first_card_carrying_dimensions_is_the_candidate(self, db) -> None:
        # One candidate per product, because there is one product to correct.
        _product(db, "ZZTJC2023")
        reading = _reading(
            _page(1, _card("ZZTJC2023")),
            _page(7, _card("ZZTJC2023", dims=(1700, 850, 600))),
        )

        candidates = match_reading(db, reading).dimension_candidates

        assert len(candidates) == 1
        assert candidates[0].printed_length_mm == Decimal("1700")
        assert candidates[0].pages == (1, 7)


class TestOneQueryForTheWholeReading:
    """Rule: the work does not grow with the number of codes printed."""

    def _reading_of(self, db, size: int, *, missing: int = 0, first: int = 9000):
        codes = []
        for index in range(size):
            code = f"ZZTWC{first + index}"
            _product(db, code)
            codes.append(code)
        codes.extend(f"ZZTNO{first + index}" for index in range(missing))
        db.flush()
        return _printed(*codes)

    def test_a_bigger_reading_is_not_more_queries(self, db) -> None:
        small = self._reading_of(db, 2, missing=1)
        large = self._reading_of(db, 20, missing=10, first=9500)

        with _selects(db) as for_small:
            match_reading(db, small)
        with _selects(db) as for_large:
            report = match_reading(db, large)

        assert len(report.matched) == 20
        assert len(report.unmatched) == 10
        assert len(for_large) == len(for_small), (
            f"{len(for_small)} statement(s) for 3 codes but {len(for_large)} for 30 - "
            "the matcher is looking codes up one at a time"
        )

    def test_it_is_three_queries_at_most(self, db) -> None:
        # Products, suggestions for whatever missed, and the promotion. Nothing
        # per code, per page or per card.
        reading = self._reading_of(db, 20, missing=10)
        promotion_id = _promotion(db)

        with _selects(db) as statements:
            match_reading(db, reading, promotion_id=promotion_id)

        assert len(statements) <= 3, statements

    def test_a_reading_that_all_matched_asks_for_no_suggestions(self, db) -> None:
        reading = self._reading_of(db, 20)

        with _selects(db) as statements:
            match_reading(db, reading)

        assert len(statements) == 1, statements


class TestAgainstTheRealFlyer:
    """Extraction and matching, end to end, on three pages of the real document.

    The two halves are built and tested separately on purpose, so this is the
    test that proves they fit: a reading straight out of ``extract_flyer`` is
    exactly what the matcher consumes, with nothing adapting between them.
    """

    @pytest.fixture(scope="class")
    def reading(self) -> FlyerReading:
        return extract_flyer(FIXTURE_PDF.read_bytes())

    def test_the_codes_the_master_has_are_matched(self, db, reading) -> None:
        printed = _product(db, "SRTWC286-SH")

        report = match_reading(db, reading)

        assert _by_code(report.matched)["SRTWC286-SH"].product_id == printed.id

    def test_the_rest_are_reported_rather_than_lost(self, db, reading) -> None:
        _product(db, "SRTWC286-SH")

        report = match_reading(db, reading)

        assert len(report.matched) == 1
        assert len(report.unmatched) == len(reading.codes) - 1

    def test_the_gift_code_printed_on_two_pages_is_one_entry(self, db, reading) -> None:
        # FG-CW06 and FG-CW13 are printed on both the cover and the bathtub
        # spread. Real duplicates, not contrived ones.
        report = match_reading(db, reading)

        assert report.duplicates["FG-CW06"] == (1, 2)
        assert report.duplicates["FG-CW13"] == (1, 2)

    def test_a_printed_size_disagreeing_with_the_master_is_flagged(self, db, reading) -> None:
        # The flyer prints SRTJC2023 at L1700 x W850 x H600.
        _product(
            db, "SRTJC2023", dims=(Decimal("1700"), Decimal("800"), Decimal("600"))
        )

        candidate = match_reading(db, reading).dimension_candidates[0]

        assert candidate.code == "SRTJC2023"
        assert candidate.verdict == CONFLICTS
        assert candidate.printed_width_mm == Decimal("850")
        assert candidate.current_width_mm == Decimal("800")

    def test_the_promotion_gap_is_the_matched_products_it_does_not_carry(
        self, db, reading
    ) -> None:
        printed = _product(db, "SRTWC286-SH")
        promotion_id = _promotion(db)

        report = match_reading(db, reading, promotion_id=promotion_id)

        assert [entry.product_id for entry in report.not_promoted] == [printed.id]

    def test_the_whole_flyer_is_still_a_handful_of_queries(self, db, reading) -> None:
        _product(db, "SRTWC286-SH")
        promotion_id = _promotion(db)

        with _selects(db) as statements:
            match_reading(db, reading, promotion_id=promotion_id)

        assert len(statements) <= 3, statements


def report_of(db, *codes: str):
    return match_reading(db, _printed(*codes))
