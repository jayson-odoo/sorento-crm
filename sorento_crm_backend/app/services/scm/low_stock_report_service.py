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
* **A split, off the shared `workbook_split` module** (PLAN-low-stock-export-split-25sep
  R2, the second case `stock_debt_service` named): `export_low_stock(split=...)` re-files
  the SAME visible rows into a "<key> - Low" / "<key>" sheet pair per supplier, category or
  both - the cap and the row counts stay whole-run figures, never per group.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory
from app.services.error_handler import AppException
from app.services.scm import summary_order_service as svc

logger = logging.getLogger(__name__)

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
        "generated_at": rep.get("generated_at"),
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


#: The in-app page's default split (owner, 26 Sep 01:40Z: "default is split by both"). The
#: export route's own default stays "none" for API callers; the page always sends its split.
VIEW_DEFAULT_SPLIT = "supplier_category"

NO_SUPPLIER = "No supplier"
NO_CATEGORY = "No category"


def _supplier_key(row: dict) -> str:
    """The split's own supplier key (`workbook_split.split_rows` folds a blank the same
    way), so a filter picks exactly the rows a supplier sheet would hold."""
    return row.get("supplier_name") or NO_SUPPLIER


def _category_key(row: dict, master: dict) -> str:
    return master.get(row["product_code"], {}).get("category_code") or NO_CATEGORY


def _facet(rows: list[dict], key) -> list[dict]:
    """`[{key, rows, low}]` over `rows`, sorted by key case-insensitively (AC-5)."""
    counts: dict[str, list[int]] = {}
    for row in rows:
        bucket = counts.setdefault(key(row), [0, 0])
        bucket[0] += 1
        if _is_low(row):
            bucket[1] += 1
    return [
        {"key": k, "rows": counts[k][0], "low": counts[k][1]}
        for k in sorted(counts, key=str.lower)
    ]


def build_low_stock_view(db: Session, *, run_id: Optional[str],
                         include_supplier: bool = True,
                         split: str = VIEW_DEFAULT_SPLIT,
                         suppliers: Optional[list[str]] = None,
                         categories: Optional[list[str]] = None) -> dict:
    """The low stock workbook as a model: the ONE builder behind both the in-app page and
    the file (PLAN-excel-preview-26sep S1, AC-1/AC-2). `export_low_stock` writes exactly
    what this returns, so the screen and the download cannot disagree.

    `rows` holds each kept row once, as `_sheet_row` cells in `columns` order; every sheet
    names its rows by index into it (AC-9), in the order the sheet prints them.

    Filters apply BEFORE the split (AC-4), on the split's own keys: a row is kept when its
    supplier key is in `suppliers` (or `suppliers` is empty) and its category key is in
    `categories` (or empty). Blank keys are the literal "No supplier" / "No category", so
    they are selectable; a key the run does not hold simply matches nothing.

    `facets` are over the WHOLE run, not the kept rows (AC-5): every choice stays visible
    with its row and low count while the user narrows.

    The cap (`MAX_LOW_STOCK_ROWS`) is on the KEPT rows (AC-7, owner ruling 26 Sep Q8), so a
    filter can bring an oversized run under it. Over the cap the model carries the counts
    and `over_cap`, but no rows and no sheets.
    """
    from app.services.scm.workbook_split import SPLIT_VALUES, split_rows, unique_sheet_title

    if split not in SPLIT_VALUES:
        raise AppException(422, f"split must be one of {', '.join(SPLIT_VALUES)}.")
    if split in ("supplier", "supplier_category") and not include_supplier:
        raise AppException(
            422, "Split by supplier is not available without the Supplier column",
        )

    frozen = _split(db, run_id)
    master = frozen["master"]
    everything = frozen["all_rows"]

    def _category(row: dict) -> str:
        return _category_key(row, master)

    wanted_suppliers = set(suppliers or ())
    wanted_categories = set(categories or ())
    kept = [
        r for r in everything
        if (not wanted_suppliers or _supplier_key(r) in wanted_suppliers)
        and (not wanted_categories or _category(r) in wanted_categories)
    ]
    low_count = sum(1 for r in kept if _is_low(r))

    columns = list(LOW_STOCK_COLUMNS)
    if not include_supplier:
        columns.pop(_SUPPLIER_INDEX)

    groups = [] if split == "none" else split_rows(
        kept, split, supplier=lambda r: r.get("supplier_name"), category=_category,
    )
    sheet_count = 2 if split == "none" else 2 * len(groups)
    over_cap = len(kept) > MAX_LOW_STOCK_ROWS

    rows: list[tuple] = []
    sheets: list[dict] = []
    if not over_cap:
        position: dict[int, int] = {}
        for index, r in enumerate(kept):
            position[id(r)] = index
            rows.append(_sheet_row(r, master.get(r["product_code"], {}),
                                   include_supplier=include_supplier))

        def _indexes(group: list[dict]) -> list[int]:
            return [position[id(r)] for r in group]

        if split == "none":
            sheets = [
                {"title": "Low stock", "row_indexes": _indexes([r for r in kept if _is_low(r)]),
                 "low": True},
                {"title": "All", "row_indexes": _indexes(kept), "low": False},
            ]
        else:
            used_titles: set[str] = set()
            for key, group_rows in groups:
                base = unique_sheet_title(key, used_titles, limit=25, reserve=(" - Low",))
                sheets.append({
                    "title": f"{base} - Low",
                    "row_indexes": _indexes([r for r in group_rows if _is_low(r)]),
                    "low": True,
                })
                sheets.append({"title": base, "row_indexes": _indexes(group_rows), "low": False})

    return {
        "run": {"run_id": frozen["run_id"], "as_of": frozen["as_of"],
                "generated_at": frozen["generated_at"]},
        "split": split,
        "columns": columns,
        "rows": rows,
        "sheets": sheets,
        "facets": {
            "suppliers": _facet(everything, _supplier_key),
            "categories": _facet(everything, _category),
        },
        "counts": {"rows": len(kept), "low": low_count, "sheets": sheet_count},
        "over_cap": over_cap,
        "max_rows": MAX_LOW_STOCK_ROWS,
        "filename": f"low-stock-{svc.compact_ddmmyyyy(frozen['as_of'])}.xlsx",
    }


def _write_workbook(view: dict, widths: list[int]) -> bytes:
    """Write the model's sheets, styled like `summary_order_service.write_sheet` (dark bold
    white header, thin border and top-aligned wrapped text on every cell, frozen at A2, the
    column widths), in openpyxl's WRITE-ONLY mode (owner ruling 26 Sep, Q8).

    Why not `write_sheet`: it appends every row and then walks every cell a second time,
    assigning a fresh border and alignment to each, which is where a 5,000-row run spent
    about 90% of its export time. Here each cell is written once and takes a COPY of one of
    two prepared style arrays (header or body), which is exactly what openpyxl's own style
    assignment ends up storing, without the per-cell lookups.
    """
    from copy import copy

    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook(write_only=True)
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")

    columns = view["columns"]
    rows = view["rows"]
    header_style = None
    body_style = None
    for sheet in view["sheets"]:
        ws = wb.create_sheet(title=sheet["title"])
        ws.freeze_panes = "A2"
        for i, width in enumerate(widths):
            ws.column_dimensions[get_column_letter(i + 1)].width = width
        if header_style is None:
            probe = WriteOnlyCell(ws)
            probe.border = border
            probe.alignment = wrap
            body_style = copy(probe._style)
            probe.font = Font(bold=True, color="FFFFFFFF")
            probe.fill = PatternFill("solid", fgColor="FF404040")
            header_style = copy(probe._style)

        def _cells(values, style):
            out = []
            for value in values:
                cell = WriteOnlyCell(ws, value=value)
                cell._style = copy(style)
                out.append(cell)
            return out

        ws.append(_cells(columns, header_style))
        for index in sheet["row_indexes"]:
            ws.append(_cells(rows[index], body_style))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_low_stock(db: Session, *, run_id: Optional[str],
                     include_supplier: bool = True,
                     split: str = "none",
                     suppliers: Optional[list[str]] = None,
                     categories: Optional[list[str]] = None) -> tuple[bytes, str, str, dict]:
    """The workbook for one run: `(bytes, content_type, filename, {"low": n, "all": m,
    "sheets": s})` (AC-10) - all three keys ALWAYS present, never a shape that varies by
    branch (the drill rule from the Stock Debt lane).

    It writes exactly the model `build_low_stock_view` returns for the same arguments
    (PLAN-excel-preview-26sep AC-2): the sheets, in order, with the rows each one names.
    So what follows describes the model as much as the file.

    The counts ride back with the bytes (reviewer item 4): the task stamps `low`/`all` onto
    the download row at `mark_ready` so S5's chat turn can say "Low: 12 of 340" without
    opening the workbook (AC-43), off ONE read of the frozen run.

    `split="none"` (the default) is the two-sheet workbook: "Low stock" FIRST so it is the
    sheet the file opens on, then "All", and `sheets` is 2. Any other `split` re-files the
    same rows (`workbook_split.split_rows`, keyed on the frozen `supplier_name` and the
    master-data `category_code`) into ONE pair of sheets per group, in sanitised-title
    order: `"<key> - Low"` (header only when nothing in the group is low, A3) then
    `"<key>"`. A key longer than 25 characters is cut so the ` - Low` suffix still fits
    Excel's 31-char limit (A4); a collision on the cut gets ` (2)` on BOTH sheets of the
    pair.

    `suppliers` / `categories` (PLAN-excel-preview-26sep AC-4/AC-6) keep only the rows whose
    split key is listed, before the split; omitted or empty keeps everything.

    `include_supplier=False` (S5's chat route, for a contact without the
    `purchase_orders.supplier` reveal key) DROPS the Supplier column rather than blanking
    it (AC-47), and a split by supplier is then refused 422 (R5): the names would leak
    through the sheet titles instead.

    Refused 422 above `MAX_LOW_STOCK_ROWS` kept rows (AC-35; counted after the filters
    since PLAN-excel-preview-26sep AC-7). The route refuses on the same number before it
    creates a download row, so this is the backstop rather than how a buyer finds out.
    """
    view = build_low_stock_view(
        db, run_id=run_id, include_supplier=include_supplier, split=split,
        suppliers=suppliers, categories=categories,
    )
    if view["over_cap"]:
        raise AppException(422, "Narrow the plan first")
    # Review N2: a split whose filters keep nothing is a view with no sheets. A workbook
    # cannot have none (openpyxl would save a lone empty "Sheet" the view never showed), so
    # there is no file that matches the view: refuse rather than write one that does not.
    if not view["sheets"]:
        raise AppException(422, "Nothing matches these filters")

    widths = list(_LOW_STOCK_WIDTHS)
    if not include_supplier:
        widths.pop(_SUPPLIER_INDEX)

    return (
        _write_workbook(view, widths),
        CONTENT_TYPE,
        view["filename"],
        {"low": view["counts"]["low"], "all": view["counts"]["rows"],
         "sheets": view["counts"]["sheets"]},
    )


def filtered_row_count(db: Session, run_id: Optional[str], *,
                       suppliers: Optional[list[str]], categories: Optional[list[str]]) -> int:
    """How many rows the filters keep (AC-7), for the export route's cap check on a run
    whose whole-run count is over the cap. Same builder, same keys, no rows serialised."""
    frozen = _split(db, run_id)
    master = frozen["master"]
    wanted_suppliers = set(suppliers or ())
    wanted_categories = set(categories or ())
    return sum(
        1 for r in frozen["all_rows"]
        if (not wanted_suppliers or _supplier_key(r) in wanted_suppliers)
        and (not wanted_categories or _category_key(r, master) in wanted_categories)
    )


# --------------------------------------------------------------------------- #
# The automation trigger the daily email hangs off (PLAN-excel-preview-26sep S1,
# AC-19..AC-22; owner rulings 26 Sep, Q1 and Q5).
# --------------------------------------------------------------------------- #

READY_TRIGGER = "low_stock_report_ready"


def report_link(run_id: str) -> str:
    """The in-system page for one run, never a file: staff emails link to the page, and the
    deep-link-after-login layout brings a signed-out reader back to it."""
    from app.config import settings

    base = (settings.frontend_base_url or "").rstrip("/")
    return f"{base}/scm/low-stock-report/{run_id}"


def ready_context(db: Session, run_id: str) -> dict:
    """The trigger's template context: `report.{link, as_of, date_label, low, rows}`. The
    counts are the default page's (whole run, no filters) off the same frozen read."""
    from datetime import date as _date

    frozen = _split(db, run_id)
    as_of = frozen["as_of"]
    day = _date.fromisoformat(as_of)
    return {
        "report": {
            "link": report_link(run_id),
            "as_of": as_of,
            "date_label": f"{day.day} {day.strftime('%b %Y')}",
            "low": len(frozen["low_rows"]),
            "rows": len(frozen["all_rows"]),
        },
    }


def dispatch_ready(db: Session, run_id: str) -> dict:
    """Fire `low_stock_report_ready` once for a finished run: every enabled automation on
    it sends its own template to its own `recipient_config` (Q5). The caller decides what a
    failure means; the daily run swallows it.

    Only a COMPLETED run is reported (review B1): `run_reorder` never raises, it marks a
    failed run `failed` and returns, so a failed plan would otherwise mail buyers a "0 low"
    all-clear linking to an empty page. Read off the run row, so no caller can skip it."""
    from app.models.scm import ReorderRun
    from app.services.automation_service import AutomationService

    status = db.query(ReorderRun.status).filter(ReorderRun.id == run_id).scalar()
    if status != "completed":
        logger.warning(
            "low_stock_report_ready not dispatched: run %s is %s, not completed", run_id, status,
        )
        return {"trigger_type": READY_TRIGGER, "fired": 0, "results": []}

    return AutomationService(db).dispatch_event(
        READY_TRIGGER,
        context=ready_context(db, run_id),
        source_kind="reorder_run",
        source_id=str(run_id),
    )
