"""QUOTE-CERT-TAB: find where a model code is printed on a certificate PDF, and burn boxes into a copy.

Pure functions over PDF bytes (PyMuPDF). A Box is `{"page", "x", "y", "w", "h", "product_id"}` with x/y/w/h
as FRACTIONS of the page AS DISPLAYED (rotation applied), origin top-left. Everything below works in
displayed space: word and rule geometry is run through `page.rotation_matrix` first.
Contract: documentation/plans/certificates/quote-cert-tab-08nov-acceptance-criteria.md "Matcher".
"""
from __future__ import annotations

import logging
from typing import Any

import pymupdf

logger = logging.getLogger(__name__)

RED = (0.88, 0.11, 0.28)
_DROP = set(" -.,;:()[]/")
_MAX_RUN = 4
_RULE_MIN_LEN = 10.0
_THIN = 1.5
_EDGE_PUNCT = ".,;:()[]/-"


def normalise(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch not in _DROP and not ch.isspace())


def is_number_only(code: str) -> bool:
    norm = normalise(code)
    return bool(norm) and norm.isdigit()


def _open(pdf_bytes: bytes):
    try:
        doc = pymupdf.open(stream=bytes(pdf_bytes), filetype="pdf")
    except Exception:  # noqa: BLE001 - unreadable bytes are a normal input
        return None
    try:
        if doc.needs_pass or doc.is_encrypted:
            doc.close()
            return None
    except Exception:  # noqa: BLE001
        pass
    return doc


def page_count(pdf_bytes: bytes) -> int | None:
    doc = _open(pdf_bytes)
    if doc is None:
        return None
    try:
        return len(doc)
    finally:
        doc.close()


def _words(page) -> list[tuple[str, pymupdf.Rect, str]]:
    """Reading-order words as (normalised, displayed rect, printed), empty normalisations dropped."""
    matrix = page.rotation_matrix
    raw = sorted(page.get_text("words"), key=lambda w: (w[5], w[6], w[7]))
    out = []
    for w in raw:
        norm = normalise(w[4])
        if not norm:
            continue
        out.append((norm, (pymupdf.Rect(w[:4]) * matrix).normalize(), w[4]))
    return out


def _rules(page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """(horizontal [(y, x0, x1)], vertical [(x, y0, y1)]) rules in displayed space."""
    matrix = page.rotation_matrix
    horizontal: list[tuple[float, float, float]] = []
    vertical: list[tuple[float, float, float]] = []

    def add_rect(rect: pymupdf.Rect) -> None:
        rect = (rect * matrix).normalize()
        if rect.height < _THIN and rect.width >= _RULE_MIN_LEN:
            horizontal.append(((rect.y0 + rect.y1) / 2, rect.x0, rect.x1))
        elif rect.width < _THIN and rect.height >= _RULE_MIN_LEN:
            vertical.append(((rect.x0 + rect.x1) / 2, rect.y0, rect.y1))
        elif rect.width >= _RULE_MIN_LEN and rect.height >= _RULE_MIN_LEN:
            horizontal.append((rect.y0, rect.x0, rect.x1))
            horizontal.append((rect.y1, rect.x0, rect.x1))
            vertical.append((rect.x0, rect.y0, rect.y1))
            vertical.append((rect.x1, rect.y0, rect.y1))

    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return horizontal, vertical
    for drawing in drawings:
        for item in drawing.get("items", []):
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1] * matrix, item[2] * matrix
                if abs(p1.y - p2.y) < 1 and abs(p1.x - p2.x) >= _RULE_MIN_LEN:
                    horizontal.append(((p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x)))
                elif abs(p1.x - p2.x) < 1 and abs(p1.y - p2.y) >= _RULE_MIN_LEN:
                    vertical.append(((p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y)))
            elif kind == "re":
                add_rect(pymupdf.Rect(item[1]))
            elif kind == "qu":
                add_rect(pymupdf.Quad(item[1]).rect)
    return horizontal, vertical


def _band(word: pymupdf.Rect, rules) -> pymupdf.Rect:
    horizontal, vertical = rules
    above = [y for y, x0, x1 in horizontal if y <= word.y0 + 0.5 and x0 <= word.x1 and x1 >= word.x0]
    below = [y for y, x0, x1 in horizontal if y >= word.y1 - 0.5 and x0 <= word.x1 and x1 >= word.x0]
    if not above or not below:
        return pymupdf.Rect(word.x0 - 2, word.y0 - 2, word.x1 + 2, word.y1 + 2)
    top, bottom = max(above), min(below)
    xs = [x for x, y0, y1 in vertical if y0 < bottom and y1 > top]
    if xs:
        left, right = min(min(xs), word.x0 - 2), max(max(xs), word.x1 + 2)
    else:
        left, right = word.x0 - 2, word.x1 + 2
    return pymupdf.Rect(left, top, right, bottom)


def _fractions(rect: pymupdf.Rect, page, page_no: int) -> dict[str, Any]:
    width, height = page.rect.width, page.rect.height
    x0, y0 = max(0.0, rect.x0 / width), max(0.0, rect.y0 / height)
    x1, y1 = min(1.0, rect.x1 / width), min(1.0, rect.y1 / height)
    return {"page": page_no, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _runs(words, max_len: int):
    """Every run of 1..max_len consecutive words as (start, length, joined normalised)."""
    for i in range(len(words)):
        acc = ""
        for n in range(1, max_len + 1):
            if i + n > len(words):
                break
            acc += words[i + n - 1][0]
            yield i, n, acc


def find_boxes(pdf_bytes: bytes, code: str) -> dict[str, Any]:
    doc = _open(pdf_bytes)
    if doc is None:
        return {"has_text": False, "boxes": []}
    try:
        target = normalise(code)
        has_text = False
        boxes: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        for index in range(len(doc)):
            page = doc[index]
            words = _words(page)
            if not words:
                continue
            has_text = True
            if not target:
                continue
            rules = _rules(page)
            skip_until = 0
            for i in range(len(words)):
                if i < skip_until:
                    continue
                acc = ""
                for n in range(1, _MAX_RUN + 1):
                    if i + n > len(words):
                        break
                    acc += words[i + n - 1][0]
                    if len(acc) > len(target):
                        break
                    if acc == target:
                        rect = None
                        for _norm, word_rect, _printed in words[i : i + n]:
                            band = _band(word_rect, rules)
                            rect = band if rect is None else rect | band
                        box = _fractions(rect, page, index + 1)
                        key = (box["page"], round(box["x"], 4), round(box["y"], 4), round(box["w"], 4), round(box["h"], 4))
                        if key not in seen:
                            seen.add(key)
                            boxes.append(box)
                        skip_until = i + n
                        break
        return {"has_text": has_text, "boxes": boxes}
    except Exception:  # noqa: BLE001
        logger.warning("certificate pdf match failed", exc_info=True)
        return {"has_text": False, "boxes": []}
    finally:
        doc.close()


def suggest_code(pdf_bytes: bytes, product_code: str) -> str | None:
    """The printed code for a product (CERT-14): the longest 1-3 word run that is a substring of the
    product code, at least 4 characters and containing a digit; ties go to reading order."""
    doc = _open(pdf_bytes)
    if doc is None:
        return None
    try:
        product_norm = normalise(product_code)
        if not product_norm:
            return None
        best: tuple[int, str] | None = None
        for index in range(len(doc)):
            words = _words(doc[index])
            for i, n, acc in _runs(words, 3):
                if len(acc) < 4 or not any(ch.isdigit() for ch in acc) or acc not in product_norm:
                    continue
                if best is None or len(acc) > best[0]:
                    printed = " ".join(w[2] for w in words[i : i + n]).strip(_EDGE_PUNCT + " ")
                    best = (len(acc), printed)
        return best[1] if best else None
    except Exception:  # noqa: BLE001
        logger.warning("certificate pdf suggestion failed", exc_info=True)
        return None
    finally:
        doc.close()


def burn_boxes(pdf_bytes: bytes, boxes: list[dict[str, Any]]) -> bytes:
    """A COPY of the PDF with each box drawn as a red 1.5 pt rectangle."""
    doc = _open(pdf_bytes)
    if doc is None:
        return bytes(pdf_bytes)
    try:
        for box in boxes or []:
            number = int(box["page"]) - 1
            if number < 0 or number >= len(doc):
                continue
            page = doc[number]
            width, height = page.rect.width, page.rect.height
            shown = pymupdf.Rect(
                box["x"] * width,
                box["y"] * height,
                (box["x"] + box["w"]) * width,
                (box["y"] + box["h"]) * height,
            )
            rect = (shown * page.derotation_matrix).normalize()
            page.draw_rect(rect, color=RED, width=1.5)
        return doc.tobytes()
    finally:
        doc.close()
