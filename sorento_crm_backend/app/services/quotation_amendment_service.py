"""Customer amendment requests on the quotation link (QUOTE-CUSTOMER-AMEND).

The customer suggests a quantity and/or a unit price per line, or a line's removal, on the sign
page of the issue they hold. The salesperson decides each suggestion on the quotation's own line
grid, and Apply drafts the next revision of ONLY the scopes with an accepted suggestion.

Three rules this module owns, each because the alternative was considered and is worse:

1. **A request never touches the issued lines.** What the customer holds stays what was sent; the
   suggestions live in their own rows until Apply writes them onto the COPY a revision makes.
2. **Accepted values go through the line writer.** ``upsert_line`` recomputes the floor flags and
   the total exactly as a hand edit does, so a below-floor price reaches the existing approval
   gate at issue and is not waved through because it arrived from a customer.
3. **No signing while a request is open.** Owner decision Q1 (a), reversing the 2026-08-05 rule
   for the free-text request: a signature beside unanswered suggestions is a record of both.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.projects import (
    AMENDMENT_DECISIONS,
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
from app.services import project_quotation_approval_service as approvals
from app.services import project_quotation_document_service as documents
from app.services import project_quotation_service as scopes
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

AMENDMENT_REQUESTED_TEMPLATE = "quotation_amendment_requested"

STATUS_OPEN = "open"
STATUS_APPLIED = "applied"
STATUS_SUPERSEDED = "superseded"

FIELD_QUANTITY = "quantity"
FIELD_PRICE = "unit_price"
FIELD_REMOVE = "remove"

MAX_QUANTITY = Decimal("9999999.99")
MAX_PRICE = Decimal("9999999999.99")
MAX_REASON = 500
_CENTS = Decimal("0.01")
# Digits, then at most two decimals. Written out rather than left to Decimal(), which also takes
# "1e3", "NaN" and "Infinity".
_AMOUNT = re.compile(r"^\d+(\.\d{1,2})?$")


# ------------------------------------------------------------------ reads


def open_request(db: Session, issue_id: str) -> Optional[QuotationAmendmentRequest]:
    return (
        db.query(QuotationAmendmentRequest)
        .filter(
            QuotationAmendmentRequest.issue_id == str(issue_id),
            QuotationAmendmentRequest.status == STATUS_OPEN,
        )
        .first()
    )


def request_for_issue(db: Session, issue_id: str) -> Optional[QuotationAmendmentRequest]:
    """The open request of an issue, else its latest answered one."""
    return open_request(db, issue_id) or (
        db.query(QuotationAmendmentRequest)
        .filter(QuotationAmendmentRequest.issue_id == str(issue_id))
        .order_by(QuotationAmendmentRequest.submitted_at.desc())
        .first()
    )


def latest_request_for_document(
    db: Session, document: ProjectQuotationDocument
) -> Optional[QuotationAmendmentRequest]:
    """What the Lines tab shows: the request on the document's LATEST issue, if there is one.

    A request on an older issue is history once a newer issue exists, so it is not offered for
    deciding here.
    """
    latest = documents.current_issue(db, document)
    if latest is None:
        return None
    return request_for_issue(db, latest.id)


def get_request_for_document_or_404(
    db: Session, document: ProjectQuotationDocument, request_id: str
) -> QuotationAmendmentRequest:
    """The request, checked against THIS document, not merely fetched by id."""
    request = (
        db.query(QuotationAmendmentRequest)
        .join(
            ProjectQuotationIssue,
            ProjectQuotationIssue.id == QuotationAmendmentRequest.issue_id,
        )
        .filter(
            QuotationAmendmentRequest.id == str(request_id),
            ProjectQuotationIssue.document_id == document.id,
        )
        .first()
    )
    if request is None:
        raise AppException(
            status_code=404,
            message="That suggestion request was not found.",
            code="quotation_amendment_not_found",
        )
    return request


def _rows_of(db: Session, request: QuotationAmendmentRequest) -> List[QuotationAmendmentRequestRow]:
    return (
        db.query(QuotationAmendmentRequestRow)
        .filter(QuotationAmendmentRequestRow.request_id == request.id)
        .order_by(QuotationAmendmentRequestRow.created_at, QuotationAmendmentRequestRow.id)
        .all()
    )


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


# ------------------------------------------------------------------ submit


def _refuse(status_code: int, code: str, message: str) -> AppException:
    return AppException(status_code=status_code, message=message, code=code)


def _amount(value: Any, code: str, message: str) -> Decimal:
    """A two-decimal amount from what the browser sent, or the lane's own 422."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise _refuse(422, code, message)
    text_value = str(value).strip()
    if not _AMOUNT.match(text_value):
        raise _refuse(422, code, message)
    try:
        return Decimal(text_value).quantize(_CENTS)
    except InvalidOperation:  # pragma: no cover - the pattern already excludes it
        raise _refuse(422, code, message)


def _assert_can_ask(db: Session, record: ProjectQuotationIssue) -> None:
    if record.accepted_at is not None:
        raise _refuse(
            409,
            "quotation_already_accepted",
            "This quotation has already been accepted. Contact Sorento if something needs to change.",
        )
    documents.assert_not_superseded(db, record)
    if open_request(db, record.id) is not None:
        raise _refuse(
            409,
            "quotation_amendment_open",
            "Your suggested changes are already with Sorento.",
        )
    answered = (
        db.query(QuotationAmendmentRequest.id)
        .filter(
            QuotationAmendmentRequest.issue_id == record.id,
            QuotationAmendmentRequest.status == STATUS_APPLIED,
        )
        .first()
    )
    if answered is not None:
        raise _refuse(
            409,
            "quotation_amendment_applied",
            "Sorento has answered your suggestions. Your salesperson will send the revised quotation.",
        )


def _rows_from(
    issued: Dict[str, Tuple[ProjectQuotationLine, ProjectQuotationIssueScope]],
    lines: Iterable[Dict[str, Any]],
) -> List[Tuple[ProjectQuotationLine, str, Optional[Decimal], Optional[Decimal]]]:
    """Validate every suggested line BEFORE anything is written: (line, field, from, to)."""
    rows: List[Tuple[ProjectQuotationLine, str, Optional[Decimal], Optional[Decimal]]] = []
    seen = set()
    for change in lines:
        line_id = str((change or {}).get("line_id") or "")
        entry = issued.get(line_id)
        if entry is None:
            # Never echoes the id, and never lists the ones that do exist.
            raise _refuse(
                422,
                "quotation_amendment_line_unknown",
                "One of these lines is not on this quotation.",
            )
        if line_id in seen:
            raise _refuse(
                422,
                "quotation_amendment_line_duplicate",
                "The same line appears twice in this request.",
            )
        seen.add(line_id)
        line = entry[0]
        quantity = change.get("quantity")
        price = change.get("unit_price")

        if change.get("remove") is True:
            if quantity is not None or price is not None:
                raise _refuse(
                    422,
                    "quotation_amendment_remove_conflict",
                    "A line marked for removal cannot also change its quantity or price.",
                )
            rows.append((line, FIELD_REMOVE, None, None))
            continue

        if quantity is not None:
            qty_message = "Quantity must be at least 1, with up to two decimals."
            value = _amount(quantity, "quotation_amendment_qty_invalid", qty_message)
            issued_qty = Decimal(line.quantity or 0).quantize(_CENTS)
            if value != issued_qty:
                if value < Decimal("1") or value > MAX_QUANTITY:
                    raise _refuse(422, "quotation_amendment_qty_invalid", qty_message)
                rows.append((line, FIELD_QUANTITY, issued_qty, value))

        if price is not None:
            price_message = "Unit price must be above 0, with up to two decimals."
            value = _amount(price, "quotation_amendment_price_invalid", price_message)
            issued_price = Decimal(line.unit_price or 0).quantize(_CENTS)
            if value != issued_price:
                if value <= 0 or value > MAX_PRICE:
                    raise _refuse(422, "quotation_amendment_price_invalid", price_message)
                # A zero-priced companion's money sits on its parent line.
                if issued_price == 0 and not line.is_rate_only:
                    raise _refuse(
                        422,
                        "quotation_amendment_price_invalid",
                        "The price of this line is part of the line above it.",
                    )
                rows.append((line, FIELD_PRICE, issued_price, value))
    return rows


def submit_request(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    lines: List[Dict[str, Any]],
    note: Optional[str],
    requester_name: Optional[str],
    ip_address: Optional[str],
) -> QuotationAmendmentRequest:
    """Store one request: the changed lines and the optional note, all or nothing.

    The issue is read ``FOR UPDATE`` so a double tap serialises and the second submit sees the
    first's open request; the partial unique index is the backstop under a true race.
    """
    locked = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == record.id)
        .with_for_update()
        .first()
    ) or record
    _assert_can_ask(db, locked)

    rows = _rows_from(_issued_lines(db, locked), lines or [])
    text_note = (note or "").strip() or None
    if not rows and not text_note:
        raise _refuse(
            422,
            "quotation_amendment_empty",
            "Change a quantity or price, or add a note, before sending.",
        )

    name = (requester_name or "").strip() or None
    now = datetime.utcnow()
    request = QuotationAmendmentRequest(
        company_id=locked.company_id,
        issue_id=locked.id,
        status=STATUS_OPEN,
        requester_name=name,
        note=text_note,
        ip_address=ip_address,
        submitted_at=now,
    )
    try:
        with db.begin_nested():
            db.add(request)
            db.flush()
            for line, field, value_from, value_to in rows:
                db.add(
                    QuotationAmendmentRequestRow(
                        company_id=locked.company_id,
                        request_id=request.id,
                        line_id=line.id,
                        field=field,
                        value_from=value_from,
                        value_to=value_to,
                    )
                )
            db.flush()
    except IntegrityError:
        raise _refuse(
            409,
            "quotation_amendment_open",
            "Your suggested changes are already with Sorento.",
        )

    # The free-text columns keep the existing panel and history working.
    if text_note:
        locked.changes_requested_at = now
        locked.changes_requested_note = text_note
        locked.changes_requested_by_name = name
        db.flush()

    _record_requested(
        db, record=locked, request=request, line_count=len({str(r[0].id) for r in rows})
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
            body_text=f"{who} suggested changes to {reference}"
            + (f": {request.note}" if request.note else "."),
        )
        db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "quotation amendment activity not written: issue=%s (%s)", record.id, exc
        )

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
        logger.warning(
            "quotation amendment notification not sent: issue=%s (%s)", record.id, exc
        )


# ------------------------------------------------------------------ decide


def _assert_open(request: QuotationAmendmentRequest) -> None:
    if request.status != STATUS_OPEN:
        raise _refuse(
            409,
            "quotation_amendment_not_open",
            "These suggestions have already been answered.",
        )


def decide_row(
    db: Session,
    *,
    request: QuotationAmendmentRequest,
    row_id: str,
    decision: str,
    reason: Optional[str],
    actor_user_id: str,
) -> QuotationAmendmentRequestRow:
    """Accept, reject (with an optional reason) or put one suggestion back to pending."""
    if decision not in AMENDMENT_DECISIONS:
        raise _refuse(
            422,
            "quotation_amendment_decision_invalid",
            "A decision is accepted, rejected or pending.",
        )
    text_reason = (reason or "").strip() or None
    if text_reason is not None and len(text_reason) > MAX_REASON:
        raise _refuse(
            422,
            "quotation_amendment_reason_too_long",
            f"Keep the reason to {MAX_REASON} characters.",
        )
    row = (
        db.query(QuotationAmendmentRequestRow)
        .filter(
            QuotationAmendmentRequestRow.id == str(row_id),
            QuotationAmendmentRequestRow.request_id == request.id,
        )
        .first()
    )
    if row is None:
        raise _refuse(404, "quotation_amendment_row_not_found", "That suggestion was not found.")
    _assert_open(request)

    row.decision = decision
    # A reason explains a rejection; it does not survive the row being decided otherwise.
    row.decision_reason = text_reason if decision == "rejected" else None
    if decision == "pending":
        row.decided_by = None
        row.decided_at = None
    else:
        row.decided_by = actor_user_id
        row.decided_at = datetime.utcnow()
    db.flush()
    return row


# ------------------------------------------------------------------ apply


def _assert_no_later_draft(
    db: Session, touched: List[Tuple[ProjectQuotation, ProjectQuotationIssueScope]]
) -> None:
    """A touched scope must still sit on the version the customer was sent.

    Merging into a hand-edited draft would mean matching lines by position, because a revision
    gives its copies new ids: a guess, so it is refused instead.
    """
    for scope, pair in touched:
        live = scopes.current_version(db, scope.id)
        if str(live.id) != str(pair.version_id):
            raise _refuse(
                409,
                "quotation_amendment_draft_open",
                f"A revision is already open on {scope.scope_label}; issue or discard it first.",
            )


def apply_request(
    db: Session,
    *,
    request: QuotationAmendmentRequest,
    actor_user_id: str,
    written: Optional[List[ProjectQuotationLine]] = None,
) -> List[ProjectQuotationVersion]:
    """Draft the next revision of every scope with an accepted suggestion. Returns the drafts.

    Every refusal is checked before the first write, so a refused Apply leaves nothing behind.
    The result is a DRAFT: nothing is issued, and a below-floor price stops it issuing until a
    manager approves (``assert_issuable``).

    ``written``, when passed, receives every line an accepted value was written onto, so the
    caller can send the same below-floor alert a hand edit sends (``pop_breach_events``) once
    the write is committed.
    """
    _assert_open(request)
    rows = _rows_of(db, request)
    if any(row.decision == "pending" for row in rows):
        raise _refuse(
            422,
            "quotation_amendment_undecided",
            "Accept or reject every suggestion before applying.",
        )

    record = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == request.issue_id)
        .first()
    )
    issued = _issued_lines(db, record) if record is not None else {}
    accepted = [row for row in rows if row.decision == "accepted"]

    # Scopes in the issue's own order, each once.
    touched: List[Tuple[ProjectQuotation, ProjectQuotationIssueScope]] = []
    seen = set()
    for row in accepted:
        entry = issued.get(str(row.line_id))
        if entry is None:
            continue
        pair = entry[1]
        if str(pair.quotation_id) in seen:
            continue
        seen.add(str(pair.quotation_id))
        scope = db.query(ProjectQuotation).filter(ProjectQuotation.id == pair.quotation_id).first()
        if scope is not None:
            touched.append((scope, pair))
    touched.sort(key=lambda item: (item[1].sort_order or 0))

    if touched and record is not None:
        document = (
            db.query(ProjectQuotationDocument)
            .filter(ProjectQuotationDocument.id == record.document_id)
            .first()
        )
        approvals.assert_unlocked(db, document)
        _assert_no_later_draft(db, touched)

    drafts: List[ProjectQuotationVersion] = []
    for scope, pair in touched:
        copies: Dict[str, ProjectQuotationLine] = {}
        draft = scopes.revise(
            db, quotation=scope, actor_user_id=actor_user_id, line_map=copies
        )
        for row in accepted:
            entry = issued.get(str(row.line_id))
            if entry is None or str(entry[1].quotation_id) != str(scope.id):
                continue
            copy = copies.get(str(row.line_id))
            if copy is None:
                continue
            if row.field == FIELD_REMOVE:
                scopes.delete_line(db, version=draft, line=copy)
                copies.pop(str(row.line_id), None)
                continue
            line = scopes.upsert_line(
                db,
                version=draft,
                actor_user_id=actor_user_id,
                payload={row.field: Decimal(row.value_to)},
                line=copy,
            )
            if written is not None and line not in written:
                written.append(line)
        drafts.append(draft)

    request.status = STATUS_APPLIED
    request.applied_at = datetime.utcnow()
    request.applied_by = actor_user_id
    db.flush()
    return drafts


# ------------------------------------------------------------------ superseded


def close_open_requests_superseded_by(
    db: Session, document: ProjectQuotationDocument, new_issue: ProjectQuotationIssue
) -> int:
    """A newer revision went out while a request was open: that request is closed, unanswered."""
    older = (
        db.query(QuotationAmendmentRequest)
        .join(
            ProjectQuotationIssue,
            ProjectQuotationIssue.id == QuotationAmendmentRequest.issue_id,
        )
        .filter(
            ProjectQuotationIssue.document_id == document.id,
            ProjectQuotationIssue.id != new_issue.id,
            QuotationAmendmentRequest.status == STATUS_OPEN,
        )
        .all()
    )
    for request in older:
        request.status = STATUS_SUPERSEDED
    if older:
        db.flush()
    return len(older)


# ------------------------------------------------------------------ serialize


def _floors_for(
    db: Session, rows: List[QuotationAmendmentRequestRow]
) -> Dict[str, Optional[Decimal]]:
    """The floor of every line with a suggested price, through the line writer's own rule."""
    floors: Dict[str, Optional[Decimal]] = {}
    for row in rows:
        if row.field != FIELD_PRICE or str(row.line_id) in floors:
            continue
        line = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == row.line_id).first()
        floor = None
        if line is not None:
            version = (
                db.query(ProjectQuotationVersion)
                .filter(ProjectQuotationVersion.id == line.version_id)
                .first()
            )
            scope = (
                db.query(ProjectQuotation)
                .filter(ProjectQuotation.id == version.quotation_id)
                .first()
                if version is not None
                else None
            )
            product = (
                db.query(Product).filter(Product.id == line.product_id).first()
                if line.product_id
                else None
            )
            if scope is not None:
                resolved = scopes.line_floor(db, line=line, quotation=scope, product=product)
                floor = resolved.value if resolved is not None else None
        floors[str(row.line_id)] = floor
    return floors


def _totals(
    db: Session, request: QuotationAmendmentRequest, rows: List[QuotationAmendmentRequestRow]
) -> Tuple[Decimal, Decimal]:
    """What the issue came to, and what it would come to with the ACCEPTED rows applied.

    By the same rule every total uses (``line_amount``: a rate-only line adds nothing), so the
    summary row cannot disagree with the draft Apply is about to write.
    """
    record = (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.id == request.issue_id)
        .first()
    )
    if record is None:
        return Decimal("0.00"), Decimal("0.00")
    accepted: Dict[str, Dict[str, Optional[Decimal]]] = {}
    for row in rows:
        if row.decision == "accepted":
            accepted.setdefault(str(row.line_id), {})[row.field] = row.value_to
    before = Decimal("0.00")
    after = Decimal("0.00")
    for line_id, (line, _pair) in _issued_lines(db, record).items():
        amount = documents.line_amount(line)
        before += amount
        changes = accepted.get(line_id)
        if not changes:
            after += amount
            continue
        if FIELD_REMOVE in changes or line.is_rate_only:
            continue
        quantity = Decimal(changes.get(FIELD_QUANTITY) or line.quantity or 0)
        price = Decimal(changes.get(FIELD_PRICE) or line.unit_price or 0)
        after += (quantity * price).quantize(_CENTS)
    return before, after


def serialize_request(
    db: Session, request: Optional[QuotationAmendmentRequest], *, staff: bool = True
) -> Optional[Dict[str, Any]]:
    """The request and its rows. Staff get ``below_floor`` / ``floor_value`` on price rows and the
    totals; the customer's page does not (``staff=False``), because a floor is internal pricing."""
    if request is None:
        return None
    rows = _rows_of(db, request)
    floors = _floors_for(db, rows) if staff else {}
    serialized = []
    for row in rows:
        item: Dict[str, Any] = {
            "id": str(row.id),
            "line_id": str(row.line_id),
            "field": row.field,
            "value_from": row.value_from,
            "value_to": row.value_to,
            "decision": row.decision,
            "decision_reason": row.decision_reason,
        }
        if staff:
            floor = floors.get(str(row.line_id)) if row.field == FIELD_PRICE else None
            item["floor_value"] = floor
            item["below_floor"] = bool(
                floor is not None
                and row.value_to is not None
                and Decimal(row.value_to) < Decimal(floor)
            )
        serialized.append(item)
    payload: Dict[str, Any] = {
        "id": str(request.id),
        "status": request.status,
        "submitted_at": request.submitted_at,
        "requester_name": request.requester_name,
        "note": request.note,
        "applied_at": request.applied_at,
        "rows": serialized,
    }
    if staff:
        payload["total_issued"], payload["total_after"] = _totals(db, request, rows)
    return payload
