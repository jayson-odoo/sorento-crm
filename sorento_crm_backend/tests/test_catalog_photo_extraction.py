"""Reading product photos and their captions out of a supplier catalogue PDF.

Written before the module exists (CATALOG-IMAGES, Phase 2, red). Contract:
``documentation/plans/products/PLAN-catalog-image-extract-27oct.md``, section
"Phase 2 contract, answer-independent part", rules R1 (photos), R2 (block) and
R4 (placeholders).

Pure: no database. Every fixture PDF is built here with PyMuPDF from generated
images, so no real catalogue is committed.
"""
from __future__ import annotations

import hashlib
import io

import pytest

from app.services.dealer_kit.catalog_photos import CatalogPhoto, extract_catalog_photos
from app.services.dealer_kit.flyer_extraction import EncryptedFlyerError
from tests._flyer_pdf import cmyk_jpeg, flyer_pdf

PAGE_W = 595.0
PAGE_H = 842.0


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #
def _png(color: tuple[int, int, int] = (200, 40, 40), size: tuple[int, int] = (200, 200)) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def _rgba_png(size: tuple[int, int] = (200, 200)) -> bytes:
    from PIL import Image

    image = Image.new("RGBA", size, (10, 120, 200, 255))
    # Punch a transparent corner so the soft mask is real, not all-opaque.
    image.paste((0, 0, 0, 0), (0, 0, size[0] // 2, size[1] // 2))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _pdf(pages: list[dict]) -> bytes:
    """``pages``: list of ``{"images": [(rect, stream)], "texts": [(x, y, text)]}``.

    ``y`` is the text baseline measured from the top, as everywhere in fitz.
    """
    import pymupdf

    doc = pymupdf.open()
    for spec in pages:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        for rect, stream in spec.get("images", []):
            page.insert_image(pymupdf.Rect(*rect), stream=stream, keep_proportion=False)
        for x, y, text in spec.get("texts", []):
            page.insert_text((x, y), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def _one(images, texts=()) -> list[CatalogPhoto]:
    return extract_catalog_photos(_pdf([{"images": images, "texts": list(texts)}]))


def _decode(photo: CatalogPhoto):
    from PIL import Image

    return Image.open(io.BytesIO(photo.image_bytes))


# --------------------------------------------------------------------------- #
# R2 block codes, R4 placeholders
# --------------------------------------------------------------------------- #
class TestBlockCodes:
    def test_multi_code_caption_lists_codes_in_printed_order(self) -> None:
        # E1: cabinet, basin, pop-up waste, then dims / material / price text.
        photos = _one(
            [((50, 100, 250, 300), _png())],
            [
                (50, 320, "SRTBF12613 SRTWB11800 SRTW2600"),
                (50, 332, "900x450x800 Ceramic LP: RM 999"),
            ],
        )

        assert len(photos) == 1
        assert photos[0].block_codes == ["SRTBF12613", "SRTWB11800", "SRTW2600"]
        assert photos[0].primary_code == "SRTBF12613"
        assert photos[0].placeholders == []

    def test_codes_on_separate_caption_lines_keep_printed_order(self) -> None:
        photos = _one(
            [((50, 100, 250, 300), _png())],
            [
                (50, 320, "SRTBF12613 Cabinet"),
                (50, 332, "SRTWB11800 Basin"),
                (50, 344, "SRTW2600 Pop-up waste"),
            ],
        )

        assert photos[0].block_codes == ["SRTBF12613", "SRTWB11800", "SRTW2600"]

    def test_dimensions_material_and_price_text_never_become_codes(self) -> None:
        photos = _one(
            [((50, 100, 250, 300), _png())],
            [(50, 320, "SRTBF12613 600x450x800 Ceramic LP: RM 999 MDF18 ABC12")],
        )

        assert photos[0].block_codes == ["SRTBF12613"]

    def test_trailing_punctuation_is_stripped_from_a_code(self) -> None:
        photos = _one(
            [((50, 100, 250, 300), _png())],
            [(50, 320, "SRTBF12613, SRTW5112-MW;")],
        )

        assert photos[0].block_codes == ["SRTBF12613", "SRTW5112-MW"]

    @pytest.mark.parametrize(
        "code", ["SRT73-WH-DIY", "SRT-FH12-CP", "SRTWT1906-BL-DIY"]
    )
    def test_hyphenated_diy_codes_are_block_codes(self, code: str) -> None:
        photos = _one([((50, 100, 250, 300), _png())], [(50, 320, code)])

        assert photos[0].block_codes == [code]

    def test_non_code_words_stay_out_beside_a_hyphenated_code(self) -> None:
        photos = _one(
            [((50, 100, 250, 300), _png())],
            [(50, 320, "SRT73-WH-DIY MDF18 ABC12 SUS-STEEL 900x450x800 LP: RM 999")],
        )

        assert photos[0].block_codes == ["SRT73-WH-DIY"]

    def test_a_code_wrapped_onto_a_hyphen_led_line_is_joined(self) -> None:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_image(pymupdf.Rect(50, 100, 250, 300), stream=_png())
        page.insert_text((50, 320), "SRTKT1931SS\n-BL-DIY", fontsize=9)
        data = doc.tobytes()
        doc.close()

        photos = extract_catalog_photos(data)

        assert photos[0].block_codes == ["SRTKT1931SS-BL-DIY"]

    def test_a_row_one_photo_takes_its_hyphenated_caption_not_the_next_rows(self) -> None:
        photos = _one(
            [
                ((50, 100, 250, 250), _png((200, 0, 0))),
                ((50, 330, 250, 480), _png((0, 0, 200))),
            ],
            [(50, 270, "SRT73-WH-DIY"), (50, 500, "SRT-FH12-CP")],
        )

        assert [p.block_codes for p in photos] == [["SRT73-WH-DIY"], ["SRT-FH12-CP"]]

    def test_a_placeholder_is_listed_apart_and_never_a_block_code(self) -> None:
        # E2
        photos = _one(
            [((50, 100, 250, 300), _png())],
            [(50, 320, "SRTBF12613 SRTWB_____ SRTW2600")],
        )

        assert photos[0].placeholders == ["SRTWB_____"]
        assert photos[0].block_codes == ["SRTBF12613", "SRTW2600"]
        assert "SRTWB_____" not in photos[0].block_codes

    def test_a_photo_with_no_caption_is_still_returned(self) -> None:
        photos = _one([((50, 100, 250, 300), _png())])

        assert len(photos) == 1
        assert photos[0].block_codes == []
        assert photos[0].placeholders == []
        assert photos[0].primary_code is None

    def test_two_photos_above_one_caption_share_its_codes(self) -> None:
        # E4: front view and open view. The caption's x0 (145) sits inside both
        # photos' [x0 - 20, x1] windows.
        photos = _one(
            [
                ((50, 100, 160, 200), _png((200, 0, 0))),
                ((140, 100, 250, 200), _png((0, 0, 200))),
            ],
            [(145, 225, "SRTBF12613 SRTWB11800")],
        )

        assert len(photos) == 2
        assert photos[0].block_codes == ["SRTBF12613", "SRTWB11800"]
        assert photos[1].block_codes == ["SRTBF12613", "SRTWB11800"]


# --------------------------------------------------------------------------- #
# The owner's proximity rule
# --------------------------------------------------------------------------- #
class TestProximityRule:
    def test_each_photo_takes_the_caption_of_its_own_column(self) -> None:
        photos = _one(
            [
                ((50, 100, 200, 250), _png((200, 0, 0))),
                ((300, 100, 450, 250), _png((0, 0, 200))),
            ],
            [(50, 270, "SRTAA1111"), (300, 270, "SRTBB2222")],
        )

        assert [p.primary_code for p in photos] == ["SRTAA1111", "SRTBB2222"]
        assert photos[0].block_codes == ["SRTAA1111"]
        assert photos[1].block_codes == ["SRTBB2222"]

    def test_a_caption_above_the_photo_is_not_taken(self) -> None:
        photos = _one(
            [((50, 300, 250, 450), _png())],
            [(50, 280, "SRTUP9999")],
        )

        assert len(photos) == 1
        assert photos[0].block_codes == []

    def test_the_nearer_of_two_captions_below_wins(self) -> None:
        photos = _one(
            [((50, 100, 250, 250), _png())],
            [(50, 270, "SRTNEAR111"), (50, 400, "SRTFAR2222")],
        )

        assert photos[0].primary_code == "SRTNEAR111"


# --------------------------------------------------------------------------- #
# R1 skips
# --------------------------------------------------------------------------- #
class TestSkips:
    def test_a_30pt_icon_is_skipped(self) -> None:
        photos = _one([((50, 50, 80, 80), _png())])

        assert photos == []

    def test_a_40pt_image_is_kept(self) -> None:
        photos = _one([((50, 50, 90, 90), _png())])

        assert len(photos) == 1

    def test_under_40pt_on_one_side_only_is_skipped(self) -> None:
        photos = _one([((50, 50, 250, 80), _png())])

        assert photos == []

    def test_a_full_page_background_is_skipped(self) -> None:
        photos = _one(
            [
                ((0, 0, PAGE_W, PAGE_H), _png((240, 240, 240))),
                ((50, 100, 250, 300), _png((200, 0, 0))),
            ]
        )

        assert len(photos) == 1
        assert photos[0].rect[2] - photos[0].rect[0] == pytest.approx(200, abs=1)

    def test_a_banner_across_the_top_is_skipped(self) -> None:
        photos = _one(
            [
                ((0, 0, PAGE_W, 120), _png((0, 100, 0), (600, 120))),
                ((50, 200, 250, 400), _png((200, 0, 0))),
            ]
        )

        assert len(photos) == 1
        assert photos[0].rect[1] == pytest.approx(200, abs=1)

    def test_a_wide_image_lower_down_is_not_a_banner(self) -> None:
        # 70% of the page wide: well under the 80% band threshold. (Was 93%
        # before the rule widened to "anywhere on the page", round 2.)
        photos = _one([((90, 400, 90 + 0.7 * PAGE_W, 560), _png((0, 100, 0), (600, 160)))])

        assert len(photos) == 1

    def test_a_band_80_percent_wide_in_the_middle_of_the_page_is_skipped(self) -> None:
        width = 0.8 * PAGE_W
        photos = _one([((50, 400, 50 + width, 560), _png((0, 100, 0), (600, 160)))])

        assert photos == []

    def test_an_image_79_percent_wide_in_the_middle_of_the_page_is_kept(self) -> None:
        width = 0.79 * PAGE_W
        photos = _one([((50, 400, 50 + width, 560), _png((0, 100, 0), (600, 160)))])

        assert len(photos) == 1

    def test_an_inline_image_with_no_xref_is_skipped(self) -> None:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_image(pymupdf.Rect(50, 100, 250, 300), stream=_png())
        # 8x8 RGB inline image, 8 bits, hex encoded, placed 100x100pt.
        hexdata = "FF0000" * 64
        inline = (
            "\nq 100 0 0 100 300 %s cm\n"
            "BI /W 8 /H 8 /CS /RGB /BPC 8 /F /AHx ID %s> EI\nQ\n"
            % (PAGE_H - 300, hexdata)
        )
        page.wrap_contents()
        doc.update_stream(page.get_contents()[0], page.read_contents() + inline.encode())
        data = doc.tobytes()
        doc.close()

        photos = extract_catalog_photos(data)

        # Only the xref image survives; the inline one has no xref to read.
        assert len(photos) == 1
        assert photos[0].rect[0] == pytest.approx(50, abs=1)


class TestPlacements:
    def test_one_image_placed_twice_is_two_photos(self) -> None:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        xref = page.insert_image(pymupdf.Rect(50, 100, 200, 250), stream=_png())
        page.insert_image(pymupdf.Rect(300, 100, 450, 250), xref=xref)
        page.insert_text((50, 270), "SRTAA1111", fontsize=9)
        page.insert_text((300, 270), "SRTBB2222", fontsize=9)
        data = doc.tobytes()
        doc.close()

        photos = extract_catalog_photos(data)

        assert len(photos) == 2
        assert [p.primary_code for p in photos] == ["SRTAA1111", "SRTBB2222"]

    def test_order_is_page_then_top_to_bottom_then_left_to_right(self) -> None:
        data = _pdf(
            [
                {
                    "images": [
                        ((300, 400, 450, 550), _png((1, 1, 1))),
                        ((50, 100, 200, 250), _png((2, 2, 2))),
                        ((300, 100, 450, 250), _png((3, 3, 3))),
                    ]
                },
                {"images": [((50, 100, 200, 250), _png((4, 4, 4)))]},
            ]
        )

        photos = extract_catalog_photos(data)

        assert [(p.page, round(p.rect[1]), round(p.rect[0])) for p in photos] == [
            (1, 100, 50),
            (1, 100, 300),
            (1, 400, 300),
            (2, 100, 50),
        ]

    def test_page_is_one_based(self) -> None:
        photos = _one([((50, 100, 200, 250), _png())])

        assert photos[0].page == 1


# --------------------------------------------------------------------------- #
# Crop and re-encode
# --------------------------------------------------------------------------- #
class TestCropAndEncode:
    def test_an_image_bleeding_past_the_page_edge_comes_back_cropped(self) -> None:
        # 400x200 px placed over x -100..300: 300 of 400 pt is on the page, so
        # about 3/4 of the pixels survive. Top-left of the page is x=0.
        source = _png((10, 200, 10), (400, 200))
        photos = _one([((-100, 100, 300, 300), source)])

        assert len(photos) == 1
        photo = photos[0]
        assert 270 <= photo.width <= 330
        assert photo.width < 400
        assert photo.height == pytest.approx(200, abs=8)
        assert photo.rect[0] == pytest.approx(0, abs=1)
        assert photo.rect[2] == pytest.approx(300, abs=1)

    def test_cmyk_jpeg_comes_back_as_rgb_jpeg_not_the_source_stream(self) -> None:
        source = cmyk_jpeg(200, 200)
        data = flyer_pdf(
            image=source,
            image_size=(200, 200),
            rect=(50, 100, 250, 300),
            codes=[("SRTBF12613", 50, 320)],
            page_size=(PAGE_W, PAGE_H),
        )

        photos = extract_catalog_photos(data)

        assert len(photos) == 1
        photo = photos[0]
        assert photo.mime == "image/jpeg"
        assert _decode(photo).mode == "RGB"
        assert photo.image_bytes != source
        assert photo.block_codes == ["SRTBF12613"]

    def test_a_source_with_a_soft_mask_is_stored_as_png(self) -> None:
        photos = _one([((50, 100, 250, 300), _rgba_png())])

        assert len(photos) == 1
        assert photos[0].mime == "image/png"
        assert _decode(photos[0]).format == "PNG"

    def test_an_opaque_source_is_stored_as_jpeg(self) -> None:
        photos = _one([((50, 100, 250, 300), _png())])

        assert photos[0].mime == "image/jpeg"
        assert _decode(photos[0]).format == "JPEG"
        assert _decode(photos[0]).mode == "RGB"

    def test_sha256_is_the_hash_of_the_stored_bytes(self) -> None:
        photo = _one([((50, 100, 250, 300), _png())])[0]

        assert photo.sha256 == hashlib.sha256(photo.image_bytes).hexdigest()

    def test_width_and_height_are_those_of_the_stored_image(self) -> None:
        photo = _one([((50, 100, 250, 300), _png((9, 9, 9), (320, 180)))])[0]

        decoded = _decode(photo)
        assert (photo.width, photo.height) == decoded.size


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #
class TestRefusals:
    def test_not_a_pdf_is_a_value_error(self) -> None:
        with pytest.raises(ValueError):
            extract_catalog_photos(b"not a pdf")

    def test_an_encrypted_pdf_is_refused(self) -> None:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_image(pymupdf.Rect(50, 100, 250, 300), stream=_png())
        data = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner"
        )
        doc.close()

        with pytest.raises(EncryptedFlyerError):
            extract_catalog_photos(data)
