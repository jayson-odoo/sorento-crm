"""Customer feedback on the quotation link (QUOTE-CUSTOMER-AMEND, reworked by PS-QUOTE-MATRIX).

The customer leaves notes on the sign page of the issue they hold: on a whole item or on one cell,
optionally with a hint (a quantity, a price, "remove this", another model at a price). Two rules
this module owns:

1. **Feedback never touches a line.** Nothing is accepted, rejected or applied; the salesperson
   reads the notes and edits the draft however they see fit, then ticks a note handled.
2. **Feedback never blocks.** A second submit, signing and issuing all work with notes open, so no
   code here gates anything on an earlier request.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    AMENDMENT_FIELDS,
    Project,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
    ProjectQuotationVersion,
    QuotationAmendmentRequest,
    QuotationAmendmentRequestRow,
)
from app.services import project_quotation_document_service as documents
from app.services import quotation_matrix as matrix
from app.services.error_handler import AppException
from app.services.project_quotation_service import line_text

logger = logging.getLogger(__name__)

AMENDMENT_REQUESTED_TEMPLATE = "quotation_amendment_requested"

FIELD_QUANTITY = "quantity"
FIELD_PRICE = "unit_price"
FIELD_REMOVE = "remove"
FIELD_SWAP = "model_swap"
FIELD_NOTE = "note"

MAX_QUANTITY = Decimal("9999999.99")
MAX_PRICE = Decimal("9999999999.99")
MAX_NOTE = 1000
# A link is public, so repeat feedback is capped per issue by its TOTAL request count (simpler
# than counting only unhandled ones, and a customer with 50 submits has said it all).
MAX_REQUESTS_PER_ISSUE = 50
FEEDBACK_LIST_LIMIT = 50
MAX_MODEL = 200
_CENTS = Decimal("0.01")
# Digits, then at most two decimals. Written out rather than left to Decimal(), which also takes
# "1e3", "NaN" and "Infinity".
_AMOUNT = re.compile(r"^\d+(\.\d{1,2})?$")


def _refuse(status_code: int, code: str, message: str) -> AppException:
    return AppException(status_code=status_code, message=message, code=code)


# ------------------------------------------------------------------ submit


def _amount(value: Any, code: str, message: str) -> Decimal:
    """A two-decimal amount from what the browser sent, or the lane's own 422."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise _refuse(422, code, message)
    text_value = str(value).strip()
    # Length first: a 30-digit string passes the pattern but overflows Decimal's context in
    # quantize (a 500). The longest legal amount is 10 digits, a dot and 2 decimals.
    if len(text_value) > 32 or not _AMOUNT.match(text_value):
        raise _refuse(422, code, message)
    try:
        return Decimal(text_value).quantize(_CENTS)
    except InvalidOperation:
        raise _refuse(422, code, message)


def _issued_lines(
    db: Session, record: ProjectQuotationIssue
) -> Dict[str, Tuple[ProjectQuotationLine, ProjectQuotationIssueScope]]:
    """Every line the issue carried, keyed by id, with the (scope, version) pair it came from."""
    pairs = (
        db.query(ProjectQuotationIssueScope)
        .filter(ProjectQuotationIssueScope.issue_id == record.id)
        .all()
    )
    by_version = {str(pair.version_id): pair for pair in pairs}
    if not by_version:
        return {}
    lines = (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id.in_(list(by_version)))
        .all()
    )
    return {str(line.id): (line, by_version[str(line.version_id)]) for line in lines}


def _assert_can_ask(db: Session, record: ProjectQuotationIssue) -> None:
    if record.accepted_at is not None:
        raise _refuse(
            409,
            "quotation_already_accepted",
            "This quotation has already been accepted. Contact Sorento if something needs to change.",
        )
    documents.assert_not_superseded(db, record)


def _rows_from(
    db: Session,
    issued: Dict[str, Tuple[ProjectQuotationLine, ProjectQuotationIssueScope]],
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Validate every item BEFORE anything is written; one dict per row to store."""
    columns_of: Dict[str, List[Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        line_id = str(item.get("line_id") or "")
        entry = issued.get(line_id)
        if entry is None:
            # Never echoes the id, and never lists the ones that do exist.
            raise _refuse(
                422, "quotation_amendment_line_unknown", "One of these lines is not on this quotation."
            )
        line, pair = entry
        kind = item.get("kind")
        if kind not in AMENDMENT_FIELDS:
            raise _refuse(422, "quotation_feedback_kind_invalid", "That kind of note is not known.")

        cell_key = (item.get("cell_key") or "").strip() or None
        if cell_key is not None:
            if kind not in (FIELD_NOTE, FIELD_QUANTITY):
                raise _refuse(
                    422,
                    "quotation_feedback_cell_kind",
                    "A cell takes a note or a quantity, nothing else.",
                )
            vid = str(pair.version_id)
            if vid not in columns_of:
                version = (
                    db.query(ProjectQuotationVersion)
                    .filter(ProjectQuotationVersion.id == pair.version_id)
                    .first()
                )
                columns_of[vid] = (version.matrix_columns if version else None) or []
            if matrix.cell_label(columns_of[vid], cell_key) is None:
                raise _refuse(
                    422, "quotation_feedback_cell_unknown", "That cell is not on this quotation."
                )

        key = (line_id, cell_key, kind)
        if key in seen:
            raise _refuse(
                422,
                "quotation_amendment_line_duplicate",
                "The same note appears twice in this request.",
            )
        seen.add(key)

        note = (item.get("note") or "").strip() or None
        if note is not None and len(note) > MAX_NOTE:
            raise _refuse(422, "quotation_feedback_note_invalid", f"Keep a note to {MAX_NOTE} characters.")
        value = item.get("value")
        value_from: Optional[Decimal] = None
        value_to: Optional[Decimal] = None
        hint: Optional[str] = None

        if kind == FIELD_NOTE:
            if note is None:
                raise _refuse(422, "quotation_feedback_note_required", "Write the note before sending.")
        elif kind == FIELD_QUANTITY:
            message = "Quantity must be between 0 and 9,999,999.99, with up to two decimals."
            if value is None:
                raise _refuse(422, "quotation_amendment_qty_invalid", message)
            value_to = _amount(value, "quotation_amendment_qty_invalid", message)
            if value_to > MAX_QUANTITY:
                raise _refuse(422, "quotation_amendment_qty_invalid", message)
            if cell_key is not None:
                value_from = Decimal(str((line.qty_cells or {}).get(cell_key, 0))).quantize(_CENTS)
            else:
                value_from = Decimal(line.quantity or 0).quantize(_CENTS)
        elif kind == FIELD_PRICE:
            message = "Unit price must be above 0, with up to two decimals."
            if value is None:
                raise _refuse(422, "quotation_amendment_price_invalid", message)
            value_to = _amount(value, "quotation_amendment_price_invalid", message)
            if value_to <= 0 or value_to > MAX_PRICE:
                raise _refuse(422, "quotation_amendment_price_invalid", message)
            value_from = Decimal(line.unit_price or 0).quantize(_CENTS)
        elif kind == FIELD_REMOVE:
            if value is not None:
                raise _refuse(422, "quotation_feedback_value_invalid", "Removing an item takes no value.")
        else:  # model_swap
            hint = " ".join((item.get("model") or "").split())
            if not hint or len(hint) > MAX_MODEL:
                raise _refuse(
                    422, "quotation_feedback_model_invalid", f"Name the other model, up to {MAX_MODEL} characters."
                )
            if value is not None:
                message = "Unit price must be above 0, with up to two decimals."
                value_to = _amount(value, "quotation_amendment_price_invalid", message)
                if value_to <= 0 or value_to > MAX_PRICE:
                    raise _refuse(422, "quotation_amendment_price_invalid", message)

        rows.append(
            {
                "line_id": line.id,
                "field": kind,
                "cell_key": cell_key,
                "value_from": value_from,
                "value_to": value_to,
                "hint_text": hint,
                "note": note,
            }
        )
    return rows


def submit_request(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    items: List[Dict[str, Any]],
    note: Optional[str],
    requester_name: Optional[str],
    ip_address: Optional[str],
) -> QuotationAmendmentRequest:
    """Store one request: its notes and the optional top-level note, all or nothing."""
    locked = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == record.id)
        .with_for_update()
        .first()
    ) or record
    _assert_can_ask(db, locked)
    sent = (
        db.query(func.count(QuotationAmendmentRequest.id))
        .filter(QuotationAmendmentRequest.issue_id == locked.id)
        .scalar()
    )
    if (sent or 0) >= MAX_REQUESTS_PER_ISSUE:
        raise _refuse(
            429,
            "quotation_feedback_limit",
            "You have sent a lot of feedback on this quotation. Please contact Sorento directly.",
        )

    rows = _rows_from(db, _issued_lines(db, locked), items or [])
    text_note = (note or "").strip() or None
    if not rows and not text_note:
        raise _refuse(422, "quotation_feedback_empty", "Add a note before sending.")

    # One line: the name is quoted into a notification title and a WhatsApp message.
    name = " ".join((requester_name or "").split()) or None
    now = datetime.utcnow()
    request = QuotationAmendmentRequest(
        company_id=locked.company_id,
        issue_id=locked.id,
        status="open",
        requester_name=name,
        note=text_note,
        ip_address=ip_address,
        submitted_at=now,
    )
    db.add(request)
    db.flush()
    for row in rows:
        db.add(
            QuotationAmendmentRequestRow(company_id=locked.company_id, request_id=request.id, **row)
        )
    db.flush()

    # The free-text columns keep the existing panel and history working.
    if text_note:
        locked.changes_requested_at = now
        locked.changes_requested_note = text_note
        locked.changes_requested_by_name = name
        db.flush()

    _record_requested(
        db, record=locked, request=request, line_count=len({str(r["line_id"]) for r in rows})
    )
    return request


def _record_requested(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    request: QuotationAmendmentRequest,
    line_count: int,
) -> None:
    """Tell the feed and the salesperson. Best-effort, both: the request is already stored."""
    document = (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id == record.document_id)
        .first()
    )
    project = (
        db.query(Project).filter(Project.id == document.project_id).first()
        if document is not None
        else None
    )
    if project is None:
        return

    who = request.requester_name or "The customer"
    reference = record.our_ref_text or (document.document_no if document else "")
    try:
        from app.services import project_activity_service as activity

        activity.record_project_event(
            db,
            project=project,
            template=AMENDMENT_REQUESTED_TEMPLATE,
            payload={
                "document_id": str(record.document_id),
                "issue_id": str(record.id),
                "issue_no": record.issue_no,
                "our_ref": reference,
                "request_id": str(request.id),
                "line_count": line_count,
                "requested_by": request.requester_name,
            },
            body_text=f"{who} left feedback on {reference}"
            + (f": {request.note}" if request.note else "."),
        )
        db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("quotation feedback activity not written: issue=%s (%s)", record.id, exc)

    try:
        from app.services import project_notify_service as notify

        notify.notify_quotation_amendment_requested(
            db,
            project=project,
            document=document,
            record=record,
            request=request,
            line_count=line_count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("quotation feedback notification not sent: issue=%s (%s)", record.id, exc)


# ------------------------------------------------------------------ staff


def feedback_for_document(
    db: Session, document: ProjectQuotationDocument, *, request_id: Optional[str] = None
) -> Dict[str, Any]:
    """The latest requests on the document, newest first, rows in line order.

    ``open_count`` counts every unhandled row of the document, not just the ones listed.
    ``request_id`` lists that one request instead, however old: the Handled tick answers with its
    row, which can sit in a request older than the latest page.
    """
    from app.models.user import User

    open_count = (
        db.query(func.count(QuotationAmendmentRequestRow.id))
        .join(
            QuotationAmendmentRequest,
            QuotationAmendmentRequest.id == QuotationAmendmentRequestRow.request_id,
        )
        .join(ProjectQuotationIssue, ProjectQuotationIssue.id == QuotationAmendmentRequest.issue_id)
        .filter(
            ProjectQuotationIssue.document_id == document.id,
            QuotationAmendmentRequestRow.handled_at.is_(None),
        )
        .scalar()
    ) or 0
    query = (
        db.query(QuotationAmendmentRequest, ProjectQuotationIssue)
        .join(ProjectQuotationIssue, ProjectQuotationIssue.id == QuotationAmendmentRequest.issue_id)
        .filter(ProjectQuotationIssue.document_id == document.id)
    )
    if request_id is not None:
        query = query.filter(QuotationAmendmentRequest.id == str(request_id))
    requests = (
        query.order_by(QuotationAmendmentRequest.submitted_at.desc(), QuotationAmendmentRequest.id)
        .limit(FEEDBACK_LIST_LIMIT)
        .all()
    )
    by_request: Dict[str, List[QuotationAmendmentRequestRow]] = {}
    if requests:
        for row in (
            db.query(QuotationAmendmentRequestRow)
            .filter(QuotationAmendmentRequestRow.request_id.in_([r.id for r, _i in requests]))
            .all()
        ):
            by_request.setdefault(str(row.request_id), []).append(row)

    line_ids = {str(r.line_id) for rows in by_request.values() for r in rows}
    lines = (
        {
            str(l.id): l
            for l in db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id.in_(line_ids)).all()
        }
        if line_ids
        else {}
    )
    versions = (
        {
            str(v.id): v
            for v in db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.id.in_({str(l.version_id) for l in lines.values()}))
            .all()
        }
        if lines
        else {}
    )
    scopes = (
        {
            str(s.id): s
            for s in db.query(ProjectQuotation)
            .filter(ProjectQuotation.id.in_({str(v.quotation_id) for v in versions.values()}))
            .all()
        }
        if versions
        else {}
    )
    scope_order = (
        {
            str(p.quotation_id): p.sort_order or 0
            for p in db.query(ProjectQuotationIssueScope)
            .filter(ProjectQuotationIssueScope.issue_id.in_([str(i.id) for _r, i in requests]))
            .all()
        }
        if requests
        else {}
    )
    handler_ids = {r.handled_by for rows in by_request.values() for r in rows if r.handled_by}
    names = (
        {u.id: (u.name or u.email) for u in db.query(User).filter(User.id.in_(handler_ids)).all()}
        if handler_ids
        else {}
    )

    def position(row: QuotationAmendmentRequestRow):
        line = lines.get(str(row.line_id))
        version = versions.get(str(line.version_id)) if line else None
        return (
            scope_order.get(str(version.quotation_id), 0) if version else 0,
            line.sort_order or 0 if line else 0,
            line.created_at or datetime.min if line else datetime.min,
            str(row.line_id),
            row.created_at or datetime.min,
            str(row.id),
        )

    out: List[Dict[str, Any]] = []
    for request, issue in requests:
        rows = []
        for row in sorted(by_request.get(str(request.id), []), key=position):
            line = lines.get(str(row.line_id))
            version = versions.get(str(line.version_id)) if line else None
            scope = scopes.get(str(version.quotation_id)) if version else None
            rows.append(
                {
                    "id": str(row.id),
                    "line_id": str(row.line_id),
                    "scope_id": str(scope.id) if scope else None,
                    "scope_label": scope.scope_label if scope else None,
                    "line_description": line_text(line) if line else None,
                    "cell_key": row.cell_key,
                    "cell_label": (
                        matrix.cell_label(version.matrix_columns, row.cell_key)
                        if row.cell_key and version
                        else None
                    ),
                    "kind": row.field,
                    "value_from": row.value_from,
                    "value_to": row.value_to,
                    "model": row.hint_text,
                    "note": row.note,
                    "handled_at": row.handled_at,
                    "handled_by_name": names.get(row.handled_by or ""),
                }
            )
        out.append(
            {
                "id": str(request.id),
                "issue_label": issue.revision_label or issue.our_ref_text,
                "submitted_at": request.submitted_at,
                "requester_name": request.requester_name,
                "note": request.note,
                "rows": rows,
            }
        )
    return {"open_count": open_count, "requests": out}


def set_handled(
    db: Session,
    *,
    document: ProjectQuotationDocument,
    row_id: str,
    handled: bool,
    actor_user_id: str,
) -> QuotationAmendmentRequestRow:
    """Tick a note handled (who and when) or reopen it. The only thing staff do to a note."""
    row = (
        db.query(QuotationAmendmentRequestRow)
        .join(
            QuotationAmendmentRequest,
            QuotationAmendmentRequest.id == QuotationAmendmentRequestRow.request_id,
        )
        .join(ProjectQuotationIssue, ProjectQuotationIssue.id == QuotationAmendmentRequest.issue_id)
        .filter(
            QuotationAmendmentRequestRow.id == str(row_id),
            ProjectQuotationIssue.document_id == document.id,
        )
        .first()
    )
    if row is None:
        raise _refuse(404, "quotation_feedback_not_found", "That note was not found.")
    row.handled_at = datetime.utcnow() if handled else None
    row.handled_by = actor_user_id if handled else None
    db.flush()
    return row


# ------------------------------------------------------------------ customer page


def sign_page_feedback(db: Session, issue_id: str) -> Optional[Dict[str, Any]]:
    """What the sign page reads of notes already sent: where they point, to mark those spots."""
    requests = (
        db.query(QuotationAmendmentRequest)
        .filter(QuotationAmendmentRequest.issue_id == str(issue_id))
        .order_by(QuotationAmendmentRequest.submitted_at.desc(), QuotationAmendmentRequest.id)
        .all()
    )
    if not requests:
        return None
    rows = (
        db.query(QuotationAmendmentRequestRow)
        .filter(QuotationAmendmentRequestRow.request_id.in_([r.id for r in requests]))
        .order_by(QuotationAmendmentRequestRow.created_at, QuotationAmendmentRequestRow.id)
        .all()
    )
    latest = requests[0]
    return {
        "id": str(latest.id),
        "submitted_at": latest.submitted_at,
        "requester_name": latest.requester_name,
        "note": latest.note,
        "rows": [
            {"id": str(r.id), "line_id": str(r.line_id), "cell_key": r.cell_key, "field": r.field}
            for r in rows
        ],
    }
