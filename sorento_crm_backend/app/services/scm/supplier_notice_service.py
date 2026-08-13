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

    Notice = {
      id, supplier_id, supplier_name, loading_plan_id, channel: 'email'|'chat',
      recipient: str|null, status: 'pending'|'sent'|'failed'|'skipped',
      status_reason: str|null, sent_at: iso|null, attempt_count: int, last_error: str|null,
      document_filename: str|null, has_document: bool,
      container_type, container_count, planned_cbm, line_count, production_line_count,
      created_at: iso, created_by: str|null,
    }
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import LoadingPlan, LoadingPlanLine
from app.models.supplier_notice import SupplierNotice, SupplierNoticeLine
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

EVENT_KEY = "supplier_loading_notice"

#: Email is the channel that sends today. Chat is declared, and dark: nothing links a supplier
#: to a Respond contact yet, so a chat row records the intent and states why it did not send.
#: When a WeChat channel exists in the workspace it lights up with no change here (AC-F4).
CHANNELS = ("email", "chat")


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _supplier(db: Session, supplier_id: str) -> dict:
    row = db.execute(
        text("SELECT id, supplier_code, supplier_name, email FROM suppliers WHERE id = :i"),
        {"i": supplier_id},
    ).mappings().first()
    if row is None:
        raise AppException(404, "Supplier not found")
    return dict(row)


# --------------------------------------------------------------------------- document


def _document_html(*, supplier: dict, plan: LoadingPlan, pack: list[dict],
                   produce: list[dict]) -> str:
    """The notice, in both languages, in the shape the supplier already reads (AC-F2).

    Bilingual side by side rather than two documents: the supplier's staff read the Chinese and
    our own people have to be able to check what went out, and two files drift the moment one is
    edited. The production items are a separate table, not a flag on a row, because they are a
    different ask - one is "load this", the other is "make this".
    """
    def rows(items: list[dict], qty_label: str) -> str:
        if not items:
            return (
                '<tr><td colspan="5" class="empty">'
                "Nothing in this section / 此部分无项目</td></tr>"
            )
        out = []
        for i, ln in enumerate(items, start=1):
            cbm = ln.get("cbm")
            out.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td>{escape(str(ln.get('item_code') or ''))}</td>"
                f"<td>{escape(str(ln.get('product_name') or ''))}</td>"
                f"<td class='num'>{_qty(ln.get('qty'))}</td>"
                f"<td class='num'>{'' if cbm is None else f'{float(cbm):.3f}'}</td>"
                "</tr>"
            )
        return "".join(out)

    departure = plan.inventory_as_of.strftime("%d/%m/%Y") if plan.inventory_as_of else "-"
    containers = (
        f"{plan.container_count} x {escape(str(plan.container_type or ''))}".strip()
        if plan.container_count
        else "-"
    )
    return f"""
<html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 14mm; }}
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
</style></head><body>
  <h1>Loading Notice / 装柜通知</h1>
  <p class="sub">{escape(str(supplier.get('supplier_name') or ''))}
     ({escape(str(supplier.get('supplier_code') or ''))})</p>
  <table class="meta">
    <tr><td class="k">Containers / 柜数</td><td>{containers}</td></tr>
    <tr><td class="k">Volume planned / 计划体积</td><td>{_cbm(plan.planned_cbm)} cbm</td></tr>
    <tr><td class="k">Capacity / total 容量</td><td>{_cbm(plan.capacity_cbm)} cbm</td></tr>
    <tr><td class="k">Inventory as at / 库存日期</td><td>{departure}</td></tr>
  </table>

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
</body></html>
""".strip()


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


def _store(data: bytes, filename: str) -> tuple[str, str]:
    from app.services.storage_router import default_provider, get_backend

    provider = default_provider()
    key = f"exports/supplier-notice/{datetime.utcnow():%Y/%m}/{_rand()}/{filename}"
    stored_key, _signed = get_backend(provider).upload_file(
        file_content=data, file_path=key, content_type="application/pdf"
    )
    return provider, stored_key or key


def _rand() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- send


def _dispatch(db: Session, notice: SupplierNotice, supplier: dict) -> None:
    """Send one notice on its own channel, and log the attempt either way (AC-F5)."""
    if notice.channel == "email":
        _send_email(db, notice, supplier)
    else:
        # Declared and dark. Nothing links a supplier to a Respond contact, so there is no
        # identity to send to - said plainly rather than logged as a failure, because nobody
        # can fix a "failure" whose cause is that the feature does not exist yet. It is still
        # logged: the screen shows two channels and an outbox holding only one of them reads as
        # a log that dropped a row.
        notice.status = "skipped"
        notice.status_reason = "No chat channel is linked to this supplier yet."
        _log_attempt(db, notice, ok=False, detail=notice.status_reason, skipped=True)


def _send_email(db: Session, notice: SupplierNotice, supplier: dict) -> None:
    to = (supplier.get("email") or "").strip()
    if not to:
        notice.status = "skipped"
        notice.status_reason = "This supplier has no email address on file."
        _log_attempt(db, notice, ok=False, detail=notice.status_reason, skipped=True)
        return

    notice.recipient = to
    subject = f"Loading notice / 装柜通知 - {supplier.get('supplier_name') or ''}".strip()
    body = (
        "Please see the attached loading notice for the items to pack and load, and the items "
        "that need production.\n\n"
        "请查收附件装柜通知，内含需装柜及需生产的项目。"
    )

    try:
        from app.services import email_outbox_service

        email_outbox_service.enqueue(
            db,
            event_key=EVENT_KEY,
            to=to,
            subject=subject,
            body_text=body,
            metadata={"supplier_notice_id": str(notice.id),
                      "loading_plan_id": str(notice.loading_plan_id or "")},
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


def serialize(db: Session, notice: SupplierNotice) -> dict[str, Any]:
    return {
        "id": str(notice.id),
        "supplier_id": str(notice.supplier_id),
        "supplier_name": _supplier_name(db, str(notice.supplier_id)),
        "loading_plan_id": str(notice.loading_plan_id) if notice.loading_plan_id else None,
        "notice_type": notice.notice_type,
        "channel": notice.channel,
        "recipient": notice.recipient,
        "status": notice.status,
        "status_reason": notice.status_reason,
        "sent_at": notice.sent_at.isoformat() if notice.sent_at else None,
        "attempt_count": notice.attempt_count,
        "last_error": notice.last_error,
        "document_filename": notice.document_filename,
        "has_document": bool(notice.storage_key),
        "container_type": notice.container_type,
        "container_count": notice.container_count,
        "planned_cbm": _f(notice.planned_cbm),
        "line_count": notice.line_count,
        "production_line_count": notice.production_line_count,
        "created_at": notice.created_at.isoformat() if notice.created_at else None,
        "created_by": notice.created_by,
    }


def _supplier_name(db: Session, supplier_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT supplier_name FROM suppliers WHERE id = :i"), {"i": supplier_id}
    ).first()
    return row[0] if row else None


def list_for_plan(db: Session, plan_id: str) -> list[dict]:
    rows = (
        db.query(SupplierNotice)
        .filter(SupplierNotice.loading_plan_id == plan_id)
        .order_by(SupplierNotice.created_at.desc(), SupplierNotice.channel)
        .all()
    )
    return [serialize(db, n) for n in rows]


def list_for_supplier(db: Session, supplier_id: str, *, limit: int = 50) -> list[dict]:
    rows = (
        db.query(SupplierNotice)
        .filter(SupplierNotice.supplier_id == supplier_id)
        .order_by(SupplierNotice.created_at.desc(), SupplierNotice.channel)
        .limit(limit)
        .all()
    )
    return [serialize(db, n) for n in rows]


def document_url(db: Session, notice_id: str, *, expires_in: int = 3600) -> dict:
    notice = db.query(SupplierNotice).filter(SupplierNotice.id == notice_id).one_or_none()
    if notice is None:
        raise AppException(404, "Supplier notice not found")
    if not notice.storage_key:
        raise AppException(409, "This notice has no document.")

    from app.services.storage_router import get_backend

    url = get_backend(notice.storage_provider).get_signed_url(
        notice.storage_key, expires_in=expires_in
    )
    return {"url": url, "filename": notice.document_filename, "expires_in": expires_in}
