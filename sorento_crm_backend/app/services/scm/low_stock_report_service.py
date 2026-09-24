"""The low stock workbook - two sheets off ONE frozen run (S3, AC-30..AC-37).

`PLAN-low-stock-report.md`. The client's own `Stock Balance 28 Aug 2026.xls` is two sheets
per category: a "- Low" sheet listing what sits below its reorder level, and the full sheet
beside it. Owner ruling 14 Sep: one workbook per run, exactly two sheets - "Low stock" and
"All" - sixteen columns on both, bounded by a reorder run so Suggested qty is the ENGINE's
figure rather than a second opinion computed here.

A sibling module rather than more lines in the 3,085-line `summary_order_service`: it reads
that module's frozen report and its cell builders (`_docs_text`, `_qty_text`, `_ddmmyyyy`,
`_remarks_text`, `_xlsx_safe_text`, `write_sheet`) and adds nothing to the sheet the buyer
already prints.

What is DIFFERENT from the order sheet, and why:

* **The "All" sheet matches the plan list** (PLAN-low-stock-last-in-and-list-scope S2,
  owner ruling 15 Sep, superseding the parent plan's AC-32/AC-33 "hidden covered rows
  included"): hidden-by-default rows are dropped through the SAME `visible_rows` helper
  `export_report` calls, because the owner measured the two documents disagreeing (1,266
  All rows against 833 on the list for one run) and ruled they must not.
* **Three columns come from MASTER DATA, joined at export time** (AC-34) - Description,
  Category and Reorder qty. Every other column reads the frozen row, because it is a
  planning figure that belongs to the run's moment; a description a buyer fixed this
  morning belongs to today's sheet.
* **Its own cap.** `MAX_LOW_STOCK_ROWS` is 5,000 against the order sheet's 2,000: one is a
  document a buyer prints and walks down, the other is a workbook they filter in Excel.
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory
from app.services.error_handler import AppException
from app.services.scm import summary_order_service as svc

#: The sixteen columns, in the client's own order (AC-31). Description and Category lead,
#: and Reorder qty sits beside Reorder level, because that is how the sheet this replaces
#: is read: find the category, read what is short, read what to order. No new column for
#: PLAN-low-stock-last-in-and-list-scope S1 (owner ruling, second round): "Last in qty"
#: itself becomes a text cell (`svc._last_in_text`).
LOW_STOCK_COLUMNS = (
    "Item code", "Description", "Category", "BRW on hand", "Reorder level",
    "Reorder qty", "Suggested qty", "Suggestion", "Order qty", "Dealer o/s",
    "Supplier", "BRW PO qty", "BRW incoming qty", "Last in qty", "Last in date",
    "Remarks",
)

#: Widths parallel to `LOW_STOCK_COLUMNS`, so dropping the Supplier column (AC-47) shifts
#: the widths with it rather than leaving every later column sized for its neighbour.
#: index 13 (Last in qty) widened to 34 (PLAN-low-stock-last-in-and-list-scope S1 fix
#: round), same as the order sheet's N: the cell is a document line now, same width class
#: as the incoming-document cells.
_LOW_STOCK_WIDTHS = (16, 42, 14, 12, 12, 12, 12, 30, 12, 12, 20, 14, 14, 34, 12, 16)

#: This kind's OWN cap, on the "All" sheet (AC-35). `summary_order_service.MAX_EXPORT_ROWS`
#: (2,000) is untouched - two documents, two sizes.
MAX_LOW_STOCK_ROWS = 5000

_SUPPLIER_INDEX = LOW_STOCK_COLUMNS.index("Supplier")

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def attachment_url(provider: Optional[str], key: str) -> str:
    """A URL Respond.io can fetch the stored workbook from (S5, AC-43/AC-45).

    The exact branch `respond_chat_template_service.upload_chat_attachment` uses, and for
    its reason: the CloudFront signer percent-encodes and SIGNS the path itself, while the
    R2 CDN builder concatenates raw - so R2 is encoded here rather than changing a builder
    every stored row depends on. The storage key already ends in the filename, which is the
    only name channel Respond has (its attachment object is `{type, url}`).

    Shared by the route (the turn's own answer) and the worker's push, so the contact gets
    the same URL whichever path delivers the file.

    SECURITY (note N-c, 14 Sep): on R2 this URL is UNAUTHENTICATED and NEVER EXPIRES -
    anyone holding it can fetch the workbook, which carries supplier names, PO and SPO
    numbers and dealer outstanding quantities. It stops working only when the object is
    deleted, which `purge_expired_downloads` does with the `user_downloads` row at 30 days.
    That is the same mechanism every chat attachment in this product already relies on (a
    WhatsApp message body is itself an unauthenticated copy of the link), so this route
    does not invent a weaker rule - but it is why the URL is kept out of the outbox
    payloads this lane writes (security SF-2, `export_tasks._push_low_stock_to_chat`). The
    S3 branch is a 7-day signed URL and expires on its own.
    """
    from app.services.storage_router import PROVIDER_R2, cdn_base_url, get_backend

    if provider == PROVIDER_R2:
        return cdn_base_url(provider, quote(key, safe="/"))
    return get_backend(provider).get_signed_url(key, expires_in=60 * 60 * 24 * 7)


def _master_map(db: Session, product_codes: list[str]) -> dict[str, dict]:
    """`{product_code: {description, category_code, reorder_quantity}}` in ONE batch query
    (AC-34).

    Description is `products.description`, never `product_name`: the owner's measurement on
    the lavish page is that `product_name` holds the code repeated, so printing it would
    give the buyer the item code twice and no description at all. Reorder qty is
    `products.reorder_quantity` and is BLANK when NULL **or 0** - a 0 there reads as "order
    none", which is not what an unset field means.
    """
    if not product_codes:
        return {}
    rows = (
        db.query(
            Product.product_code,
            Product.description,
            ProductCategory.category_code,
            Product.reorder_quantity,
        )
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.product_code.in_(product_codes))
        .all()
    )
    return {
        code: {
            "description": description or "",
            "category_code": category_code or "",
            "reorder_quantity": float(reorder_quantity) if reorder_quantity else None,
        }
        for code, description, category_code, reorder_quantity in rows
    }


def _is_low(row: dict) -> bool:
    """AC-32: both figures known, and on hand STRICTLY below the level.

    The client's own rule, applied to the RAW pool figure - not to a net, and not to
    anything the engine decided. At the level is not below it: holding 100 against a level
    of 100 is what a reorder level is for. A NULL `pool_on_hand` (a run frozen before
    migration 504) is "nobody measured", not "zero on hand", so it is not low either.
    """
    pool_on_hand = row.get("pool_on_hand")
    reorder_level = row.get("reorder_level")
    if pool_on_hand is None or reorder_level is None:
        return False
    return float(pool_on_hand) < float(reorder_level)


def _split(db: Session, run_id: Optional[str]) -> dict:
    """The two row sets and the stamp, from ONE read of the frozen run.

    Both sheets are sorted by `(category_code, product_code)`: the client's file is filed
    by category and a buyer walks it category by category. A product with no category
    sorts under "" - first - rather than being hidden at the end of a file nobody scrolls.

    "All" is the SAME population the plan list shows (PLAN-low-stock-last-in-and-list-
    scope S2, owner ruling 15 Sep: "I prefer All to match the list exported") - hidden-by-
    default rows dropped via the shared `svc.visible_rows`, superseding the parent plan's
    AC-32 ("hidden covered rows included"). "Low stock" stays a subset of whatever "All"
    prints.
    """
    rep = svc.report(db, run_id=run_id)
    rows = svc.visible_rows(db, rep)
    master = _master_map(db, [r["product_code"] for r in rows])
    ordered = sorted(
        rows,
        key=lambda r: (
            (master.get(r["product_code"], {}).get("category_code") or ""),
            r["product_code"],
        ),
    )
    return {
        "run_id": rep["run_id"],
        "as_of": rep.get("as_of") or svc._today().isoformat(),
        "master": master,
        "all_rows": ordered,
        "low_rows": [r for r in ordered if _is_low(r)],
    }


#: `row_counts()` is GONE (reviewer item 4, round 1 S6): it called `_split` a second time,
#: so every chat report serialised the whole frozen run TWICE on the worker - a real cost on
#: the 1,546-product runs this lane measured. `export_low_stock` now returns the counts it
#: already has, as the fourth element of its tuple, so the task does one read.


def _sheet_row(row: dict, master: dict, *, include_supplier: bool) -> tuple:
    """One product, in `LOW_STOCK_COLUMNS` order.

    Quantities are NUMBERS (the order sheet's H1 rule): a workbook is opened to be summed,
    and a text "1,234" defeats that the moment somebody selects the column. BRW on hand,
    Reorder level, Order qty, Reorder qty and Last in date print BLANK rather than 0 when
    the row carries none - a 0 there reads as a fact nobody measured. BRW PO qty keeps the
    order sheet's exception: once a document exists behind the total the cell becomes
    `_docs_text`'s text, PO number and all (S2). BRW incoming qty is the order sheet's own
    `_incoming_text` (AC-A1, PLAN-order-sheet-oi-reports-22sep.md) - the SPO number never
    appears in this cell, only the container. Last in qty
    (PLAN-low-stock-last-in-and-list-scope S1, AC-A2) is the order sheet's own
    `_last_in_text` - ALWAYS text, the container/qty document line, never a bare number and
    never the SPO number either.
    """
    chosen = row.get("chosen_qty")
    pool_on_hand = row.get("pool_on_hand")
    reorder_level = row.get("reorder_level")
    receipt = row.get("last_receipt")
    po_open_qty = row.get("po_open_qty")
    po_open_docs = row.get("po_open_docs") or []
    incoming_spo_qty = row.get("incoming_spo_qty")
    incoming_spo_docs = row.get("incoming_spo_docs") or []
    reorder_quantity = master.get("reorder_quantity")
    cells = (
        svc._xlsx_safe_text(row["product_code"]),
        svc._xlsx_safe_text(master.get("description") or ""),
        svc._xlsx_safe_text(master.get("category_code") or ""),
        float(pool_on_hand) if pool_on_hand is not None else "",
        float(reorder_level) if reorder_level is not None else "",
        float(reorder_quantity) if reorder_quantity else "",
        float(row.get("suggested_qty") or 0),
        svc._xlsx_safe_text(row.get("suggestion") or ""),
        float(chosen) if chosen is not None else "",
        float(row.get("dealer_outstanding") or 0),
        svc._xlsx_safe_text(row.get("supplier_name") or ""),
        (svc._xlsx_safe_text(svc._docs_text(po_open_qty, po_open_docs)) if po_open_docs
         else float(po_open_qty or 0)),
        (svc._xlsx_safe_text(svc._incoming_text(incoming_spo_qty, incoming_spo_docs))
         if incoming_spo_docs else float(incoming_spo_qty or 0)),
        svc._xlsx_safe_text(svc._last_in_text(receipt)),
        svc._xlsx_safe_text(svc._ddmmyyyy(receipt.get("date"))) if receipt else "",
        svc._xlsx_safe_text(svc._remarks_text(row)),
    )
    if include_supplier:
        return cells
    return cells[:_SUPPLIER_INDEX] + cells[_SUPPLIER_INDEX + 1:]


def export_low_stock(db: Session, *, run_id: Optional[str],
                     include_supplier: bool = True) -> tuple[bytes, str, str, dict]:
    """The workbook for one run: `(bytes, content_type, filename, {"low": n, "all": m})`.

    The counts ride back with the bytes (reviewer item 4) because this function has already
    built both row sets: the task stamps them onto the download row at `mark_ready` so S5's
    chat turn can say "Low: 12 of 340" without opening the workbook (AC-43), and reading
    them from here rather than a second `row_counts()` call is what keeps a chat report to
    ONE read of the frozen run.

    "Low stock" is written FIRST so `wb.active` is the sheet the file was opened for, then
    "All". `include_supplier=False` (S5's chat route, for a contact without the
    `purchase_orders.supplier` reveal key) DROPS the column from both sheets rather than
    blanking it - a blank column still tells the reader a supplier exists and is being
    withheld, which is the leak the reveal key exists to prevent (AC-47).

    Refused above `MAX_LOW_STOCK_ROWS` on the "All" sheet (AC-35). The route refuses on the
    same number before it creates a download row, so this is the backstop rather than how a
    buyer finds out.
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    split = _split(db, run_id)
    if len(split["all_rows"]) > MAX_LOW_STOCK_ROWS:
        raise AppException(422, "Narrow the plan first")

    columns = list(LOW_STOCK_COLUMNS)
    widths = list(_LOW_STOCK_WIDTHS)
    if not include_supplier:
        columns.pop(_SUPPLIER_INDEX)
        widths.pop(_SUPPLIER_INDEX)
    width_map = {get_column_letter(i + 1): w for i, w in enumerate(widths)}

    master = split["master"]
    wb = Workbook()
    for index, (title, rows) in enumerate(
        (("Low stock", split["low_rows"]), ("All", split["all_rows"]))
    ):
        ws = wb.active if index == 0 else wb.create_sheet()
        ws.title = title
        svc.write_sheet(
            ws,
            columns,
            [_sheet_row(r, master.get(r["product_code"], {}),
                        include_supplier=include_supplier) for r in rows],
            width_map,
        )

    buf = BytesIO()
    wb.save(buf)
    return (
        buf.getvalue(),
        CONTENT_TYPE,
        f"low-stock-{svc.compact_ddmmyyyy(split['as_of'])}.xlsx",
        {"low": len(split["low_rows"]), "all": len(split["all_rows"])},
    )
