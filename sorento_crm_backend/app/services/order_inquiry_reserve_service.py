"""Order inquiry: request CS to reserve stock (`PLAN-oi-request-cs-reserve.md`, slices
2/3; `oi-request-cs-reserve-acceptance-criteria.md` AC-RS-1 to AC-RS-21, AC-RS-30/31/32).

R1-R11 (owner, 22 Sep 2026). Purchasing asks CS to cover part of a raised row from own or
pool stock before buying the balance: `create_request` (3.2) writes one
`OrderInquiryReserveRequest` plus one row per named order-inquiry row and dispatches ONE
`order_inquiry_reserve_requested` email (R9); `reserve` (3.3) is Eling's own Confirm - it
writes one `OrderInquiryLink` per row reserved above zero, naming the reserve request row
as its target (the THIRD leg the widened `ck_order_inquiry_links_one_target` CHECK now
allows), refreshes the row's own coverage state through the SAME writer every other link
uses (`ProjectOrderInquiryService.refresh_link_state`), and dispatches ONE
`order_inquiry_reserved` email. `cancel_request` (3.2) is the requester's own undo while
nothing has been reserved yet - no email, R5's "no amend after confirm" applies once
`reserved`, and reversal from there is the existing Unlink (AC-RS-14), never a fresh
writer here.

**Post-commit dispatch** mirrors `_dispatch_changed_with_links` /
`register_order_inquiry_post_commit_dispatch` in `project_order_inquiry_service.py`
(9355), the SIMPLER of that file's two shapes - not `_fire_pending_handover`'s
transaction-chain bookkeeping, which exists there because ONE write can give several
sibling orders their own savepoint and a failing one must not discard an already-earned
sibling's queued item. Neither `create_request` nor `reserve` ever opens a savepoint of
its own, so there is no sibling to protect and the plain queue-on-`Session.info` /
drain-`after_commit` / discard-`after_soft_rollback` shape is the whole of what "simplest
thing that works" asks for here. Context is built EAGERLY, before the commit that queues
it (the same reason `_record_handover` does: several callers run deep inside somebody
else's transaction, and `AutomationService` commits internally, which a fresh session
reads only once the write it is about has actually landed).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import event, func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
    RESERVE_CANCELLED,
    RESERVE_REQUESTED,
    RESERVE_RESERVED,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_REQUESTABLE_VERBS = (IV_ORDER, IV_ORDER_BACK)
_REQUESTABLE_STATES = (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)


def _dec(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a malformed number is data, not a crash
        return _ZERO


def _qty_str(value: Any) -> str:
    """`50`, never `50.0000` - `_qty_str` everywhere else in this domain."""
    return format(_dec(value).normalize(), "f")


def _fmt_date(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d/%m/%Y")


def _row_label(row: OrderInquiryRow) -> str:
    return row.item_code or str(row.id)


def _remaining(db: Session, row: OrderInquiryRow) -> Decimal:
    """`row.qty - sum(links.qty) - bundled_qty` (plan 3.2) - the row's own arithmetic,
    not the worklist's line-outstanding-capped `_UNLINKED_QTY`: a reserve request is
    about what THIS row itself still has open, the same way the row's own qty is what
    the request caps `qty_requested` against (AC-RS-3)."""
    linked = db.query(func.coalesce(func.sum(OrderInquiryLink.qty), 0)).filter(
        OrderInquiryLink.row_id == row.id
    ).scalar()
    return _dec(row.qty) - _dec(linked) - _dec(row.bundled_qty)


def _default_warehouse_id(db: Session, stock_location: Optional[str]) -> Optional[str]:
    """The pool of `stock_location` (R3): `BRW-BB` -> `BRW`'s own id; a bare pool code
    resolves to itself, since it names no `pool_warehouse_id` of its own."""
    if not stock_location:
        return None
    warehouse = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == stock_location).first()
    )
    if warehouse is None:
        return None
    return warehouse.pool_warehouse_id or warehouse.id


def _warehouse_code(db: Session, warehouse_id: Optional[str]) -> Optional[str]:
    if not warehouse_id:
        return None
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    return warehouse.warehouse_code if warehouse is not None else None


def _person(db: Session, user_id: Optional[str]) -> Optional[Dict[str, str]]:
    """`{name, email}`, or `None` - the same shape `_handover_actor` builds
    (`project_order_inquiry_service.py:3150`)."""
    if not user_id:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.email:
        return None
    return {"name": user.name or user.email, "email": user.email}


def _open_request_row_ids(db: Session, row_ids: Sequence[str]) -> set:
    if not row_ids:
        return set()
    rows = (
        db.query(OrderInquiryReserveRequestRow.row_id)
        .join(
            OrderInquiryReserveRequest,
            OrderInquiryReserveRequest.id == OrderInquiryReserveRequestRow.request_id,
        )
        .filter(
            OrderInquiryReserveRequestRow.row_id.in_(list(row_ids)),
            OrderInquiryReserveRequest.state == RESERVE_REQUESTED,
        )
        .all()
    )
    return {row_id for (row_id,) in rows}


def _row_context(db: Session, row: OrderInquiryRow, rr: OrderInquiryReserveRequestRow) -> Dict[str, Any]:
    """One `reserve.rows[]` entry, read fresh off the row/request-row at dispatch time -
    the same field set both the request and the reserved template read (3.6): `remaining`
    doubles as the request mail's REMAINING and the reserved mail's BALANCE, since the two
    templates print it at different MOMENTS (before the request changes nothing, after the
    reserve link has already landed) rather than under two different keys."""
    return {
        "item_code": row.item_code,
        "delivery_date": _fmt_date(row.delivery_date),
        "qty": _qty_str(row.qty),
        "remaining": _qty_str(_remaining(db, row)),
        "qty_requested": _qty_str(rr.qty_requested),
        "location": _warehouse_code(db, rr.warehouse_id),
        "qty_reserved": _qty_str(rr.qty_reserved) if rr.qty_reserved is not None else None,
        "reason": rr.reason,
    }


def _build_context(
    db: Session,
    request: OrderInquiryReserveRequest,
    pairs: Sequence[tuple],
    *,
    actor_user_id: Optional[str],
) -> Dict[str, Any]:
    """The shared context both triggers dispatch with (plan 3.6): `actor` is whoever DID
    this action (the requester for the request event, the reserver for the reserved
    event); `requester` is always the request's own `requested_by`, so the reserved
    email's `include_requester` keeps naming the ORIGINAL asker even though `actor` has
    moved on to Eling."""
    from app.services.automation_triggers import build_order_inquiry_link
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    inquiry = (
        db.query(OrderInquiry).filter(OrderInquiry.id == request.order_inquiry_id).first()
    )
    facts: Dict[str, Any] = {}
    if inquiry is not None:
        facts = ProjectOrderInquiryService(db)._handover_order_facts(
            inquiry.project_sales_order_id
        )
    rows_ctx = [_row_context(db, row, rr) for rr, row in pairs]
    link = f"{build_order_inquiry_link(request.order_inquiry_id)}?reserve={request.id}"
    reserve = {
        "inquiry_no": inquiry.inquiry_no if inquiry is not None else None,
        "ordinal": request.ordinal,
        "so_number": facts.get("so_number"),
        "customer": facts.get("customer"),
        "project": facts.get("project"),
        "requested_by": _person(db, request.requested_by),
        "requested_at": _fmt_date(request.requested_at),
        "note": request.note,
        "rows": rows_ctx,
        "row_count": len(rows_ctx),
        "state": request.state,
        "link": link,
    }
    return {
        "reserve": reserve,
        "actor": _person(db, actor_user_id),
        "raiser": _person(db, inquiry.raised_by) if inquiry is not None else None,
        "requester": _person(db, request.requested_by),
        "today": date.today().strftime("%d/%m/%Y"),
    }


class OrderInquiryReserveService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------ 3.2 request

    def create_request(
        self,
        *,
        inquiry_id: str,
        rows: Sequence[Dict[str, Any]],
        note: Optional[str],
        actor_user_id: Optional[str],
    ) -> OrderInquiryReserveRequest:
        inquiry = self.db.query(OrderInquiry).filter(OrderInquiry.id == inquiry_id).first()
        if inquiry is None:
            raise AppException(
                404, "This order inquiry no longer exists.", code="order_inquiry_not_found"
            )
        if not rows:
            raise AppException(
                422, "Select at least one row to request.", code="reserve_request_no_rows"
            )

        row_ids = [str(entry["row_id"]) for entry in rows]
        by_id = {
            row.id: row
            for row in self.db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.id.in_(row_ids))
            .all()
        }
        already_open = _open_request_row_ids(self.db, row_ids)

        prepared: List[tuple] = []
        for entry in rows:
            row_id = str(entry["row_id"])
            row = by_id.get(row_id)
            if row is None or str(row.order_inquiry_id) != str(inquiry_id):
                raise AppException(
                    409,
                    f"Row {row_id} does not belong to this order inquiry.",
                    code="reserve_request_wrong_inquiry",
                )
            if row.verb not in _REQUESTABLE_VERBS:
                raise AppException(
                    409,
                    f"{_row_label(row)} is not an ORDER / ORDER BACK row and cannot be "
                    "requested for reserve.",
                    code="reserve_request_wrong_verb",
                )
            if row.state not in _REQUESTABLE_STATES:
                raise AppException(
                    409,
                    f"{_row_label(row)} is not open for a reserve request.",
                    code="reserve_request_wrong_state",
                )
            if row_id in already_open:
                raise AppException(
                    409,
                    f"{_row_label(row)} already has an open reserve request.",
                    code="reserve_request_already_open",
                )
            remaining = _remaining(self.db, row)
            if remaining <= _ZERO:
                raise AppException(
                    409,
                    f"{_row_label(row)} has nothing left to request.",
                    code="reserve_request_nothing_remaining",
                )
            qty_requested = _dec(entry.get("qty_requested"))
            if qty_requested <= _ZERO or qty_requested > remaining:
                raise AppException(
                    422,
                    f"{_row_label(row)}: requested quantity must be more than 0 and at "
                    f"most {_qty_str(remaining)}.",
                    code="reserve_request_qty_out_of_range",
                )
            warehouse_id = entry.get("warehouse_id") or _default_warehouse_id(
                self.db, row.stock_location
            )
            prepared.append((row, qty_requested, warehouse_id))

        ordinal = (
            self.db.query(func.coalesce(func.max(OrderInquiryReserveRequest.ordinal), 0))
            .filter(OrderInquiryReserveRequest.order_inquiry_id == inquiry_id)
            .scalar()
            or 0
        ) + 1

        request = OrderInquiryReserveRequest(
            id=str(uuid.uuid4()),
            company_id=inquiry.company_id,
            order_inquiry_id=inquiry_id,
            ordinal=ordinal,
            state=RESERVE_REQUESTED,
            requested_by=actor_user_id,
            note=note,
        )
        self.db.add(request)
        self.db.flush()

        pairs = []
        for row, qty_requested, warehouse_id in prepared:
            rr = OrderInquiryReserveRequestRow(
                id=str(uuid.uuid4()),
                company_id=inquiry.company_id,
                request_id=request.id,
                row_id=row.id,
                qty_requested=qty_requested,
                warehouse_id=warehouse_id,
            )
            self.db.add(rr)
            pairs.append((rr, row))
        self.db.flush()

        context = _build_context(self.db, request, pairs, actor_user_id=actor_user_id)
        self.db.info.setdefault(_REQUESTED_PENDING_KEY, []).append(
            {"context": context, "source_id": str(request.id)}
        )
        return request

    # ------------------------------------------------------------- 3.2 cancel

    def cancel_request(
        self, *, request_id: str, actor_user_id: Optional[str]
    ) -> OrderInquiryReserveRequest:
        request = (
            self.db.query(OrderInquiryReserveRequest)
            .filter(OrderInquiryReserveRequest.id == request_id)
            .first()
        )
        if request is None:
            raise AppException(
                404,
                "This reserve request no longer exists.",
                code="reserve_request_not_found",
            )
        if request.state != RESERVE_REQUESTED:
            raise AppException(
                409,
                "Only an open reserve request can be cancelled.",
                code="reserve_request_not_cancellable",
            )
        request.state = RESERVE_CANCELLED
        request.cancelled_by = actor_user_id
        request.cancelled_at = datetime.utcnow()
        self.db.flush()
        return request

    # ------------------------------------------------------------- 3.3 reserve

    def reserve(
        self,
        *,
        request_id: str,
        rows: Sequence[Dict[str, Any]],
        actor_user_id: Optional[str],
    ) -> OrderInquiryReserveRequest:
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        request = (
            self.db.query(OrderInquiryReserveRequest)
            .filter(OrderInquiryReserveRequest.id == request_id)
            .first()
        )
        if request is None:
            raise AppException(
                404,
                "This reserve request no longer exists.",
                code="reserve_request_not_found",
            )
        if request.state != RESERVE_REQUESTED:
            raise AppException(
                409,
                "This reserve request is no longer open.",
                code="reserve_request_not_open",
            )

        request_rows = {
            rr.id: rr
            for rr in self.db.query(OrderInquiryReserveRequestRow)
            .filter(OrderInquiryReserveRequestRow.request_id == request.id)
            .all()
        }
        answered = {str(entry["request_row_id"]) for entry in rows}
        if answered != set(request_rows.keys()):
            raise AppException(
                422,
                "Every row of this request must be answered in one call.",
                code="reserve_request_incomplete",
            )

        prepared: List[tuple] = []
        for entry in rows:
            rr = request_rows[str(entry["request_row_id"])]
            row = self.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == rr.row_id).first()
            if row is None:
                raise AppException(
                    409,
                    "One of this request's rows no longer exists.",
                    code="reserve_request_row_missing",
                )
            qty_reserved = _dec(entry.get("qty_reserved"))
            if qty_reserved < _ZERO or qty_reserved > _dec(rr.qty_requested):
                raise AppException(
                    422,
                    f"{_row_label(row)}: reserved quantity must be between 0 and "
                    f"{_qty_str(rr.qty_requested)}.",
                    code="reserve_qty_out_of_range",
                )
            reason = (entry.get("reason") or "").strip() or None
            if qty_reserved < _dec(rr.qty_requested) and not reason:
                raise AppException(
                    422,
                    f"{_row_label(row)}: a reason is required when reserving less than "
                    "requested.",
                    code="reserve_reason_required",
                )
            warehouse_id = entry.get("warehouse_id") or rr.warehouse_id
            prepared.append((rr, row, qty_reserved, warehouse_id, reason))

        touched_rows: List[OrderInquiryRow] = []
        for rr, row, qty_reserved, warehouse_id, reason in prepared:
            rr.qty_reserved = qty_reserved
            rr.reason = reason
            rr.warehouse_id = warehouse_id
            if qty_reserved > _ZERO:
                code = _warehouse_code(self.db, warehouse_id) or ""
                self.db.add(
                    OrderInquiryLink(
                        id=str(uuid.uuid4()),
                        company_id=row.company_id,
                        row_id=row.id,
                        reserve_request_row_id=rr.id,
                        document=f"Reserved @ {code}",
                        qty=qty_reserved,
                        linked_by=actor_user_id,
                        auto=False,
                    )
                )
                touched_rows.append(row)
        self.db.flush()
        if touched_rows:
            ProjectOrderInquiryService(self.db).refresh_link_state(touched_rows)

        request.state = RESERVE_RESERVED
        request.reserved_by = actor_user_id
        request.reserved_at = datetime.utcnow()
        self.db.flush()

        pairs = [(rr, row) for rr, row, *_rest in prepared]
        context = _build_context(self.db, request, pairs, actor_user_id=actor_user_id)
        self.db.info.setdefault(_RESERVED_PENDING_KEY, []).append(
            {"context": context, "source_id": str(request.id)}
        )
        return request


# --------------------------------------------------------------- post-commit dispatch

#: `Session.info` keys for the two dispatches this module queues mid-transaction and
#: fires once the session actually commits - see `register_order_inquiry_reserve_post_
#: commit_dispatch` below and its module docstring for why this is the SIMPLER of the
#: two shapes `project_order_inquiry_service.py` carries.
_REQUESTED_PENDING_KEY = "oi_reserve_requested_pending"
_RESERVED_PENDING_KEY = "oi_reserve_reserved_pending"

_POST_COMMIT_DISPATCH_REGISTERED = False


def register_order_inquiry_reserve_post_commit_dispatch() -> None:
    """Fire every queued reserve dispatch once this session's write actually commits.

    Copied from `_dispatch_changed_with_links` / `register_order_inquiry_post_commit_
    dispatch` (`project_order_inquiry_service.py:9355`) - queue on `Session.info`, drain
    on `after_commit` with a FRESH session (a dispatch is real, independent work;
    `AutomationService` commits its own outbox rows), discard on `after_soft_rollback`.
    Idempotent and called once at startup, same as every other global session listener
    this app registers.
    """
    global _POST_COMMIT_DISPATCH_REGISTERED
    if _POST_COMMIT_DISPATCH_REGISTERED:
        return

    def _drain(session, key: str, trigger_type: str, source_kind: str) -> None:
        pending = session.info.pop(key, None)
        if not pending:
            return
        from app.database import SessionLocal
        from app.services.automation_service import AutomationService

        fresh = SessionLocal()
        try:
            for item in pending:
                try:
                    AutomationService(fresh).dispatch_event(
                        trigger_type,
                        context=item["context"],
                        source_kind=source_kind,
                        source_id=item["source_id"],
                    )
                except Exception:  # noqa: BLE001 - a post-commit side effect never raises
                    fresh.rollback()
                    logger.exception(
                        "Automation dispatch(%s) failed for reserve request %s",
                        trigger_type,
                        item.get("source_id"),
                    )
        finally:
            fresh.close()

    @event.listens_for(Session, "after_commit")
    def _fire_pending_reserve_requested(session):  # noqa: ANN001
        _drain(
            session,
            _REQUESTED_PENDING_KEY,
            "order_inquiry_reserve_requested",
            "order_inquiry_reserve_request",
        )

    @event.listens_for(Session, "after_commit")
    def _fire_pending_reserve_reserved(session):  # noqa: ANN001
        _drain(
            session,
            _RESERVED_PENDING_KEY,
            "order_inquiry_reserved",
            "order_inquiry_reserve_request",
        )

    @event.listens_for(Session, "after_soft_rollback")
    def _discard_pending_reserve(session, previous_transaction):  # noqa: ANN001
        session.info.pop(_REQUESTED_PENDING_KEY, None)
        session.info.pop(_RESERVED_PENDING_KEY, None)

    _POST_COMMIT_DISPATCH_REGISTERED = True
