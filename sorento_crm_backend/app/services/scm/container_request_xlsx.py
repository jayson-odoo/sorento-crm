"""The container request as an `.xlsx`, in the supplier's own layout - F4.

Ms Tee's ask, verbatim: send them the SAME sheet back with the quantity to load filled in.
So this does not invent a form. It takes the stock list they uploaded, keeps their title
line, their header spellings and their row order exactly as they wrote them, and appends ONE
column - `需装数量 / Qty to load`. A product we are asking for that their sheet never named is
appended below their last row rather than dropped, because it is still part of the ask.

REBUILT, never edited in place. Their file may be an old `.xls` (OLE2), which openpyxl can
read through `outstanding_reader.sheet_rows` and cannot write at all, so a "load it and save
it" export would fail on exactly the suppliers who send the oldest files. Reading the values
and writing a fresh workbook works for both containers, and what is being preserved is the
data and its order, not their cell borders.

THE ROUND TRIP IS THE CONTRACT (AC-C2). The supplier's next stock list is very often this
file with the numbers changed, so whatever goes out has to come back in through
`supplier_inventory_reader.read_workbook`. That is asserted in
`tests/scm/test_container_request_xlsx.py` on both layouts below - it is the property that
would otherwise break silently, months later, in the one place nobody looks.

Two layouts, one entry point:

* their sheet + our column, whenever the upload was retained (`supplier_stock_list`
  attachment, `supplier_inventory_service.store_stock_list_attachment`);
* our own five columns (AC-C5) when it was not, when the stored bytes will not open, or when
  the sheet has no item-code column to write a quantity against. A fallback, never an error:
  the request itself is the point, and a send must not die because a stored file is corrupt.
"""
from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver
from app.services.scm.outstanding_reader import all_sheet_rows
from app.services.scm.supplier_inventory_reader import DOC_TYPE

logger = logging.getLogger(__name__)

#: The one column we add. Bilingual for the same reason the PDF is: their staff read the
#: Chinese, ours have to be able to check what went out.
QTY_TO_LOAD_HEADER = "需装数量 / Qty to load"

#: What the file says when there is no sheet of theirs to answer in (AC-C5). Their own
#: spellings still, because it is a document they read - and because the reader resolves
#: these same aliases, which is what keeps the fallback round-trippable too.
FALLBACK_HEADER = ["型号", "品名", "包装好库存", "空瓷", QTY_TO_LOAD_HEADER]


def filename(supplier: dict) -> str:
    """`container-request-{code}-{stamp}.xlsx` - the PDF's own stem, other extension (AC-C1).

    Same sanitising as `supplier_notice_service._request_filename`, so the two files a
    supplier receives in one email are named alike rather than nearly alike.
    """
    code = (supplier.get("supplier_code") or "supplier").replace("/", "-").replace(" ", "-")
    stamp = datetime.utcnow().strftime("%Y%m%d")
    return f"container-request-{code}-{stamp}.xlsx"


def build(
    db: Session,
    *,
    supplier: dict,
    supplier_id: str,
    lines: list[dict],
) -> bytes:
    """The request as a workbook. Never raises: a bad stored file falls back, it does not fail.

    ``lines`` are the reviewed lines as `request_and_notify` already holds them:
    `{item_code, product_name, qty}`.
    """
    raw = _uploaded_sheet(db, supplier_id)
    if raw:
        try:
            return _with_qty_to_load(raw, db=db, lines=lines)
        except Exception as exc:  # noqa: BLE001 - a stored file is not the caller's fault
            logger.warning(
                "container request xlsx: supplier %s has a retained stock list that could "
                "not be answered in (%s); falling back to our own columns",
                supplier_id,
                exc,
            )
    return _fallback(db, supplier_id=supplier_id, lines=lines)


# --------------------------------------------------------------------------- their sheet


def _uploaded_sheet(db: Session, supplier_id: str) -> Optional[bytes]:
    """The bytes of the stock list they last sent us, if it was retained.

    Best-effort by construction: retention is itself best-effort
    (`store_stock_list_attachment` logs and continues), so an absent or unreachable object is
    an ordinary state here rather than an error.
    """
    try:
        from app.services.resources_service import AttachmentService
        from app.services.scm import supplier_inventory_service

        held = supplier_inventory_service.latest_stock_list_attachment(
            db, supplier_id=supplier_id
        )
        if not held:
            return None
        return AttachmentService(db).get_file_content(held["attachment_id"])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "container request xlsx: could not read supplier %s's retained stock list (%s)",
            supplier_id,
            exc,
        )
        return None


def _with_qty_to_load(data: bytes, *, db: Session, lines: list[dict]) -> bytes:
    """Their rows, verbatim, plus one column. Raises when the sheet has no item-code column."""
    rows = [list(r) for r in all_sheet_rows(data)]
    resolver = AliasResolver.for_doc_type(db, DOC_TYPE)
    header_idx, col_field = _header(rows, resolver)
    if header_idx is None:
        raise ValueError("no item_code column in the retained stock list")

    code_col = next(pos for pos, f in col_field.items() if f == "item_code")
    name_col = next((pos for pos, f in col_field.items() if f == "product_name"), None)
    width = max(len(r) for r in rows)
    qty_col = width

    asked = {
        str(ln.get("item_code")): _qty(ln.get("qty"))
        for ln in lines
        if ln.get("item_code") is not None
    }

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active or wb.create_sheet()
    ws.title = "Container request"

    placed: set[str] = set()
    for idx, row in enumerate(rows):
        out = list(row) + [None] * (width - len(row))
        if idx == header_idx:
            out.append(QTY_TO_LOAD_HEADER)
        elif idx > header_idx:
            code = _text(out[code_col]) if code_col < len(out) else None
            qty = asked.get(code) if code else None
            out.append(qty)
            if code and code in asked:
                placed.add(code)
        else:
            # A title line above the header keeps its own width: an empty cell under a
            # header it sits above would read as a value nobody filled in.
            out.append(None)
        ws.append(out)

    # Asked for and not on their list: appended under their rows, in the order we asked.
    for ln in lines:
        code = _text(ln.get("item_code"))
        if not code or code in placed:
            continue
        out: list[Any] = [None] * (width + 1)
        out[code_col] = code
        if name_col is not None:
            out[name_col] = ln.get("product_name")
        out[qty_col] = asked.get(code)
        ws.append(out)

    return _bytes(wb)


def _header(rows: list[list], resolver: AliasResolver) -> tuple[Optional[int], dict[int, str]]:
    """The header row and its column map, by `supplier_inventory_reader`'s own rule.

    Not row 1 by decree: these files carry a title line, and sometimes a blank one above it.
    The header is the first row that resolves an item code - the same test the reader applies,
    so a file it can read is a file this can answer in.
    """
    for idx, raw in enumerate(rows):
        mapped: dict[int, str] = {}
        for pos, cell in enumerate(raw):
            field = resolver.field_for_header(cell)
            if field:
                mapped[pos] = field
        if "item_code" in mapped.values():
            return idx, mapped
    return None, {}


# --------------------------------------------------------------------------- our columns


def _fallback(db: Session, *, supplier_id: str, lines: list[dict]) -> bytes:
    """AC-C5: item code, name, what they told us they hold, and what to load.

    Their holdings come off the snapshot rows rather than off the file, because on this branch
    there is no file - and a row with no snapshot behind it (a product they have never listed)
    still belongs on the sheet, with the holdings blank rather than zero.
    """
    held = _held(db, supplier_id)

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active or wb.create_sheet()
    ws.title = "Container request"
    ws.append(list(FALLBACK_HEADER))
    for ln in lines:
        code = _text(ln.get("item_code"))
        stock = held.get(code or "", {})
        ws.append(
            [
                code,
                ln.get("product_name"),
                stock.get("qty_packed"),
                stock.get("qty_unfinished"),
                _qty(ln.get("qty")),
            ]
        )
    return _bytes(wb)


def _held(db: Session, supplier_id: str) -> dict[str, dict]:
    from app.models.scm import SupplierInventory

    rows = (
        db.query(
            SupplierInventory.item_code,
            SupplierInventory.qty_packed,
            SupplierInventory.qty_unfinished,
        )
        .filter(SupplierInventory.supplier_id == supplier_id)
        .all()
    )
    return {
        str(r.item_code): {
            "qty_packed": float(r.qty_packed or 0),
            "qty_unfinished": float(r.qty_unfinished or 0),
        }
        for r in rows
    }


# --------------------------------------------------------------------------- shared


def _qty(value) -> Optional[float]:
    """What to write in the Qty to load cell, and `None` is a real answer (AC-C3).

    A zero would read as "pack none of these", which is a different instruction from "we did
    not ask about these" - and the supplier acts on the difference.
    """
    if value is None:
        return None
    number = float(value)
    if number <= 0:
        return None
    return int(number) if number == int(number) else number


def _text(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def _bytes(wb) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
