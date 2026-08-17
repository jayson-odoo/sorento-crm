"""Which currency a supplier's document is priced in, and where that answer came from.

Shared by the proforma channel and the packing-list channel because both parse a unit price
out of a file that may or may not say what money it is in, and a price stored without its
currency is a number with no meaning (the reason `inbound_shipment_lines.currency` exists).

The order is fixed and NAMED, so the preview can say which source won (AC-P3.1):

    the upload form  >  the document itself  >  the supplier's price list  >  nothing

There is deliberately no house default. A supplier whose price list is mixed-currency
resolves to `none`, not to the majority (AC-P3.3): guessing MYR on a Chinese proforma is
worse than asking, because the guess is invisible once it is stored.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

#: Spelling -> ISO code, IN ORDER. Order is load-bearing twice over: `rmb` is checked before
#: `rm` (or every `金额（rmb）` header reads as Malaysian ringgit), and the fuller spelling of
#: a pair is always checked first for the same reason.
_TOKENS: tuple[tuple[str, str], ...] = (
    ("rmb", "CNY"),
    ("cny", "CNY"),
    ("人民币", "CNY"),
    ("元", "CNY"),
    ("¥", "CNY"),
    ("usd", "USD"),
    ("us$", "USD"),
    ("myr", "MYR"),
    ("rm", "MYR"),
)


def _fold(value: Any) -> str:
    """Lower-case, width-folded, space-stripped. Punctuation is KEPT, unlike
    `normalize_header`, because `US$` and `¥` are currency spellings and stripping them
    would throw away the only thing the cell said."""
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().lower().replace(" ", "")


def currency_from_text(values: Iterable[Any]) -> Optional[str]:
    """The currency a header or a labelled cell STATES, or None.

    Reads `RMB`, `单价(元)`, `金额（rmb）`, `Currency: USD`. A hint, never applied on its own:
    the caller decides whether the document outranks the form value (`resolve_currency`).
    """
    for value in values:
        folded = _fold(value)
        if not folded:
            continue
        for token, code in _TOKENS:
            if token in folded:
                return code
    return None


def price_column_currency(
    raw_header: Any, col_field: dict, *, extra: Iterable[Any] = ()
) -> Optional[str]:
    """The currency the PRICE columns of a header row name, e.g. `RMB` / `单价(元)`.

    `extra` goes first, for a labelled `Currency:` cell that names it outright. Both readers
    call this so a pre-loading list read as a packing list and the same file read as a
    proforma cannot disagree about what money it is in.
    """
    texts = list(extra)
    header = list(raw_header or [])
    for pos in sorted(p for p, f in col_field.items() if f in ("unit_price", "amount")):
        if pos < len(header):
            texts.append(header[pos])
    return currency_from_text(texts)


def normalise_currency(value: Any) -> Optional[str]:
    """One cell or form value as an ISO code. `RMB` -> `CNY`, `rm` -> `MYR`, `usd` -> `USD`.

    A three-letter code we do not have a spelling for is taken verbatim (upper-cased), so a
    supplier invoicing in SGD needs no code change. Anything else is None rather than a
    truncated guess - the column is `String(3)`.
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    hinted = currency_from_text([text])
    if hinted:
        return hinted
    letters = re.sub(r"[^A-Za-z]", "", text).upper()
    return letters if len(letters) == 3 else None


def supplier_price_list_currency(db: Session, supplier_id: Optional[str]) -> Optional[str]:
    """The one currency this supplier's price list agrees on, or None.

    Company-scoped through the ORM (`product_suppliers` is an owned table), so another
    company's price rows cannot answer the question. Exactly one distinct value counts;
    two make this source silent rather than a vote.
    """
    if not supplier_id:
        return None
    from app.models.procurement import ProductSupplier

    rows = (
        db.query(ProductSupplier.currency)
        .filter(
            ProductSupplier.supplier_id == supplier_id,
            ProductSupplier.currency.isnot(None),
            ProductSupplier.currency != "",
        )
        .distinct()
        .all()
    )
    codes = {c for c in (normalise_currency(r[0]) for r in rows) if c}
    return next(iter(codes)) if len(codes) == 1 else None


def resolve_currency(
    db: Session,
    *,
    supplier_id: Optional[str] = None,
    requested: Any = None,
    stated: Any = None,
) -> Tuple[Optional[str], str]:
    """`(code, source)` where source is `form | document | supplier_price_list | none`.

    `requested` is what the operator typed on the upload form; `stated` is what the reader
    found in the file. The source travels with the code so the preview can show it - a
    currency that appeared from somewhere is the kind of thing nobody questions until the
    variance report is wrong.
    """
    code = normalise_currency(requested)
    if code:
        return code, "form"
    code = normalise_currency(stated)
    if code:
        return code, "document"
    code = supplier_price_list_currency(db, supplier_id)
    if code:
        return code, "supplier_price_list"
    return None, "none"
