"""Stock transfers: the writer that raises them and the state machine that retires them
(`PLAN-scm-cs-planning-uat.md` section E, captain's Q2 ruling of 25 Aug 2026).

Two halves, in one file because they are one idea:

* `write_for_decision` / `cancel_open_for_decision` - what a supply confirmation implies.
  Every decided reserve or borrow drawn from a warehouse that is NOT the line's own
  location is a physical movement somebody has to make, so it is written down as one. A
  same-location component moves nothing and writes nothing; incoming supply is not stock we
  hold and writes nothing.
* `StockTransferService` - the page. Read, approve, mark moved, cancel, bulk approve.
  **Nothing closes automatically**: `moved` is a person saying they keyed it into AutoCount,
  and our stock figures follow on the next upload (the ruling).

Beside `inventory_service.py` rather than in an `app/services/inventory/` package: there is
one file, and a package for one file is a directory to open before you reach the code.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import (
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.sales_agent import SalesAgent
from app.models.order import Customer
from app.models.stock_transfer import (
    TRANSFER_APPROVED,
    TRANSFER_CANCELLED,
    TRANSFER_KIND_BORROW,
    TRANSFER_KIND_OWN_GROUP,
    TRANSFER_KIND_POOL,
    TRANSFER_MOVED,
    TRANSFER_OPEN_STATES,
    TRANSFER_NO_DIGITS,
    TRANSFER_NO_PREFIX,
    TRANSFER_PROPOSED,
    StockTransfer,
    next_transfer_no,
)
from app.models.user import User
from app.services.error_handler import AppException
from app.services.scm.front_planning_engine import qty_text

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")

# Two aliases of the warehouse TABLE and three of the user table, so one row read names both
# ends of the move and both actors rather than costing four extra queries per page.
#
# `Table.alias()`, deliberately, NOT `orm.aliased(Warehouse)`. The company-scope listener
# splices a `with_loader_criteria(Warehouse, ..., include_aliases=True)` onto every ORM
# SELECT that names the entity, and with TWO aliases of it in one statement the adaptation
# emitted `warehouses.company_id` into the second join's ON clause - a FROM-clause entry
# that is not there ("Perhaps you meant the table alias warehouses_1"), measured as a 500
# on every read. A plain table alias carries no mapper, so nothing is spliced onto it. The
# row it decorates is already scoped: the transfer itself is the scoped entity, and these
# joins only turn its own warehouse ids into the codes a person reads.
_FromWarehouse = Warehouse.__table__.alias("from_wh")
_ToWarehouse = Warehouse.__table__.alias("to_wh")
_ApprovedBy = User.__table__.alias("approved_by_user")
_MovedBy = User.__table__.alias("moved_by_user")
_CancelledBy = User.__table__.alias("cancelled_by_user")

#: The engine's rung constants, spelled here as the plan's section 2 words map them.
_KIND_BY_RUNG = {
    "group_take": TRANSFER_KIND_OWN_GROUP,
    "pool": TRANSFER_KIND_POOL,
    "group_borrow": TRANSFER_KIND_BORROW,
    "cross_group_borrow": TRANSFER_KIND_BORROW,
}

#: What each state may become. A `moved` or `cancelled` row is terminal: the stock is
#: already somewhere else, or the move was called off, and neither is undone by paperwork.
_TRANSITIONS = {
    TRANSFER_PROPOSED: {TRANSFER_APPROVED, TRANSFER_CANCELLED},
    TRANSFER_APPROVED: {TRANSFER_MOVED, TRANSFER_CANCELLED},
    TRANSFER_MOVED: set(),
    TRANSFER_CANCELLED: set(),
}

_STATE_WORDS = {
    TRANSFER_PROPOSED: "Proposed",
    TRANSFER_APPROVED: "Approved",
    TRANSFER_MOVED: "Moved",
    TRANSFER_CANCELLED: "Cancelled",
}

#: The sort set the list accepts. It MUST equal `TransferSort` in
#: `app/api/v1/inventory/stock_transfers.py` - FastAPI cannot build a `Literal` from a
#: runtime set, so the two are written twice and a test asserts they agree, exactly as the
#: order-inquiry worklist's pair does.
SORTABLE_FIELDS = (
    "transfer_no",
    "state",
    "kind",
    "qty",
    "item_code",
    "from_location",
    "to_location",
    "so_number",
    "proposed_at",
)


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return _ZERO
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a snapshot is JSON a person may have edited
        return _ZERO


def _group_of(code: Optional[str]) -> Optional[str]:
    """The ownership-group suffix a warehouse code carries: `BRW-BB` -> `BB`.

    The suffix after the FIRST hyphen, upper-cased, which is
    `app.services.scm.sales_agent_service.group_of_warehouse_code`'s own rule. A plain site
    code (`BRW`, `MWH`, `DC1`) has no hyphen and therefore no group: it is a POOL.
    """
    if not code:
        return None
    text = str(code).strip()
    cut = text.find("-")
    if cut < 0:
        return None
    return text[cut + 1:].strip().upper() or None


def kind_for_component(component: Dict[str, Any], own_location: Optional[str]) -> str:
    """Which of the three words a warehouse reads on the row.

    The engine's `rung` decides whenever the component carries one, which every component
    frozen since ladder v3 does. A component from an older revision carries none, so it is
    read the way the frontend's `supplyVocabulary.fallbackRung` reads it - on the OWNERSHIP
    GROUP, never on the site: for a `BRW-BB` line, `DC1-BB` is the agent's own group at
    another site and `BRW` is the shared pool. A borrow is always a borrow, whatever the
    code says, because the quantity belongs to another order.
    """
    rung = component.get("rung")
    if rung in _KIND_BY_RUNG:
        return _KIND_BY_RUNG[rung]
    if component.get("kind") == "borrow":
        return TRANSFER_KIND_BORROW
    source = component.get("source_location")
    group = _group_of(source)
    if not group:
        return TRANSFER_KIND_POOL
    if group == _group_of(own_location):
        return TRANSFER_KIND_OWN_GROUP
    return TRANSFER_KIND_BORROW


def cancel_open_for_order(
    db: Session, order_id: str, *, keep_decision_id: str, reason: str
) -> int:
    """Call off every open transfer this sales order still has, bar the ones the
    revision being written owns.

    Keyed on the ORDER rather than on the revision it is superseding, because the
    revision chain is not a reliable broom: `_write_transfers` is best-effort, so a
    confirmation whose transfer write failed leaves rev 1's rows open while rev 2 becomes
    the one that is superseded next, and cancelling `previous.id` alone would strand them
    open forever against a revision nobody is holding. Every open row on the order that
    does not belong to the revision being written is, by definition, a movement no live
    decision is asking for.

    Open means `proposed` or `approved`. A `moved` row is left exactly where it is: the
    stock has physically moved, and rewriting the record of it because the plan changed
    would be a lie about a warehouse's morning.
    """
    rows = (
        db.query(StockTransfer)
        .filter(
            StockTransfer.project_sales_order_id == order_id,
            StockTransfer.state.in_(TRANSFER_OPEN_STATES),
            # A row whose decision is NULL is an orphan and is swept too; `!=` alone would
            # skip it, because SQL compares NULL to nothing.
            or_(
                StockTransfer.supply_decision_id.is_(None),
                StockTransfer.supply_decision_id != keep_decision_id,
            ),
        )
        .all()
    )
    now = datetime.utcnow()
    for row in rows:
        row.state = TRANSFER_CANCELLED
        row.cancelled_reason = reason
        row.cancelled_at = now
        row.updated_at = now
    return len(rows)


def moved_qty_by_key(
    db: Session, order_id: str, *, exclude_decision_id: Optional[str] = None
) -> Dict[Tuple[str, str, str, str], Decimal]:
    """How much of this order has ALREADY physically moved, per movement.

    Keyed on `(so_line_id, product_id, from_warehouse_id, to_warehouse_id)` - the four
    facts that make two rows the same instruction to a warehouse. Only `moved` rows count:
    a proposed or approved one has not happened yet and is cancelled by the supersede
    above, and a cancelled one never will.
    """
    rows = (
        db.query(
            StockTransfer.so_line_id,
            StockTransfer.product_id,
            StockTransfer.from_warehouse_id,
            StockTransfer.to_warehouse_id,
            func.sum(StockTransfer.qty),
        )
        .filter(
            StockTransfer.project_sales_order_id == order_id,
            StockTransfer.state == TRANSFER_MOVED,
        )
        .group_by(
            StockTransfer.so_line_id,
            StockTransfer.product_id,
            StockTransfer.from_warehouse_id,
            StockTransfer.to_warehouse_id,
        )
    )
    if exclude_decision_id:
        rows = rows.filter(
            or_(
                StockTransfer.supply_decision_id.is_(None),
                StockTransfer.supply_decision_id != exclude_decision_id,
            )
        )
    return {
        (str(line or ""), str(product or ""), str(source or ""), str(target or "")): _dec(total)
        for line, product, source, target, total in rows.all()
    }


def write_for_decision(
    db: Session,
    order: ProjectSalesOrder,
    decision: SOSupplyDecision,
    snapshots: Sequence[Dict[str, Any]],
    *,
    warehouse_id_for_code,
) -> List[StockTransfer]:
    """One `proposed` transfer per decided component that has to physically move.

    Read off the frozen SNAPSHOTS rather than off the payload, so a line the confirmation
    named and a line it merely carried forward are written by one loop: the carried line's
    components are the previous revision's frozen dicts, in the same shape, and its
    transfers were cancelled with that revision, so it needs fresh ones or the movement it
    still implies would silently disappear on an unrelated reconfirm.

    Written for a reserve and for a borrow. NOT for a Buy (nothing is held anywhere yet)
    and NOT for incoming supply (it arrives at the line's own location on a document
    somebody else already raised). NOT for a component whose source IS the line's own
    location, which is the whole point: that stock is already where it has to be.

    **And NOT for a quantity that has already physically moved.** The rule the writer runs
    on: for each component, net out what is already `moved` for the same
    `(so_line_id, product_id, from_warehouse_id, to_warehouse_id)` on earlier revisions of
    this order, and write a row only for the remainder above zero. Without it, a line
    carried forward through an unrelated reconfirm - or the same composition reconfirmed
    after the stock was carried across - proposed the identical movement a second time, and
    a warehouse would have moved it twice. A LARGER quantity after a move still raises a
    row, for the difference alone.
    """
    written: List[StockTransfer] = []
    # Consumed as the components are walked, so two components of one confirmation that are
    # the same instruction cannot each claim the whole moved quantity.
    moved_left = moved_qty_by_key(db, str(order.id), exclude_decision_id=str(decision.id))
    # The whole block of numbers is minted HERE rather than left to the model's
    # `before_insert` stamp, and the stamp leaves an already-set number alone. One flush
    # inserting several rows of the same mapper runs every listener BEFORE any of them
    # reaches the database, so six moves from one confirmation all read the highest number
    # plus one and collided on `uq_project_stock_transfer_no` - measured, not imagined.
    counter = int(next_transfer_no(db, order.company_id)[len(TRANSFER_NO_PREFIX):])
    now = datetime.utcnow()
    for movement in _movements(snapshots, warehouse_id_for_code):
        qty = movement["qty"]
        already = moved_left.get(movement["key"], _ZERO)
        if already > _ZERO:
            taken = min(already, qty)
            moved_left[movement["key"]] = already - taken
            qty -= taken
            if qty <= _ZERO:
                continue
        transfer = StockTransfer(
            company_id=order.company_id,
            transfer_no=f"{TRANSFER_NO_PREFIX}{counter:0{TRANSFER_NO_DIGITS}d}",
            so_line_id=movement["so_line_id"],
            project_sales_order_id=order.id,
            supply_decision_id=decision.id,
            product_id=movement["product_id"],
            from_warehouse_id=movement["from_warehouse_id"],
            to_warehouse_id=movement["to_warehouse_id"],
            qty=qty,
            kind=movement["kind"],
            state=TRANSFER_PROPOSED,
            proposed_at=now,
        )
        db.add(transfer)
        written.append(transfer)
        counter += 1
    if written:
        db.flush()
    return written


def movements_implied(snapshots: Sequence[Dict[str, Any]], *, warehouse_id_for_code) -> int:
    """How many rows this composition SHOULD have raised, netting aside.

    Read by the confirm path when the write failed, so the planner is told how many
    movements are missing rather than left with a log line on a server. Counted BEFORE
    netting, because the netting needs the database read the failure just lost.
    """
    return sum(1 for _ in _movements(snapshots, warehouse_id_for_code))


def _movements(
    snapshots: Sequence[Dict[str, Any]], warehouse_id_for_code
) -> Iterator[Dict[str, Any]]:
    """Every component of every snapshot that is a physical movement, in one place.

    One reader for the writer and for the "how many were missed" count, so the two cannot
    disagree about what counts as a movement.
    """
    for snapshot in snapshots:
        own_location = snapshot.get("location")
        to_warehouse_id = warehouse_id_for_code(own_location) if own_location else None
        product_id = snapshot.get("product_id")
        core_line_id = snapshot.get("core_line_id")
        for component in snapshot.get("components") or []:
            if component.get("kind") not in ("reserve", "borrow"):
                continue
            qty = _dec(component.get("qty"))
            if qty <= _ZERO:
                continue
            source_location = component.get("source_location")
            if source_location and own_location and source_location == own_location:
                continue
            from_warehouse_id = component.get("source_warehouse_id") or (
                warehouse_id_for_code(source_location) if source_location else None
            )
            if not from_warehouse_id or not to_warehouse_id or not product_id:
                # Nothing to instruct a warehouse with. Logged rather than raised: the
                # confirmation itself succeeded, and refusing it now would fail a promise
                # over a movement note.
                logger.warning(
                    "stock transfer skipped: from=%s to=%s product=%s",
                    source_location,
                    own_location,
                    product_id,
                )
                continue
            if str(from_warehouse_id) == str(to_warehouse_id):
                continue
            yield {
                "so_line_id": core_line_id,
                "product_id": product_id,
                "from_warehouse_id": str(from_warehouse_id),
                "to_warehouse_id": str(to_warehouse_id),
                "qty": qty,
                "kind": kind_for_component(component, own_location),
                "key": (
                    str(core_line_id or ""),
                    str(product_id or ""),
                    str(from_warehouse_id),
                    str(to_warehouse_id),
                ),
            }


class StockTransferService:
    """The Transfers page: read, and the four deliberate state changes."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ reads

    def _base_query(self):
        """One join chain, used by the list and by the single read.

        Outer joins throughout: a transfer whose core sales-order line was dropped by a
        re-uploaded book still has to appear on the page - the stock has already been
        promised - and an inner join would make it vanish instead.
        """
        return (
            self.db.query(
                StockTransfer,
                Product.product_code,
                Product.product_name,
                _FromWarehouse.c.warehouse_code,
                _ToWarehouse.c.warehouse_code,
                SalesOrder.id,
                SalesOrder.so_number,
                Customer.customer_name,
                SalesAgent.id,
                SalesAgent.sales_agent,
                SalesAgent.person_label,
                ProjectSalesOrderLine.line_no,
                SOSupplyDecision.revision_no,
                _ApprovedBy.c.name,
                _MovedBy.c.name,
                _CancelledBy.c.name,
            )
            .outerjoin(Product, Product.id == StockTransfer.product_id)
            .outerjoin(_FromWarehouse, _FromWarehouse.c.id == StockTransfer.from_warehouse_id)
            .outerjoin(_ToWarehouse, _ToWarehouse.c.id == StockTransfer.to_warehouse_id)
            .outerjoin(SalesOrderLine, SalesOrderLine.id == StockTransfer.so_line_id)
            .outerjoin(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
            .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
            .outerjoin(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.core_sales_order_line_id == StockTransfer.so_line_id,
            )
            .outerjoin(
                SOSupplyDecision, SOSupplyDecision.id == StockTransfer.supply_decision_id
            )
            .outerjoin(_ApprovedBy, _ApprovedBy.c.id == StockTransfer.approved_by)
            .outerjoin(_MovedBy, _MovedBy.c.id == StockTransfer.moved_by)
            .outerjoin(_CancelledBy, _CancelledBy.c.id == StockTransfer.cancelled_by)
        )

    def _filtered(
        self,
        *,
        query: Optional[str] = None,
        state: Optional[str] = None,
        kind: Optional[str] = None,
        from_warehouse_id: Optional[str] = None,
        to_warehouse_id: Optional[str] = None,
        product_id: Optional[str] = None,
        sales_order_id: Optional[str] = None,
        project_sales_order_id: Optional[str] = None,
        sales_agent_id: Optional[str] = None,
    ):
        q = self._base_query()
        if state:
            q = q.filter(StockTransfer.state == state)
        if kind:
            q = q.filter(StockTransfer.kind == kind)
        if from_warehouse_id:
            q = q.filter(StockTransfer.from_warehouse_id == from_warehouse_id)
        if to_warehouse_id:
            q = q.filter(StockTransfer.to_warehouse_id == to_warehouse_id)
        if product_id:
            q = q.filter(StockTransfer.product_id == product_id)
        if sales_order_id:
            q = q.filter(SalesOrderLine.sales_order_id == sales_order_id)
        if project_sales_order_id:
            q = q.filter(StockTransfer.project_sales_order_id == project_sales_order_id)
        if sales_agent_id:
            q = q.filter(SalesOrder.sales_agent_id == sales_agent_id)
        text = (query or "").strip()
        if text:
            like = f"%{text}%"
            q = q.filter(
                or_(
                    StockTransfer.transfer_no.ilike(like),
                    StockTransfer.autocount_ref.ilike(like),
                    Product.product_code.ilike(like),
                    Product.product_name.ilike(like),
                    SalesOrder.so_number.ilike(like),
                    _FromWarehouse.c.warehouse_code.ilike(like),
                    _ToWarehouse.c.warehouse_code.ilike(like),
                    Customer.customer_name.ilike(like),
                    # The AGENT is searched here rather than offered as a select. The page's
                    # audience is the warehouse, and neither `master_data.sales_agents.view`
                    # nor `scm.dashboard.view` - the two reads a select would need - is
                    # granted to a warehouse role, so a dropdown would 403 for exactly the
                    # people it is for. Typing the code needs no second permission.
                    SalesAgent.sales_agent.ilike(like),
                    SalesAgent.person_label.ilike(like),
                )
            )
        return q

    def _sort_column(self, sort: Optional[str]):
        return {
            "transfer_no": StockTransfer.transfer_no,
            "state": StockTransfer.state,
            "kind": StockTransfer.kind,
            "qty": StockTransfer.qty,
            "item_code": Product.product_code,
            "from_location": _FromWarehouse.c.warehouse_code,
            "to_location": _ToWarehouse.c.warehouse_code,
            "so_number": SalesOrder.so_number,
            "proposed_at": StockTransfer.proposed_at,
        }.get(sort or "", StockTransfer.proposed_at)

    def list_transfers(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        sort: Optional[str] = None,
        direction: str = "desc",
        **filters,
    ) -> Tuple[List[Dict[str, Any]], int]:
        q = self._filtered(**filters)
        total = q.count()
        column = self._sort_column(sort)
        ordered = column.desc() if (direction or "desc").lower() == "desc" else column.asc()
        # `id` closes every ordering: `now()` is fixed for a transaction, so six transfers
        # written by one confirmation share `proposed_at` to the microsecond and would page
        # in an order Postgres is free to change between requests.
        rows = (
            q.order_by(ordered.nullslast(), StockTransfer.id)
            .offset(max(page - 1, 0) * limit)
            .limit(limit)
            .all()
        )
        return [_serialize(row) for row in rows], total

    def get(self, transfer_id: str) -> Dict[str, Any]:
        row = self._base_query().filter(StockTransfer.id == transfer_id).first()
        if row is None:
            raise AppException(
                status_code=404,
                message="That stock transfer does not exist.",
                code="stock_transfer_not_found",
            )
        return _serialize(row)

    # ------------------------------------------------------------ transitions

    def _for_update(self, transfer_id: str) -> StockTransfer:
        row = (
            self.db.query(StockTransfer)
            .filter(StockTransfer.id == transfer_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise AppException(
                status_code=404,
                message="That stock transfer does not exist.",
                code="stock_transfer_not_found",
            )
        return row

    def _check(self, row: StockTransfer, target: str) -> None:
        if target in _TRANSITIONS.get(row.state, set()):
            return
        raise AppException(
            status_code=422,
            message=(
                f"{row.transfer_no} is {_STATE_WORDS.get(row.state, row.state).lower()}, "
                f"so it cannot be {_STATE_WORDS.get(target, target).lower().rstrip('d')}d."
            ),
            code="stock_transfer_state",
        )

    def approve(self, transfer_id: str, *, actor_user_id: str) -> Dict[str, Any]:
        row = self._for_update(transfer_id)
        self._check(row, TRANSFER_APPROVED)
        row.state = TRANSFER_APPROVED
        row.approved_by = actor_user_id
        row.approved_at = datetime.utcnow()
        self.db.flush()
        return self.get(transfer_id)

    def mark_moved(
        self, transfer_id: str, *, autocount_ref: str, actor_user_id: str
    ) -> Dict[str, Any]:
        ref = (autocount_ref or "").strip()
        if not ref:
            raise AppException(
                status_code=422,
                message="The AutoCount transfer document number is required.",
                code="stock_transfer_ref_required",
            )
        row = self._for_update(transfer_id)
        self._check(row, TRANSFER_MOVED)
        row.state = TRANSFER_MOVED
        row.autocount_ref = ref
        row.moved_by = actor_user_id
        row.moved_at = datetime.utcnow()
        self.db.flush()
        return self.get(transfer_id)

    def cancel(self, transfer_id: str, *, reason: str, actor_user_id: str) -> Dict[str, Any]:
        cleaned = (reason or "").strip()
        if not cleaned:
            raise AppException(
                status_code=422,
                message="Say why the transfer is being called off.",
                code="stock_transfer_reason_required",
            )
        row = self._for_update(transfer_id)
        self._check(row, TRANSFER_CANCELLED)
        row.state = TRANSFER_CANCELLED
        row.cancelled_reason = cleaned
        row.cancelled_by = actor_user_id
        row.cancelled_at = datetime.utcnow()
        self.db.flush()
        return self.get(transfer_id)

    def bulk_approve(self, ids: Sequence[str], *, actor_user_id: str) -> Dict[str, Any]:
        """Approve everything ticked, in ONE locked read.

        One `SELECT ... FOR UPDATE` over the whole selection rather than a query per id: a
        page of 200 was 200 round trips and 200 separate locks taken in whatever order the
        client happened to send, which is how two people approving overlapping selections
        deadlock. The rows come back in one statement, locked together, and the loop is
        pure arithmetic over what was already read.

        Best-effort per row rather than all-or-nothing: a selection where one row was
        cancelled a minute ago by somebody else is not a mistake worth refusing the others
        for, and `skipped` says exactly which and why.
        """
        wanted = [str(value) for value in ids]
        rows = (
            self.db.query(StockTransfer)
            .filter(StockTransfer.id.in_(wanted))
            .order_by(StockTransfer.id)
            .with_for_update()
            .all()
        )
        by_id = {str(row.id): row for row in rows}

        approved = 0
        skipped: List[Dict[str, Any]] = []
        now = datetime.utcnow()
        for transfer_id in wanted:
            row = by_id.get(transfer_id)
            if row is None:
                skipped.append(
                    {
                        "id": transfer_id,
                        "transfer_no": None,
                        "reason": "That stock transfer does not exist.",
                    }
                )
                continue
            if TRANSFER_APPROVED not in _TRANSITIONS.get(row.state, set()):
                skipped.append(
                    {
                        "id": str(row.id),
                        "transfer_no": row.transfer_no,
                        "reason": (
                            f"Already {_STATE_WORDS.get(row.state, row.state).lower()}."
                        ),
                    }
                )
                continue
            row.state = TRANSFER_APPROVED
            row.approved_by = actor_user_id
            row.approved_at = now
            approved += 1
        self.db.flush()
        return {"approved": approved, "skipped": skipped}



def _serialize(row) -> Dict[str, Any]:
    (
        transfer,
        product_code,
        product_name,
        from_code,
        to_code,
        sales_order_id,
        so_number,
        customer_name,
        sales_agent_id,
        agent_code,
        person_label,
        so_line_no,
        revision_no,
        approved_by_name,
        moved_by_name,
        cancelled_by_name,
    ) = row
    return {
        "id": str(transfer.id),
        "transfer_no": transfer.transfer_no,
        "state": transfer.state,
        "kind": transfer.kind,
        "qty": qty_text(_dec(transfer.qty)),
        "product_id": str(transfer.product_id) if transfer.product_id else None,
        "item_code": product_code,
        "product_name": product_name,
        "from_warehouse_id": str(transfer.from_warehouse_id)
        if transfer.from_warehouse_id
        else None,
        "from_location": from_code,
        "to_warehouse_id": str(transfer.to_warehouse_id) if transfer.to_warehouse_id else None,
        "to_location": to_code,
        "sales_order_id": str(sales_order_id) if sales_order_id else None,
        "so_number": so_number,
        "so_line_no": so_line_no,
        "project_sales_order_id": str(transfer.project_sales_order_id)
        if transfer.project_sales_order_id
        else None,
        "customer_name": customer_name,
        "sales_agent_id": str(sales_agent_id) if sales_agent_id else None,
        "agent_code": agent_code,
        "agent_name": person_label,
        "supply_decision_id": str(transfer.supply_decision_id)
        if transfer.supply_decision_id
        else None,
        "revision_no": revision_no,
        "proposed_at": transfer.proposed_at,
        "approved_by": transfer.approved_by,
        "approved_by_name": approved_by_name,
        "approved_at": transfer.approved_at,
        "moved_by": transfer.moved_by,
        "moved_by_name": moved_by_name,
        "moved_at": transfer.moved_at,
        "cancelled_by": transfer.cancelled_by,
        "cancelled_by_name": cancelled_by_name,
        "cancelled_at": transfer.cancelled_at,
        "cancelled_reason": transfer.cancelled_reason,
        "autocount_ref": transfer.autocount_ref,
        "created_at": transfer.created_at,
        "updated_at": transfer.updated_at,
    }
