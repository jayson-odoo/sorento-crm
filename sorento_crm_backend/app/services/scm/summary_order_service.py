"""SCM S3b - the Summary Order Report and the order-quantity decision (UAC C2, C3).

The printed sheet Mr Loo fills in with a pen, made decidable: one row per product network
wide, every aggregate openable, and the order quantity his to set.

**The report is a frozen artefact of a run, not a live query.** AC-C2.9 requires that a past
week be reviewable, and the order book moves every day, so recomputing it would answer a
different question wearing the same date. `write_rows` is called at the end of `run_reorder`
and freezes `scm.order_summary_row`; every read here is a read of those rows.

**One dated engine.** The shortfall is `coverage_service.network_positions`, which is the same
`build_timeline` the Coverage Timeline panel draws. Nothing here recomputes a balance. If it
did, a report row and the panel beside it could state different shortfalls for the same
product on the same screen, which is the one class of disagreement that ends trust in a
planning tool.

**The project / dealer split reads `sales_orders.order_type`**, decided while scoping this
slice: `demand_class` is populated in 0 of 17 rows while `order_type` carries project / dealer
on 14 of them. A row whose type is unset is counted in NEITHER aggregate and surfaced as
unclassified rather than defaulted into one, because defaulting decides a split nobody stated.

**No ids on the wire.** Everything is addressed by human code. `run_id` is the single
exception and it is opaque: it says which week is being read and is never rendered.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product
from app.models.scm import (
    DemandStat,
    OrderSummaryRow,
    ReorderRecommendation,
    ReorderRun,
    SupplierPerformance,
)
from app.services.error_handler import AppException
from app.services.scm.coverage_service import CoverageService
from app.services.scm.cost_capture_service import cost_variance
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

log = logging.getLogger(__name__)

_SEED = "order_summary"

# Which `sales_orders.order_type` values feed which aggregate. A value in neither is
# UNCLASSIFIED and is counted in neither, rather than being folded into "dealer" because that
# is the bigger bucket - a split nobody stated is not a split.
_PROJECT_TYPES = ("project",)
_DEALER_TYPES = ("dealer", "retail", "end_user")

# How long since the last purchase order before an item reads as a dead line rather than a
# fast mover (AC-C2.6). The SERVER owns this verdict so the flag cannot drift between screens.
DEFAULT_STALE_AFTER_DAYS = 365

# Dimensions are stored in millimetres (a 1000 x 500 x 200 carton is one real row), so a
# cubic metre is 1e9 cubic millimetres.
_MM3_PER_M3 = 1_000_000_000


def _uuid() -> str:
    return str(uuid.uuid4())


def _today() -> date:
    """Malaysia wall-clock, matching every other dated figure in this module."""
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _unit_volume_cbm(p: Product) -> Optional[float]:
    """Cubic metres per unit, or None when any dimension is missing.

    None rather than 0 for the whole row when ANY of the three is absent: multiplying a
    missing dimension by the other two yields 0, and a volume of 0 reads as "no space
    needed" - which is a loading decision taken on a figure nobody measured. Recorded for
    roughly 15% of the catalogue today.
    """
    l, w, h = p.dimensions_length, p.dimensions_width, p.dimensions_height
    if l is None or w is None or h is None:
        return None
    return round(float(l) * float(w) * float(h) / _MM3_PER_M3, 6)


# =========================================================================== #
# freeze: called by the run, once, at the end
# =========================================================================== #


def write_rows(db: Session, run_id: str, *, as_of: Optional[date] = None) -> int:
    """Freeze one Summary Order Report row per product the run produced a recommendation for.

    Scoped to the run's own products rather than the whole catalogue: a product the engine had
    nothing to say about has no suggested quantity and no decision to make, and 22,805 rows
    nobody can act on is the information fatigue AC-C2.2a exists to prevent.

    Idempotent. A re-run of the writer for the same run updates in place rather than
    duplicating, which the unique index on (run_id, product_id) enforces anyway; doing it here
    means a retried job does not fail.
    """
    stamp_date = as_of or _today()
    computed_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))

    # suggested = the SUM of the run's rounded quantities for the product. A network-scope run
    # has one recommendation per product so the sum IS that figure; a warehouse-scope run
    # (the M8-D5 default) has one per location, and summing over-states against a single
    # network rounding, never under-states.
    #
    # `rounded_qty` is only actually rounded when the item has an order multiple, and moq /
    # order_multiple are populated in 0 of 17,408 supplier links, so in practice it holds the
    # raw engine figure: 1819.722194 for C-FH24. The plan grid hides that behind an integer
    # format, but this report pre-fills an EDITABLE order quantity from it, so the box read
    # 1819.722194 under a label saying 1,820. A purchase order for 1819.722194 units is not a
    # thing anybody raises.
    rec_rows = (
        db.query(
            ReorderRecommendation.product_id,
            func.coalesce(func.sum(ReorderRecommendation.rounded_qty), 0),
        )
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.rec_type == "buy",
        )
        .group_by(ReorderRecommendation.product_id)
        .all()
    )
    # Rounded UP to a whole unit, which is the conservative direction: rounding down would
    # suggest less than the policy says is needed. This is NOT a rounding policy - a real moq
    # or order multiple, once configured, is applied by the engine and arrives here already
    # applied. It is only the last step that makes the figure orderable.
    suggested = {str(pid): float(math.ceil(float(qty or 0))) for pid, qty in rec_rows}
    product_ids = list(suggested)
    if not product_ids:
        return 0

    positions = CoverageService(db).network_positions(product_ids)
    demand = _demand_aggregates(db, product_ids)
    stats = _avg_daily_demand(db, product_ids)
    spare = _spare_pool(db, product_ids)
    products = {
        str(p.id): p
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }
    existing = {
        str(r.product_id): r
        for r in db.query(OrderSummaryRow)
        .filter(OrderSummaryRow.run_id == run_id)
        .all()
    }

    written = 0
    for pid in product_ids:
        pos = positions.get(pid)
        agg = demand.get(pid, {})
        product = products.get(pid)
        row = existing.get(pid) or OrderSummaryRow(
            id=_uuid(), run_id=run_id, product_id=pid
        )
        row.as_of = stamp_date
        row.on_hand = pos.on_hand if pos else 0
        row.project_demand = agg.get("project_qty", 0.0)
        row.dealer_outstanding = agg.get("dealer_qty", 0.0)
        row.qty_on_order = pos.qty_on_order if pos else 0
        row.qty_in_transit = pos.qty_in_transit if pos else 0
        row.shortfall = pos.shortfall if pos else 0
        row.shortfall_at = pos.shortfall_at if pos else None
        row.suggested_qty = suggested.get(pid, 0.0)
        row.avg_daily_demand = stats.get(pid)
        row.unit_volume_cbm = _unit_volume_cbm(product) if product else None
        row.spare_lands_at_warehouse_id = spare.get(pid)
        row.project_demand_line_count = agg.get("project_lines", 0)
        row.dealer_outstanding_line_count = agg.get("dealer_lines", 0)
        row.max_days_outstanding = agg.get("max_days_outstanding")
        row.computed_at = computed_at
        row.source_system = "scm"
        row.source_ref = _SEED
        if pid not in existing:
            db.add(row)
        written += 1

    db.commit()
    return written


def _demand_aggregates(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """Project and dealer outstanding quantity, line counts, and the worst dealer ageing.

    One query for the whole batch. Split on `sales_orders.order_type`; a line whose order
    carries no type lands in neither aggregate and is counted separately, because folding it
    into one of them would state a split the data does not hold.
    """
    rows = (
        db.query(
            SalesOrderLine.product_id,
            SalesOrder.order_type,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
            SalesOrder.order_date,
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id.in_(product_ids),
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
        )
        .all()
    )
    today = _today()
    out: dict[str, dict] = {}
    for r in rows:
        pid = str(r.product_id)
        acc = out.setdefault(
            pid,
            {
                "project_qty": 0.0, "project_lines": 0,
                "dealer_qty": 0.0, "dealer_lines": 0,
                "unclassified_qty": 0.0, "unclassified_lines": 0,
                "max_days_outstanding": None,
            },
        )
        qty = float(r.qty_ordered or 0) - float(r.qty_delivered or 0)
        kind = (r.order_type or "").strip().lower()
        if kind in _PROJECT_TYPES:
            acc["project_qty"] += qty
            acc["project_lines"] += 1
        elif kind in _DEALER_TYPES:
            acc["dealer_qty"] += qty
            acc["dealer_lines"] += 1
            # Ageing is only meaningful on the dealer half: AC-C2.4's point is that a small
            # quantity waiting 214 days outranks a large one raised last week, and project
            # lines are ranked by their required date instead.
            if r.order_date is not None:
                days = (today - r.order_date).days
                cur = acc["max_days_outstanding"]
                acc["max_days_outstanding"] = days if cur is None else max(cur, days)
        else:
            acc["unclassified_qty"] += qty
            acc["unclassified_lines"] += 1
    return out


def _avg_daily_demand(db: Session, product_ids: list[str]) -> dict[str, Optional[float]]:
    """Network average daily demand: the SUM over locations, not their mean.

    Summed because months of cover is a network figure here - the whole network's stock
    against the whole network's consumption. Averaging would understate the drawdown and
    overstate cover, which is the wrong direction for a planning figure.

    Absent for roughly 38% of the book, and absent means NULL: a zero would read as "will
    never run out" and make months of cover infinite.
    """
    rows = (
        db.query(DemandStat.product_id, func.sum(DemandStat.avg_daily_demand))
        .filter(DemandStat.product_id.in_(product_ids))
        .group_by(DemandStat.product_id)
        .all()
    )
    return {str(pid): _f(total) for pid, total in rows if total is not None}


def _spare_pool(db: Session, product_ids: list[str]) -> dict[str, Optional[str]]:
    """Which pool spare stock above the shortfall lands in (AC-C2.7).

    The pool holding the most of the item today, because that is where a delivery is actually
    put away, and NULL when the item is held nowhere - the screen then says the spare has no
    stated home rather than naming a pool at random.
    """
    rows = (
        db.query(
            Stock.product_id,
            func.coalesce(Warehouse.pool_warehouse_id, Warehouse.id).label("pool_id"),
            func.sum(Stock.quantity_on_hand).label("qty"),
        )
        .join(Warehouse, Warehouse.id == Stock.warehouse_id)
        .filter(
            Stock.product_id.in_(product_ids),
            Warehouse.counts_as_available.is_(True),
            Stock.quantity_on_hand > 0,
        )
        .group_by(Stock.product_id, "pool_id")
        .all()
    )
    best: dict[str, tuple[float, str]] = {}
    for pid, pool_id, qty in rows:
        key = str(pid)
        q = float(qty or 0)
        if key not in best or q > best[key][0]:
            best[key] = (q, str(pool_id))
    return {pid: pool for pid, (_q, pool) in best.items()}


# =========================================================================== #
# read: the report
# =========================================================================== #


def _run_for(db: Session, run_id: Optional[str]) -> ReorderRun:
    """The run being read: the one named, or the newest completed one.

    A specific `run_id` is what makes a past week reproducible (AC-C2.9). With none given the
    newest COMPLETED run is used rather than the newest run of any status, because a run still
    writing its rows would show a half-frozen book that fills in as the reader scrolls.
    """
    if run_id:
        run = db.query(ReorderRun).filter(ReorderRun.id == run_id).one_or_none()
        if run is None:
            raise AppException(404, "That plan does not exist.")
        return run
    run = (
        db.query(ReorderRun)
        .filter(ReorderRun.status == "completed")
        .order_by(ReorderRun.started_at.desc())
        .first()
    )
    if run is None:
        raise AppException(
            404, "No completed plan yet, so there is no order summary to read."
        )
    return run


def report(db: Session, *, run_id: Optional[str] = None) -> dict:
    """The whole frozen report for one run.

    Returned WHOLE and paginated by the client, because the sheet it replaces is read as one
    book. `as_of` comes off the stored rows rather than the request: the report states the
    date it was computed for, and letting a caller pass a different one would label a frozen
    position with a date it does not describe.
    """
    run = _run_for(db, run_id)
    rows = (
        db.query(OrderSummaryRow, Product, Supplier, Warehouse)
        .join(Product, Product.id == OrderSummaryRow.product_id)
        .outerjoin(Supplier, Supplier.id == OrderSummaryRow.chosen_supplier_id)
        .outerjoin(Warehouse, Warehouse.id == OrderSummaryRow.spare_lands_at_warehouse_id)
        .filter(OrderSummaryRow.run_id == run.id)
        .order_by(Product.product_code)
        .all()
    )
    return {
        "run_id": str(run.id),
        # Off the rows, not off `date.today()`: an empty report has no computed date to state,
        # and inventing today's would date a book that was never built.
        "as_of": (rows[0][0].as_of.isoformat() if rows else None),
        "generated_at": (
            rows[0][0].computed_at.isoformat() if rows else None
        ),
        "rows": [_serialise_row(r, p, s, w) for r, p, s, w in rows],
    }


def _serialise_row(row: OrderSummaryRow, product: Product, supplier, pool) -> dict:
    return {
        "product_code": product.product_code,
        "product_name": product.product_name,
        "uom": getattr(getattr(product, "base_uom", None), "uom_code", None),
        "on_hand": _f(row.on_hand) or 0.0,
        "project_demand": _f(row.project_demand) or 0.0,
        "dealer_outstanding": _f(row.dealer_outstanding) or 0.0,
        "qty_on_order": _f(row.qty_on_order) or 0.0,
        "qty_in_transit": _f(row.qty_in_transit) or 0.0,
        "shortfall": _f(row.shortfall) or 0.0,
        "suggested_qty": _f(row.suggested_qty) or 0.0,
        "chosen_qty": _f(row.chosen_qty),
        "chosen_supplier_code": supplier.supplier_code if supplier else None,
        "chosen_supplier_name": supplier.supplier_name if supplier else None,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        # Nullable on purpose. A 0 here would read as "already out of stock" / "no space
        # needed" rather than "nobody measured this".
        "avg_daily_demand": _f(row.avg_daily_demand),
        "unit_volume_cbm": _f(row.unit_volume_cbm),
        "spare_lands_at": pool.warehouse_code if pool else None,
        "project_demand_line_count": row.project_demand_line_count or 0,
        "dealer_outstanding_line_count": row.dealer_outstanding_line_count or 0,
        "max_days_outstanding": row.max_days_outstanding,
    }


# =========================================================================== #
# read: what one aggregate opens to
# =========================================================================== #


def _product_by_code(db: Session, product_code: str) -> Product:
    product = (
        db.query(Product)
        .filter(func.upper(Product.product_code) == (product_code or "").strip().upper())
        .first()
    )
    if product is None:
        raise AppException(404, f"No product with code {product_code}.")
    return product


def demand_drill(db: Session, product_code: str, *, kind: str) -> dict:
    """The lines behind one aggregate, SERVER-sorted.

    The server owns the ordering so the ageing a person reads is the ageing the server
    computed: `dealer` comes back worst-first by days outstanding (AC-C2.4), `project` by
    required date with undated lines last. A client that re-sorted could show a different
    worst line than the row's own flag.
    """
    if kind not in ("project", "dealer"):
        raise AppException(422, "A drill is either project or dealer.")
    product = _product_by_code(db, product_code)
    types = _PROJECT_TYPES if kind == "project" else _DEALER_TYPES

    rows = (
        db.query(
            SalesOrder.so_number,
            SalesOrder.order_date,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
            SalesOrderLine.required_date,
            SalesOrder.requested_delivery_date,
            Customer.customer_name,
        )
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .filter(
            SalesOrderLine.product_id == product.id,
            func.lower(func.coalesce(SalesOrder.order_type, "")).in_(types),
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
        )
        .all()
    )
    today = _today()
    project_lines: list[dict] = []
    dealer_lines: list[dict] = []
    total = 0.0
    for r in rows:
        qty = float(r.qty_ordered or 0) - float(r.qty_delivered or 0)
        total += qty
        if kind == "project":
            project_lines.append({
                # AC-C2.3 asks for the PROJECT name, and the SCM order book does not carry
                # one: `sales_orders` has customer, type and dates, and the project-sales
                # module's `project_sales_orders` is a separate book with no link to this
                # one. The customer is the closest true label (on a project order it is the
                # main contractor), so it is used and the gap is recorded in the plan rather
                # than filled with a fabricated project name.
                "project_name": r.customer_name or "",
                "so_number": r.so_number or "",
                "qty": round(qty, 4),
                "required_date": (
                    r.required_date.isoformat() if r.required_date
                    else (r.requested_delivery_date.isoformat()
                          if r.requested_delivery_date else None)
                ),
            })
        else:
            dealer_lines.append({
                "dealer_name": r.customer_name or "",
                "so_number": r.so_number or "",
                "qty": round(qty, 4),
                "days_outstanding": (
                    (today - r.order_date).days if r.order_date is not None else 0
                ),
                "ordered_date": r.order_date.isoformat() if r.order_date else None,
            })

    # Undated project lines LAST rather than first: `date.min` would put a line nobody has
    # dated at the top of a list ordered by urgency.
    project_lines.sort(key=lambda x: (x["required_date"] is None, x["required_date"] or ""))
    dealer_lines.sort(key=lambda x: -x["days_outstanding"])

    return {
        "product_code": product.product_code,
        "kind": kind,
        "total_qty": round(total, 4),
        "project_lines": project_lines,
        "dealer_lines": dealer_lines,
    }


# =========================================================================== #
# read: the supplier candidates
# =========================================================================== #


def suppliers_for(
    db: Session, product_code: str, *, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS
) -> dict:
    """Every supplier this product could be bought from, with what a buyer needs to choose.

    Supplier is a CHOICE, not a fixed value (AC-C2.5), and cost alone cannot answer whether to
    change supplier (AC-C3.5) - so on-time rate and lead time travel with every cost figure
    rather than living on another screen.

    Two flags exist to stop a cheap-looking candidate being taken at face value:

    * ``delivered_line_count`` of 0 means they have never delivered THIS item. Sent as 0
      rather than omitted, because the screen has to say so.
    * ``is_stale`` is the SERVER's verdict on the last PO date against ``stale_after_days``,
      so the flag cannot drift between screens. An item last bought years ago is a dead line
      wearing a fast mover's price.

    Both costs are ex-works in the row's own currency (AC-C3.4). Neither is a landed cost:
    freight and duty are not in the purchase order, so calling either "landed" would understate
    what the stock actually costs.
    """
    product = _product_by_code(db, product_code)
    today = _today()

    # The candidate SET is the LINKED suppliers, from `product_suppliers` - the same table the
    # reorder engine sources from, and the same one `decision_service` re-prices against. Built
    # from purchase history instead, this screen offered nobody for an item that had never been
    # bought while the plan beside it showed a supplier and a cost for that very item, and a
    # newly linked supplier could never be chosen at all. "Supplier is a selectable choice"
    # (AC-C2.5) means the choices are the links, not the receipts.
    #
    # That table also carries moq, order_multiple, unit_cost, currency and
    # standard_lead_time_days across 17,408 rows, so those figures are read rather than
    # reported absent.
    link_rows = (
        db.query(
            Supplier.id,
            Supplier.supplier_code,
            Supplier.supplier_name,
            ProductSupplier.unit_cost,
            ProductSupplier.currency,
            ProductSupplier.standard_lead_time_days,
            ProductSupplier.moq,
            ProductSupplier.order_multiple,
            ProductSupplier.is_primary_supplier,
        )
        .join(ProductSupplier, ProductSupplier.supplier_id == Supplier.id)
        .filter(ProductSupplier.product_id == product.id)
        .all()
    )

    # Every supplier with a PO line for this item, newest line first, so the first row seen per
    # supplier IS their last purchase. Ordered in SQL rather than compared in Python: a
    # max(date) subquery per supplier is the same answer at more cost.
    po_rows = (
        db.query(
            Supplier.id,
            Supplier.supplier_code,
            Supplier.supplier_name,
            PurchaseOrder.po_number,
            PurchaseOrderLine.unit_cost,
            PurchaseOrderLine.currency,
            func.coalesce(PurchaseOrderLine.expected_date, PurchaseOrder.issue_date),
            PurchaseOrder.issue_date,
        )
        .join(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
        .join(PurchaseOrderLine, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .filter(PurchaseOrderLine.product_id == product.id)
        .order_by(PurchaseOrder.issue_date.desc().nullslast())
        .all()
    )

    candidates: dict[str, dict] = {}
    for (
        sid, code, name, link_cost, link_ccy, link_lead, moq, multiple, primary
    ) in link_rows:
        candidates[str(sid)] = {
            "supplier_code": code,
            "supplier_name": name,
            "currency": (link_ccy or "").upper() or None,
            "last_po_cost": _f(link_cost),
            "last_po_date": None,
            "last_po_number": None,
            # From the link, and NULL is the truth today: `moq` and `order_multiple` are
            # populated in 0 of 17,408 rows, so a rounding rule cannot be stated. Sending 1
            # would read as "round to anything", which is a rule nobody set. (The table also
            # has a legacy `min_order_quantity` column the model does not map, equally empty,
            # so nothing is lost by reading only `moq`.)
            "moq": _f(moq),
            "order_multiple": _f(multiple),
            "lead_time_days": int(link_lead) if link_lead is not None else None,
            "_issued": None,
            "_primary": bool(primary),
        }

    # PO history layered ON TOP of the links, never instead of them. A supplier who has been
    # bought from but is no longer linked still appears: they are a real historical source and
    # hiding them would lose the cost comparison that makes a switch arguable.
    for sid, code, name, po_number, cost, currency, _expected, issued in po_rows:
        key = str(sid)
        c = candidates.get(key)
        if c is None:
            c = candidates[key] = {
                "supplier_code": code,
                "supplier_name": name,
                "currency": None,
                "last_po_cost": None,
                "last_po_date": None,
                "last_po_number": None,
                "moq": None,
                "order_multiple": None,
                "lead_time_days": None,
                "_issued": None,
                "_primary": False,
            }
        if c["last_po_number"] is not None:
            continue  # already holds this supplier's newest PO
        c["last_po_number"] = po_number
        c["last_po_date"] = issued.isoformat() if issued else None
        c["_issued"] = issued
        # The ORDERED cost is what AC-C3.1 asks for and it wins over the link's own figure:
        # the link is a quoted price, the PO line is what was actually committed to.
        if cost is not None:
            c["last_po_cost"] = _f(cost)
            c["currency"] = (currency or "").upper() or c["currency"]

    incoming = _last_incoming_cost(db, str(product.id))
    perf = _supplier_performance(db, str(product.id), list(candidates))
    delivered = _delivered_line_counts(db, str(product.id), list(candidates))

    out: list[dict] = []
    for key, c in candidates.items():
        issued = c.pop("_issued")
        primary = c.pop("_primary", False)
        inc_cost, inc_date, inc_ccy = incoming.get(key, (None, None, None))
        variance = cost_variance(
            c["last_po_cost"], c["currency"], inc_cost, inc_ccy
        )
        stale_days = (today - issued).days if issued else None
        p = perf.get(key, {})
        out.append({
            **c,
            "_is_primary": primary,
            "last_incoming_cost": _f(inc_cost),
            "last_incoming_date": inc_date.isoformat() if inc_date else None,
            # None whenever the two sides are not comparable (a missing figure, or two
            # currencies). Subtracting different units would produce a number that looks like
            # a reprice and is not one.
            "cost_variance": _f(variance.get("variance")),
            "on_time_rate": _f(p.get("on_time_rate")),
            # MEASURED lead time wins over the link's standard figure: what a supplier
            # actually takes is the number a place-by date has to be derived from, and the
            # link's value is the promise. The link is the fallback, not the answer.
            "lead_time_days": (
                int(p["avg_lead_time_days"]) if p.get("avg_lead_time_days") is not None
                else c.get("lead_time_days")
            ),
            "delivered_line_count": delivered.get(key, 0),
            "is_stale": bool(stale_days is not None and stale_days > stale_after_days),
            "stale_days": stale_days,
        })

    # The primary supplier first, then cheapest comparable cost, then unknown costs last: a
    # candidate with no recorded price is not the best offer, it is an unknown. Primary leads
    # because it is the link somebody deliberately marked, and burying it under a cheaper
    # unlinked historical source would quietly argue for a switch nobody proposed.
    out.sort(
        key=lambda c: (
            not c.pop("_is_primary", False),
            c["last_po_cost"] is None,
            c["last_po_cost"] or 0,
        )
    )
    return {
        "product_code": product.product_code,
        "stale_after_days": stale_after_days,
        "candidates": out,
    }


def _last_incoming_cost(db: Session, product_id: str) -> dict[str, tuple]:
    """Per supplier, the newest inbound shipment line cost for this item.

    Populated in 0 of 1,015 rows today: the packing-list ingest cannot supply a unit price
    (`PackingListProduct` is code plus quantity), so this returns nothing until that extraction
    is extended. It is written now so the day a cost arrives the variance is correct, and the
    screen says "no incoming cost recorded" in the meantime rather than inventing one.
    """
    from app.models.procurement import InboundShipment, InboundShipmentLine

    rows = (
        db.query(
            InboundShipment.supplier_id,
            InboundShipmentLine.unit_cost,
            InboundShipmentLine.currency,
            func.coalesce(
                InboundShipment.actual_arrival_date, InboundShipment.estimated_arrival_date
            ),
        )
        .join(InboundShipment, InboundShipment.id == InboundShipmentLine.shipment_id)
        .filter(
            InboundShipmentLine.product_id == product_id,
            InboundShipmentLine.unit_cost.isnot(None),
        )
        .order_by(
            func.coalesce(
                InboundShipment.actual_arrival_date, InboundShipment.estimated_arrival_date
            ).desc().nullslast()
        )
        .all()
    )
    out: dict[str, tuple] = {}
    for sid, cost, currency, when in rows:
        key = str(sid)
        if key in out:
            continue
        out[key] = (cost, when, (currency or "").upper() or None)
    return out


def _supplier_performance(
    db: Session, product_id: str, supplier_ids: list[str]
) -> dict[str, dict]:
    """The newest performance row per supplier, for this item where one exists.

    Item-specific first and supplier-wide as the fallback: how a supplier performs on THIS
    item is the question, and their overall record is the next best evidence rather than no
    evidence.
    """
    if not supplier_ids:
        return {}
    rows = (
        db.query(SupplierPerformance)
        .filter(
            SupplierPerformance.supplier_id.in_(supplier_ids),
            or_(
                SupplierPerformance.product_id == product_id,
                SupplierPerformance.product_id.is_(None),
            ),
        )
        .order_by(
            # Item-specific rows win over supplier-wide ones at the same date, which is what
            # `product_id IS NULL` sorting last achieves.
            SupplierPerformance.period_end.desc().nullslast(),
            SupplierPerformance.product_id.is_(None),
        )
        .all()
    )
    out: dict[str, dict] = {}
    for r in rows:
        key = str(r.supplier_id)
        if key in out:
            continue
        out[key] = {
            "on_time_rate": r.on_time_rate,
            "avg_lead_time_days": r.avg_lead_time_days,
        }
    return out


def _delivered_line_counts(
    db: Session, product_id: str, supplier_ids: list[str]
) -> dict[str, int]:
    """How many PO lines of THIS item each supplier has actually received against.

    Received, not ordered: a supplier with ten open orders and no arrivals has never delivered
    it, and that is exactly what AC-C2.5 says must be visible rather than letting a low price
    make them look cheap.
    """
    if not supplier_ids:
        return {}
    rows = (
        db.query(PurchaseOrder.supplier_id, func.count(PurchaseOrderLine.id))
        .join(PurchaseOrderLine, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrder.supplier_id.in_(supplier_ids),
            PurchaseOrderLine.qty_received > 0,
        )
        .group_by(PurchaseOrder.supplier_id)
        .all()
    )
    return {str(sid): int(n or 0) for sid, n in rows}


# =========================================================================== #
# write: the order-quantity decision
# =========================================================================== #


def record_decision(
    db: Session,
    product_code: str,
    *,
    run_id: str,
    chosen_qty: float,
    supplier_code: str,
    actor: Optional[str] = None,
) -> dict:
    """Record what a person decided to order, against the run they decided it on.

    A quantity ABOVE the shortfall is valid and is NOT warned about (AC-C2.7): buying spare is
    a legitimate call about container space and price breaks, and treating it as an error
    teaches the planner to work around the tool. What the system does instead is state the
    consequence, which the screen computes from figures already on the row.

    The engine's figure is never replaced (AC-C2.8): `suggested_qty` stays on the row beside
    `chosen_qty`, with the actor and the time, so a larger number is a decision on the record
    rather than an untraceable override.

    A negative quantity IS refused. Zero is not: it is the "use the pool, do not buy" answer
    this module exists to be able to give, and it has to be recordable so S4's worklist
    reconciles one-for-one against the decisions instead of showing a gap.
    """
    if chosen_qty is None or float(chosen_qty) < 0:
        raise AppException(422, "An order quantity cannot be negative.")

    run = _run_for(db, run_id)
    product = _product_by_code(db, product_code)
    row = (
        db.query(OrderSummaryRow)
        .filter(
            OrderSummaryRow.run_id == run.id,
            OrderSummaryRow.product_id == str(product.id),
        )
        .one_or_none()
    )
    if row is None:
        raise AppException(
            404,
            f"{product.product_code} is not in that plan, so there is nothing to decide on it.",
        )

    supplier = (
        db.query(Supplier)
        .filter(func.upper(Supplier.supplier_code) == (supplier_code or "").strip().upper())
        .first()
    )
    if supplier is None:
        raise AppException(404, f"No supplier with code {supplier_code}.")

    row.chosen_qty = float(chosen_qty)
    row.chosen_supplier_id = str(supplier.id)
    row.decided_by = actor or "unknown"
    row.decided_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))
    db.commit()
    db.refresh(row)

    return {
        "product_code": product.product_code,
        "chosen_qty": _f(row.chosen_qty),
        "suggested_qty": _f(row.suggested_qty) or 0.0,
        "chosen_supplier_code": supplier.supplier_code,
        "chosen_supplier_name": supplier.supplier_name,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat(),
    }
