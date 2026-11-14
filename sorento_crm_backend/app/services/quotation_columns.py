"""The quotation's line columns: ONE definition, read by the PDF and the customer's sign page.

QUOTE-SIGN-COLUMNS (owner, 2 Nov): the sign page kept its own column list and lost the product
photo the PDF prints. Both now read the column set from here, so the page the customer signs and
the document in their inbox cannot disagree on what is a column, its label or its place.

Its own module, not the PDF service: the sign page's serializer must not import WeasyPrint's
neighbours to learn a list of labels.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Tuple

IMAGE = "image"
#: NON-CANCELLABLE-ITEMS (owner, 11 Nov 2026): "say Non cancellable at the remark".
REMARK = "remark"

#: (key, label), in the sample workbook's order. The key is what a renderer switches on; the label
#: is what the customer reads, on paper and on screen alike.
COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("item", "ITEM"),
    (IMAGE, "PRODUCT IMAGE"),
    ("spec", "TECHNICAL SPEC"),
    ("description", "DESCRIPTION"),
    ("brand", "BRAND"),
    ("product_code", "PRODUCT CODE"),
    ("qty", "QTY"),
    ("unit_rate", "UNIT RATE (RM)"),
    ("complete_set", "COMPLETE SET"),
    # Before GRAND TOTAL so the money stays the last column, where every total row puts it.
    (REMARK, "REMARK"),
    ("amount", "GRAND TOTAL"),
)


def for_lines(lines: Iterable[Any]) -> List[Tuple[str, str]]:
    """The columns one scope prints.

    PRODUCT IMAGE only when a line of the scope carries a photo (AC-F4): a column of blank cells
    squeezes the columns that do carry information. TECHNICAL SPEC always stays: it is in the
    sample's column set whether or not a line has a drawing.

    REMARK only when a line of the scope is Non-cancellable (NON-CANCELLABLE-ITEMS), for the
    same reason as the photo: a scope with nothing to remark on prints exactly as before.
    """
    lines = list(lines)
    show_image = any(getattr(line, "image_attachment_id", None) for line in lines)
    show_remark = any(
        getattr(line, "is_non_cancellable", False) and not getattr(line, "is_section", False)
        for line in lines
    )
    hidden = set()
    if not show_image:
        hidden.add(IMAGE)
    if not show_remark:
        hidden.add(REMARK)
    return [column for column in COLUMNS if column[0] not in hidden]


def remark(line: Any) -> str:
    """What the REMARK cell prints for one line: the Non-cancellable note, else nothing."""
    if getattr(line, "is_non_cancellable", False) and not getattr(line, "is_section", False):
        return NON_CANCELLABLE_REMARK
    return ""


#: The remark text, one spelling for the PDF, the sign page and the screen.
NON_CANCELLABLE_REMARK = "Non-cancellable"


__all__ = ["COLUMNS", "IMAGE", "NON_CANCELLABLE_REMARK", "REMARK", "for_lines", "remark"]
