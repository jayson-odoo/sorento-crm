"""Reading a flyer page's ARTWORK, so a seeded section looks like the paper (S7.5, group F).

Written before the extractor changes. Nothing here touches a database: reading a
page's art is as pure as reading its cards, and keeping it that way is what lets
these assertions run against the real document rather than a mock of it.

Three of the four group F criteria live here, because all three are decided by
the extractor:

* **AC-F1** a CMYK JPEG banner comes out RGB. Browsers do not render CMYK JPEG
  reliably and Meta rejects it outright, which is the same defect that broke
  WhatsApp media. The real flyer's banners are DeviceCMYK - 15 of 15 measured -
  so this is the normal case, not an edge one.
* **AC-F2** artwork extending past the page box is cropped to the page. Flyer
  page 4 places one image at 1.17x the page width anchored 662pt ABOVE the top
  edge; taken whole it is a different picture from the one that was printed.
* **AC-F4** a picture sitting directly above a product code is that product's
  photo, not artwork. This is the one most likely to go wrong and the most
  expensive when it does: it fills the asset library with product shots and puts
  a bath tub behind a section heading. The composited photo sheet on fixture
  page 3 IS a picture of bath fittings, and it is exactly the image the naive
  rule would choose as that page's background.

AC-F3 is the frontend's (the banner is the section BACKGROUND and the heading is
a text block over it); the backend half - that the seed binds one and keeps the
other a block - is in ``test_dealer_kit_flyer_artwork_assets.py`` along with the
storage chain.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from app.services.dealer_kit.flyer_extraction import FlyerReading, extract_flyer
from app.services.image_normalizer import needs_rgb_conversion

from tests._flyer_pdf import (
    A3_HEIGHT_PT,
    A3_WIDTH_PT,
    BANNER_RECT,
    OVERSIZED_RECT,
    cmyk_jpeg,
    flyer_pdf,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# Fixture page 1 is the flyer's cover: one image the size of the whole page, with
# every product printed OVER it. Index 0.
COVER_PAGE = 0
# Fixture page 2 is the bathtub spread. Its header band is typeset as a vector
# rectangle rather than an image, so this page has no banner at all - which the
# hand-verified golden already records as `full_width_band: false`.
BATHTUB_PAGE = 1
# Fixture page 3 is the water closet spread: a real image band across the top, a
# composited sheet of product photos placed 1.17x page width at y=-662, and three
# wide card panels each carrying a code.
WATER_CLOSET_PAGE = 2

# The composited product-photo sheet on fixture page 3. Named because it is the
# picture a naive banner rule chooses, and it is a photograph of toilets.
PHOTO_SHEET_XREF = 168
# The marble band across the top of the same page: the real banner.
BAND_XREFS = {126, 127}
# A header element on the same page, set from x=478 to x=932 on an 842pt sheet
# and from y=-36: it bleeds off two edges at once.
RIGHT_BLEED_XREF = 128


@pytest.fixture(scope="module")
def reading() -> FlyerReading:
    return extract_flyer(FIXTURE.read_bytes())


@pytest.fixture(scope="module")
def reading_with_images() -> FlyerReading:
    return extract_flyer(FIXTURE.read_bytes(), with_artwork_images=True)


def _boxes(page) -> list[tuple[float, float, float, float]]:
    """Each artwork as (left, top, right, bottom) in page fractions."""
    return [
        (art.x_pct, art.y_pct, art.x_pct + art.width_pct, art.y_pct + art.height_pct)
        for art in page.artwork
    ]


def _covers_the_whole_page(box) -> bool:
    left, top, right, bottom = box
    return left <= 0.02 and top <= 0.02 and right >= 0.98 and bottom >= 0.98


def _near(left: tuple[int, int, int], right: tuple[int, int, int]) -> bool:
    """Same colour, allowing for JPEG. Two flat fills survive a round trip easily."""
    return all(abs(a - b) <= 12 for a, b in zip(left, right))


# --------------------------------------------------------------------------- #
# AC-F4 - a product's photo is not the page's artwork
# --------------------------------------------------------------------------- #
class TestProductPhotosAreNotArtwork:
    def test_a_picture_directly_above_a_product_code_is_not_artwork(self) -> None:
        """The plainest case, stated on its own so a failure names the rule.

        A picture 0.4 of the page wide with a SKU printed 12pt beneath it is a
        product photo. It clears the width filter easily, which is precisely why
        width alone was never enough.
        """
        data = flyer_pdf(
            image=cmyk_jpeg(600, 300),
            image_size=(600, 300),
            rect=(100.0, 200.0, 440.0, 500.0),
            codes=[("SRTZZ0001", 120.0, 512.0)],
        )

        page = extract_flyer(data).pages[0]

        assert [card.code for card in page.cards] == ["SRTZZ0001"]
        assert page.artwork == []

    def test_a_picture_with_a_code_printed_on_it_is_not_artwork(self) -> None:
        """Fixture page 3 sets three codes directly onto their card panels.

        The panel is 0.28 of the page wide and the code sits inside it, so
        "directly above" has to mean "belongs to", not "is vertically adjacent
        to". Stated synthetically as well as against the fixture because the
        fixture case only exists at one width.
        """
        data = flyer_pdf(
            image=cmyk_jpeg(600, 300),
            image_size=(600, 300),
            rect=(100.0, 200.0, 440.0, 500.0),
            codes=[("SRTZZ0002", 140.0, 420.0)],
        )

        assert extract_flyer(data).pages[0].artwork == []

    def test_the_one_photo_two_products_are_printed_under_is_not_artwork(
        self, reading: FlyerReading
    ) -> None:
        """The pattern the real flyer actually has, and the hardest one.

        Fixture page 3 places one 0.53-page-wide panel across a pair of cards -
        the same image, three times, once per pair. It is well over the width
        filter, it is not a small square, and it looks exactly like a design
        element until you notice a SKU sitting on it. The extractor must not
        decide which of the two products owns the picture; it must decline to
        call the picture artwork at all.
        """
        page = reading.pages[WATER_CLOSET_PAGE]

        wide_panels = [
            art
            for art in page.artwork
            if 0.4 <= art.width_pct <= 0.7 and 0.30 <= art.y_pct <= 0.35
        ]
        assert wide_panels == []

    def test_no_artwork_carries_a_printed_code_unless_it_is_the_whole_page(
        self, reading: FlyerReading
    ) -> None:
        """The general form, checked on every page of the real document.

        A full-bleed page background is exempt and has to be: the cover is one
        image the size of the paper with every product printed over it, so
        "contains a code" would throw away the one piece of art on the page.
        Nothing else may hold a code.
        """
        for page in reading.pages:
            for art, box in zip(page.artwork, _boxes(page)):
                if _covers_the_whole_page(box):
                    continue
                left, top, right, bottom = box
                inside = [
                    card.code
                    for card in page.cards
                    if left <= card.x / page.width <= right
                    and top <= card.y / page.height <= bottom
                ]
                assert inside == [], (
                    f"page {page.number}: artwork xref={art.xref} at {box} "
                    f"carries printed codes {inside}"
                )

    def test_a_full_bleed_page_background_is_still_artwork(
        self, reading: FlyerReading
    ) -> None:
        """The cover is one image the size of the page. It IS the page's design."""
        page = reading.pages[COVER_PAGE]

        assert any(_covers_the_whole_page(box) for box in _boxes(page))

    def test_the_photo_sheet_never_becomes_the_banner(
        self, reading_with_images: FlyerReading
    ) -> None:
        """The failure this criterion exists to prevent, named outright.

        Fixture page 3 carries a composited sheet of toilet photographs placed
        1.17x the page width. Cropped to the page it is full width and starts at
        the very top, so on geometry alone it beats the real band. Choosing it
        puts a bath fitting behind the section heading.
        """
        page = reading_with_images.pages[WATER_CLOSET_PAGE]

        assert page.banner is not None
        assert page.banner.artwork.xref != PHOTO_SHEET_XREF
        assert page.banner.artwork.xref in BAND_XREFS


# --------------------------------------------------------------------------- #
# AC-F2 - cropped to the page box
# --------------------------------------------------------------------------- #
class TestCroppedToThePage:
    def test_no_artwork_reaches_past_the_page_edges(self, reading: FlyerReading) -> None:
        for page in reading.pages:
            for art, box in zip(page.artwork, _boxes(page)):
                left, top, right, bottom = box
                assert left >= 0.0, f"page {page.number} xref={art.xref} starts off-page"
                assert top >= 0.0, f"page {page.number} xref={art.xref} starts above the page"
                assert right <= 1.0 + 1e-6, f"page {page.number} xref={art.xref} runs off the right"
                assert bottom <= 1.0 + 1e-6, f"page {page.number} xref={art.xref} runs off the foot"

    def test_a_real_bleeding_element_is_reported_at_the_page_edge(
        self, reading: FlyerReading
    ) -> None:
        """Fixture page 3 sets one header element from x=478 to x=932 on an 842pt page.

        Reported whole it is 0.539 of the page wide and 90pt of it does not
        exist. Cropped it stops exactly at the edge, which is what a section
        background has to do.
        """
        page = reading.pages[WATER_CLOSET_PAGE]

        art = next(
            (art for art in page.artwork if art.xref == RIGHT_BLEED_XREF), None
        )
        assert art is not None, "the header element that runs off the right edge was dropped"

        assert art.x_pct + art.width_pct == pytest.approx(1.0, abs=1e-6)
        assert art.y_pct == pytest.approx(0.0, abs=1e-6)
        # It is placed 0.539 of the page wide; only 0.432 of it was printed.
        assert art.width_pct == pytest.approx(0.432, abs=0.005)

    def test_the_stored_banner_is_only_the_part_that_was_printed(self) -> None:
        """The 1.17x-at-y=-662 case, with the pixels checked rather than the box.

        The source is cyan on top and magenta below. Only its bottom 52% falls
        on the page, so a quarter of the way down the STORED banner must be
        magenta - a quarter of the way down the whole image is cyan. That is the
        difference between the background a reader saw on paper and a picture
        nobody has ever seen.
        """
        from PIL import Image

        source_high = 2000
        source = cmyk_jpeg(2050, source_high, split=True)
        data = flyer_pdf(
            image=source,
            image_size=(2050, source_high),
            rect=OVERSIZED_RECT,
        )

        page = extract_flyer(data, with_artwork_images=True).pages[0]
        assert page.banner is not None

        _left, top, _right, bottom = OVERSIZED_RECT
        visible_top_fraction = (0.0 - top) / (bottom - top)
        expected_high = round(source_high * (1.0 - visible_top_fraction))

        stored = Image.open(io.BytesIO(page.banner.image)).convert("RGB")
        assert stored.height == pytest.approx(expected_high, abs=2)

        # Read the two halves off the SOURCE rather than naming colours, so the
        # assertion survives whatever a CMYK JPEG round trip does to them.
        original = Image.open(io.BytesIO(source)).convert("RGB")
        upper = original.getpixel((original.width // 2, original.height // 4))
        lower = original.getpixel((original.width // 2, source_high - 100))
        assert upper != lower, "the fixture image does not actually have two halves"

        quarter = stored.getpixel((stored.width // 2, stored.height // 4))
        assert _near(quarter, lower)
        assert not _near(quarter, upper), "the banner still carries the half nobody printed"

    def test_the_geometry_of_a_cropped_banner_is_the_visible_rectangle(self) -> None:
        data = flyer_pdf(
            image=cmyk_jpeg(2050, 2000),
            image_size=(2050, 2000),
            rect=OVERSIZED_RECT,
        )

        page = extract_flyer(data).pages[0]
        assert len(page.artwork) == 1
        art = page.artwork[0]

        assert art.x_pct == pytest.approx(0.0)
        assert art.y_pct == pytest.approx(0.0)
        assert art.width_pct == pytest.approx(1.0)
        assert art.height_pct == pytest.approx(OVERSIZED_RECT[3] / A3_HEIGHT_PT, abs=1e-3)


# --------------------------------------------------------------------------- #
# AC-F1 - CMYK comes out RGB
# --------------------------------------------------------------------------- #
class TestColourSpace:
    def test_a_cmyk_banner_is_converted_before_it_is_handed_over(self) -> None:
        """The source really is the defect, and what comes back really is not.

        Both halves are asserted on purpose. A test that only checked the output
        would pass just as happily against a fixture that was never CMYK, which
        is how a conversion quietly stops running.
        """
        from PIL import Image

        source = cmyk_jpeg(1755, 445)
        assert needs_rgb_conversion(source, "image/jpeg") is True

        data = flyer_pdf(image=source, image_size=(1755, 445), rect=BANNER_RECT)
        page = extract_flyer(data, with_artwork_images=True).pages[0]

        assert page.banner is not None
        assert Image.open(io.BytesIO(page.banner.image)).mode == "RGB"
        assert needs_rgb_conversion(page.banner.image, page.banner.mime) is False

    @pytest.mark.skipif(
        not os.getenv("FLYER_FIXTURE_PDF"),
        reason="the whole 36 page flyer is 20MB and does not belong in the repository",
    )
    def test_every_banner_in_the_real_flyer_comes_out_rgb(self) -> None:
        """The document this feature exists for, when somebody has it to hand."""
        from PIL import Image

        data = Path(os.environ["FLYER_FIXTURE_PDF"]).read_bytes()
        reading = extract_flyer(data, with_artwork_images=True)

        banners = [page.banner for page in reading.pages if page.banner]
        assert banners, "the real flyer has header bands on most of its pages"
        for banner in banners:
            assert Image.open(io.BytesIO(banner.image)).mode == "RGB"


# --------------------------------------------------------------------------- #
# Which piece of art becomes the background
# --------------------------------------------------------------------------- #
class TestBannerChoice:
    def test_the_band_across_the_top_is_the_banner(
        self, reading_with_images: FlyerReading
    ) -> None:
        page = reading_with_images.pages[WATER_CLOSET_PAGE]

        assert page.banner is not None
        assert page.banner.artwork.width_pct >= 0.8
        assert page.banner.artwork.y_pct == pytest.approx(0.0, abs=0.02)
        # A band, so it is laid across the top at its own proportions rather than
        # zoomed to fill a section whose height comes from its content.
        assert page.banner.fit == "width"

    def test_a_full_page_background_is_laid_out_to_cover(
        self, reading_with_images: FlyerReading
    ) -> None:
        page = reading_with_images.pages[COVER_PAGE]

        assert page.banner is not None
        assert page.banner.fit == "cover"

    def test_a_page_whose_header_is_typeset_rather_than_placed_has_no_banner(
        self, reading_with_images: FlyerReading
    ) -> None:
        """Fixture page 2's header band is a vector rectangle, not an image.

        The hand-verified golden records it as having no full-width band, so a
        banner here would be this module inventing one - and the section keeps
        its plain background, which is the honest answer.
        """
        assert reading_with_images.pages[BATHTUB_PAGE].banner is None

    def test_a_banner_is_never_an_image_this_system_cannot_read_back(
        self, reading_with_images: FlyerReading
    ) -> None:
        """Fixture page 3 has a 0.80-wide top element PyMuPDF reports as xref 0.

        An xref of 0 means the placement could not be resolved to a stored
        image, so there are no bytes to put in the asset library. Choosing it
        would bind a section to a background that can never load.
        """
        page = reading_with_images.pages[WATER_CLOSET_PAGE]

        assert page.banner is not None
        assert page.banner.artwork.xref != 0
        assert page.banner.image

    def test_extraction_without_images_stays_free_of_them(
        self, reading: FlyerReading
    ) -> None:
        """The default reads geometry only.

        Decoding every banner costs real time on a 36 page flyer, and the match
        report - which is recomputed on every read of a reading - needs none of
        it. Only the upload asks for the bytes.
        """
        assert all(page.banner is None for page in reading.pages)
        assert reading.pages[WATER_CLOSET_PAGE].artwork


# --------------------------------------------------------------------------- #
# What the seeded page will be laid out against
# --------------------------------------------------------------------------- #
class TestPaperGeometry:
    def test_the_synthetic_pages_measure_a3(self) -> None:
        """Guards the helper itself: a wrong page size would move every fraction."""
        data = flyer_pdf(image=cmyk_jpeg(100, 100), image_size=(100, 100), rect=BANNER_RECT)
        page = extract_flyer(data).pages[0]

        assert page.width == pytest.approx(A3_WIDTH_PT)
        assert page.height == pytest.approx(A3_HEIGHT_PT)
