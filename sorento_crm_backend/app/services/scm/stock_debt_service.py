"""Stock Debt: every outstanding sales order without supply, as a month x product balance.

S2 of `PLAN-scm-borrow-ladder-v7-stock-debt.md` (section 3.4), rulings R6/R7, R15, R21, R23.

**The view SHOWS; the board DECIDES** (R23). Nothing here writes, proposes or reserves. It
reads the same book the ladder reads, hands it to `supply_assignment.assign()` - the one
piece of arithmetic both surfaces share - and prints the answer as a balance PER MONTH
(R37: what is debted in August stays in August) with the lines and documents behind each
cell. A cell and its drill are two readings of the same walk: free supply dated in the
month, less what the lines due in it went short of on their own dates.

**One read per input, never one per product.** The page is the whole flagged catalogue
(1,000-2,000 products on the live book), so every fact is fetched for the WHOLE set in one
query and then split by product in Python: on hand, open demand, SPO, PO, the decisions that
pin stock and the links that pin a document. A per-product query here is what would turn a
screen into a minute. The trigger for a persisted debt table is stated in plan 3.6 and it is
this cost - measured, not guessed.

**No debt table** (plan 3.6). Debt is computed from the book, and the parts of it that are
decisions (ORDER_BACK rows, placement links, confirmed allocations) are already persisted by
the board. A table would be a second copy of a derived figure, stale the moment anybody
confirms anything.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.models.product import Product
from app.models.project_so import (
    INQUIRY_CANCELLED,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrderLine,
    SOLineAllocation,
)
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import sales_agent_service
from app.services.scm.demand import demand_qty, is_open_demand
from app.services.scm.front_planning_engine import DEFAULT_LEAD_TIME_DAYS
from app.services.scm.planning_predicate import fulfilment_planning_predicate
from app.services.scm.supply_assignment import (
    BUCKET_TBA,
    BUCKET_UNDATED,
    BUCKET_UNLOCATED,
    KIND_ON_HAND,
    KIND_PO,
    KIND_SPO,
    Assignment,
    DemandLine,
    Hold,
    SupplyEvent,
    assign,
    effective_date,
    month_axis,
    month_key,
    tone_for,
)

_ZERO = Decimal("0")

#: The month keys that are not months. Addressable exactly like a `YYYY-MM` cell, because
#: the screen's TBA, No date and No location columns are cells a reader clicks like any
#: other (R28).
BUCKET_KEYS = (BUCKET_TBA, BUCKET_UNDATED, BUCKET_UNLOCATED)


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


class StockDebtService:
    def __init__(self, db: Session):
        self.db = db
        #: The reader that already knows how to read SPO, PO and lead times, and the one the
        #: board uses. Sharing it is what stops the view and the board disagreeing about
        #: what is on the water.
        self.supply = ProjectSupplyService(db)

    # ------------------------------------------------------------------ the two answers

    def list(
        self,
        *,
        query: Optional[str] = None,
        group: Optional[str] = None,
        only_debt: bool = True,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """The month x product board (AC-S2-6).

        The three axis fields travel on the ENVELOPE rather than per row, because the axis is
        a property of the whole filtered set: derived per page, the columns would change
        under the reader as they page.
        """
        warehouses = self._warehouses(group)
        products = self._products(warehouses, query)
        assignments = self._assignments(products, warehouses)

        rows = []
        for product_id, code, name in products:
            result = assignments[product_id]
            if only_debt and not self._in_debt(result):
                continue
            rows.append((product_id, code, name, result))

        axis = self._axis(row[3] for row in rows)
        rows.sort(key=lambda row: self._sort_key(row[3], row[1]))

        start = max(page - 1, 0) * limit
        page_rows = rows[start : start + limit]
        return {
            "data": [
                {
                    "product_id": product_id,
                    "product_code": code,
                    "product_name": name,
                    "months": self._months_on_axis(result, axis, product_id),
                    "tba": result.tba,
                    "undated": result.undated,
                    "unlocated": result.unlocated,
                }
                for product_id, code, name, result in page_rows
            ],
            "pagination": {"total": len(rows), "page": page, "limit": limit},
            "months": axis,
            "tba_month": month_key(self._tba_from()),
            "groups": self._groups(),
        }

    def cell(
        self, product_id: str, month: str, group: Optional[str] = None
    ) -> Dict[str, Any]:
        """The demand and the supply behind one cell (AC-S2-7, R28).

        The same reads as the board, narrowed to one product, so the two tables foot with the
        cell that opened them by construction rather than by agreement: the drill's
        `free_qty` less its `short_qty`, over the rows of one month, IS that month's balance
        (R37). `group` is the
        narrowing the BOARD was showing when the cell was pressed, and it is not optional
        detail: `group=BB` recomputes the balance from the BB span only, so a drill that read
        the whole book would answer a different question from the cell that opened it.
        """
        if month not in BUCKET_KEYS and not self._is_month_key(month):
            raise AppException(
                status_code=422,
                message="month must be YYYY-MM, 'tba', 'undated' or 'unlocated'.",
                code="stock_debt_bad_month",
            )
        warehouses = self._warehouses(group)
        product = (
            self.db.query(Product.id, Product.product_code, Product.product_name)
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            raise AppException(
                status_code=404, message="Product not found.", code="NOT_FOUND"
            )
        products = [(str(product.id), product.product_code, product.product_name)]
        assignments = self._assignments(products, warehouses, keep_events=True)
        result = assignments[str(product.id)]
        events = self._event_cache[str(product.id)]

        assigned_to: Dict[str, Dict[str, float]] = {}
        for line in result.lines:
            for item in line.assigned:
                assigned_to.setdefault(item.event.key, {}).setdefault(
                    line.line.so_number, 0.0
                )
                assigned_to[item.event.key][line.line.so_number] += item.qty

        demand = [
            {
                "so_number": line.line.so_number,
                "agent_code": line.line.agent_code,
                "warehouse_code": line.line.warehouse,
                "required_date": line.line.required_date,
                "open_qty": line.line.open_qty,
                "assigned_qty": round(sum(item.qty for item in line.assigned), 4),
                "assigned_source": self._source_text(line),
                "status": line.status,
                # What this line booked into the month it sits in (R37): what it was short
                # of ON ITS OWN DATE. A `late` line ends covered and still carries one,
                # which is why the drill states it rather than leaving the reader to
                # subtract Assigned from Open and get a different number from the cell.
                "short_qty": line.short_at_date,
            }
            for line in result.lines
            if line.bucket == month
        ]
        demand.sort(key=lambda row: (row["required_date"] or date.max, row["so_number"]))

        supply: List[Dict[str, Any]] = []
        if month not in BUCKET_KEYS:
            as_of = date.today()
            current = month_key(as_of)
            for event in events:
                # An uncounted document (overdue, or with no date at all) is listed in the
                # CURRENT month: its own arrival month has gone, and the axis starts today.
                counted = event not in result.uncounted
                key = (
                    month_key(effective_date(event.at, as_of)) if counted else current
                )
                if key != month:
                    continue
                supply.append(
                    {
                        "kind": event.kind,
                        "ref": event.ref,
                        "warehouse_code": event.warehouse,
                        "date": event.at,
                        "bought_for": event.bought_for,
                        "qty": event.qty,
                        # What nobody took, once the whole walk was over - the other half of
                        # the cell (R37). An overdue document is free of nothing: it is not
                        # supply until somebody re-dates it (R31).
                        "free_qty": result.free.get(event.key, 0.0) if counted else 0.0,
                        "overdue": not counted and event.at is not None,
                        "assigned_to": [
                            {"so_number": so_number, "qty": round(qty, 4)}
                            for so_number, qty in sorted(
                                assigned_to.get(event.key, {}).items()
                            )
                        ],
                    }
                )
            supply.sort(key=lambda row: (row["date"] or date.max, row["ref"] or ""))
        return {"demand": demand, "supply": supply}

    # ------------------------------------------------------------------ the reads

    def _warehouses(self, group: Optional[str]) -> Dict[str, Warehouse]:
        """The bins fulfilment planning reads, narrowed to one ownership group on request.

        `group=BB` narrows the SPAN of every read below it rather than filtering finished
        rows (AC-S2-6): the balance asked for is the BB group's own, and a row filtered after
        the fact would still have let another group's stock cover a BB order.
        """
        rows = self.db.query(Warehouse).filter(fulfilment_planning_predicate()).all()
        if group:
            wanted = group.strip().upper()
            rows = [
                row
                for row in rows
                if sales_agent_service.group_of_warehouse_code(row.warehouse_code)
                == wanted
            ]
        return {str(row.id): row for row in rows}

    def _groups(self) -> List[str]:
        """The ownership groups the flag currently admits, for the toolbar's select."""
        rows = (
            self.db.query(Warehouse.warehouse_code)
            .filter(fulfilment_planning_predicate())
            .all()
        )
        return sorted(
            {
                group
                for group in (
                    sales_agent_service.group_of_warehouse_code(row[0]) for row in rows
                )
                if group
            }
        )

    def _products(
        self, warehouses: Dict[str, Warehouse], query: Optional[str]
    ) -> List[Tuple[str, str, Optional[str]]]:
        """Every product with stock, demand or incoming at those bins, code and name.

        Four id reads and one product read, because a product with nothing at a flagged bin
        has no debt to state and no row to render. The demand read reaches one step further
        than the other three: an UNLOCATED sales-order line names no bin at all, and a screen
        that lists what is owed while silently dropping 2,312 open lines (30 Aug dev copy)
        is answering a narrower question than the one it is asked.
        """
        ids = set(warehouses)
        if not ids:
            return []
        candidates: set = set()
        candidates |= {
            str(row[0])
            for row in self.db.query(Stock.product_id)
            .filter(Stock.warehouse_id.in_(ids), Stock.quantity_on_hand > 0)
            .distinct()
            .all()
        }
        candidates |= {
            str(row[0])
            for row in self.db.query(SalesOrderLine.product_id)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(
                self._demand_span(ids),
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .distinct()
            .all()
        }
        candidates |= {
            str(row[0])
            for row in self.db.query(SPOAllocation.product_id)
            .filter(
                SPOAllocation.warehouse_id.in_(ids),
                SPOAllocation.line_status == "open",
                SPOAllocation.allocated_quantity > SPOAllocation.quantity_received,
            )
            .distinct()
            .all()
        }
        candidates |= {
            str(row[0])
            for row in self.db.query(PurchaseOrderLine.product_id)
            .filter(
                PurchaseOrderLine.warehouse_id.in_(ids),
                PurchaseOrderLine.line_status == "open",
                PurchaseOrderLine.qty_ordered > PurchaseOrderLine.qty_received,
            )
            .distinct()
            .all()
        }
        if not candidates:
            return []

        rows = self.db.query(
            Product.id, Product.product_code, Product.product_name
        ).filter(Product.id.in_(candidates))
        if query:
            needle = f"%{query.strip()}%"
            rows = rows.filter(
                or_(
                    Product.product_code.ilike(needle),
                    Product.product_name.ilike(needle),
                )
            )
        return [
            (str(row.id), row.product_code or "", row.product_name)
            for row in rows.all()
        ]

    @staticmethod
    def _demand_span(warehouse_ids):
        """"A line this view is answerable for": at one of these bins, or at NO bin.

        One expression, used by the candidate read and by `_demand`, so the products that
        get a row and the lines that fill it can never come from two different rules.
        `assign()` gives an unlocated line its own bucket - it is in no group's pile, so it
        draws nothing (AC-S2-1b's sibling case) - but it is COUNTED and it is listed.
        """
        return or_(
            SalesOrderLine.warehouse_id.in_(list(warehouse_ids)),
            SalesOrderLine.warehouse_id.is_(None),
        )

    def _assignments(
        self,
        products: Sequence[Tuple[str, str, Optional[str]]],
        warehouses: Dict[str, Warehouse],
        *,
        keep_events: bool = False,
    ) -> Dict[str, Assignment]:
        """One `assign()` per product, off ONE read per input for the whole set."""
        self._event_cache: Dict[str, List[SupplyEvent]] = {}
        self._lead_cache: Dict[str, int] = {}
        product_ids = [product_id for product_id, _code, _name in products]
        as_of = date.today()
        tba_from = self._tba_from()
        if not product_ids:
            return {}

        warehouse_ids = list(warehouses)
        codes = {
            warehouse_id: warehouse.warehouse_code or warehouse_id
            for warehouse_id, warehouse in warehouses.items()
        }
        pools = set(self.supply.site_pool_warehouses())

        # FIRST, and deliberately: `lead_times` fills the memo the per-line fallback in
        # `_po_rows` reads. Called after `_supply`, every PO line whose supplier agreement
        # states no lead paid its own round trip - ~1,900 extra queries per list request on
        # the dev copy.
        leads = self.supply.lead_times(product_ids)
        supply_rows = self._supply(product_ids, warehouse_ids, codes, pools)
        demand_rows = self._demand(product_ids, warehouse_ids, codes, pools)
        holds = self._holds(
            product_ids,
            {line.key for lines in demand_rows.values() for line in lines},
        )

        out: Dict[str, Assignment] = {}
        for product_id in product_ids:
            # The product's own lead, or the ladder's default - the SAME source the reserve
            # window uses (plan risk 5), so the red horizon here and the window there agree.
            # `is None`, never `or` - the same test `_po_rows` and `reserve_window_end`
            # make. A supplier who states a 0-day lead is stating something (stock off the
            # shelf), and reading that as "nobody says" turned it into 90 days, which paints
            # three months of a product that can be bought today red.
            lead = leads.get(product_id)
            self._lead_cache[product_id] = (
                DEFAULT_LEAD_TIME_DAYS if lead is None else lead
            )
            events = supply_rows.get(product_id, [])
            lines = demand_rows.get(product_id, [])
            line_keys = {line.key for line in lines}
            out[product_id] = assign(
                product_id,
                as_of=as_of,
                tba_from=tba_from,
                lead_days=self._lead_cache[product_id],
                supply=events,
                demand=lines,
                pinned=[hold for hold in holds if hold.line_key in line_keys],
            )
            if keep_events:
                self._event_cache[product_id] = events
        return out

    def _supply(
        self,
        product_ids: Sequence[str],
        warehouse_ids: Sequence[str],
        codes: Dict[str, str],
        pools: set,
    ) -> Dict[str, List[SupplyEvent]]:
        """On hand, SPO and PO for the whole page - three reads, none of them per product.

        On hand is `quantity_on_hand - quantity_reserved`, the same arithmetic
        `_free_stock` states: reserved stock is spoken for by a picking or despatch that is
        already under way, so offering it to a sales-order line here would promise the same
        units twice. The confirmed HOLDS are subtracted separately, by pinning them to the
        lines that hold them (`_holds`) - which is the more useful shape, because the drill
        can then say which order has them.
        """
        as_of = date.today()
        out: Dict[str, List[SupplyEvent]] = {}

        rows = (
            self.db.query(
                Stock.product_id,
                Stock.warehouse_id,
                func.sum(
                    func.coalesce(Stock.quantity_on_hand, 0)
                    - func.coalesce(Stock.quantity_reserved, 0)
                ).label("qty"),
            )
            .filter(
                Stock.product_id.in_(product_ids),
                Stock.warehouse_id.in_(warehouse_ids),
            )
            .group_by(Stock.product_id, Stock.warehouse_id)
            .all()
        )
        for row in rows:
            qty = _float(row.qty)
            if qty <= 0:
                continue
            warehouse_id = str(row.warehouse_id)
            out.setdefault(str(row.product_id), []).append(
                SupplyEvent(
                    key=f"on_hand:{warehouse_id}",
                    kind=KIND_ON_HAND,
                    warehouse=codes.get(warehouse_id),
                    at=as_of,
                    qty=qty,
                    is_pool=warehouse_id in pools,
                )
            )

        for (product_id, warehouse_id), refs in self.supply.incoming_by_location(
            product_ids, warehouse_ids
        ).items():
            for ref in refs:
                out.setdefault(product_id, []).append(
                    SupplyEvent(
                        key=f"spo:{ref.allocation_id}",
                        kind=KIND_SPO,
                        warehouse=codes.get(warehouse_id),
                        at=ref.arrival_date,
                        qty=_float(ref.qty),
                        ref=f"SPO {ref.spo_number}" if ref.spo_number else "SPO",
                        is_pool=warehouse_id in pools,
                    )
                )

        for (product_id, warehouse_id), lines in self.supply.po_by_location(
            product_ids, warehouse_ids
        ).items():
            for line in lines:
                out.setdefault(product_id, []).append(
                    SupplyEvent(
                        key=f"po:{line.line_id}",
                        kind=KIND_PO,
                        warehouse=codes.get(warehouse_id),
                        at=line.arrival_date,
                        qty=_float(line.qty),
                        ref=f"PO {line.po_number} line {line.po_line_no}",
                        bought_for=line.bought_for,
                        is_pool=warehouse_id in pools,
                    )
                )
        return out

    def _demand(
        self,
        product_ids: Sequence[str],
        warehouse_ids: Sequence[str],
        codes: Dict[str, str],
        pools: set,
    ) -> Dict[str, List[DemandLine]]:
        """Every open sales-order line at those bins, plus the ones at NO bin - the same
        `is_open_demand()` rule the ladder and `scm.committed_v` share, so the debt and the
        plan count one book. `_demand_span` is why an unlocated line is here."""
        rows = (
            self.db.query(
                SalesOrderLine.id,
                SalesOrderLine.product_id,
                SalesOrderLine.warehouse_id,
                SalesOrderLine.required_date,
                demand_qty().label("qty"),
                SalesOrder.so_number,
                SalesAgent.sales_agent,
            )
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(SalesAgent, SalesAgent.id == SalesOrder.sales_agent_id)
            .filter(
                SalesOrderLine.product_id.in_(product_ids),
                self._demand_span(warehouse_ids),
                SalesOrder.status == "open",
                is_open_demand(),
            )
            .all()
        )
        out: Dict[str, List[DemandLine]] = {}
        for row in rows:
            warehouse_id = str(row.warehouse_id) if row.warehouse_id else ""
            out.setdefault(str(row.product_id), []).append(
                DemandLine(
                    key=str(row.id),
                    so_number=row.so_number or "",
                    line_no=None,
                    # None for an unlocated line, which is what puts it in its own bucket.
                    warehouse=codes.get(warehouse_id),
                    agent_code=row.sales_agent,
                    required_date=row.required_date,
                    open_qty=_float(row.qty),
                    is_pool=warehouse_id in pools,
                )
            )
        return out

    def _holds(self, product_ids: Sequence[str], line_keys: set) -> List[Hold]:
        """What is already promised: confirmed allocations and placement links (R21).

        Two shapes, one meaning. A `so_line_allocations` row is a decision holding STOCK at a
        bin; an `order_inquiry_links` row is a placement holding a DOCUMENT. Both bind before
        anybody queues (AC-S2-2), and both are keyed to the CORE sales-order line, which is
        what the demand read above is keyed on.

        **The allocation half is `ProjectSupplyService._hold_query`, not a second spelling of
        it.** That is the one predicate for "this row is holding stock right now" - confirmed,
        located, not an ORDER source, and belonging to no decision or to an ACTIVE one - and
        it is shared with the free-stock arithmetic precisely so the two cannot come to
        disagree. Restated by hand here, it had already lost `confirmed_at IS NOT NULL`, so a
        decision saved but never confirmed held stock on this screen and nowhere else.

        **Each hold carries the bin or document it names.** `assign()` honours a hold whose
        supply is outside the read span (a site pool, an unflagged bin, another group under
        `group=`) off exactly these fields (AC-S2-1b), so the drill still says `On hand BRW`
        rather than leaving a pinned line looking unsourced.
        """
        if not line_keys:
            return []
        keys = list(line_keys)
        out: List[Hold] = []

        rows = (
            self.supply._hold_query(
                [str(pid) for pid in product_ids],
                exclude_line_ids=None,
                entities=(
                    ProjectSalesOrderLine.core_sales_order_line_id,
                    SOLineAllocation.warehouse_id,
                    SOLineAllocation.qty,
                    Warehouse.warehouse_code,
                ),
            )
            .join(Warehouse, Warehouse.id == SOLineAllocation.warehouse_id)
            .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(keys))
            .all()
        )
        for core_line_id, warehouse_id, qty, warehouse_code in rows:
            if _float(qty) <= 0:
                continue
            out.append(
                Hold(
                    line_key=str(core_line_id),
                    supply_key=f"on_hand:{warehouse_id}",
                    qty=_float(qty),
                    kind=KIND_ON_HAND,
                    warehouse=warehouse_code,
                )
            )

        links = (
            self.db.query(
                ProjectSalesOrderLine.core_sales_order_line_id,
                OrderInquiryLink.spo_allocation_id,
                OrderInquiryLink.po_line_id,
                OrderInquiryLink.qty,
                SPOAllocation.spo_number,
                PurchaseOrder.po_number,
            )
            .join(OrderInquiryRow, OrderInquiryRow.id == OrderInquiryLink.row_id)
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id,
            )
            .outerjoin(
                SPOAllocation, SPOAllocation.id == OrderInquiryLink.spo_allocation_id
            )
            .outerjoin(
                PurchaseOrderLine, PurchaseOrderLine.id == OrderInquiryLink.po_line_id
            )
            .outerjoin(
                PurchaseOrder,
                PurchaseOrder.id == PurchaseOrderLine.purchase_order_id,
            )
            .filter(
                ProjectSalesOrderLine.core_sales_order_line_id.in_(keys),
                # A cancelled inquiry row holds nothing - the same filter every other
                # consumer of these links applies (`planning_change_service`,
                # `project_order_inquiry_service`). Without it a withdrawn placement went
                # on pinning a document to a line nobody is waiting on.
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
            .all()
        )
        for row in links:
            qty = _float(row.qty)
            if qty <= 0:
                continue
            if row.spo_allocation_id:
                supply_key = f"spo:{row.spo_allocation_id}"
                kind, ref = KIND_SPO, (
                    f"SPO {row.spo_number}" if row.spo_number else "SPO"
                )
            else:
                supply_key = f"po:{row.po_line_id}"
                kind, ref = KIND_PO, (
                    f"PO {row.po_number}" if row.po_number else "PO"
                )
            out.append(
                Hold(
                    line_key=str(row[0]),
                    supply_key=supply_key,
                    qty=qty,
                    kind=kind,
                    ref=ref,
                )
            )
        return out

    # ------------------------------------------------------------------ small helpers

    def _tba_from(self) -> date:
        """The policy's TBA line, read once per request off the row the admin screen edits."""
        from app.services.scm.priority import DEFAULT_TBA_DATE_FROM

        return (
            self.supply._fulfilment_settings().get("tba_date_from")
            or DEFAULT_TBA_DATE_FROM
        )

    @staticmethod
    def _is_month_key(value: str) -> bool:
        try:
            year, month = value.split("-")
            return len(value) == 7 and 1 <= int(month) <= 12 and len(year) == 4
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _in_debt(result: Assignment) -> bool:
        """Anything owed and unsupplied - a negative month, or bucketed demand.

        The three buckets count, and the AC's "no negative month" wording is read that way
        deliberately: AC-S2-3 calls a TBA line's whole quantity DEBT, so a product whose only
        debt is 2030 demand, or an order nobody has given a location, would otherwise be
        dropped from the one screen that exists to list what is owed.
        """
        return (
            any(month.balance < 0 for month in result.months)
            or result.tba < 0
            or result.undated < 0
            or result.unlocated < 0
        )

    @staticmethod
    def _sort_key(result: Assignment, code: str) -> tuple:
        """Earliest red month, then product code; no red month sorts after every red one.

        Red is "cannot be bought in time", so the order is the order the work is urgent in.
        """
        red = next(
            (month.key for month in result.months if month.tone == "red"), None
        )
        return (red is None, red or "", code or "")

    def _axis(self, results: Iterable[Assignment]) -> List[str]:
        """The month columns of the whole filtered set: today to the last month anything is
        dated in. One axis for every row, or the columns move as the reader pages."""
        first = month_key(date.today())
        last = first
        for result in results:
            for month in result.months:
                if month.key > last:
                    last = month.key
        return month_axis(first, last)

    def _months_on_axis(
        self, result: Assignment, axis: Sequence[str], product_id: str
    ) -> List[dict]:
        """One entry per axis key, in axis order. Past a row's own last event the months
        read 0, because nothing is due and nothing arrives in them (R37) - the balance does
        not carry, so a column states its own month or it states nothing owed."""
        as_of = date.today()
        lead = self._lead_cache.get(product_id, DEFAULT_LEAD_TIME_DAYS)
        by_key = {month.key: month for month in result.months}
        out: List[dict] = []
        for key in axis:
            month = by_key.get(key)
            balance = month.balance if month is not None else 0.0
            out.append(
                {
                    "key": key,
                    "balance": balance,
                    "tone": month.tone
                    if month is not None
                    else tone_for(balance, key, as_of=as_of, lead_days=lead),
                }
            )
        return out

    def _source_text(self, line) -> Optional[str]:
        """What a demand row says it is covered FROM - `On hand BRW-BB`, `SPO ...`, `PO ...`.

        Human text, not an id: this is the sentence a planner reads before pressing Plan.
        """
        labels: List[str] = []
        for item in line.assigned:
            event = item.event
            label = (
                f"On hand {event.warehouse}"
                if event.kind == KIND_ON_HAND
                else (event.ref or event.kind.upper())
            )
            if label not in labels:
                labels.append(label)
        return ", ".join(labels) if labels else None
