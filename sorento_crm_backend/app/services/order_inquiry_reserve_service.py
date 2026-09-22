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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryReserveEvent,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    OrderInquiryRow,
    RESERVE_CANCELLED,
    RESERVE_EVENT_RESERVED,
    RESERVE_EVENT_UNRESERVED,
    RESERVE_REQUESTED,
    RESERVE_RESERVED,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_REQUESTABLE_VERBS = (IV_ORDER, IV_ORDER_BACK)
_REQUESTABLE_STATES = (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)


def _dec(value: Any) -> Decimal:
    # SF-9 (security review): `Decimal("nan")`/`Decimal("inf")` construct cleanly -
    # neither raises here - and only blow up (`decimal.InvalidOperation`, an uncaught
    # 500) on the FIRST comparison a caller makes against the result. The schema-level
    # `_finite_qty` validator (`app/schemas/project_order_inquiry.py`) is the real gate
    # for the three request-body fields; this is the belt-and-braces for every other
    # caller of `_dec` (a live `qty`/`qty_requested` read off the row itself, for one),
    # so a non-finite value is treated exactly like the "not a number at all" case
    # already below it, not left to crash three lines downstream.
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value if value.is_finite() else _ZERO
    try:
        parsed = Decimal(str(value))
    except Exception:  # noqa: BLE001 - a malformed number is data, not a crash
        return _ZERO
    return parsed if parsed.is_finite() else _ZERO


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


def _validated_warehouse_id(
    db: Session, warehouse_id: Optional[str], row_label: str
) -> Optional[str]:
    """SF-3 (review round): `warehouse_id` - whichever of the two writers sets it,
    explicit on the payload or R3's own default - must resolve through the SAME
    company-scoped ORM query every other reader of `Warehouse` uses, to an ACTIVE row,
    or 422 naming the row. A foreign-company id is invisible to this query already
    (`do_orm_execute`'s own company-scope filter), so it reads exactly like a bad id
    rather than needing a second, explicit tenant check."""
    if not warehouse_id:
        return None
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if warehouse is None or not warehouse.is_active:
        raise AppException(
            422,
            f"{row_label}: choose an active warehouse.",
            code="reserve_bad_warehouse",
        )
    return warehouse.id


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


def _actor_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    """A history entry's own `actor_name` (F3): a human name or email, never a UUID
    (CLAUDE.md Cursor rules) - the same reading `_serialize_reserve_request`'s local
    `_name` helper uses for `requested_by_name`/`reserved_by_name`."""
    if not user_id:
        return None
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    return user.name or user.email


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
            warehouse_id = _validated_warehouse_id(self.db, warehouse_id, _row_label(row))
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
            # Explicit, not the column's own `server_default=func.now()`: several
            # writes in this feature's own lifecycle (a request, then a reserve, then
            # an unreserve) commonly land in the SAME outer Postgres transaction
            # (`tests/_pg_fixture.py`'s savepoint mode; a real request can share one
            # too), and `now()` is frozen for the whole transaction block
            # (LESSONS-LEARNT "now() ties in transaction") - the History tab's own
            # "newest first" would tie every entry to one instant and fall back to
            # insertion order, which is requested-first, never what the reader wants.
            requested_at=datetime.utcnow(),
            note=note,
        )
        self.db.add(request)
        try:
            self.db.flush()
        except IntegrityError:
            # SF-8 (review round): a genuine race - another session minted this SAME
            # ordinal between the read above and this INSERT. The partial/unique index
            # (`uq_order_inquiry_reserve_requests_ordinal`) is what caught it; rolling
            # back to the savepoint (same shape `form_action_service.py`'s own pending-
            # action park uses) keeps the session usable for the caller's 409, never an
            # unhandled 500. Simpler than a re-mint-and-retry: the loser's request is
            # small enough that "click again" costs nothing, and a blind retry here
            # cannot tell a genuine collision apart from a real duplicate ordinal bug.
            self.db.rollback()
            raise AppException(
                409,
                "Another reserve request was just raised for this inquiry. Try again.",
                code="reserve_request_ordinal_collision",
            )

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
        self,
        *,
        request_id: str,
        actor_user_id: Optional[str],
        actor_can_reserve: bool = False,
    ) -> OrderInquiryReserveRequest:
        """SF-1 (review round): the route/deferred-action gate only proves the actor
        holds ONE of the two purchasing-side grants (`ACKNOWLEDGE`/`RESERVE`) - it says
        nothing about whether THIS request is theirs. Ownership is checked HERE: the
        requester who raised it, or anyone holding the reserve permission (Eling may
        always withdraw an ask nobody has answered yet), never a colleague who merely
        also holds `ACKNOWLEDGE`. `actor_can_reserve` is the caller's own fact -
        computed at the route for an immediate cancel, and recomputed at commit time for
        the deferred one (`record_actions.py`) - never re-derived here, so this method
        stays a pure permission-free ownership check."""
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
        is_requester = (
            actor_user_id is not None and str(actor_user_id) == str(request.requested_by)
        )
        if not (is_requester or actor_can_reserve):
            raise AppException(
                403,
                "Only the person who requested this, or CS, may cancel it.",
                code="reserve_request_cancel_forbidden",
            )
        request.state = RESERVE_CANCELLED
        request.cancelled_by = actor_user_id
        request.cancelled_at = datetime.utcnow()
        self.db.flush()
        return request

    # -------------------------------------------------- 3.3 / 6c F2: reserve, per row

    def reserve_row(
        self,
        *,
        request_id: str,
        row_id: str,
        warehouse_id: Optional[str],
        qty_reserved: Any,
        reason: Optional[str],
        actor_user_id: Optional[str],
    ) -> OrderInquiryReserveRequestRow:
        """Eling answers ONE row of a request (`PLAN-oi-request-cs-reserve.md` section
        6c, F2 - supersedes the old all-rows 3.3). The request stays `requested` while
        any row is unanswered and becomes `reserved` - with exactly ONE
        `order_inquiry_reserved` dispatch, naming every row of the request - on the
        answer that completes it. `row_id` is `OrderInquiryRow.id`, never the request
        row's own id (module docstring, NAMED ASSUMPTION 1)."""
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
        if request.state == RESERVE_CANCELLED:
            raise AppException(
                409,
                "This reserve request is no longer open.",
                code="reserve_request_not_open",
            )

        # SF-9 (security review): `.with_for_update()` closes the lost-update race - two
        # concurrent reserves on the SAME request row used to both read `qty_reserved is
        # None`, both pass, and both insert their own link. This lock serializes the two
        # transactions on this row, so the loser re-reads it already answered and 409s on
        # the guard below, the same shape `create_request`'s ordinal race already used.
        rr = (
            self.db.query(OrderInquiryReserveRequestRow)
            .filter(
                OrderInquiryReserveRequestRow.request_id == request.id,
                OrderInquiryReserveRequestRow.row_id == row_id,
            )
            .with_for_update()
            .first()
        )
        if rr is None:
            raise AppException(
                404,
                "That row is not part of this reserve request.",
                code="reserve_request_row_not_found",
            )
        if rr.qty_reserved is not None:
            raise AppException(
                409,
                "This row has already been answered.",
                code="reserve_request_row_already_answered",
            )

        row = self.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == rr.row_id).first()
        if row is None:
            raise AppException(
                409,
                "This request's row no longer exists.",
                code="reserve_request_row_missing",
            )

        # SF-5 (round 1, carried over): `qty_requested` is frozen at REQUEST time - a
        # PO/SPO link placed on the row afterwards, before Eling answers, lowers what
        # is actually left. The cap is the SMALLER of the two.
        live_remaining = _remaining(self.db, row)
        cap = min(_dec(rr.qty_requested), live_remaining)
        qty_reserved_dec = _dec(qty_reserved)
        if qty_reserved_dec < _ZERO or qty_reserved_dec > cap:
            raise AppException(
                422,
                f"{_row_label(row)}: reserved quantity must be between 0 and "
                f"{_qty_str(cap)}.",
                code="reserve_qty_out_of_range",
            )
        reason_clean = (reason or "").strip() or None
        # R2's "short of the request" reads against the row's own LIVE cap, not the
        # frozen `qty_requested`: reserving everything that is actually still left is
        # not a choice Eling made to explain, even though it reads short of what was
        # first asked.
        if qty_reserved_dec < cap and not reason_clean:
            raise AppException(
                422,
                f"{_row_label(row)}: a reason is required when reserving less than "
                "requested.",
                code="reserve_reason_required",
            )
        warehouse_id_final = warehouse_id or rr.warehouse_id
        warehouse_id_final = _validated_warehouse_id(
            self.db, warehouse_id_final, _row_label(row)
        )

        rr.qty_reserved = qty_reserved_dec
        rr.reason = reason_clean
        rr.warehouse_id = warehouse_id_final
        if qty_reserved_dec > _ZERO:
            code = _warehouse_code(self.db, warehouse_id_final) or ""
            self.db.add(
                OrderInquiryLink(
                    id=str(uuid.uuid4()),
                    company_id=row.company_id,
                    row_id=row.id,
                    reserve_request_row_id=rr.id,
                    document=f"Reserved @ {code}",
                    qty=qty_reserved_dec,
                    linked_by=actor_user_id,
                    auto=False,
                )
            )
            self.db.add(
                OrderInquiryReserveEvent(
                    id=str(uuid.uuid4()),
                    company_id=row.company_id,
                    reserve_request_row_id=rr.id,
                    kind=RESERVE_EVENT_RESERVED,
                    qty=qty_reserved_dec,
                    warehouse_id=warehouse_id_final,
                    note=reason_clean,
                    actor_id=actor_user_id,
                    # Explicit - see `create_request`'s own note on `requested_at`.
                    created_at=datetime.utcnow(),
                )
            )
        try:
            self.db.flush()
        except IntegrityError:
            # SF-9: the `.with_for_update()` lock above closes the race for two real
            # concurrent requests, but this partial unique index
            # (`uq_order_inquiry_links_reserve_request_row`) is the backstop for a
            # request row read stale (the ORM guard already passed on a snapshot that
            # predates another writer's link) - same shape as `create_request`'s own
            # ordinal collision.
            self.db.rollback()
            raise AppException(
                409,
                "This row has already been answered.",
                code="reserve_request_row_already_answered",
            )
        if qty_reserved_dec > _ZERO:
            ProjectOrderInquiryService(self.db).refresh_link_state([row])
            self.db.flush()

        # F2: the request completes the moment its LAST row is answered - never a
        # count taken before this row's own answer landed.
        still_open = (
            self.db.query(OrderInquiryReserveRequestRow)
            .filter(
                OrderInquiryReserveRequestRow.request_id == request.id,
                OrderInquiryReserveRequestRow.qty_reserved.is_(None),
            )
            .count()
        )
        if still_open == 0:
            request.state = RESERVE_RESERVED
            request.reserved_by = actor_user_id
            request.reserved_at = datetime.utcnow()
            self.db.flush()

            all_request_rows = (
                self.db.query(OrderInquiryReserveRequestRow)
                .filter(OrderInquiryReserveRequestRow.request_id == request.id)
                .order_by(OrderInquiryReserveRequestRow.id.asc())
                .all()
            )
            rows_by_id = {
                order_row.id: order_row
                for order_row in self.db.query(OrderInquiryRow)
                .filter(
                    OrderInquiryRow.id.in_([arr.row_id for arr in all_request_rows])
                )
                .all()
            }
            pairs = [
                (arr, rows_by_id[arr.row_id])
                for arr in all_request_rows
                if arr.row_id in rows_by_id
            ]
            context = _build_context(self.db, request, pairs, actor_user_id=actor_user_id)
            self.db.info.setdefault(_RESERVED_PENDING_KEY, []).append(
                {"context": context, "source_id": str(request.id)}
            )
        return rr

    # ------------------------------------------------------- 6c F5: unreserve, per row

    def unreserve_row(
        self,
        *,
        request_id: str,
        row_id: str,
        qty: Any,
        note: Optional[str],
        actor_user_id: Optional[str],
    ) -> OrderInquiryReserveRequestRow:
        """Reduces what was reserved on an OI ROW (`PLAN-oi-request-cs-reserve.md`
        section 6c, F5; re-review finding 1, captain ruling 23 Sep). Its own action,
        never Unlink (F5's own words: "unlink is unlink, unreserve is unreserve").

        **Scoped to the LINE, not to the one request row named in the URL.** A row
        can hold reserve links from several requests (R5: reserved then requested
        again on the balance) - `request_id`/`row_id` are the ACCESS anchor only
        (the same 404 guard as before, proving the caller may act on this row at
        all), never the release's own scope. The release itself walks EVERY link
        the row still carries, across every request that has ever answered it,
        newest request first then newest link first - releasing "the last thing put
        on" before reaching further back - reducing each link and deleting it at
        net 0, writing one `unreserved` event per link touched (its own qty, tied to
        the request row whose own link it came off) and recomputing `qty_reserved`
        on each touched request row so it keeps reading its own link's remaining
        qty rather than a frozen answer. The bound a 422 names is the row's own
        AGGREGATE net across every link, not the one link tied to the URL's own
        request. No email either way."""
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

        # SF-9: the same lost-update race as `reserve_row` (a lock, not a rewrite of the
        # unreserve arithmetic) - two concurrent unreserves on this row would otherwise
        # both read the same `net_reserved` and both write `net - qty` off it. This is
        # the ACCESS anchor only now - it proves `request_id`/`row_id` is a legitimate,
        # company-scoped pair to act on, never the release's own scope (below).
        anchor = (
            self.db.query(OrderInquiryReserveRequestRow)
            .filter(
                OrderInquiryReserveRequestRow.request_id == request.id,
                OrderInquiryReserveRequestRow.row_id == row_id,
            )
            .with_for_update()
            .first()
        )
        if anchor is None:
            raise AppException(
                404,
                "That row is not part of this reserve request.",
                code="reserve_request_row_not_found",
            )

        row = self.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).first()
        if row is None:
            raise AppException(
                409,
                "This request's row no longer exists.",
                code="reserve_request_row_missing",
            )

        # Line scope: every (request row, link, request) this OI ROW still carries,
        # across EVERY request that has ever answered it - not only the anchor's
        # own. Newest request first (ordinal desc), then newest link first
        # (created_at desc). `.with_for_update()` locks every row this query joins,
        # the same SF-9 backstop as before, now widened to the whole set a release
        # may touch.
        pairs = (
            self.db.query(OrderInquiryReserveRequestRow, OrderInquiryLink, OrderInquiryReserveRequest)
            .join(
                OrderInquiryLink,
                OrderInquiryLink.reserve_request_row_id == OrderInquiryReserveRequestRow.id,
            )
            .join(
                OrderInquiryReserveRequest,
                OrderInquiryReserveRequest.id == OrderInquiryReserveRequestRow.request_id,
            )
            .filter(OrderInquiryReserveRequestRow.row_id == row_id)
            .order_by(
                OrderInquiryReserveRequest.ordinal.desc(),
                OrderInquiryLink.created_at.desc(),
            )
            .with_for_update()
            .all()
        )
        net_reserved_total = sum((_dec(link.qty) for _, link, _ in pairs), _ZERO)
        qty_dec = _dec(qty)
        if qty_dec <= _ZERO or qty_dec > net_reserved_total:
            raise AppException(
                422,
                f"{_row_label(row)}: unreserve quantity must be between 0 and "
                f"{_qty_str(net_reserved_total)} (the net reserved).",
                code="reserve_unreserve_qty_out_of_range",
            )
        note_clean = (note or "").strip() or None

        remaining_to_release = qty_dec
        for rr, link, _req in pairs:
            if remaining_to_release <= _ZERO:
                break
            link_qty = _dec(link.qty)
            release_amount = min(link_qty, remaining_to_release)
            remaining_link_qty = link_qty - release_amount
            # `OrderInquiryLink` carries no `warehouse_id` of its own (`document` is
            # its only place-name); the ANSWERING request row's own `warehouse_id`
            # is Eling's answer and is what this event's own "@ pool" reads.
            warehouse_id_for_event = rr.warehouse_id
            if remaining_link_qty > _ZERO:
                link.qty = remaining_link_qty
            else:
                self.db.delete(link)
            # Recomputed to the link's own remaining qty: once a LATER unreserve
            # call (anchored anywhere on the row) has eaten into this request row's
            # own answer, `qty_reserved` must stop reading the frozen original.
            rr.qty_reserved = remaining_link_qty
            self.db.add(
                OrderInquiryReserveEvent(
                    id=str(uuid.uuid4()),
                    company_id=row.company_id,
                    reserve_request_row_id=rr.id,
                    kind=RESERVE_EVENT_UNRESERVED,
                    qty=release_amount,
                    warehouse_id=warehouse_id_for_event,
                    note=note_clean,
                    actor_id=actor_user_id,
                    # Explicit - see `create_request`'s own note on `requested_at`.
                    created_at=datetime.utcnow(),
                )
            )
            remaining_to_release -= release_amount

        self.db.flush()
        ProjectOrderInquiryService(self.db).refresh_link_state([row])
        self.db.flush()
        return anchor

    # ----------------------------------------------------------- 6c F3: per-row history

    def history_for_row(
        self, *, request_id: str, row_id: str
    ) -> List[Dict[str, Any]]:
        """Newest first, across EVERY request that has ever touched this OI ROW, any
        state (H1, captain ruling on the browser walk) - not only the one `request_id`
        named in the URL. A cancelled, never-answered request stays visible even once
        a LATER request on the same row has since been reserved: purchasing raised a
        request, CS never got to it, purchasing cancelled and asked again - the first
        ask is still part of the story. `request_id` still anchors the call (a bogus
        or foreign one 404s exactly as before, AC-RS-61's own access rule is
        unchanged) but no longer scopes WHICH rows' entries are read; `requested` /
        `cancelled` derive straight off each request row's own parent request (no
        second copy); `reserved` / `unreserved` come off `order_inquiry_reserve_events`
        (`PLAN-oi-request-cs-reserve.md` section 6c, F3)."""
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
        anchor = (
            self.db.query(OrderInquiryReserveRequestRow)
            .filter(
                OrderInquiryReserveRequestRow.request_id == request.id,
                OrderInquiryReserveRequestRow.row_id == row_id,
            )
            .first()
        )
        if anchor is None:
            raise AppException(
                404,
                "That row is not part of this reserve request.",
                code="reserve_request_row_not_found",
            )

        # H1: every request row this OI row has ever appeared on, across every
        # request - the anchor above only proves `request_id`/`row_id` is a
        # legitimate, company-scoped pair to ask about at all.
        rows_and_requests = (
            self.db.query(OrderInquiryReserveRequestRow, OrderInquiryReserveRequest)
            .join(
                OrderInquiryReserveRequest,
                OrderInquiryReserveRequest.id == OrderInquiryReserveRequestRow.request_id,
            )
            .filter(OrderInquiryReserveRequestRow.row_id == row_id)
            .all()
        )

        entries: List[Dict[str, Any]] = []
        for rr, req in rows_and_requests:
            entries.append(
                {
                    "kind": "requested",
                    "qty": _qty_str(rr.qty_requested),
                    "location": _warehouse_code(self.db, rr.warehouse_id),
                    "reason": None,
                    "actor_name": _actor_name(self.db, req.requested_by),
                    "created_at": req.requested_at,
                }
            )
            if req.state == RESERVE_CANCELLED and req.cancelled_at is not None:
                entries.append(
                    {
                        "kind": "cancelled",
                        "qty": None,
                        "location": None,
                        "reason": None,
                        "actor_name": _actor_name(self.db, req.cancelled_by),
                        "created_at": req.cancelled_at,
                    }
                )
            events = (
                self.db.query(OrderInquiryReserveEvent)
                .filter(OrderInquiryReserveEvent.reserve_request_row_id == rr.id)
                .all()
            )
            for event_row in events:
                entries.append(
                    {
                        "kind": event_row.kind,
                        "qty": _qty_str(event_row.qty),
                        "location": _warehouse_code(self.db, event_row.warehouse_id),
                        "reason": event_row.note,
                        "actor_name": _actor_name(self.db, event_row.actor_id),
                        "created_at": event_row.created_at,
                    }
                )
        entries.sort(
            key=lambda entry: entry["created_at"] or datetime.min, reverse=True
        )
        return entries

    # --------------------------------------------------------------- toast-only read

    def notified_name(
        self,
        *,
        trigger_type: str,
        actor_user_id: Optional[str],
        raiser_user_id: Optional[str],
    ) -> Optional[str]:
        """Best-effort read of who the request mail's To address names, for the
        dialog's own toast (plan 3.7: "Request #2 sent to Eling"). A PUBLIC method
        here rather than the route reaching across into `AutomationService`'s own
        private `_normalize_recipient_config` directly (review round, layering) -
        the route asks its OWN service for this, the same as every other read.
        Never load-bearing: a disabled or not-yet-configured automation simply reads
        null, and the actual send already happened synchronously inside the write's
        own commit (`register_order_inquiry_reserve_post_commit_dispatch`'s
        `after_commit` listener runs before this)."""
        try:
            from app.models.automation import Automation
            from app.services.automation_recipients import resolve_recipients
            from app.services.automation_service import AutomationService

            automation = (
                self.db.query(Automation)
                .filter(Automation.trigger_type == trigger_type, Automation.enabled.is_(True))
                .order_by(Automation.created_at.asc())
                .first()
            )
            if automation is None:
                return None
            config = AutomationService._normalize_recipient_config(automation.recipient_config)
            context = {
                "actor": _person(self.db, actor_user_id),
                "raiser": _person(self.db, raiser_user_id),
            }
            recipients = resolve_recipients(self.db, config, context)
            if not recipients:
                return None
            return recipients[0].get("name")
        except Exception:  # noqa: BLE001 - a toast name is never load-bearing
            return None


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
