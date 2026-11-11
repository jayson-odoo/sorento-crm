"""SPEC-SHEET-DESIGNER-PARITY B5: a spec sheet as a PowerPoint deck.

The print page resolves every merge field and exposes the per-page layers
(``window.__tagSheetLayout``); this module only draws them: one slide per page at the page size, a
text box per text layer, a picture per image layer, an autoshape per shape layer and a real table
(merges, fills, per-cell border colours from the resolved edges) per table layer.

SECURITY: the worker never fetches a URL. A picture arrives as a ``data:`` URL read inside the
browser page; anything else is skipped here. A layer of a kind this module does not know is skipped.
"""
from __future__ import annotations

import base64
import binascii
import io
import logging
import math
import re
from typing import Any, Optional, Sequence

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

logger = logging.getLogger(__name__)

EMU_PER_MM = 36000
#: A decoded picture larger than this is skipped, not embedded.
IMAGE_MAX_BYTES = 25 * 1024 * 1024

_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_DATA_URL = re.compile(r"^data:image/(png|jpeg|jpg|gif|bmp);base64,([A-Za-z0-9+/=\s]+)$")
_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
_ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}
#: Order of the border children inside a table cell's properties.
_LN_ORDER = ("lnL", "lnR", "lnT", "lnB")


def _mm(value: Any) -> Emu:
    try:
        return Emu(int(round(float(value) * EMU_PER_MM)))
    except (TypeError, ValueError):
        return Emu(0)


def _rgb(value: Any) -> Optional[RGBColor]:
    match = _HEX.match(str(value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return RGBColor.from_string(digits.upper())


def _box(layer: dict) -> tuple[Emu, Emu, Emu, Emu]:
    return _mm(layer.get("x_mm")), _mm(layer.get("y_mm")), _mm(layer.get("width_mm")), _mm(layer.get("height_mm"))


def _turn(shape, layer: dict) -> None:
    """Rotate like CSS / Konva: about the box's top-left, not its centre (PowerPoint's pivot)."""
    degrees = float(layer.get("rotation_deg") or 0)
    if not degrees:
        return
    radians = math.radians(degrees)
    half_w, half_h = int(shape.width) / 2, int(shape.height) / 2
    # The centre after swinging (half_w, half_h) about the top-left corner.
    cx = int(shape.left) + half_w * math.cos(radians) - half_h * math.sin(radians)
    cy = int(shape.top) + half_w * math.sin(radians) + half_h * math.cos(radians)
    shape.left, shape.top = Emu(int(round(cx - half_w))), Emu(int(round(cy - half_h)))
    shape.rotation = degrees


def _style_run(run, layer: dict) -> None:
    font = run.font
    if layer.get("fontFamily"):
        font.name = str(layer["fontFamily"])
    if layer.get("fontSize"):
        font.size = Pt(float(layer["fontSize"]))
    font.bold = bool(layer.get("bold"))
    font.italic = bool(layer.get("italic"))
    font.underline = bool(layer.get("underline"))
    color = _rgb(layer.get("color"))
    if color is not None:
        font.color.rgb = color


def _add_text(slide, layer: dict) -> None:
    left, top, width, height = _box(layer)
    shape = slide.shapes.add_textbox(left, top, width, height)
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    for index, line in enumerate(str(layer.get("text") or "").split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = _ALIGN.get(str(layer.get("align")), PP_ALIGN.LEFT)
        run = paragraph.add_run()
        run.text = line
        _style_run(run, layer)
    _turn(shape, layer)


def _decode_image(url: Any) -> Optional[bytes]:
    match = _DATA_URL.match(str(url or "").strip())
    if not match:
        return None
    try:
        data = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
    except (binascii.Error, ValueError):
        return None
    return data if 0 < len(data) <= IMAGE_MAX_BYTES else None


def _add_image(slide, layer: dict) -> None:
    data = _decode_image(layer.get("url"))
    if data is None:
        return
    left, top, width, height = _box(layer)
    picture = slide.shapes.add_picture(io.BytesIO(data), left, top, width, height)
    fit = layer.get("fit")
    if fit in ("contain", "cover") and picture.image.size[0] and picture.image.size[1]:
        natural_w, natural_h = picture.image.size
        ratio = natural_w / natural_h
        box_ratio = (int(width) / int(height)) if int(height) else ratio
        if fit == "contain":
            if ratio > box_ratio:
                new_h = int(int(width) / ratio)
                picture.top = Emu(int(top) + (int(height) - new_h) // 2)
                picture.height = Emu(new_h)
            else:
                new_w = int(int(height) * ratio)
                picture.left = Emu(int(left) + (int(width) - new_w) // 2)
                picture.width = Emu(new_w)
        else:  # cover: fill the box, crop the overflow evenly
            if ratio > box_ratio:
                keep = box_ratio / ratio
                picture.crop_left = picture.crop_right = (1 - keep) / 2
            else:
                keep = ratio / box_ratio
                picture.crop_top = picture.crop_bottom = (1 - keep) / 2
    _turn(picture, layer)


def _add_shape(slide, layer: dict) -> None:
    kind = str(layer.get("shape") or "")
    left, top, width, height = _box(layer)
    if kind == "line":
        line = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, left, top, Emu(int(left) + int(width)), Emu(int(top) + int(height))
        )
        shape = line
    elif kind in ("rect", "rounded_rect", "ellipse"):
        autoshape = {"rect": MSO_SHAPE.RECTANGLE, "rounded_rect": MSO_SHAPE.ROUNDED_RECTANGLE, "ellipse": MSO_SHAPE.OVAL}[kind]
        shape = slide.shapes.add_shape(autoshape, left, top, width, height)
        fill = _rgb(layer.get("fill"))
        if fill is None:
            shape.fill.background()
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = fill
        shape.shadow.inherit = False
    else:
        return  # polygons and the like: not expressible here yet
    stroke = _rgb(layer.get("stroke"))
    width_mm = float(layer.get("strokeWidth") or 0)
    if stroke is not None and width_mm > 0:
        shape.line.color.rgb = stroke
        shape.line.width = _mm(width_mm)
    elif kind != "line":
        shape.line.fill.background()
    _turn(shape, layer)


def _set_border(tc_pr, side: str, color: RGBColor, width_mm: float) -> None:
    tag = {"left": "lnL", "right": "lnR", "top": "lnT", "bottom": "lnB"}[side]
    for old in tc_pr.findall(qn(f"a:{tag}")):
        tc_pr.remove(old)
    line = etree.SubElement(tc_pr, qn(f"a:{tag}"))
    tc_pr.remove(line)
    line.set("w", str(int(round(width_mm * EMU_PER_MM))))
    line.set("cap", "flat")
    line.set("cmpd", "sng")
    fill = etree.SubElement(line, qn("a:solidFill"))
    etree.SubElement(fill, qn("a:srgbClr")).set("val", str(color))
    etree.SubElement(line, qn("a:prstDash")).set("val", "solid")
    # Borders come before the cell fill in the schema; keep their own order.
    position = len(tc_pr)
    mine = _LN_ORDER.index(tag)
    for index, child in enumerate(tc_pr):
        name = etree.QName(child).localname
        if name not in _LN_ORDER or _LN_ORDER.index(name) > mine:
            position = index
            break
    tc_pr.insert(position, line)


def _boundaries(sizes: Sequence[float]) -> list[float]:
    out = [0.0]
    for size in sizes:
        out.append(out[-1] + float(size))
    return out


def _nearest(boundaries: list[float], value: float) -> int:
    return min(range(len(boundaries)), key=lambda i: abs(boundaries[i] - value))


def _add_table(slide, layer: dict) -> None:
    columns = [float(v) for v in layer.get("columns_mm") or []]
    rows = [float(v) for v in layer.get("rows_mm") or []]
    if not columns or not rows or len(columns) > 50 or len(rows) > 50:
        return
    left, top, _width, _height = _box(layer)
    frame = slide.shapes.add_table(len(rows), len(columns), left, top, _mm(sum(columns)), _mm(sum(rows)))
    table = frame.table
    table.first_row = False
    table.horz_banding = False
    for index, size in enumerate(columns):
        table.columns[index].width = _mm(size)
    for index, size in enumerate(rows):
        table.rows[index].height = _mm(size)

    # Every grid position -> the anchor cell that owns it.
    owner: dict[tuple[int, int], dict] = {}
    for cell in layer.get("cells") or []:
        r, c = int(cell.get("row", 0)), int(cell.get("col", 0))
        rs, cs = max(1, int(cell.get("rowSpan") or 1)), max(1, int(cell.get("colSpan") or 1))
        if not (0 <= r < len(rows) and 0 <= c < len(columns)):
            continue
        rs, cs = min(rs, len(rows) - r), min(cs, len(columns) - c)
        cell["_rs"], cell["_cs"] = rs, cs
        for i in range(rs):
            for j in range(cs):
                owner[(r + i, c + j)] = cell

    for cell in layer.get("cells") or []:
        if "_rs" not in cell:
            continue
        r, c = int(cell["row"]), int(cell["col"])
        target = table.cell(r, c)
        if cell["_rs"] > 1 or cell["_cs"] > 1:
            target.merge(table.cell(r + cell["_rs"] - 1, c + cell["_cs"] - 1))
        frame_text = target.text_frame
        frame_text.word_wrap = True
        for index, line in enumerate(str(cell.get("text") or "").split("\n")):
            paragraph = frame_text.paragraphs[0] if index == 0 else frame_text.add_paragraph()
            paragraph.alignment = _ALIGN.get(str(layer.get("align")), PP_ALIGN.LEFT)
            run = paragraph.add_run()
            run.text = line
            _style_run(run, {"fontFamily": layer.get("fontFamily"), "fontSize": layer.get("fontSize"), "color": layer.get("color")})
        target.vertical_anchor = _ANCHOR.get(str(layer.get("verticalAlign")), MSO_ANCHOR.MIDDLE)
        pad = _mm(cell.get("padding_mm") if cell.get("padding_mm") is not None else 1)
        target.margin_left = target.margin_right = target.margin_top = target.margin_bottom = pad
        fill = _rgb(cell.get("fill"))
        if fill is None:
            target.fill.background()
        else:
            target.fill.solid()
            target.fill.fore_color.rgb = fill

    # Borders: each resolved edge goes onto the cell(s) on either side of it.
    x_lines, y_lines = _boundaries(columns), _boundaries(rows)
    for edge in layer.get("edges") or []:
        color = _rgb(edge.get("color"))
        width = float(edge.get("width_mm") or 0)
        if color is None or width <= 0:
            continue
        x1, x2 = sorted((float(edge.get("x1_mm", 0)), float(edge.get("x2_mm", 0))))
        y1, y2 = sorted((float(edge.get("y1_mm", 0)), float(edge.get("y2_mm", 0))))
        horizontal = abs(y2 - y1) < 1e-6
        if horizontal:
            line = _nearest(y_lines, y1)
            spans = [j for j in range(len(columns)) if min(x2, x_lines[j + 1]) - max(x1, x_lines[j]) > 1e-6]
            pairs = [((line - 1, j), (line, j)) for j in spans]
            before_side, after_side = "bottom", "top"
        else:
            line = _nearest(x_lines, x1)
            spans = [i for i in range(len(rows)) if min(y2, y_lines[i + 1]) - max(y1, y_lines[i]) > 1e-6]
            pairs = [((i, line - 1), (i, line)) for i in spans]
            before_side, after_side = "right", "left"
        for before, after in pairs:
            for position, side in ((before, before_side), (after, after_side)):
                anchor = owner.get(position)
                if anchor is None:
                    continue
                r, c = int(anchor["row"]), int(anchor["col"])
                # Only the anchor's own outer side carries the border (not a merge's inner line).
                last_r, last_c = r + anchor["_rs"] - 1, c + anchor["_cs"] - 1
                on_edge = {
                    "top": position[0] == r,
                    "bottom": position[0] == last_r,
                    "left": position[1] == c,
                    "right": position[1] == last_c,
                }[side]
                if on_edge:
                    _set_border(table.cell(r, c)._tc.get_or_add_tcPr(), side, color, width)


_BUILDERS = {"text": _add_text, "image": _add_image, "shape": _add_shape, "table": _add_table}


def build_pptx(pages: Sequence[dict], page_mm: Sequence[float]) -> bytes:
    """One slide per page, each layer drawn in order; a layer that fails to draw is skipped."""
    deck = Presentation()
    deck.slide_width = _mm(page_mm[0])
    deck.slide_height = _mm(page_mm[1])
    blank = deck.slide_layouts[6]
    for page in pages:
        slide = deck.slides.add_slide(blank)
        for layer in (page or {}).get("layers") or []:
            builder = _BUILDERS.get(str((layer or {}).get("kind")))
            if builder is None:
                continue
            try:
                builder(slide, layer)
            except Exception:  # noqa: BLE001 - one bad layer must not lose the deck
                logger.warning("spec sheet pptx: layer %s skipped", layer.get("kind"), exc_info=True)
    out = io.BytesIO()
    deck.save(out)
    return out.getvalue()
