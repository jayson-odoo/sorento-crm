"""`GET /api/v1/sales/analysis`: the chatbot's sales answer, as the whole table in text AND
the same query as an Excel (PLAN-retail-sales-reports-26sep 5.5, R4.2; Owner ruling 26 Sep
07:16 Q2, "always text + file, no cutoff").

**One query, two formats.** The figures are `engine.run` over the `sales_yearly`
definition with the view the ask names (rows and columns), so the text, the Excel and the
Yearly comparison screen are the same query (AC-R4-6). The Excel is the kernel's own
`generate_report_xlsx`, queued with the SAME params and view and the contact's company as
its grant.

**The file path is the low stock report's** (`app/api/v1/scm/low_stock_report.py`): a
`report_xlsx` My Downloads row owned by the CRM user linked to the contact (else the act-as
user), a bounded wait (`_await_download`, capped under the chatbot's MCP timeout), and when
the file is not ready in time the delivery is claimed for the worker, which pushes it once
(`export_tasks._push_download_to_chat`). The text never waits on the file.

**Gates, in order:** `sales.reports.view` on the act-as principal (the route dependency),
the `sales` module (the router guard), then the CONTACT's own `sales_orders.sales_report`
reveal key (403 `sales_report_not_enabled`, nothing written). A contact linked to a customer
account is a dealer and is refused (AC-S1-23). The company is one of the contact's own; a
contact in two companies who names neither is asked (AC-S1-21). A question or a refusal
carries no file and writes no row (AC-R4-3).

GET, not POST, for the reason the low stock route gives: the MCP compiler adds
`view=render` only to query-param tools.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

# The low stock route's own wait and budget, not a second copy: one seam, one cap.
from app.api.v1.scm.low_stock_report import _await_download, _sync_wait_seconds  # noqa: F401
from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.error_handler import AppException

log = logging.getLogger(__name__)

router = APIRouter()

_GATE = require_permission_with_api_key("sales.reports.view")

REPORT_KEY = "sales_yearly"
GRANT = "sales_orders.sales_report"
REFUSAL = "Sorry, I can only share sales figures for your own account."
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: The ask's axis words -> the dataset's dimensions.
AXES = {"month": "month_of_year", "year": "year", "channel": "channel"}
_MAX_N = 100
_RATE_LIMIT = 20
_RATE_WINDOW_SECONDS = 600


def _unprocessable(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


def _validate(rows: str, cols: str, basis: Optional[str], date_from, date_to, n) -> None:
    if rows not in AXES or cols not in AXES:
        raise _unprocessable(
            f"Unknown axis; use one of {', '.join(sorted(AXES))}", "unknown_axis"
        )
    if rows == cols:
        raise _unprocessable("Rows and columns cannot be the same", "rows_equal_cols")
    if basis not in ("ordered", "delivered"):
        raise _unprocessable("Basis is ordered or delivered", "basis_required")
    if date_from and date_to and date_from > date_to:
        raise _unprocessable("date_from is after date_to", "date_range_inverted")
    if n is not None and not 1 <= n <= _MAX_N:
        raise _unprocessable(f"n is 1 to {_MAX_N}", "n_out_of_range")


def _company_question(names: List[str]) -> str:
    return f"{', '.join(names[:-1])} or {names[-1]}?"


@dataclass
class _Prepared:
    answer: Dict[str, Any]
    download_id: str
    resolved_contact_id: str
    sync_wait_seconds: int


def _money(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value.quantize(Decimal("0.01")))


def _answer(result, *, company_name: str, channel: Optional[str], basis: str,
            row_label: str, col_label: str, n: Optional[int]) -> Dict[str, Any]:
    """The pivot as the text reads it: one line per row, the columns in order, a Difference
    column (last year minus the one before) when the columns are two or more years."""
    from app.services.reports.datasets.sales_order_lines import BASIS_WORDS, CHANNELS

    pivot = result.layouts.summary
    labels = pivot.col_dim.value_labels or {}
    col_values = list(pivot.col_dim.values)
    columns = [labels.get(v, v) for v in col_values]
    difference = col_label == "Year" and len(col_values) >= 2

    def _cells(per_col: Dict[str, Dict[str, str]]) -> List[Optional[str]]:
        values = [per_col.get(v, {}).get("sales_value") for v in col_values]
        if difference:
            last, before = values[-1], values[-2]
            values.append(
                _money(Decimal(last) - Decimal(before or 0)) if last is not None else None
            )
        return values

    row_labels = {}
    if pivot.row_dim.key == "month_of_year":
        from app.services.reports.datasets.sales_order_lines import MONTH_OF_YEAR

        row_labels = dict(MONTH_OF_YEAR)
    rows = [
        {
            "label": row_labels.get(value, value),
            "values": _cells(pivot.cells.get(value, {})),
            "total": pivot.row_totals.get(value, {}).get("sales_value"),
        }
        for value in pivot.row_values
    ]
    total_count = len(rows)
    if n is not None:
        # Ranked by the row's own total, then its label: the top X rule (PR #1263).
        rows = sorted(rows, key=lambda r: (-Decimal(r["total"] or 0), r["label"]))[:n]

    totals = _cells(pivot.col_totals)
    channel_words = dict(CHANNELS)
    return {
        "status": "ready",
        "report": "Sales",
        "company": company_name,
        "channel": channel_words.get(channel, channel) if channel else "All channels",
        "basis": BASIS_WORDS[basis],
        "period": result.period_label,
        "rows_label": row_label,
        "cols_label": col_label,
        "count_label": f"{row_label}s",
        "columns": columns + (["Difference"] if difference else []),
        "rows": rows,
        "totals": {"values": totals, "total": pivot.grand_total.get("sales_value")},
        "total_count": total_count,
        "attachments": [],
    }


def _prepare(
    db: Session,
    *,
    rows: str,
    cols: str,
    channel: Optional[str],
    basis: Optional[str],
    company: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    n: Optional[int],
    contact_id: str,
    space_id: str,
    principal_id: str,
) -> Union[Dict[str, Any], _Prepared]:
    """Every blocking step, on a worker thread (the low stock route's security B1 shape)."""
    from app.api.v1.reports.reports import _export_filename
    from app.config import settings
    from app.models.access import RespondContactCustomer
    from app.models.base import set_company_scope
    from app.models.company import Company, RespondContactCompany
    from app.schemas.report import ReportViewConfig
    from app.services import queue_service, rate_limit
    from app.services.contact_field_reveal_service import granted_keys
    from app.services.download_service import DownloadService
    from app.services.field_access import resolve_contact_with_null_workspace_fallback
    from app.services.reports import engine, registry as reg
    from app.tasks.report_export_tasks import generate_report_xlsx

    _validate(rows, cols, basis, date_from, date_to, n)
    if channel is not None and channel not in ("dealer", "project"):
        raise _unprocessable("Channel is dealer or project", "unknown_channel")

    resolved = resolve_contact_with_null_workspace_fallback(
        db, contact_id=contact_id, space_id=space_id
    )
    if not rate_limit.hit(
        "sales_analysis", str(resolved or contact_id),
        limit=_RATE_LIMIT, window_seconds=_RATE_WINDOW_SECONDS,
    ).allowed:
        return {"status": "busy", "message": "Too many sales reports in the last 10 minutes."}

    keys = granted_keys(db, resolved) if resolved else []
    if GRANT not in keys:
        raise AppException(
            status_code=403,
            message="Sales report is not enabled for your account.",
            code="sales_report_not_enabled",
        )
    is_dealer = db.query(RespondContactCustomer.id).filter(
        RespondContactCustomer.contact_id == str(resolved)
    ).first()
    if is_dealer is not None:
        return {"status": "refused", "message": REFUSAL}

    # The contact's OWN companies, read off the contact this route resolved (the low
    # stock route's rule 1): never the act-as principal's, which say nothing about them.
    grants = {
        str(c)
        for (c,) in db.query(RespondContactCompany.company_id)
        .filter(RespondContactCompany.respond_contact_id == str(resolved))
        .all()
        if c
    }
    companies = {
        str(i): (str(name), str(code))
        for i, name, code in db.query(Company.id, Company.name, Company.code).all()
    }
    if company:
        wanted = company.strip().casefold()
        match = [cid for cid, (name, code) in companies.items()
                 if wanted in (name.casefold(), code.casefold())]
        if not match:
            raise _unprocessable(f"Unknown company '{company}'", "unknown_company")
        if match[0] not in grants:
            raise AppException(status_code=403, message="You do not have access to that company",
                               code="COMPANY_FORBIDDEN")
        company_id = match[0]
    elif len(grants) == 1:
        company_id = next(iter(grants))
    elif grants:
        from app.services.company_scope import DEFAULT_COMPANY_ID

        names = [companies[c][0] for c in sorted(grants, key=lambda c: (c != DEFAULT_COMPANY_ID,
                                                                        companies[c][0]))]
        return {"status": "clarify", "message": _company_question(names)}
    else:
        return {"status": "error", "message": "Could not run the sales report right now."}

    definition = reg.get(REPORT_KEY)
    today = reg.today_malaysia()
    start = date_from or date(today.year, 1, 1)
    end = date_to or today
    params = {
        "date_basis": "order_date",
        "period": {"kind": "custom", "from": start.isoformat(), "to": end.isoformat()},
        "company": [company_id],
        "channel": [channel] if channel else [],
        "basis": [basis],
    }
    view = ReportViewConfig.model_validate({
        "params": params,
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": AXES[rows], "cols": AXES[cols], "measures": ["sales_value"]},
    })
    grant = frozenset({company_id})
    result = engine.run(db, definition, params, view, company_grants=grant)
    answer = _answer(
        result,
        company_name=companies[company_id][0],
        channel=channel,
        basis=basis,
        row_label=definition.dataset.column(AXES[rows]).label,
        col_label=definition.dataset.column(AXES[cols]).label,
        n=n,
    )

    # --- the file: the same params, the same view ------------------------------------
    owner_user_id = str(db.execute(text(
        "SELECT id FROM users WHERE respond_contact_id = :c AND status = 'ACTIVE' "
        "ORDER BY created_at, id LIMIT 1"
    ), {"c": str(resolved)}).scalar() or principal_id)
    set_company_scope(db, grant)
    ctx = engine.resolve(db, definition, params, company_grants=grant)
    download = DownloadService(db).create(
        user_id=owner_user_id,
        kind="report_xlsx",
        filename=_export_filename(definition, ctx.period),
    )
    download_id = str(download.id)
    answer["download_id"] = download_id
    try:
        queue_service.enqueue_job(
            generate_report_xlsx,
            download_id,
            REPORT_KEY,
            params,
            view.model_dump(mode="json"),
            owner_user_id,
            queue_name=settings.report_export_queue,
            job_timeout=600,
            company_grants=[company_id],
        )
    except Exception:  # noqa: BLE001 - the text still goes; the file is said not to
        log.exception("sales_analysis: could not queue the workbook for %s", download_id)
        DownloadService(db).mark_failed(download_id, "Could not queue the export")
        db.commit()
        answer["status"] = "error"
        return answer
    sync_wait = _sync_wait_seconds(db)
    db.commit()
    return _Prepared(answer=answer, download_id=download_id,
                     resolved_contact_id=str(resolved), sync_wait_seconds=sync_wait)


def _ready_attachments(db: Session, download_id: str) -> Optional[List[Dict[str, str]]]:
    from app.services.scm import low_stock_report_service

    row = db.execute(text(
        "SELECT status, storage_provider, storage_key, filename FROM user_downloads WHERE id = :id"
    ), {"id": download_id}).mappings().first()
    if not row or row["status"] != "ready" or not row["storage_key"]:
        return None
    key = row["storage_key"]
    url = low_stock_report_service.attachment_url(row["storage_provider"], key)
    return [{
        "url": url,
        "filename": key.rsplit("/", 1)[-1] or row["filename"] or "sales.xlsx",
        "mimeType": MIME_XLSX,
        "attachmentType": "file",
    }]


def _finish(db: Session, prepared: _Prepared, snapshot: Optional[dict]) -> Dict[str, Any]:
    answer = dict(prepared.answer)
    if snapshot is not None and snapshot.get("status") == "failed":
        answer["status"] = "error"
        return answer
    try:
        ready = _ready_attachments(db, prepared.download_id)
    except Exception:  # noqa: BLE001 - no URL is a file not sent, never a 500
        log.exception("sales_analysis: no attachment URL for %s", prepared.download_id)
        answer["status"] = "error"
        return answer
    if ready:
        answer["attachments"] = ready
        return answer
    claimed = db.execute(text(
        "UPDATE user_downloads SET deliver_to_contact_id = :c "
        "WHERE id = :id AND status <> 'ready'"
    ), {"c": prepared.resolved_contact_id, "id": prepared.download_id}).rowcount
    db.commit()
    if not claimed:
        ready = _ready_attachments(db, prepared.download_id)
        if ready:
            answer["attachments"] = ready
            return answer
    answer["status"] = "pending"
    return answer


@router.get("/analysis")
async def sales_analysis(
    rows: str = Query("channel"),
    cols: str = Query("year"),
    channel: Optional[str] = Query(None),
    basis: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    n: Optional[int] = Query(None),
    contact_id: str = Query(...),
    space_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(_GATE),
):
    """The answer (`ready` with the file, `pending` with the file on its way, `error` when
    the file failed but the figures stand), or `clarify` / `refused` / `busy` with one line
    and no file. All HTTP 200 except the 403s and 422s, because each is something the bot
    can say."""
    prepared = await asyncio.to_thread(
        _prepare, db,
        rows=rows, cols=cols, channel=channel, basis=basis, company=company,
        date_from=date_from, date_to=date_to, n=n,
        contact_id=contact_id, space_id=space_id, principal_id=str(current_user["id"]),
    )
    if isinstance(prepared, dict):
        return prepared
    try:
        snapshot = await asyncio.wait_for(
            _await_download(prepared.download_id), prepared.sync_wait_seconds
        )
    except asyncio.TimeoutError:
        snapshot = None
    except Exception:  # noqa: BLE001 - a failed poll falls through to the claim
        log.exception("sales_analysis: waiting on %s failed", prepared.download_id)
        snapshot = None
    return await asyncio.to_thread(_finish, db, prepared, snapshot)
