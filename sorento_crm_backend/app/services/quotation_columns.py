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
    ("amount", "GRAND TOTAL"),
)


def for_lines(lines: Iterable[Any]) -> List[Tuple[str, str]]:
    """The columns one scope prints.

    PRODUCT IMAGE only when a line of the scope carries a photo (AC-F4): a column of blank cells
    squeezes the columns that do carry information. TECHNICAL SPEC always stays: it is in the
    sample's column set whether or not a line has a drawing.
    """
    show_image = any(getattr(line, "image_attachment_id", None) for line in lines)
    return [column for column in COLUMNS if column[0] != IMAGE or show_image]


__all__ = ["COLUMNS", "IMAGE", "for_lines"]
