"""QUOTE-CERT-TAB red tests: the certificate PDF matcher and the box burner (UAC tests 1-2).

Written BEFORE `app/services/certificate_pdf_service.py` exists. Every PDF is generated here with
PyMuPDF, so no real certificate is committed. The service import is done INSIDE each test so each
test fails on its own, at the first call into the not-yet-built module.

Contract (UAC "Matcher"): `find_boxes(pdf_bytes, code) -> {"has_text", "boxes"}` with Box fractions
of the page AS DISPLAYED (rotation applied), origin top-left; `burn_boxes(pdf_bytes, boxes) -> bytes`.
"""
from __future__ import annotations

import pymupdf
import pytest

PAGE_W, PAGE_H = 595.0, 842.0
X_LEFT, X_MID, X_RIGHT = 50.0, 200.0, 545.0
TOP = 100.0
TOL = 0.004  # fraction tolerance (~3 pt on a 842 pt page)


def table_pdf(pages, *, rotation: int = 0, ruled: bool = True) -> bytes:
    """One ruled table per page. `pages` is a list of row lists; a row is
    `(code_text, [description lines], height_pt)`. Returns the PDF bytes."""
    doc = pymupdf.open()
    for rows in pages:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        total = 30 + sum(r[2] for r in rows)
        ys = [TOP, TOP + 30]
        for _, _, height in rows:
            ys.append(ys[-1] + height)
        if ruled:
            for y in ys:
                page.draw_line((X_LEFT, y), (X_RIGHT, y))
            for x in (X_LEFT, X_MID, X_RIGHT):
                page.draw_line((x, TOP), (x, TOP + total))
        page.insert_text((60, TOP + 20), "Model", fontsize=11)
        page.insert_text((210, TOP + 20), "Description", fontsize=11)
        for i, (code, lines, _height) in enumerate(rows):
            top = ys[i + 1]
            page.insert_text((60, top + 18), code, fontsize=11)
            for n, line in enumerate(lines):
                page.insert_text((210, top + 18 + 15 * n), line, fontsize=11)
        if rotation:
            page.set_rotation(rotation)
    out = doc.tobytes()
    doc.close()
    return out


ROWS = [
    ("12A", ["basin mixer"], 30),
    ("13A,", ["bath mixer"], 30),
    ("14A", ["wall hung closet", "second line of the same row"], 50),
    ("114A", ["pedestal"], 30),
    ("14AB", ["cistern"], 30),
]
# Row band of "14A": top = TOP + 30 + 30 + 30 = 190, bottom = 240.
ROW_14A_TOP, ROW_14A_BOTTOM = 190.0, 240.0


def image_only_pdf() -> bytes:
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (200, 100), (255, 255, 255)).save(buf, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_image(pymupdf.Rect(50, 50, 400, 250), stream=buf.getvalue())
    out = doc.tobytes()
    doc.close()
    return out


def _displayed(page, word_rect) -> pymupdf.Rect:
    """A word rect (as get_text('words') reports it) in displayed space."""
    return (pymupdf.Rect(word_rect) * page.rotation_matrix).normalize()


def _box_rect(box, page) -> pymupdf.Rect:
    w, h = page.rect.width, page.rect.height
    return pymupdf.Rect(box["x"] * w, box["y"] * h, (box["x"] + box["w"]) * w, (box["y"] + box["h"]) * h)


def _hit_word(pdf: bytes, token: str, page_no: int = 0):
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc[page_no]
    for word in page.get_text("words"):
        if word[4].strip(".,;:()[]").lower() == token.lower():
            return page, word
    raise AssertionError(f"{token} not in the generated pdf")


# ------------------------------------------------------------------ 1 matcher


def test_01_exact_code_hits_the_wrapped_row_once_and_covers_the_whole_band():
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([ROWS])
    result = find_boxes(pdf, "14A")
    assert result["has_text"] is True
    assert len(result["boxes"]) == 1, result
    box = result["boxes"][0]
    assert box["page"] == 1
    # The fractions are of the displayed page and stay inside it.
    for key in ("x", "y", "w", "h"):
        assert 0 <= box[key] <= 1
    assert box["x"] + box["w"] <= 1 + 1e-9 and box["y"] + box["h"] <= 1 + 1e-9
    # Row band: from the rule above to the rule below, across the table.
    assert box["y"] == pytest.approx(ROW_14A_TOP / PAGE_H, abs=TOL)
    assert box["y"] + box["h"] == pytest.approx(ROW_14A_BOTTOM / PAGE_H, abs=TOL)
    assert box["x"] == pytest.approx(X_LEFT / PAGE_W, abs=TOL)
    assert box["x"] + box["w"] == pytest.approx(X_RIGHT / PAGE_W, abs=TOL)


def test_01_longer_and_suffixed_codes_are_not_hits_for_a_shorter_code():
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([ROWS])
    only = find_boxes(pdf, "14A")["boxes"]
    # 114A (240-270) and 14AB (270-300) rows must not be inside the single 14A box.
    assert len(only) == 1
    assert only[0]["y"] + only[0]["h"] <= 245.0 / PAGE_H
    # And each of those has its own exact hit when asked for by its own code.
    assert len(find_boxes(pdf, "114A")["boxes"]) == 1
    assert len(find_boxes(pdf, "14AB")["boxes"]) == 1


def test_01_absent_code_gives_no_boxes_but_has_text():
    from app.services.certificate_pdf_service import find_boxes

    result = find_boxes(table_pdf([ROWS]), "ZZ999")
    assert result == {"has_text": True, "boxes": []}


def test_01_case_insensitive_and_punctuation_stripped_from_the_token_ends():
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([ROWS])
    assert len(find_boxes(pdf, "14a")["boxes"]) == 1
    # The row prints "13A," with a trailing comma.
    assert len(find_boxes(pdf, "13A")["boxes"]) == 1


def test_01_multi_word_code_matches_consecutive_tokens_on_one_line():
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([[("WCM PC 1", ["close coupled"], 30), ("WCM PC 12", ["other"], 30)]])
    result = find_boxes(pdf, "WCM PC 1")
    assert len(result["boxes"]) == 1, result
    assert result["boxes"][0]["y"] == pytest.approx((TOP + 30) / PAGE_H, abs=TOL)


def test_01_a_code_on_two_pages_gives_two_boxes_on_their_own_pages():
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([ROWS, ROWS])
    boxes = find_boxes(pdf, "14A")["boxes"]
    assert sorted(b["page"] for b in boxes) == [1, 2]


def test_01_no_ruled_lines_widen_the_hit_line_by_two_points():
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([ROWS], ruled=False)
    boxes = find_boxes(pdf, "12A")["boxes"]
    assert len(boxes) == 1
    page, word = _hit_word(pdf, "12A")
    rect = _box_rect(boxes[0], page)
    assert rect.y0 <= word[1] and rect.y1 >= word[3]
    assert rect.y0 >= word[1] - 3.0 and rect.y1 <= word[3] + 3.0
    assert rect.x0 <= word[0] and rect.x1 >= word[2]


def test_01_image_only_pdf_has_no_text_and_no_boxes():
    from app.services.certificate_pdf_service import find_boxes

    assert find_boxes(image_only_pdf(), "14A") == {"has_text": False, "boxes": []}


def test_01_garbage_bytes_do_not_raise():
    from app.services.certificate_pdf_service import find_boxes

    assert find_boxes(b"this is not a pdf", "14A") == {"has_text": False, "boxes": []}
    assert find_boxes(b"", "14A") == {"has_text": False, "boxes": []}


@pytest.mark.parametrize("rotation", [90, 270])
def test_01_rotated_page_boxes_cover_the_row_as_displayed(rotation):
    from app.services.certificate_pdf_service import find_boxes

    pdf = table_pdf([ROWS], rotation=rotation)
    result = find_boxes(pdf, "14A")
    assert len(result["boxes"]) == 1, result
    page, word = _hit_word(pdf, "14A")
    assert page.rotation == rotation
    box = result["boxes"][0]
    shown = _displayed(page, word[:4])
    rect = _box_rect(box, page)
    assert rect.x0 <= shown.x0 + 1 and rect.x1 >= shown.x1 - 1
    assert rect.y0 <= shown.y0 + 1 and rect.y1 >= shown.y1 - 1
    # The band is a row, not the whole page: it is wider than the word and far shorter than the page.
    assert rect.width > shown.width * 3
    assert rect.height < page.rect.height * 0.5


# ------------------------------------------------------------------ 2 burn


def _drawing_count(pdf: bytes) -> int:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return sum(len(p.get_drawings()) for p in doc)


def test_02_burn_adds_one_red_rectangle_per_box_and_leaves_the_input_alone():
    from app.services.certificate_pdf_service import burn_boxes

    pdf = table_pdf([ROWS])
    before = bytes(pdf)
    boxes = [
        {"page": 1, "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05, "product_id": None},
        {"page": 1, "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.1, "product_id": None},
    ]
    out = burn_boxes(pdf, boxes)
    assert pdf == before, "the input bytes must not change"
    assert out != pdf and out[:5] == b"%PDF-"
    assert _drawing_count(out) == _drawing_count(pdf) + 2

    doc = pymupdf.open(stream=out, filetype="pdf")
    red = [
        d
        for d in doc[0].get_drawings()
        if d.get("color") and all(abs(a - b) < 0.02 for a, b in zip(d["color"], (0.88, 0.11, 0.28)))
    ]
    assert len(red) == 2
    assert all(abs((d.get("width") or 0) - 1.5) < 0.05 for d in red)
    first = red[0]["rect"]
    assert first.x0 == pytest.approx(0.1 * PAGE_W, abs=1.0)
    assert first.y0 == pytest.approx(0.2 * PAGE_H, abs=1.0)


def test_02_burn_with_no_boxes_draws_nothing_extra():
    from app.services.certificate_pdf_service import burn_boxes

    pdf = table_pdf([ROWS])
    assert _drawing_count(burn_boxes(pdf, [])) == _drawing_count(pdf)


def test_02_burn_puts_each_box_on_its_own_page():
    from app.services.certificate_pdf_service import burn_boxes

    pdf = table_pdf([ROWS, ROWS])
    out = burn_boxes(pdf, [{"page": 2, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1, "product_id": None}])
    doc = pymupdf.open(stream=out, filetype="pdf")
    base = pymupdf.open(stream=pdf, filetype="pdf")
    assert len(doc[0].get_drawings()) == len(base[0].get_drawings())
    assert len(doc[1].get_drawings()) == len(base[1].get_drawings()) + 1
