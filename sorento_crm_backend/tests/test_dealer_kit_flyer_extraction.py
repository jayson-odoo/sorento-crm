"""Reading a printed flyer well enough to seed a catalogue from it.

Written before the extractor, against three pages cut from the REAL 2025-2026
A3 flyer (``tests/fixtures/dealer_kit/flyer_sample.pdf``) rather than a
synthetic PDF. A synthetic fixture would only ever prove that the extractor
reads PDFs somebody wrote to be read; what has to hold is that it reads the
document Sorento's designer actually produced, with its overlapping artwork,
its wall of small print, and its two-products-one-photo cards.

The fixture's images are thumbnailed to almost nothing on purpose. The
extractor reads image PLACEMENT and never image content, so the pixels are
weight the repository does not need to carry.

Nothing here touches a database. Extraction is pure: bytes in, a reading out.
Matching codes to products is the NEXT slice, and keeping the two apart is what
makes this one exhaustively testable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.dealer_kit.flyer_extraction import (
    FlyerReading,
    extract_flyer,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# Page 2 of the fixture is page 3 of the flyer: the water closet spread. Dense,
# two grid rows, and a bottom band of specification small print.
WATER_CLOSET_PAGE = 2


@pytest.fixture(scope="module")
def reading() -> FlyerReading:
    return extract_flyer(FIXTURE.read_bytes())


class TestPages:
    def test_reads_every_page(self, reading: FlyerReading) -> None:
        assert len(reading.pages) == 3

    def test_keeps_the_page_numbers_a_human_would_use(self, reading: FlyerReading) -> None:
        # One-based. A designer looking at the review screen is holding the
        # printed flyer, where the first page is page 1.
        assert [page.number for page in reading.pages] == [1, 2, 3]

    def test_records_the_page_size_so_a_print_profile_can_match_it(
        self, reading: FlyerReading
    ) -> None:
        page = reading.pages[0]
        # A3 portrait, in points.
        assert round(page.width) == 842
        assert round(page.height) == 1191
        assert page.orientation == "portrait"


class TestCards:
    def test_finds_the_product_codes(self, reading: FlyerReading) -> None:
        codes = {card.code for card in reading.pages[WATER_CLOSET_PAGE].cards}

        # Every one of these is on the printed page.
        assert {"SRTWC286-SH", "SRTSCBD702", "SRTSCBD701", "SRTSCBD291"} <= codes

    def test_does_not_invent_cards_out_of_body_text(self, reading: FlyerReading) -> None:
        page = reading.pages[WATER_CLOSET_PAGE]

        # The page carries far more text than products. A card is a code, and
        # only a code: "S-Trap: Bottom Outlet" is a specification line, not a SKU.
        assert 10 <= len(page.cards) <= 40

    def test_a_card_carries_the_lines_printed_under_its_code(
        self, reading: FlyerReading
    ) -> None:
        card = _card(reading, "SRTWC286-SH")

        blob = " ".join(card.lines)
        assert "LP: RM 1,260" in blob
        assert "L680xW365xH735mm" in blob.replace(" ", "")

    def test_reads_the_dimensions_a_product_may_be_missing(
        self, reading: FlyerReading
    ) -> None:
        # The reason this slice matters beyond layout: only 3,331 of 22,805
        # products have length and height, and a product without them is drawn
        # as a placeholder box in the room designer.
        card = _card(reading, "SRTWC286-SH")

        assert card.length_mm == 680
        assert card.width_mm == 365
        assert card.height_mm == 735

    def test_leaves_dimensions_unset_when_the_flyer_does_not_print_them(
        self, reading: FlyerReading
    ) -> None:
        without = [card for card in _all_cards(reading) if card.length_mm is None]

        # Plenty of cards carry no size at all. Guessing one would put a
        # measurement nobody chose into the product master.
        assert without
        assert all(card.width_mm is None and card.height_mm is None for card in without)

    def test_reads_both_the_list_price_and_the_offer_price(
        self, reading: FlyerReading
    ) -> None:
        card = _card(reading, "SRTSCBD702")

        assert card.list_price == pytest.approx(442)
        assert card.offer_price == pytest.approx(299)

    def test_reading_a_price_is_lossy_and_the_promotion_is_the_truth(
        self, reading: FlyerReading
    ) -> None:
        # SRTWC286-SH prints "SP RM 599" on page 4, but the figure sits outside
        # the card's column band, so this module reads "SP", "RM" and no number.
        # Pinned as a test because it is the evidence for a decision: a brochure
        # takes its offer price from the promotion it is linked to, and a
        # difference between print and promotion is far more likely to be one of
        # these misses than a real discrepancy.
        card = _card(reading, "SRTWC286-SH")

        assert card.list_price == pytest.approx(1260)
        assert card.offer_price is None
        assert "SP" in card.lines

    def test_a_reading_is_never_a_document(self, reading: FlyerReading) -> None:
        # A price baked into a page document freezes one number for every
        # audience.
        assert not hasattr(reading, "doc")
        assert not hasattr(reading.pages[0], "doc")

    def test_a_card_knows_where_it_sat_on_the_page(self, reading: FlyerReading) -> None:
        card = _card(reading, "SRTWC286-SH")

        assert 0 <= card.x < 842
        assert 0 <= card.y < 1191


class TestGrids:
    def test_groups_cards_into_the_rows_they_were_printed_in(
        self, reading: FlyerReading
    ) -> None:
        page = reading.pages[WATER_CLOSET_PAGE]

        # The spread is laid out as bands of products, and each band becomes one
        # collection block. One grid holding every card on the page would seed a
        # single undifferentiated wall.
        assert len(page.grids) >= 2

    def test_a_grid_keeps_the_left_to_right_order_of_the_paper(
        self, reading: FlyerReading
    ) -> None:
        for grid in reading.pages[WATER_CLOSET_PAGE].grids:
            xs = [card.x for card in grid.cards]
            assert xs == sorted(xs)

    def test_every_card_belongs_to_exactly_one_grid(self, reading: FlyerReading) -> None:
        page = reading.pages[WATER_CLOSET_PAGE]

        gridded = [card.code for grid in page.grids for card in grid.cards]
        assert sorted(gridded) == sorted(card.code for card in page.cards)
        assert len(gridded) == len(set(gridded))

    def test_a_grid_reports_how_many_across_it_was_printed(
        self, reading: FlyerReading
    ) -> None:
        for grid in reading.pages[WATER_CLOSET_PAGE].grids:
            assert grid.columns == len(grid.cards)
            assert grid.columns >= 1


class TestHeadings:
    def test_reads_the_section_title(self, reading: FlyerReading) -> None:
        page = reading.pages[WATER_CLOSET_PAGE]

        assert page.heading is not None
        assert "WATER CLOSET" in page.heading.upper()

    def test_a_heading_is_not_also_a_card_line(self, reading: FlyerReading) -> None:
        page = reading.pages[WATER_CLOSET_PAGE]

        for card in page.cards:
            assert page.heading not in card.lines


class TestArtwork:
    def test_notices_the_full_width_artwork(self, reading: FlyerReading) -> None:
        # The banner across the top of the spread. Not a product photo, and the
        # thing a seeded section looks bare without.
        page = reading.pages[WATER_CLOSET_PAGE]

        assert any(art.width_pct > 0.8 for art in page.artwork)

    def test_does_not_report_product_photos_as_artwork(
        self, reading: FlyerReading
    ) -> None:
        page = reading.pages[WATER_CLOSET_PAGE]

        # A picture sitting directly above a code is that product's photo, and
        # it comes from the product master at render time, not from the PDF.
        for art in page.artwork:
            assert art.width_pct > 0.25


class TestCodes:
    def test_collects_every_distinct_code_in_the_document(
        self, reading: FlyerReading
    ) -> None:
        assert len(reading.codes) == len({card.code for card in _all_cards(reading)})
        assert "SRTWC286-SH" in reading.codes

    def test_a_code_appearing_twice_is_one_entry(self, reading: FlyerReading) -> None:
        assert len(reading.codes) == len(set(reading.codes))

    def test_reads_a_code_the_typesetter_punctuated(self, reading: FlyerReading) -> None:
        # The cover sets the gift codes as "FG-CW13:" because a description
        # follows. The colon belongs to the sentence, not to the SKU, and a card
        # lost to a punctuation mark is a product missing from the catalogue.
        assert "FG-CW13" in reading.codes
        assert not any(code.endswith(":") for code in reading.codes)


class TestRobustness:
    def test_refuses_something_that_is_not_a_pdf(self) -> None:
        with pytest.raises(ValueError):
            extract_flyer(b"this is not a pdf")

    def test_survives_a_pdf_with_no_products_in_it(self, reading: FlyerReading) -> None:
        # The cover. Codes but no priced grid, and an extractor that only works
        # on the dense pages is one that falls over on page 1 of every flyer.
        cover = reading.pages[0]

        assert cover.number == 1
        assert isinstance(cover.cards, list)
        assert isinstance(cover.grids, list)


def _all_cards(reading: FlyerReading):
    return [card for page in reading.pages for card in page.cards]


def _card(reading: FlyerReading, code: str):
    for card in _all_cards(reading):
        if card.code == code:
            return card
    raise AssertionError(f"{code} was not read from the flyer")
