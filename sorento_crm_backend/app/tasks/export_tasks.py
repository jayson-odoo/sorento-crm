"""Background tasks for user-requested exports (My Downloads).

Decoupled from the request path: the API creates a UserDownload row (status
'pending') and enqueues one of these tasks. The task renders the artifact,
uploads it to the default storage provider, and flips the row to 'ready' (with a
storage key) or 'failed' (with an error). The "My Downloads" drawer polls the
per-user rows while any are in flight.
"""
import logging
from typing import Optional

from app.database import SessionLocal
from app.services.company_scope import set_company_scope
from app.services.download_service import DownloadService
from app.services.storage_router import default_provider, get_backend

logger = logging.getLogger(__name__)


def _record_failure(db, svc: DownloadService, download_id: str, error: Exception, label: str) -> None:
    """Write the failure onto the download row, whatever it was that failed.

    The rollback is the point. When the thing that failed was the DATABASE - a query against a
    column the running code expects and the schema does not yet have, say - psycopg2 leaves the
    transaction aborted, and every later statement on that session raises
    `InFailedSqlTransaction`. `mark_failed` is a later statement on that session, so without a
    rollback first it raises too, and the row is left sitting in 'processing' for good: the
    drawer polls it forever, and its sweeper only reaps rows in 'sent'. The user is told nothing.

    Marking the failure is itself best-effort - if even this cannot be written, log it and let
    the task return normally rather than poisoning RQ's failed registry.
    """
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 - a session too broken to roll back is still worth trying
        logger.exception("%s: rollback before marking download %s failed", label, download_id)
    try:
        svc.mark_failed(download_id, str(error))
    except Exception:  # noqa: BLE001
        logger.exception("%s: could not mark download %s failed", label, download_id)


def generate_complaint_pdf(download_id: str, complaint_id: str, user_id: str) -> dict:
    """Render a complaint PDF, store it, and update the download row.

    Best-effort and self-contained: any failure marks the download 'failed' with
    a readable message rather than raising into RQ's failed registry.
    """
    db = SessionLocal()
    # Worker sessions default to the fail-closed UNSET scope; complaints are a
    # global (non-owned) entity and their attachments are shared, so run this
    # export system-wide (all companies).
    set_company_scope(db, None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services.complaint_pdf_service import ComplaintPDFService

        pdf_bytes, filename = ComplaintPDFService(db).render_pdf(complaint_id)

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/complaint-pdf/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=pdf_bytes,
            file_path=key,
            content_type="application/pdf",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info("generate_complaint_pdf: download %s ready (%d bytes)", download_id, len(pdf_bytes))
        return {"download_id": download_id, "status": "ready", "bytes": len(pdf_bytes)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_complaint_pdf failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_complaint_pdf")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_stock_inquiry_pdf(
    download_id: str,
    inquiry_id: str,
    user_id: str,
    revision_id: Optional[str] = None,
    include_revisions: bool = False,
) -> dict:
    """Render a product inquiry PDF, store it, and update the download row.

    Best-effort and self-contained: any failure marks the download 'failed' with
    a readable message rather than raising into RQ's failed registry.

    ``revision_id`` / ``include_revisions`` were added by
    PLAN-portal-submission-revisions 6.3/6.4. They are ordinary
    positional-or-keyword parameters WITH DEFAULTS, and the routes pass them by
    keyword; the defaults are what keeps a job queued by an older release -
    three positional args, no keywords - running here unchanged.
    """
    db = SessionLocal()
    # Worker sessions default to the fail-closed UNSET scope; stock inquiries are a
    # global (non-owned) entity and their attachments are shared, so run this
    # export system-wide (all companies) - same as the complaint export.
    set_company_scope(db, None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services.stock_inquiry_pdf_service import StockInquiryPDFService

        pdf_bytes, filename = StockInquiryPDFService(db).render_pdf(
            inquiry_id,
            revision_id=revision_id,
            include_revisions=bool(include_revisions),
        )

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/product-inquiry-pdf/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=pdf_bytes,
            file_path=key,
            content_type="application/pdf",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_stock_inquiry_pdf: download %s ready (%d bytes)", download_id, len(pdf_bytes)
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(pdf_bytes)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_stock_inquiry_pdf failed for download %s", download_id)
        try:
            svc.mark_failed(download_id, str(e))
        except Exception:
            logger.exception(
                "generate_stock_inquiry_pdf: could not mark download %s failed", download_id
            )
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_purchase_request_pdf(
    download_id: str,
    request_id: str,
    user_id: str,
    revision_id: Optional[str] = None,
    include_revisions: bool = False,
) -> dict:
    """Render a purchase request / sponsorship form PDF, store it, update the row.

    Best-effort and self-contained: any failure marks the download 'failed' with a
    readable message rather than raising into RQ's failed registry. Mirrors
    generate_stock_inquiry_pdf, including the optional revision parameters and
    their defaults.
    """
    db = SessionLocal()
    # Worker sessions default to the fail-closed UNSET scope. PR/SF are global
    # (non-owned) and their attachments are shared, so export system-wide - the
    # same choice the complaint and stock-inquiry exports make.
    set_company_scope(db, None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services.purchase_request_pdf_service import PurchaseRequestPDFService

        pdf_bytes, filename = PurchaseRequestPDFService(db).render_pdf(
            request_id,
            revision_id=revision_id,
            include_revisions=bool(include_revisions),
        )

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/purchase-request-pdf/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=pdf_bytes,
            file_path=key,
            content_type="application/pdf",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_purchase_request_pdf: download %s ready (%d bytes)",
            download_id,
            len(pdf_bytes),
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(pdf_bytes)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_purchase_request_pdf failed for download %s", download_id)
        try:
            svc.mark_failed(download_id, str(e))
        except Exception:
            logger.exception(
                "generate_purchase_request_pdf: could not mark download %s failed", download_id
            )
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_promotions_pdf(
    download_id: str, promotion_ids: list, user_id: str, company_id: Optional[str] = None
) -> dict:
    """Compile the selected promotions' attachment flyers into one PDF, store it,
    and update the download row.

    Best-effort and self-contained: any failure marks the download 'failed' with
    a readable message rather than raising into RQ's failed registry.
    """
    db = SessionLocal()
    # Worker sessions default to the fail-closed UNSET scope, which would hide the
    # owned Promotion/PromotionAttachment rows. Re-establish the enqueuer's active
    # company (snapshotted at enqueue) so the export actually sees them; None =
    # system-wide (e.g. a system principal that enqueued without a single company).
    set_company_scope(db, frozenset({company_id}) if company_id else None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services.promotions_pdf_service import PromotionsPdfService

        pdf_bytes, filename, skipped = PromotionsPdfService(db).render_pdf(list(promotion_ids or []))

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/promotions-pdf/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=pdf_bytes,
            file_path=key,
            content_type="application/pdf",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_promotions_pdf: download %s ready (%d bytes, %d skipped)",
            download_id, len(pdf_bytes), len(skipped),
        )
        return {
            "download_id": download_id,
            "status": "ready",
            "bytes": len(pdf_bytes),
            "skipped": skipped,
        }
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_promotions_pdf failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_promotions_pdf")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def _quotation_issue_or_die(db, issue_id: str):
    """The issue row the export renders from, or a readable failure.

    The download row outlives what it points at - a document can be deleted between the
    enqueue and the render - so a missing revision has to become a failed download rather
    than an AttributeError deep inside the renderer.
    """
    from app.models.projects import ProjectQuotationIssue

    issue = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == str(issue_id))
        .first()
    )
    if issue is None:
        raise ValueError(
            "This revision no longer exists, so it cannot be exported."
        )
    return issue


def generate_quotation_issue_pdf(
    download_id: str, issue_id: str, user_id: str, company_id: Optional[str] = None
) -> dict:
    """Render one issued quotation as a PDF, store it, and update the download row.

    The renderer is the SAME one the on-demand route uses and it still reads the ISSUE
    snapshot, so a download next year is what was sent. What is new is only that the bytes are
    persisted once, as this download job's artifact - nothing else ever reads that object, and
    the document itself keeps rendering on demand.

    Best-effort and self-contained: any failure marks the download 'failed' with a readable
    message rather than raising into RQ's failed registry.
    """
    db = SessionLocal()
    # Worker sessions default to the fail-closed UNSET scope, which would hide every
    # company-owned quotation row. Re-establish the enqueuer's active company (snapshotted at
    # enqueue); None = system-wide, for a principal with no single company.
    set_company_scope(db, frozenset({company_id}) if company_id else None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services import project_quotation_pdf_service as pdf

        pdf_bytes, filename = pdf.render_issue_pdf(
            db, _quotation_issue_or_die(db, issue_id)
        )

        provider = default_provider()
        backend = get_backend(provider)
        # Keyed by DOWNLOAD id, not by the reference: two exports of the same revision are two
        # rows, and a shared key would have the second silently overwrite the first's file.
        key = f"exports/quotation-pdf/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=pdf_bytes,
            file_path=key,
            content_type="application/pdf",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_quotation_issue_pdf: download %s ready (%d bytes)",
            download_id, len(pdf_bytes),
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(pdf_bytes)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_quotation_issue_pdf failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_quotation_issue_pdf")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_quotation_issue_xlsx(
    download_id: str, issue_id: str, user_id: str, company_id: Optional[str] = None
) -> dict:
    """Render one issued quotation as a workbook, store it, and update the download row.

    Same snapshot as the PDF, so the two artifacts of one revision can never quote different
    money. Separate task rather than a format flag: they upload under different prefixes with
    different mime types, and an xlsx served as application/pdf downloads as a file Excel
    refuses to open.
    """
    db = SessionLocal()
    set_company_scope(db, frozenset({company_id}) if company_id else None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services import project_quotation_excel_service as excel

        payload, filename = excel.render_issue_xlsx(
            db, _quotation_issue_or_die(db, issue_id)
        )

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/quotation-xlsx/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=payload,
            file_path=key,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_quotation_issue_xlsx: download %s ready (%d bytes)",
            download_id, len(payload),
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(payload)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_quotation_issue_xlsx failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_quotation_issue_xlsx")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_chat_history_csv(download_id: str, filters: dict) -> dict:
    """Stream a chat-history CSV to storage and update the download row.

    CSV rather than XLSX, and streamed from a keyset walk rather than materialised:
    message text is long and the row count over a wide date range is unbounded, so
    building a spreadsheet in memory is the wrong shape. Memory stays flat regardless
    of how much the filter matches.
    """
    import csv
    import io
    from datetime import datetime

    db = SessionLocal()
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        from app.services.chat_history_query import MAX_LIMIT, list_messages

        def _dt(value):
            if not value:
                return None
            return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "sent_at_utc", "respond_ts_utc", "direction", "contact", "phone",
            "message", "turn_id", "message_id", "delivery_status",
            "latency_seconds", "webhook_lag_seconds",
        ])

        cursor = None
        rows_written = 0
        while True:
            rows, cursor = list_messages(
                db,
                date_from=_dt(filters.get("date_from")),
                date_to=_dt(filters.get("date_to")),
                contact_id=filters.get("contact_id"),
                direction=filters.get("direction"),
                search=filters.get("search"),
                breached_only=bool(filters.get("breached_only")),
                limit=MAX_LIMIT,
                cursor=cursor,
            )
            for r in rows:
                writer.writerow([
                    r.sent_at.isoformat() if r.sent_at else "",
                    r.respond_ts.isoformat() if r.respond_ts else "",
                    r.type,
                    r.contact_display,
                    r.phone_number,
                    r.message,
                    r.turn_id or "",
                    r.message_id or "",
                    r.delivery_status or "",
                    f"{r.latency_seconds:.3f}" if r.latency_seconds is not None else "",
                    f"{r.webhook_lag_seconds:.3f}" if r.webhook_lag_seconds is not None else "",
                ])
                rows_written += 1
            if not cursor:
                break

        content = buffer.getvalue().encode("utf-8-sig")  # BOM so Excel reads UTF-8
        filename = f"chat-history-{rows_written}-rows.csv"

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/chat-history/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=content,
            file_path=key,
            content_type="text/csv",
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_chat_history_csv: download %s ready (%d rows, %d bytes)",
            download_id, rows_written, len(content),
        )
        return {"download_id": download_id, "status": "ready", "rows": rows_written}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_chat_history_csv failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_chat_history_csv")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_order_sheet(download_id: str, run_id: str, fmt: str, user_id: str) -> dict:
    """Render the reorder run's order sheet, store it, and update the download row.

    S4, PLAN-po-spo-site-pool-and-order-sheet-downloads.md (AC-15..AC-17). Mirrors
    `generate_complaint_pdf` line for line: `mark_processing`, render, upload, `mark_ready`
    - `_record_failure` on any exception, never raising into RQ.

    The row's OWN filename - stamped by the route at creation time, `order-sheet-
    <as_of ddmmyyyy>.<ext>` (AC-15) - is read back and reused for the storage key and the
    `mark_ready` call, rather than `summary_order_service.export_report`'s own returned
    name: that function still carries the "order-summary-..." convention the retired
    synchronous GET used, and passing it through would silently rename the row.
    """
    db = SessionLocal()
    # Security S1 (review fix round A, A2): the worker has NO request-scoped company - a
    # bare `set_company_scope(db, None)` here would read every company's rows, which is
    # exactly the isolation break `_adopt_run_company_scope` exists to close for
    # `run_reorder` itself. The run row is the one thing that states which company this
    # export belongs to, so it is read under NO scope (the row itself is what tells us),
    # then its OWN company is adopted before anything company-scoped is touched -
    # `reorder_run_service._adopt_run_company_scope`, the same shape
    # `generate_promotions_pdf` above uses via its own snapshotted `company_id` param.
    from app.models.base import get_company_scope
    from app.models.scm import ReorderRun
    from app.services.scm.reorder_run_service import _adopt_run_company_scope

    # C3 (review fix round C): restored in `finally`, the same shape `_execute_run` uses
    # for `run_reorder` (reorder_run_service.py ~L548-560) - a caller whose session this
    # task reuses (a synchronous test, `_NoCloseSession`) did not ask to have its scope
    # changed underneath it, and leaving the run's company adopted after return would
    # silently re-scope whatever that caller reads next.
    caller_scope = get_company_scope(db)
    set_company_scope(db, None)
    run = db.get(ReorderRun, run_id)
    if run is not None:
        _adopt_run_company_scope(db, run)
    else:
        logger.warning(
            "generate_order_sheet: run %s not found; export runs under no company", run_id
        )
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)
        row = svc.get(download_id)
        filename = row.filename if row else None

        from app.services.scm import summary_order_service

        file_bytes, content_type, fallback_filename = summary_order_service.export_report(
            db, run_id=run_id, fmt=fmt,
        )
        filename = filename or fallback_filename

        provider = default_provider()
        backend = get_backend(provider)
        key = f"exports/order-sheet/{download_id}/{filename}"
        stored_key, _signed = backend.upload_file(
            file_content=file_bytes,
            file_path=key,
            content_type=content_type,
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_order_sheet: download %s ready (%d bytes)", download_id, len(file_bytes)
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(file_bytes)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_order_sheet failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_order_sheet")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        set_company_scope(db, caller_scope)
        db.close()
