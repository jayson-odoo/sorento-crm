"""S8 - approving a Loading Plan tells the supplier what to pack.

Ms Tee's third step is one action: approve, and the supplier hears about it on every channel we
can reach them on, and she gets a document she can also paste into chat herself. That is the
whole slice, and the shape below follows from it.

**The notice is a copy, not a view.** The plan re-runs in place every time the container count
changes (AC-E6), so a notice that read through to the plan would silently rewrite itself and
"what did we ask for last month" would have no answer. The lines are copied at approval.

**The document exists before any send is queued.** A notice with no document is never sent, and
a supplier with no address still gets a notice and a downloadable document rather than an error
(AC-F3). That ordering is also what lets email carry the file: the outbox holds a storage
reference and the drainer resolves it.

**One row per channel.** An email that sent and a chat that failed are two facts, and AC-F6 asks
the screen to state what was sent, to whom, on which channel, and when. A single row with a list
of channels would have to pick one status for both.

Frontend contract (Phase 1):

    POST /api/v1/scm/loading-plans/{id}/notices  -> {notice_id, notices: [Notice], document: {...}}
    GET  /api/v1/scm/loading-plans/{id}/notices  -> {data: [Notice]}
    GET  /api/v1/scm/supplier-notices/{id}/document -> {url, filename, expires_in}

    POST /api/v1/scm/container-requests -> {notices: [Notice], document_filename}
      body: {plan_id|supplier_id, lines, channel: 'email'|'chat', recipients: [email]|null,
             chat_contact_id: str|null, note: str|null}
    GET  /api/v1/scm/supplier-notices/chat-contacts?supplier_id&query
      -> {data: [{id, name, phone, channel, suggested}], total, wechat_connected,
          wechat_channel_name, unavailable_reason}

    Notice = {
      id, supplier_id, supplier_name, loading_plan_id, channel: 'email'|'chat',
      recipient: str|null, recipients: [str]|[{respond_contact_id,name,channel}]|null,
      opened_at: iso|null, last_opened_at: iso|null, open_count: int,
      status: 'pending'|'sent'|'failed'|'skipped',
      status_reason: str|null, sent_at: iso|null, attempt_count: int, last_error: str|null,
      document_filename: str|null, has_document: bool,
      xlsx_filename: str|null, has_xlsx: bool,
      public_url: str|null, link_retired: bool,
      container_type, container_count, planned_cbm, line_count, production_line_count,
      created_at: iso, created_by: str|null,
    }

    POST /api/v1/scm/container-requests/document?format=xlsx|pdf -> the bytes, no notice
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta
from html import escape
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.base import company_scope, set_company_scope
from app.models.scm import LoadingPlan, LoadingPlanLine
from app.models.supplier_notice import SupplierNotice, SupplierNoticeLine
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm.supplier_scope import is_uuid, supplier_label

if TYPE_CHECKING:  # the model is imported lazily at every use site, as this module's peers are
    from app.services.scm.supplier_document_model import SheetModel

logger = logging.getLogger(__name__)

EVENT_KEY = "supplier_loading_notice"

#: The two channels a loading-plan APPROVAL still writes a row on: it sends on everything it
#: can reach, so an email that sent and a chat that did not are two rows. A container request
#: does NOT use this - since R9 the sender picks one channel in the send dialog and exactly
#: one row is written (see `request_and_notify`).
CHANNELS = ("email", "chat")

#: What a container request may be sent on (R9). Email is the default so a caller written
#: before the dialog existed behaves exactly as it did.
SEND_CHANNELS = ("email", "chat")

#: The notice statuses that mean the ask LEFT THE BUILDING. `sent` is handed to the outbox or
#: to Respond.io; `pending` is a row whose dispatch has not reported yet, which is still an
#: ask in flight. `failed` and `skipped` are not: nothing reached the supplier, so a plan
#: carrying only those has not been sent and is still the planner's to finish or to delete.
WENT_OUT_STATUSES = frozenset({"sent", "pending"})

#: The Respond.io channel source a supplier request rides on (R10, captain 27 Aug: "chat
#: should be using wechat" - the factories are in China). Matched against
#: `respond_channels.source`, which the template sync writes off `GET /v2/space/channel`.
WECHAT_CHANNEL_SOURCE = "wechat"

#: The template use case a chat send falls back to outside the 24h window - the same shape
#: every other chat reply uses (`respond_template.CHAT_TEMPLATE_USE_CASES`), so an admin maps
#: an approved template to it on the same screen. Nothing is seeded: connecting the WeChat
#: channel and approving its template is a Respond.io task with its own go (R10), and until
#: it is done an out-of-window send is refused rather than silently dropped.
CHAT_USE_CASE = "supplier_request_chat"

#: Deliberately not a full RFC 5322 parser: the address is typed by a person into a chip
#: field, and the only mistakes worth catching here are the ones that would make the outbox
#: row undeliverable. The route's `EmailStr` does the strict pass; this guards the service
#: for every other caller.
_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")

#: Subject/body per `notice_type`, keyed the same as the column. Both notice types travel
#: through the same `EVENT_KEY` (one registered email event, `EMAIL_EVENT_REGISTRY`), so the
#: wording is the only thing that may differ between them - never a second event to register.
_EMAIL_COPY = {
    "loading": {
        "subject": "Loading notice / 装柜通知",
        "body": (
            "Please see the attached loading notice for the items to pack and load, and the "
            "items that need production.\n\n"
            "请查收附件装柜通知，内含需装柜及需生产的项目。"
        ),
    },
    "container_request": {
        "subject": "Container request / 配柜要求",
        "body": (
            "Please see the attached request for the next container - please pack the items "
            "listed for us. Container details will follow once they are confirmed.\n\n"
            "请查收附件配柜要求，请为我们准备以下项目装箱，柜型资料将在确认后另行通知。"
        ),
    },
}


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _supplier(db: Session, supplier_id: str) -> dict:
    """Company-scoped, injection-safe supplier lookup (B1).

    A bare `SELECT ... FROM suppliers WHERE id = :i` let a caller in company A resolve
    company B's supplier - the notice would then be emailed to B's supplier with B's name and
    address handed back in the response. `is_uuid` (the same guard `supplier_scope.py` uses)
    keeps a non-id value from reaching the UUID column comparison and 500ing; the company
    predicate is the same builder `supplier_scope.supplier_row` uses internally, reproduced
    here rather than through that helper because this module needs `email` and
    `phone_number` (the chat picker's prefill, R10), which `supplier_row` deliberately
    does not carry (the upload channels that helper serves only
    ever show the supplier's name and code back as confirmation).
    """
    if not is_uuid(supplier_id):
        raise AppException(404, "Supplier not found")
    predicate, params = company_sql_predicate(db, "company_id", param_prefix="sn")
    row = db.execute(
        text(
            "SELECT id, supplier_code, supplier_name, email, phone_number FROM suppliers "
            f"WHERE id = :i AND {predicate or 'true'}"
        ),
        {"i": str(supplier_id), **params},
    ).mappings().first()
    if row is None:
        raise AppException(404, "Supplier not found")
    return dict(row)


# --------------------------------------------------------------------------- document


def _document_html(*, supplier: dict, plan: Optional[LoadingPlan], pack: list[dict],
                   produce: list[dict], notice_type: str = "loading",
                   sheet: Optional["SheetModel"] = None) -> str:
    """The notice, in both languages, in the shape the supplier already reads (AC-F2).

    Bilingual side by side rather than two documents: the supplier's staff read the Chinese and
    our own people have to be able to check what went out, and two files drift the moment one is
    edited. The production items are a separate table, not a flag on a row, because they are a
    different ask - one is "load this", the other is "make this".

    `notice_type='container_request'` is the S13 sibling
    (`PLAN-scm-loading-plan-demand-first.md` section 4): no container has been chosen yet, so
    the meta table states nothing about containers/CBM and the production section (which is
    plan-shaped - it reads `unfinished_at_supplier`) is dropped; `plan` is None. Everything
    else - the styling, the bilingual pack table - is the same document.

    `sheet` is S4/R12: the ONE `SheetModel` the xlsx is drawn from, so the PDF prints the
    supplier's own ten columns with their merges, their yellow fields and their red figures
    rather than four of our own naming. Optional because a notice minted before S4 has no
    model behind it and its PDF must still render (AC-H2).
    """
    # A container request has no CBM yet (that stage is not reached until the supplier packs -
    # see the module docstring), so `request_and_notify` always sends `cbm: None`; a CBM
    # column that never carries a value reads as a field the supplier is meant to fill in and
    # never does. Dropped for that variant only - the loading notice keeps its columns
    # byte-identical, because a real Loading Plan line always has one.
    show_cbm = notice_type != "container_request"
    colspan = 5 if show_cbm else 4

    def rows(items: list[dict], qty_label: str) -> str:
        if not items:
            return (
                f'<tr><td colspan="{colspan}" class="empty">'
                "Nothing in this section / 此部分无项目</td></tr>"
            )
        out = []
        for i, ln in enumerate(items, start=1):
            cbm_cell = ""
            if show_cbm:
                cbm = ln.get("cbm")
                cbm_cell = f"<td class='num'>{'' if cbm is None else f'{float(cbm):.3f}'}</td>"
            out.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td>{escape(str(ln.get('item_code') or ''))}</td>"
                f"<td>{escape(str(ln.get('product_name') or ''))}</td>"
                f"<td class='num'>{_qty(ln.get('qty'))}</td>"
                f"{cbm_cell}"
                "</tr>"
            )
        return "".join(out)

    if notice_type == "container_request":
        title = "Container Request / 配柜要求"
        intro = (
            '<p class="sub">Please pack the items below for the next container - the '
            "container type and volume will follow once they are confirmed. / "
            "请为下一个货柜准备以下项目，柜型及体积将在确认后另行通知。</p>"
        )
        sections = _sheet_sections(sheet) if sheet is not None else f"""
  <h2>Requested items / 请求项目</h2>
  <table>
    <thead><tr>
      <th>#</th><th>Item / 型号</th><th>Description / 品名</th>
      <th class="num">Qty / 数量</th>
    </tr></thead>
    <tbody>{rows(pack, 'Qty')}</tbody>
  </table>
"""
    else:
        title = "Loading Notice / 装柜通知"
        departure = plan.inventory_as_of.strftime("%d/%m/%Y") if plan.inventory_as_of else "-"
        containers = (
            f"{plan.container_count} x {escape(str(plan.container_type or ''))}".strip()
            if plan.container_count
            else "-"
        )
        intro = f"""
  <table class="meta">
    <tr><td class="k">Containers / 柜数</td><td>{containers}</td></tr>
    <tr><td class="k">Volume planned / 计划体积</td><td>{_cbm(plan.planned_cbm)} cbm</td></tr>
    <tr><td class="k">Capacity / total 容量</td><td>{_cbm(plan.capacity_cbm)} cbm</td></tr>
    <tr><td class="k">Inventory as at / 库存日期</td><td>{departure}</td></tr>
  </table>
"""
        sections = f"""
  <h2>To pack and load / 需装柜</h2>
  <table>
    <thead><tr>
      <th>#</th><th>Item / 型号</th><th>Description / 品名</th>
      <th class="num">Qty / 数量</th><th class="num">CBM / 体积</th>
    </tr></thead>
    <tbody>{rows(pack, 'Qty')}</tbody>
  </table>

  <h2>Needs production / 需生产</h2>
  <table>
    <thead><tr>
      <th>#</th><th>Item / 型号</th><th>Description / 品名</th>
      <th class="num">Qty / 数量</th><th class="num">CBM / 体积</th>
    </tr></thead>
    <tbody>{rows(produce, 'Qty')}</tbody>
  </table>
"""
    # Their sheet is eleven columns wide and 120 rows long; portrait would either clip it or
    # shrink it past reading. The loading notice keeps its own page.
    page = "A4 landscape" if sheet is not None else "A4"
    return f"""
<html><head><meta charset="utf-8"><style>
  @page {{ size: {page}; margin: 10mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, 'Noto Sans CJK SC', sans-serif; font-size: 10pt;
          color: #111; }}
  h1 {{ font-size: 15pt; margin: 0 0 2mm; }}
  h2 {{ font-size: 11pt; margin: 6mm 0 2mm; border-bottom: 1px solid #999; padding-bottom: 1mm; }}
  .sub {{ color: #555; font-size: 9pt; margin: 0 0 4mm; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ border: 1px solid #bbb; padding: 1.6mm 2mm; text-align: left; }}
  th {{ background: #f2f2f2; font-weight: 600; }}
  td.num, th.num {{ text-align: right; }}
  td.empty {{ color: #777; text-align: center; }}
  .meta td {{ border: none; padding: 0.6mm 0; }}
  .meta td.k {{ color: #555; width: 40mm; }}
  table.sheet {{ font-family: "Songti SC", "宋体", Calibri, sans-serif; font-size: 8pt; }}
  table.sheet th, table.sheet td {{ padding: 0.8mm 1mm; text-align: center;
                                    vertical-align: middle; }}
  table.sheet tr {{ page-break-inside: avoid; }}
  table.sheet th.doc-title {{ font-size: 13pt; }}
  table.sheet td.fill {{ background: #ffff00; }}
  table.sheet td.red, table.sheet tr.totals td {{ color: #ff0000; }}
  table.sheet tr.totals td {{ font-weight: 600; }}
  table.sheet span.en {{ display: block; color: #555; font-size: 7pt; font-weight: 400; }}
</style></head><body>
  <h1>{title}</h1>
  <p class="sub">{escape(str(supplier.get('supplier_name') or ''))}
     ({escape(str(supplier.get('supplier_code') or ''))})</p>
  {intro}
{sections}
</body></html>
""".strip()


def _sheet_sections(sheet: "SheetModel") -> str:
    """Their own sheet as an HTML table - the same model the xlsx is written from (R12).

    Their merged families become `rowspan`, their yellow fields and red figures become
    classes, and their header keeps its Chinese with our English under it. The header sits in
    a `thead` so it repeats on every page of a 120-row list, and every row is
    `page-break-inside: avoid` so a family is never split across a page.
    """
    width = len(sheet.columns)
    title = (
        f'<tr><th class="doc-title" colspan="{width}">{escape(sheet.title)}</th></tr>'
        if sheet.title
        else ""
    )
    head = "".join(
        "<th>"
        + escape(column.label)
        + (f'<span class="en">{escape(column.label_en)}</span>' if column.label_en else "")
        + "</th>"
        for column in sheet.columns
    )
    body = "".join(
        "<tr>" + "".join(_sheet_cell(cell) for cell in row.cells) + "</tr>"
        for row in sheet.rows
    )
    foot = (
        '<tr class="totals">'
        + "".join(_sheet_cell(cell) for cell in sheet.totals.cells)
        + "</tr>"
        if sheet.totals
        else ""
    )
    return f"""
  <table class="sheet">
    <thead>{title}<tr>{head}</tr></thead>
    <tbody>{body}</tbody>
    <tfoot>{foot}</tfoot>
  </table>
"""


def _sheet_cell(cell) -> str:
    """One cell, or nothing at all when a merge above it already covers this position."""
    if cell.covered:
        return ""
    attrs = ""
    if cell.rowspan > 1:
        attrs += f' rowspan="{cell.rowspan}"'
    if cell.colspan > 1:
        attrs += f' colspan="{cell.colspan}"'
    classes = [name for name, on in (("fill", cell.fill), ("red", cell.red)) if on]
    if classes:
        attrs += f' class="{" ".join(classes)}"'
    return f"<td{attrs}>{_sheet_value(cell.value)}</td>"


def _sheet_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return escape(str(value))
    if isinstance(value, (int, float)):
        number = float(value)
        return str(int(number)) if number == int(number) else f"{number:g}"
    return escape(str(value))


def _qty(v) -> str:
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}"


def _cbm(v) -> str:
    return "0.000" if v is None else f"{float(v):.3f}"


def render_document(html: str) -> bytes:
    """HTML to PDF bytes, through the shared WeasyPrint guard."""
    from app.services.pdf_render import PDFRenderingUnavailable

    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # noqa: BLE001 - native libs missing is a deployment fact
        raise PDFRenderingUnavailable(
            "PDF rendering is unavailable on this host (WeasyPrint native libraries missing)."
        ) from exc
    return HTML(string=html).write_pdf()


# --------------------------------------------------------------------------- build


def _plan_sections(db: Session, plan: LoadingPlan) -> tuple[list[dict], list[dict]]:
    """What to pack, and what has to be made first.

    Pack = the lines the plan actually allocated volume to. A deferred line is deliberately NOT
    asked for: it did not fit, and telling a supplier to pack something we then leave behind is
    how a container goes out wrong.
    """
    from app.services.scm.loading_plan_service import unfinished_at_supplier

    lines = (
        db.query(LoadingPlanLine)
        .filter(LoadingPlanLine.plan_id == plan.id)
        .order_by(LoadingPlanLine.rank)
        .all()
    )
    names = _product_names(db, [str(ln.product_id) for ln in lines if ln.product_id])

    pack = [
        {
            "product_id": str(ln.product_id) if ln.product_id else None,
            "item_code": ln.item_code,
            "product_name": names.get(str(ln.product_id)) if ln.product_id else None,
            "po_number": ln.po_number,
            "qty": _f(ln.qty_planned),
            "cbm": _f(ln.cbm_planned),
        }
        for ln in lines
        if ln.status in ("allocated", "partial") and _f(ln.qty_planned)
    ]

    produce = [
        {
            "product_id": None,
            "item_code": r.get("item_code"),
            "product_name": r.get("product_name"),
            "po_number": None,
            "qty": r.get("qty_unfinished"),
            "cbm": None,
        }
        for r in unfinished_at_supplier(db, str(plan.supplier_id))
    ]
    return pack, produce


def _product_names(db: Session, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id, product_name FROM products WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": list({i for i in ids if i})},
    ).mappings().all()
    return {str(r["id"]): r["product_name"] for r in rows}


def approve_and_notify(db: Session, plan_id: str, *, actor: Optional[str] = None) -> dict:
    """Approve a plan: freeze what was asked for, make the document, tell the supplier.

    Returns the notices created, newest channel first. Raises only when there is nothing to
    send or nothing to send it about; a supplier we cannot reach is a `skipped` notice with a
    reason, not a failure, because the document is still the point.
    """
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).one_or_none()
    if plan is None:
        raise AppException(404, "Loading plan not found")

    supplier = _supplier(db, str(plan.supplier_id))
    pack, produce = _plan_sections(db, plan)
    if not pack and not produce:
        raise AppException(
            422,
            "This plan has nothing to pack and nothing in production, so there is nothing to "
            "tell the supplier.",
        )

    document = render_document(
        _document_html(supplier=supplier, plan=plan, pack=pack, produce=produce)
    )
    filename = _filename(supplier, plan)
    provider, key = _store(document, filename)

    notices: list[SupplierNotice] = []
    for channel in CHANNELS:
        notice = SupplierNotice(
            supplier_id=str(plan.supplier_id),
            loading_plan_id=str(plan.id),
            notice_type="loading",
            channel=channel,
            document_filename=filename,
            storage_provider=provider,
            storage_key=key,
            container_type=plan.container_type,
            container_count=plan.container_count,
            planned_cbm=plan.planned_cbm,
            line_count=len(pack),
            production_line_count=len(produce),
            created_by=actor,
        )
        db.add(notice)
        db.flush()
        for i, ln in enumerate(pack + produce):
            db.add(
                SupplierNoticeLine(
                    notice_id=str(notice.id),
                    product_id=ln.get("product_id"),
                    item_code=ln.get("item_code"),
                    product_name=ln.get("product_name"),
                    po_number=ln.get("po_number"),
                    qty=ln.get("qty") or 0,
                    cbm=ln.get("cbm"),
                    kind="pack" if i < len(pack) else "produce",
                    sort_order=i,
                )
            )
        notices.append(notice)

    db.flush()
    for notice in notices:
        _dispatch(db, notice, supplier)
    db.commit()

    return {
        "notices": [serialize(db, n) for n in notices],
        "document_filename": filename,
    }


def _filename(supplier: dict, plan: LoadingPlan) -> str:
    code = (supplier.get("supplier_code") or "supplier").replace("/", "-").replace(" ", "-")
    stamp = (plan.computed_at or datetime.utcnow()).strftime("%Y%m%d")
    return f"loading-notice-{code}-{stamp}.pdf"


def _request_filename(supplier: dict) -> str:
    code = (supplier.get("supplier_code") or "supplier").replace("/", "-").replace(" ", "-")
    stamp = datetime.utcnow().strftime("%Y%m%d")
    return f"container-request-{code}-{stamp}.pdf"


def _product_catalogue(db: Session, product_ids: list) -> dict[str, dict]:
    """`item_code` / `product_name` off the catalogue, for lines that arrive as a bare
    product id (a container request has no purchase-order line to read them off, the way a
    Loading Plan line does).

    BL-2 (SECURITY): company-scoped, same builder `_supplier`/`supplier_scope` use. Without
    it a caller could name a FOREIGN company's product id, have it resolve here, and have
    that company's product_code/product_name copied into `supplier_notice_lines` and the
    emailed PDF. A foreign id now simply is not in the catalogue, so `request_and_notify`'s
    own `requested - catalogue` check reports it as unknown (422).
    """
    ids = [str(i) for i in product_ids if i]
    if not ids:
        return {}
    predicate, params = company_sql_predicate(db, "company_id", param_prefix="pc")
    rows = db.execute(
        text(
            "SELECT id, product_code, product_name FROM products "
            f"WHERE id = ANY(CAST(:ids AS uuid[])) AND {predicate or 'true'}"
        ),
        {"ids": ids, **params},
    ).mappings().all()
    return {
        str(r["id"]): {"item_code": r["product_code"], "product_name": r["product_name"]}
        for r in rows
    }


def _set_catalogue(db: Session, set_ids: list) -> dict[str, dict]:
    """`set_code` / `name` off our product sets, for a line that names a SET (F12, AC-F12.6).

    Company-scoped for the same reason `_product_catalogue` is: without it a caller could
    name a foreign company's set id and have its code copied into `supplier_notice_lines` and
    the emailed document.
    """
    ids = [str(i) for i in set_ids if i]
    if not ids:
        return {}
    predicate, params = company_sql_predicate(db, "company_id", param_prefix="sc")
    rows = db.execute(
        text(
            "SELECT id, set_code, name FROM product_sets "
            f"WHERE id = ANY(CAST(:ids AS uuid[])) AND {predicate or 'true'}"
        ),
        {"ids": ids, **params},
    ).mappings().all()
    return {
        str(r["id"]): {"item_code": r["set_code"], "product_name": r["name"]}
        for r in rows
    }


def _request_pack(db: Session, lines: list[dict]) -> list[dict]:
    """The reviewed lines with the catalogue's own words on them, or a 422 naming what is not ours.

    A line names a product OR one of our product SETS (R19). A set line carries NO product
    id: the supplier sells the whole WC and our catalogue holds only its parts, so the
    document goes out under the set code, which is the code they wrote in the first place.
    `supplier_notice_lines.product_id` is nullable, which is what makes that recordable.

    B2: a line naming a malformed id ("nope") 500'd `_product_catalogue`'s
    `CAST(:ids AS uuid[])`, and a line naming a well-formed but unknown product 500'd later,
    on the `SupplierNoticeLine.product_id` foreign key at flush. Both are a form mistake, not
    a server error: filter to id-shaped values BEFORE the cast, resolve the catalogue off that
    filtered set, then refuse anything the catalogue could not name - which is exactly
    `requested - catalogue`, whether the id never parsed or simply is not ours.
    """
    requested_ids = {str(ln.get("product_id")) for ln in lines if ln.get("product_id")}
    catalogue = _product_catalogue(db, [pid for pid in requested_ids if is_uuid(pid)])
    unknown = requested_ids - set(catalogue)
    if unknown:
        raise AppException(
            422,
            "These products do not exist: " + ", ".join(sorted(unknown)),
            detail="product_id",
        )

    requested_sets = {str(ln.get("product_set_id")) for ln in lines if ln.get("product_set_id")}
    sets = _set_catalogue(db, [sid for sid in requested_sets if is_uuid(sid)])
    unknown_sets = requested_sets - set(sets)
    if unknown_sets:
        raise AppException(
            422,
            "These product sets do not exist: " + ", ".join(sorted(unknown_sets)),
            detail="product_set_id",
        )

    def _named(ln: dict) -> dict:
        if ln.get("product_set_id"):
            return sets.get(str(ln["product_set_id"])) or {}
        return catalogue.get(str(ln.get("product_id"))) or {}

    return [
        {
            # None on a set line: the ask is the whole set, and naming one member on the
            # record would make the document disagree with the row it came from.
            "product_id": None if ln.get("product_set_id") else ln.get("product_id"),
            "item_code": _named(ln).get("item_code"),
            "product_name": _named(ln).get("product_name"),
            "po_number": None,
            "qty": ln.get("qty"),
            "cbm": None,
        }
        for ln in lines
    ]


def _request_sheet(db: Session, supplier_id: str, pack: list[dict]) -> "SheetModel":
    """The document, built ONCE (R12 / AC-D7).

    Both renderers take this object. Building it twice would let the emailed sheet and the
    emailed PDF disagree about the same ask, which is the defect S4 exists to close.
    """
    from app.services.scm import supplier_document_model

    return supplier_document_model.build(db, supplier_id=str(supplier_id), lines=pack)


def _render_request_pdf(
    supplier: dict, pack: list[dict], sheet: Optional["SheetModel"] = None
) -> bytes:
    return render_document(
        _document_html(
            supplier=supplier,
            plan=None,
            pack=pack,
            produce=[],
            notice_type="container_request",
            sheet=sheet,
        )
    )


def request_document(
    db: Session, *, supplier_id: str, lines: list[dict], fmt: str
) -> tuple[bytes, str]:
    """The request as a file, WITHOUT sending anything (R23).

    The gear menu on "What to ask X for" hands Ms Tee the PDF or the supplier's sheet for the
    quantities currently on her screen - to read, to check, to forward by hand. That is not a
    send: no notice row, no token, no email, nothing the supplier has been told. So this
    renders and returns, and stores nothing.

    Same two builders `request_and_notify` uses, deliberately not forked: the moment the
    downloaded sheet and the emailed one can differ, the download stops being worth having.
    """
    if fmt not in ("pdf", "xlsx"):
        raise AppException(422, f"Unknown document format: {fmt}")

    supplier = _supplier(db, supplier_id)
    pack = _request_pack(db, lines)
    sheet = _request_sheet(db, str(supplier_id), pack)

    if fmt == "xlsx":
        from app.services.scm import container_request_xlsx

        return (
            container_request_xlsx.render(sheet),
            container_request_xlsx.filename(supplier),
        )
    return _render_request_pdf(supplier, pack, sheet), _request_filename(supplier)


# ------------------------------------------------------- who this send is addressed to


def _email_recipients(supplier: dict, recipients: Optional[list]) -> list[str]:
    """The addresses an email send goes to, or a 422 naming what is wrong (AC-C2).

    The supplier's own address is the DEFAULT, not the limit: the person who packs and the
    person who quotes are rarely the same mailbox, and before R9 there was no way to add the
    second one. Zero addresses is refused rather than turned into a `skipped` row: the
    approval path may still record "we could not reach them", but a send dialog that just
    asked the user who to send to has no business answering "nobody".
    """
    if recipients is None:
        raw = [supplier.get("email")]
    else:
        raw = list(recipients)

    seen: list[str] = []
    for value in raw:
        address = str(value or "").strip()
        if not address:
            continue
        if not _EMAIL_RE.match(address):
            raise AppException(
                422, f"This is not an email address: {address}", code="invalid_recipient"
            )
        if address.lower() not in {a.lower() for a in seen}:
            seen.append(address)

    if not seen:
        raise AppException(
            422,
            "Nobody would receive this request. Add at least one email address.",
            code="no_recipients",
        )
    return seen


def wechat_channel(db: Session):
    """The workspace's WeChat channel row, or None when none is connected (R10).

    Read off `respond_channels`, which the template sync fills from
    `GET /v2/space/channel` - so this is the workspace's own answer, cached in our database
    by the same job that keeps the templates, rather than a live call on the send path.
    """
    from app.models.respond_template import RespondChannel

    return (
        db.query(RespondChannel)
        .filter(
            RespondChannel.is_active.is_(True),
            RespondChannel.source.ilike(f"%{WECHAT_CHANNEL_SOURCE}%"),
        )
        .order_by(RespondChannel.created_at)
        .first()
    )


def _require_wechat_channel(db: Session):
    channel = wechat_channel(db)
    if channel is None:
        raise AppException(
            422,
            "No WeChat channel is connected in the Respond.io workspace, so this request "
            "cannot be sent by chat.",
            code="wechat_channel_missing",
        )
    return channel


def _chat_contact(db: Session, chat_contact_id: Optional[str]):
    """The Respond contact a chat send is addressed to (AC-C3)."""
    from app.models.access import RespondContact

    value = str(chat_contact_id or "").strip()
    if not value:
        raise AppException(
            422,
            "Pick the WeChat contact to send this request to.",
            code="chat_contact_required",
        )
    contact = (
        db.query(RespondContact).filter(RespondContact.id == value).one_or_none()
    )
    if contact is None:
        raise AppException(
            422, "That chat contact no longer exists.", code="chat_contact_not_found"
        )
    return contact


def _contact_label(contact) -> str:
    return (
        contact.name
        or " ".join(filter(None, [contact.first_name, contact.last_name])).strip()
        or contact.phone_number
        or str(contact.id)
    )


def _chat_identifier(db: Session, contact) -> str:
    """What Respond.io addresses this contact by, or a 422 saying we cannot reach them."""
    from app.services.respond_identifier import resolve_send_identifier

    identifier = resolve_send_identifier(
        db, str(contact.respond_io_id or contact.phone_number or "").strip()
    )
    if not identifier:
        raise AppException(
            422,
            f"{_contact_label(contact)} has no Respond.io identity, so nothing can be sent "
            "to them.",
            code="chat_contact_unreachable",
        )
    return identifier


def _chat_window_open(db: Session, identifier: str, respond_contact_id: str) -> bool:
    """Whether the contact wrote to us inside the 24h window (the composer's own answer).

    A seam, like `_chat_send`: the real one is a live Respond.io call, and a suite that had
    to reach api.respond.io to test our own branch would be testing somebody else's uptime.
    """
    from app.services.respond_messaging_service import get_window_state

    return bool(
        get_window_state(db, identifier, respond_contact_id=respond_contact_id).get("open")
    )


def _chat_template_ready(db: Session) -> bool:
    """Whether an approved template is mapped for `CHAT_USE_CASE` (the out-of-window path)."""
    from app.services.respond_template_service import get_default_row, serialize_default

    return bool(
        serialize_default(CHAT_USE_CASE, get_default_row(db, CHAT_USE_CASE)).get("is_valid")
    )


def _assert_chat_deliverable(db: Session, contact, identifier: str) -> None:
    """Refuse a chat send that could not land, BEFORE anything is written (AC-C5).

    Outside the 24h window a template is the only deliverable message, so with no approved
    one mapped there is nothing to send and saying so is the whole answer: seeding the
    template is a Respond.io task with its own go (R10). Checked here rather than left to the
    composer's own 422 so the refusal costs nothing - no notice row, and above all no retired
    link, which would leave the supplier holding a dead URL and no replacement.

    The window lookup is cached for 45 seconds by `get_window_state`, so the composer's own
    call a moment later is the same fact, not a second HTTP round trip.
    """
    if _chat_window_open(db, identifier, str(contact.id)):
        return
    if not _chat_template_ready(db):
        raise AppException(
            422,
            f"{_contact_label(contact)} last wrote to us more than 24 hours ago, and no "
            "approved chat template is configured for supplier requests, so nothing can be "
            "delivered.",
            code="template_missing",
        )


def _chat_send(db: Session, **kwargs) -> dict:
    """The composer's own send, called rather than copied (R10).

    `send_chat_message_for` already owns the whole of it: the 24h window branch, the raw text
    inside it, the approved template outside it, the Respond error handling and - the reason
    this must not be forked - the `integration_log` outbox row on success AND failure. A
    second send path here would diverge from it on the first bug.

    A one-line seam so a suite can stand in for Respond.io without reaching into another
    module's namespace.
    """
    from app.services.respond_chat_template_service import send_chat_message_for

    return send_chat_message_for(db, **kwargs)


def chat_contacts(db: Session, *, supplier_id: str, query: Optional[str] = None) -> dict:
    """WeChat contacts to pick from, the supplier's own number first (AC-C3).

    `respond_contacts` carries no channel column - Respond.io decides which channel a contact
    is reachable on - so this lists the contacts and states, once, whether the workspace has a
    WeChat channel at all. With none connected the picker is still readable and the FE
    disables the Chat option with the reason, which is what AC-C3 asks for.
    """
    from app.models.access import RespondContact

    supplier = _supplier(db, supplier_id)
    phone = _digits(supplier.get("phone_number"))
    channel = wechat_channel(db)

    q = db.query(RespondContact)
    term = (query or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(
            RespondContact.name.ilike(like)
            | RespondContact.phone_number.ilike(like)
            | RespondContact.respond_io_id.ilike(like)
        )
    rows = (
        q.order_by(func.lower(func.coalesce(RespondContact.name, RespondContact.phone_number)))
        .limit(_CHAT_CONTACT_LIMIT)
        .all()
    )

    data = [
        {
            "id": str(c.id),
            "name": _contact_label(c),
            "phone": c.phone_number,
            # What the send would actually ride on. Null when nothing is connected, so the
            # FE never labels a contact with a channel that does not exist.
            "channel": WECHAT_CHANNEL_SOURCE if channel is not None else None,
            "suggested": bool(phone) and _digits(str(c.phone_number or "")) == phone,
        }
        for c in rows
    ]
    # The supplier's own number first: it is the one Ms Tee means nine times out of ten, and
    # the factory often answers on a colleague's account the tenth.
    data.sort(key=lambda row: (not row["suggested"], (row["name"] or "").lower()))
    return {
        "data": data,
        "total": len(data),
        "wechat_connected": channel is not None,
        "wechat_channel_name": channel.name if channel is not None else None,
        "unavailable_reason": (
            None
            if channel is not None
            else "No WeChat channel is connected in the Respond.io workspace."
        ),
    }


#: A picker, not a listing: the supplier's contact is at the top and the rest is what the
#: search term narrowed to. More than this is a scroll nobody reads.
_CHAT_CONTACT_LIMIT = 20


def _digits(value: Optional[str]) -> str:
    """A phone number reduced to what two of them can be compared on.

    `+86 138-0000-0000` and `8613800000000` are the same number written by two systems.
    """
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def request_and_notify(
    db: Session,
    *,
    supplier_id: str,
    lines: list[dict],
    actor: Optional[str] = None,
    loading_plan_id: Optional[str] = None,
    channel: str = "email",
    recipients: Optional[list] = None,
    chat_contact_id: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """Send a container request - the S13 sibling of `approve_and_notify`.

    Same shape: a document before any send is queued, a supplier with no address on file
    still gets a notice and a downloadable document (AC-F3, carried over unchanged). What
    differs is the source of the lines - Ms Tee's reviewed quantities, not a Loading Plan's
    allocation - and the wording, since no container has been chosen yet (`_document_html` /
    `_EMAIL_COPY`, keyed on `notice_type`).

    ONE row, for the channel the sender chose (R9). Until S3 this wrote a row per channel and
    the chat one was `skipped` on every send since 343 - a row that always says "not done" is
    noise, not a record. `recipients` are the email addresses (defaulting to the supplier's
    own); `chat_contact_id` is the Respond contact a chat send is addressed to; `note` is the
    sender's own line, prepended to the bilingual body.

    Everything that would make the send impossible is checked BEFORE anything is written or
    retired (AC-C5: "nothing else changes"). Retiring the live link for a send that then
    could not go out would leave the supplier holding a dead URL and no new one.
    """
    if channel not in SEND_CHANNELS:
        raise AppException(422, f"Unknown channel: {channel}", code="unknown_channel")

    supplier = _supplier(db, supplier_id)
    # The lines first: a request naming a product that is not ours is a mistake about THIS
    # request, and reporting it before the addressing keeps that 422 the same one it always
    # was for every caller that never passes a channel.
    pack = _request_pack(db, lines)

    to: list[str] = []
    contact = None
    identifier: Optional[str] = None
    # What the notice records about WHO this went to (AC-C2): the addresses, or the one
    # contact. Built here, where the channel is known, so the row cannot disagree with the
    # send that produced it.
    addressed_to: list = []
    if channel == "email":
        to = _email_recipients(supplier, recipients)
        addressed_to = list(to)
    else:
        _require_wechat_channel(db)
        contact = _chat_contact(db, chat_contact_id)
        identifier = _chat_identifier(db, contact)
        _assert_chat_deliverable(db, contact, identifier)
        addressed_to = [
            {
                "respond_contact_id": str(contact.id),
                "name": _contact_label(contact),
                "channel": WECHAT_CHANNEL_SOURCE,
            }
        ]

    sheet = _request_sheet(db, str(supplier_id), pack)

    document = _render_request_pdf(supplier, pack, sheet)
    filename = _request_filename(supplier)
    provider, key = _store(document, filename)

    # F4: their own sheet back to them, with the quantity to load filled in - the same model
    # the PDF above was drawn from (R12). Best-effort by design: if the render or the store
    # below failed, the request would otherwise die for the sake of the SECOND copy of an ask
    # the PDF already states.
    xlsx_filename: Optional[str] = None
    xlsx_provider: Optional[str] = None
    xlsx_key: Optional[str] = None
    try:
        from app.services.scm import container_request_xlsx

        xlsx_filename = container_request_xlsx.filename(supplier)
        xlsx_provider, xlsx_key = _store(
            container_request_xlsx.render(sheet), xlsx_filename
        )
    except Exception:  # noqa: BLE001 - the PDF and the notice still go
        xlsx_filename = xlsx_provider = xlsx_key = None
        logger.warning(
            "container request for supplier %s: the stock-list xlsx could not be produced; "
            "the notice and its PDF are unaffected",
            supplier_id,
            exc_info=True,
        )

    # F8/AC-C7: this send is the current ask for THIS PLAN, so that plan's link already out
    # there stops answering (R3/R11 - the supplier's other plans keep theirs). Done BEFORE
    # the new rows exist so there is never a moment with two live links for one plan.
    _retire_public_tokens(db, str(supplier_id), loading_plan_id=loading_plan_id)

    # ONE token per SEND (R23, captain 27 Aug: "email and chat need to both have link"). The
    # supplier clicks it in the email, or reads it in the chat message; it is the same
    # credential either way, and a second one would be a second live link to one ask.
    public_token = secrets.token_urlsafe(_PUBLIC_TOKEN_BYTES)
    public_token_expires_at = datetime.utcnow() + timedelta(days=PUBLIC_TOKEN_TTL_DAYS)

    notice = SupplierNotice(
        supplier_id=str(supplier_id),
        # The plan this ask belongs to (part 4, R1). It was None while a container request
        # had no row behind it; the list's Sent column reads this link.
        loading_plan_id=loading_plan_id,
        notice_type="container_request",
        channel=channel,
        document_filename=filename,
        storage_provider=provider,
        storage_key=key,
        xlsx_filename=xlsx_filename,
        xlsx_storage_provider=xlsx_provider,
        xlsx_storage_key=xlsx_key,
        line_count=len(pack),
        production_line_count=0,
        # The document AS SENT, frozen beside the lines (AC-D5). Rebuilding it on every GET
        # of the link meant a newer stock list from the supplier changed the page under them,
        # so the link and the xlsx in their own inbox stopped being the same ask.
        sheet_json=sheet.to_dict(),
        created_by=actor,
        public_token=public_token,
        public_token_expires_at=public_token_expires_at,
        recipients=addressed_to,
    )
    db.add(notice)
    db.flush()
    for i, ln in enumerate(pack):
        db.add(
            SupplierNoticeLine(
                notice_id=str(notice.id),
                product_id=ln.get("product_id"),
                item_code=ln.get("item_code"),
                product_name=ln.get("product_name"),
                po_number=None,
                qty=ln.get("qty") or 0,
                cbm=None,
                kind="pack",
                sort_order=i,
            )
        )

    db.flush()
    _dispatch(
        db,
        notice,
        supplier,
        recipients=to or None,
        chat_contact=contact,
        chat_identifier=identifier,
        note=note,
    )
    db.commit()

    return {
        "notices": [serialize(db, notice)],
        "document_filename": filename,
    }


# --------------------------------------------------------------------------- public link


#: How long the supplier's link answers for (F8, AC-C7). Thirty days is the whole of its
#: life; nothing renews it, and a resend replaces it rather than extending it.
PUBLIC_TOKEN_TTL_DAYS = 30

#: 32 random bytes, the same width as the quotation counter-sign token
#: (`project_quotation_document_service.issue_sign_link`). The token IS the credential, so
#: its only real property is being unguessable.
_PUBLIC_TOKEN_BYTES = 32

#: One answer for "no such token", "expired" and "superseded by a resend". Saying which
#: confirms to anybody guessing that a token exists, and this endpoint is public.
_LINK_GONE = "This link is no longer available. Ask your contact at Sorento to resend it."


def _retire_public_tokens(
    db: Session, supplier_id: str, *, loading_plan_id: Optional[str] = None
) -> None:
    """Expire the live container-request links, for ONE plan when a plan is named.

    ONE LIVE LINK PER PLAN, not per supplier (part 4, R3/R11 - this supersedes part 3's
    per-supplier rule). Two plans against one supplier is the ordinary case, a September
    container and an October one, and each holds its own current ask: retiring per supplier
    meant a send or a cancel on either one killed the link the supplier was working off for
    the other. Within a plan the old rule stands unchanged - a resend IS the current ask, so
    the previous link stops answering.

    Without a plan the sweep is the supplier's, which is what a container request sent
    outside any plan (the pre-part-4 shape) has always done.

    The token is KEPT, not cleared: a notice is the record of what left the building, and
    "there was a link, it ran out on this date" is part of that record. Expiring it is what
    stops it answering, which is all that is needed - and it means the old link and a token
    that never existed fail through the same branch below.
    """
    now = datetime.utcnow()
    query = db.query(SupplierNotice).filter(
        SupplierNotice.supplier_id == supplier_id,
        SupplierNotice.notice_type == "container_request",
        SupplierNotice.public_token.isnot(None),
        SupplierNotice.public_token_expires_at > now,
    )
    if loading_plan_id is not None:
        query = query.filter(SupplierNotice.loading_plan_id == str(loading_plan_id))
    query.update({"public_token_expires_at": now}, synchronize_session=False)
    db.flush()


def request_by_public_token(db: Session, token: str) -> SupplierNotice:
    """Resolve a supplier link, refusing anything unknown or expired with the SAME message.

    Resolved with the company scope OPEN, then pinned shut to the notice's own company -
    exactly the shape `project_quotation_document_service.get_issue_by_sign_token` carries,
    and for the same reason. The reader is a stranger with no session and no API key, so the
    scope resolver leaves the request at UNSET, which is fail-closed and reads zero rows from
    every owned table: without the open window a live link would answer "no longer available"
    and a supplier would be told to ask for a resend of something that was never broken. The
    token is what makes opening it safe, being globally unique and the whole credential.
    Pinning afterwards is not optional: the lines and the supplier name read next must stay
    inside the company the token belongs to.
    """
    if not token:
        raise AppException(404, _LINK_GONE)
    with company_scope(db, None):
        notice = (
            db.query(SupplierNotice)
            .filter(SupplierNotice.public_token == token)
            # Both channel rows of one send carry the token (R23) and hold the same lines and
            # the same two files, so either answers identically - but a page that reads off
            # whichever row the planner happened to return is a page that can change its mind.
            # Descending puts `email` first: the row the link actually went out on.
            .order_by(SupplierNotice.channel.desc())
            .first()
        )
    if notice is not None and notice.company_id:
        set_company_scope(db, frozenset({str(notice.company_id)}))
    if (
        notice is None
        or notice.public_token_expires_at is None
        or notice.public_token_expires_at <= datetime.utcnow()
    ):
        raise AppException(404, _LINK_GONE)
    return notice


def _stamp_open(db: Session, token: str) -> None:
    """Count this open on every notice carrying the token (R11).

    Its own SAVEPOINT, released immediately: the page read is finished by the time this runs,
    and the tracking must be able to fail (a lock, a dropped connection) without taking the
    reader's page with it. `opened_at` is set once with COALESCE, because "when did they
    first open it" is a different question from "when did they last".

    Raw UPDATE rather than the ORM: it is one statement over rows the request has no session
    identity for, and `open_count = open_count + 1` in the database is what makes two
    simultaneous opens count as two.
    """
    now = datetime.utcnow()
    savepoint = db.begin_nested()
    db.execute(
        text(
            "UPDATE supplier_notices "
            "   SET opened_at = COALESCE(opened_at, :now), "
            "       last_opened_at = :now, "
            "       open_count = COALESCE(open_count, 0) + 1 "
            " WHERE public_token = :t"
        ),
        {"now": now, "t": token},
    )
    savepoint.commit()
    db.commit()


def _record_open(db: Session, token: str) -> None:
    """Best effort, always (AC-C7). The tracking is the least important thing on the page."""
    try:
        _stamp_open(db, token)
    except Exception:  # noqa: BLE001
        logger.warning(
            "supplier request: the open could not be recorded for this link", exc_info=True
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def public_request_page(db: Session, token: str) -> dict:
    """What the supplier sees: this request's lines, and their own figures beside them.

    NARROW on purpose (AC-C6). No price, no cost, no supplier id, no notice id, no other
    request - a leaked URL exposes one ask and nothing that would let its holder find a
    second. The lines are the notice's own frozen copy, so the page says what was actually
    sent rather than what the plan would compute today.

    The sheet is the one that was SENT, off `sheet_json`, not one rebuilt today: the supplier
    sends a newer stock list every few weeks, and a page that moved with it stopped agreeing
    with the xlsx sitting in their own inbox. A token issued before that column existed is
    still open in somebody's inbox, so it falls back to the rebuild (AC-H2).

    Their packed / unfinished on the `lines` block come off the CURRENT stock-list snapshot
    rather than the notice, which stores no holdings. That is their own latest statement about
    their own warehouse, which is the honest thing to show them; a product they have never
    listed reads as null rather than as zero.
    """
    notice = request_by_public_token(db, token)
    lines = (
        db.query(SupplierNoticeLine)
        .filter(SupplierNoticeLine.notice_id == str(notice.id))
        .order_by(SupplierNoticeLine.sort_order)
        .all()
    )
    held = _held_by_item_code(db, str(notice.supplier_id))
    payload = {
        "supplier_name": _supplier_name(db, str(notice.supplier_id)),
        "requested_at": notice.created_at.isoformat() if notice.created_at else None,
        "line_count": len(lines),
        # S4 / AC-D5: the third renderer of the ONE model - their own columns, their merges,
        # their marks. `lines` stays beside it (AC-H2): a link issued before S4 is open in
        # somebody's inbox and its page must keep rendering.
        "sheet": notice.sheet_json
        or _request_sheet(
            db,
            str(notice.supplier_id),
            [
                {
                    "product_id": str(ln.product_id) if ln.product_id else None,
                    "item_code": ln.item_code,
                    "product_name": ln.product_name,
                    "qty": _f(ln.qty) or 0.0,
                }
                for ln in lines
            ],
        ).to_dict(),
        "lines": [
            {
                "item_code": ln.item_code,
                "product_name": ln.product_name,
                "qty": _f(ln.qty) or 0.0,
                "qty_packed": (held.get(str(ln.item_code)) or {}).get("qty_packed"),
                "qty_unfinished": (held.get(str(ln.item_code)) or {}).get("qty_unfinished"),
            }
            for ln in lines
        ],
        "has_pdf": bool(notice.storage_key),
        "has_xlsx": bool(notice.xlsx_storage_key),
    }
    # A write on a GET, by design: this IS the tracking (R11). Last, so everything the
    # supplier came for is already read and no stamp can stand between them and it.
    _record_open(db, token)
    return payload


def _held_by_item_code(db: Session, supplier_id: str) -> dict[str, dict]:
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
            "qty_packed": _f(r.qty_packed),
            "qty_unfinished": _f(r.qty_unfinished),
        }
        for r in rows
    }


def public_document_url(db: Session, token: str, kind: str) -> dict:
    """One of the request's two files, off the same token and the same 404.

    Downloading through the link counts as an open (R11): a supplier who goes straight for
    the spreadsheet has read the request just as surely as one who scrolled the page.
    """
    notice = request_by_public_token(db, token)
    out = document_url(db, str(notice.id), kind=kind)
    _record_open(db, token)
    return out


def _public_base_url() -> Optional[str]:
    """Where this CRM's public pages live, or None when nobody has configured it.

    Its own function so the send path can be tested without an environment: a link is a
    promise to a supplier, and "None/c/.../token" in front of one is worse than no link.
    """
    from app.config import settings

    base = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
    return base or None


def public_request_url(db: Session, notice: SupplierNotice) -> Optional[str]:
    """`{base}/c/{company_code}/supplier-request/{token}`, or None if it cannot be built.

    The company segment is cosmetic - the token is globally unique and is the whole
    credential - but every public page this system hands out has that shape, and one shape is
    what makes them recognisable as ours.
    """
    base = _public_base_url()
    if not base or not notice.public_token:
        return None
    code = _company_code(db, str(notice.company_id)) if notice.company_id else None
    return f"{base}/c/{code or 'SRT'}/supplier-request/{notice.public_token}"


def _company_code(db: Session, company_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT code FROM companies WHERE id = :i"), {"i": company_id}
    ).first()
    return row[0] if row else None


#: What each file this module stores is served as. Taken off the extension rather than passed
#: in, so `_store`'s two-argument shape (which every suite here monkeypatches) is unchanged.
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _store(data: bytes, filename: str) -> tuple[str, str]:
    from app.services.storage_router import default_provider, get_backend

    provider = default_provider()
    key = f"exports/supplier-notice/{datetime.utcnow():%Y/%m}/{_rand()}/{filename}"
    ext = filename[filename.rfind(".") :].lower() if "." in filename else ""
    stored_key, _signed = get_backend(provider).upload_file(
        file_content=data,
        file_path=key,
        content_type=_CONTENT_TYPES.get(ext, "application/octet-stream"),
    )
    return provider, stored_key or key


def _rand() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- send


def _dispatch(
    db: Session,
    notice: SupplierNotice,
    supplier: dict,
    *,
    recipients: Optional[list[str]] = None,
    chat_contact=None,
    chat_identifier: Optional[str] = None,
    note: Optional[str] = None,
) -> None:
    """Send one notice on its own channel, and log the attempt either way (AC-F5).

    The keyword arguments are what a container request adds (R9): who the sender named, and
    the line they wrote. A loading-plan approval passes none of them and behaves exactly as
    it did - its email goes to `suppliers.email` and its chat row is still the declared,
    dark one, because that path never asked anybody which channel to use.
    """
    if notice.channel == "email":
        _send_email(db, notice, supplier, recipients=recipients, note=note)
    elif chat_contact is not None:
        _send_chat(db, notice, chat_contact, chat_identifier, note=note)
    else:
        # The loading-plan approval's chat row: declared and dark. That path sends on every
        # channel it can reach and names no contact, so there is no identity to send to -
        # said plainly rather than logged as a failure, because nobody can fix a "failure"
        # whose cause is that nobody chose a recipient. It is still logged: that screen shows
        # two channels, and an outbox holding one of them reads as a log that dropped a row.
        # A container request never reaches here: its chat sends carry a contact (R9).
        notice.status = "skipped"
        notice.status_reason = "No chat channel is linked to this supplier yet."
        _log_attempt(db, notice, ok=False, detail=notice.status_reason, skipped=True)


def _send_email(
    db: Session,
    notice: SupplierNotice,
    supplier: dict,
    *,
    recipients: Optional[list[str]] = None,
    note: Optional[str] = None,
) -> None:
    addresses = [a for a in (recipients or [(supplier.get("email") or "").strip()]) if a]
    if not addresses:
        notice.status = "skipped"
        notice.status_reason = "This supplier has no email address on file."
        _log_attempt(db, notice, ok=False, detail=notice.status_reason, skipped=True)
        return

    # `recipient` keeps the first address, for the screens and logs written against it;
    # `recipients` is the whole list (AC-C2).
    notice.recipient = addresses[0][:320]
    notice.recipients = list(addresses)
    copy = _EMAIL_COPY.get(notice.notice_type, _EMAIL_COPY["loading"])
    subject = f"{copy['subject']} - {supplier.get('supplier_name') or ''}".strip()
    body = _body_with_note(copy["body"], note)

    # The third thing in the one email (AC-C1): a link to the same request, for the reader who
    # will not open an attachment on a phone. Appended only when a URL can actually be built -
    # an unconfigured base would otherwise put "None/c/..." in front of a supplier.
    link = public_request_url(db, notice)
    if link:
        body = (
            f"{body}\n\n"
            f"在线查看 / View online:\n{link}\n"
            f"此链接30天内有效。 / This link works for 30 days."
        )

    try:
        from app.services import email_outbox_service

        metadata: dict[str, Any] = {
            "supplier_notice_id": str(notice.id),
            "loading_plan_id": str(notice.loading_plan_id or ""),
        }
        # ONE email carrying both files (AC-C1). The outbox row's own attachment columns hold
        # the PDF; the second file travels in the metadata the drainer already reads, because
        # a notice has exactly two documents and a second set of columns on every outbox row
        # would be three columns nothing else in the system fills.
        if notice.xlsx_storage_key:
            metadata["extra_attachments"] = [
                {
                    "filename": notice.xlsx_filename,
                    "storage_provider": notice.xlsx_storage_provider,
                    "storage_key": notice.xlsx_storage_key,
                }
            ]

        # One row per address rather than one row with the rest in cc (AC-C2): each address
        # then has its own delivery, its own retries and its own failure, which is what the
        # outbox is for. A bounce at the freight desk must not stop the factory's copy.
        for address in addresses:
            email_outbox_service.enqueue(
                db,
                event_key=EVENT_KEY,
                to=address,
                subject=subject,
                body_text=body,
                metadata=metadata,
                attachment_filename=notice.document_filename,
                attachment_storage_provider=notice.storage_provider,
                attachment_storage_key=notice.storage_key,
            )
    except Exception as exc:  # noqa: BLE001 - the attempt is logged, then reported on the row
        notice.status = "failed"
        notice.last_error = str(exc)[:5000]
        notice.attempt_count = (notice.attempt_count or 0) + 1
        _log_attempt(db, notice, ok=False, detail=str(exc))
        return

    # Queued, not delivered. `sent` here means "handed to the one producer of SMTP traffic",
    # which is the furthest this call can honestly claim; the drainer owns delivery, its retries
    # and its own failure record.
    notice.status = "sent"
    notice.sent_at = datetime.utcnow()
    notice.attempt_count = (notice.attempt_count or 0) + 1
    _log_attempt(db, notice, ok=True, detail="queued to email outbox")


def _body_with_note(body: str, note: Optional[str]) -> str:
    """The sender's own line first, then the bilingual body (R9).

    First rather than last because it is the one sentence written for this send: "ship before
    CNY" under three paragraphs of standing wording is a sentence nobody reads.
    """
    line = str(note or "").strip()
    return f"{line}\n\n{body}" if line else body


def _send_chat(
    db: Session,
    notice: SupplierNotice,
    contact,
    identifier: Optional[str],
    *,
    note: Optional[str] = None,
) -> None:
    """Send the request on WeChat, through the composer's own path (R10, AC-C4).

    The message is the same bilingual wording the email carries plus the public link, because
    the link is what a factory actually opens - the two files hang off it. Inside the 24h
    window the composer sends that text; outside it, the approved template for
    `CHAT_USE_CASE`. Either way it writes the `integration_log` outbox row, on success AND on
    failure, which is why this calls it rather than talking to Respond.io directly.
    """
    notice.recipient = _contact_label(contact)[:320]
    copy = _EMAIL_COPY.get(notice.notice_type, _EMAIL_COPY["loading"])
    text_out = _body_with_note(copy["body"], note)
    link = public_request_url(db, notice)
    if link:
        text_out = (
            f"{text_out}\n\n"
            f"在线查看 / View online:\n{link}\n"
            f"此链接30天内有效。 / This link works for 30 days."
        )

    try:
        _chat_send(
            db,
            identifier=identifier or _chat_identifier(db, contact),
            respond_contact_id=str(contact.id),
            text=text_out,
            chat_use_case=CHAT_USE_CASE,
            business_table="supplier_notices",
            business_id=str(notice.id),
            sender_name=notice.created_by or "Sorento",
            created_by=None,
        )
    except Exception as exc:  # noqa: BLE001 - reported on the row, never raised at the caller
        # The composer already wrote the failed outbox row; the notice carries the reason so
        # the Requests sent card can say what happened without anybody opening the log.
        message = _error_message(exc)
        notice.status = "failed"
        notice.status_reason = message[:255]
        notice.last_error = message[:5000]
        notice.attempt_count = (notice.attempt_count or 0) + 1
        logger.warning(
            "supplier notice %s: the WeChat send failed (%s)", notice.id, message
        )
        return

    notice.status = "sent"
    notice.sent_at = datetime.utcnow()
    notice.attempt_count = (notice.attempt_count or 0) + 1


def _error_message(exc: Exception) -> str:
    """The human half of an AppException, or the exception's own words.

    `AppException.detail` is the `{message, detail, code}` dict the error handler builds, and
    `str(exc)` on one of those reads as a dict - which is not a sentence to put on a screen.
    """
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("detail") or exc)
    return str(exc)


def _log_attempt(db: Session, notice: SupplierNotice, *, ok: bool, detail: str,
                 skipped: bool = False) -> None:
    """One integration log per attempt, success or failure (AC-F5).

    Best-effort: logging must never be the reason a send fails. `business_id` is the notice id
    because the column is a UUID and a composite string does not fit in one.
    """
    try:
        from app.schemas.integration import IntegrationLogCreate
        from app.services.integration_service import IntegrationLogService

        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="email",
                business_table="supplier_notices",
                business_id=str(notice.id),
                external_reference=notice.recipient,
                direction="outbound",
                endpoint=EVENT_KEY,
                http_method="POST",
                status="skipped" if skipped else ("success" if ok else "failed"),
                error_message=None if ok else detail[:5000],
            ),
            request_payload_dict={
                "channel": notice.channel,
                "recipient": notice.recipient,
                "document": notice.document_filename,
                "loading_plan_id": str(notice.loading_plan_id or ""),
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning("supplier notice %s: could not write integration log", notice.id,
                       exc_info=True)


# --------------------------------------------------------------------------- read


def _link_live(notice: SupplierNotice) -> bool:
    return bool(
        notice.public_token_expires_at
        and notice.public_token_expires_at > datetime.utcnow()
    )


def serialize(db: Session, notice: SupplierNotice) -> dict[str, Any]:
    return {
        "id": str(notice.id),
        "supplier_id": str(notice.supplier_id),
        "supplier_name": _supplier_name(db, str(notice.supplier_id)),
        "loading_plan_id": str(notice.loading_plan_id) if notice.loading_plan_id else None,
        "notice_type": notice.notice_type,
        "channel": notice.channel,
        "recipient": notice.recipient,
        # Everybody this send named (AC-C2). Null on a row written before migration 442 that
        # never had an address either; a one-address send is backfilled to `[address]`.
        "recipients": notice.recipients,
        # The opens (AC-C8). `opened_at` is the first and never moves; the card reads
        # "Opened n times, last dd/mm HH:mm" off the three together, "Not opened yet" at 0.
        "opened_at": notice.opened_at.isoformat() if notice.opened_at else None,
        "last_opened_at": (
            notice.last_opened_at.isoformat() if notice.last_opened_at else None
        ),
        "open_count": notice.open_count or 0,
        "status": notice.status,
        "status_reason": notice.status_reason,
        "sent_at": notice.sent_at.isoformat() if notice.sent_at else None,
        "attempt_count": notice.attempt_count,
        "last_error": notice.last_error,
        "document_filename": notice.document_filename,
        "has_document": bool(notice.storage_key),
        "xlsx_filename": notice.xlsx_filename,
        "has_xlsx": bool(notice.xlsx_storage_key),
        # Built here, never in the browser: the address of a public page is a server fact
        # (it has to match what went out in the email), and null when it has run out or when
        # no public base URL is configured - which is what hides the Copy link button. A dead
        # URL is never handed to the browser: a copied dead link is worse than no button.
        "public_url": (
            public_request_url(db, notice) if _link_live(notice) else None
        ),
        # ...but "this send HAD a link and it has run out" is a different fact from "this
        # send never had one", and only the first one earns the muted "Link retired" line on
        # an older row (R23). One boolean, because `public_url` already answers the live case.
        "link_retired": bool(notice.public_token) and not _link_live(notice),
        "container_type": notice.container_type,
        "container_count": notice.container_count,
        "planned_cbm": _f(notice.planned_cbm),
        "line_count": notice.line_count,
        "production_line_count": notice.production_line_count,
        "created_at": notice.created_at.isoformat() if notice.created_at else None,
        "created_by": notice.created_by,
    }


def _supplier_name(db: Session, supplier_id: str) -> Optional[str]:
    """N-2: routed through `supplier_scope.supplier_label` - the same is_uuid guard and
    company predicate as every other supplier lookup in this module, rather than a second
    bare unscoped `SELECT`. No behaviour change for a caller in their own company; a foreign
    or malformed id now names nothing here instead of leaking a name across companies."""
    _code, name = supplier_label(db, supplier_id)
    return name


def list_for_plan(db: Session, plan_id: str) -> list[dict]:
    rows = (
        db.query(SupplierNotice)
        .filter(SupplierNotice.loading_plan_id == plan_id)
        .order_by(SupplierNotice.created_at.desc(), SupplierNotice.channel)
        .all()
    )
    return [serialize(db, n) for n in rows]


def latest_notice_for_plans(db: Session, plan_ids: list[str]) -> dict[str, dict]:
    """The newest send per loading plan, for the list's Sent and Opened columns (AC-A1).

    One row per plan, and it has to be the LATEST: a plan that was resent would otherwise
    report the opens of a link nobody can open any more. Serialising the whole notice here
    would put the lines, the files and the token behind every row of a 50-row grid, so this
    answers with the five fields those two columns read.
    """
    ids = [str(i) for i in plan_ids or [] if is_uuid(str(i))]
    if not ids:
        return {}
    rows = (
        db.query(SupplierNotice)
        .filter(SupplierNotice.loading_plan_id.in_(ids))
        .order_by(
            SupplierNotice.loading_plan_id,
            SupplierNotice.created_at.desc(),
            SupplierNotice.id.desc(),
        )
        .distinct(SupplierNotice.loading_plan_id)
        .all()
    )
    return {
        str(n.loading_plan_id): {
            "channel": n.channel,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
            # The FIRST open, which never moves, alongside the latest one: the record page
            # says when they first looked, the column says when they last did.
            "opened_at": n.opened_at.isoformat() if n.opened_at else None,
            "last_opened_at": (
                n.last_opened_at.isoformat() if n.last_opened_at else None
            ),
            "open_count": n.open_count or 0,
        }
        for n in rows
    }


def list_for_supplier(
    db: Session,
    supplier_id: str,
    *,
    limit: int = 50,
    loading_plan_id: Optional[str] = None,
) -> list[dict]:
    """Notices for one supplier, newest first; for ONE plan when a plan is named.

    The plan record page asks with its own id (R3/R11): the history it prints is what left
    the building for the plan being read, and the same supplier's other plans belong on their
    own pages. Without the parameter the answer is unchanged, which is what the supplier-level
    callers still want.

    N-3: a malformed ``supplier_id`` reached `SupplierNotice.supplier_id == supplier_id`
    raw and 500'd on the UUID column comparison. This is a filter, not a lookup by id -
    every other GET here that filters a listing by an optional/free-form id
    (`list_loading_plans`, `list_supplier_inventory`) answers "nothing matches" rather than
    404ing, so a non-id-shaped value is treated the same way: it can never match a real
    notice, so it reads as zero rows instead of a server error.
    """
    if not is_uuid(supplier_id):
        return []
    query = db.query(SupplierNotice).filter(SupplierNotice.supplier_id == supplier_id)
    if loading_plan_id is not None:
        if not is_uuid(loading_plan_id):
            return []
        query = query.filter(SupplierNotice.loading_plan_id == loading_plan_id)
    rows = (
        query.order_by(SupplierNotice.created_at.desc(), SupplierNotice.channel)
        .limit(limit)
        .all()
    )
    return [serialize(db, n) for n in rows]


#: The two files a notice can carry, and where each one's storage triple lives (F4).
_DOCUMENT_KINDS = {
    "pdf": ("storage_provider", "storage_key", "document_filename"),
    "xlsx": ("xlsx_storage_provider", "xlsx_storage_key", "xlsx_filename"),
}


def document_url(
    db: Session, notice_id: str, *, kind: str = "pdf", expires_in: int = 3600
) -> dict:
    """A short-lived link to one of the notice's files.

    `kind` defaults to `pdf`, so every existing caller reads exactly as before; `xlsx` is the
    stock list handed back with the quantity to load (F4), which only a container request has.
    """
    notice = db.query(SupplierNotice).filter(SupplierNotice.id == notice_id).one_or_none()
    if notice is None:
        raise AppException(404, "Supplier notice not found")
    if kind not in _DOCUMENT_KINDS:
        raise AppException(422, f"Unknown document kind: {kind}")

    provider_attr, key_attr, name_attr = _DOCUMENT_KINDS[kind]
    key = getattr(notice, key_attr, None)
    if not key:
        raise AppException(409, "This notice has no document.")

    from app.services.storage_router import get_backend

    url = get_backend(getattr(notice, provider_attr, None)).get_signed_url(
        key, expires_in=expires_in
    )
    return {
        "url": url,
        "filename": getattr(notice, name_attr, None),
        "expires_in": expires_in,
    }
