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
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product, UnitOfMeasure
from app.models.scm import (
    DemandStat,
    OrderSummaryLocationAllocation,
    OrderSummaryRow,
    ReorderRecommendation,
    ReorderRun,
    SupplierPerformance,
)
from app.services.error_handler import AppException
from app.services.scm import plan_grain
from app.services.scm.coverage_service import CoverageService
from app.services.scm.demand import (
    ACTIVE_DECISION_STATE,
    BUY_VERB,
    UNPLACED_INQUIRY_STATE,
)
from app.services.scm.reorder_engine import allocate as eng_allocate
from app.services.scm.reorder_engine import round_order_qty as eng_round_order_qty
from app.services.scm.cost_capture_service import cost_variance
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime

log = logging.getLogger(__name__)

_SEED = "order_summary"

# The three channels a demand line can read as (front planning 5.2). `dealer` is the
# LEGACY name of retail: the stored column is still `dealer_outstanding` and an older
# caller may still ask for `kind=dealer`, so it is accepted as an alias and nothing else.
PROJECT_KIND = "project"
RETAIL_KIND = "retail"
UNCLASSIFIED_KIND = "unclassified"
DEALER_ALIAS = "dealer"
DEMAND_KINDS = (PROJECT_KIND, RETAIL_KIND, UNCLASSIFIED_KIND, DEALER_ALIAS)


def _channel_of(demand_class: Optional[str]) -> str:
    """The channel a persisted `sales_orders.demand_class` reads as.

    `project` is Project; NULL is the classification exception; everything else is Retail.
    The mapper that produces the stored value already resolves every textual source to one
    of the two words (`demand_class.class_of`), so nothing is re-derived here - this only
    says which of the three buckets a stored value belongs in, and a value nobody stamped
    is never quietly folded into the bigger bucket.
    """
    if demand_class is None:
        return UNCLASSIFIED_KIND
    return PROJECT_KIND if str(demand_class).strip().lower() == PROJECT_KIND else RETAIL_KIND


# The recommendation kinds that carry a product-location DEMAND reading (front planning
# 5.3). A buy is the only one that sizes a purchase, but a group that was covered by its
# own stock, could not be sourced, or is waiting on a reorder level still holds real
# demand at real locations - and a product whose location A buys while location B is
# covered would otherwise lose B's readings and B itself from the evidence. A
# `disposition` is deliberately absent: it is a statement about idle stock, not demand.
CHANNEL_REC_TYPES = ("buy", "covered", "exception", "needs_level")
BUY_REC_TYPE = "buy"

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

    **One row per product, with channel as analysis inside it** (front planning 5.3). The
    row carries its Project / Retail / unclassified readings, the frozen per-location facts
    they were summed from, and the UOM divisibility the whole run is decided at - and the
    key stays `(run_id, product_id)`, because a purchase order is raised once for the
    company and channel is not part of that identity.

    The freeze READS every kind of planning row (`CHANNEL_REC_TYPES`), not only the buys:
    a product buying at location A must still show what location B - covered by its own
    stock, unsourceable, or waiting on a level - holds and where it is. Which products get
    a row is a narrower question and is `_belongs_on_the_book`.

    **`suggested_qty` is rounded ONCE** (AC-F11). The old derivation summed each location's
    already-rounded quantity and ceiled the total, which applies the supplier's terms per
    location and then rounds a second time; the product total now goes through MOQ and the
    order multiple once and is quantized to the product's frozen `uom_decimal_places`.
    Unclassified demand is visible on the row and never enters that total (AC-E06).

    A LEGACY run - one created before the front-planning contract - keeps the old
    derivation and writes no channel field at all. Its NULLs are a durable marker, not a
    backfill nobody has run (AC-F10).

    Idempotent. A re-run of the writer for the same run updates in place rather than
    duplicating, which the unique index on (run_id, product_id) enforces anyway; doing it here
    means a retried job does not fail.
    """
    stamp_date = as_of or _today()
    computed_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))
    run = _run_for(db, run_id)
    is_legacy = plan_grain.is_legacy_run(run)

    # Read per LOCATION, not pre-summed: the channel breakdown, the shared supply
    # references and the location split all live on the individual frozen rows, and the
    # product figure is their sum.
    rec_rows = (
        db.query(
            ReorderRecommendation.product_id,
            ReorderRecommendation.warehouse_id,
            ReorderRecommendation.rec_type,
            ReorderRecommendation.rounded_qty,
            ReorderRecommendation.inputs,
        )
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.rec_type.in_(CHANNEL_REC_TYPES),
        )
        .all()
    )
    by_product: dict[str, list] = {}
    for r in rec_rows:
        by_product.setdefault(str(r.product_id), []).append(r)
    product_ids = [pid for pid, recs in by_product.items() if _belongs_on_the_book(recs)]
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
    decimals = {} if is_legacy else _uom_decimal_places(db, product_ids)
    constraints = {} if is_legacy else _supplier_constraints(db, product_ids)
    need_dates = {} if is_legacy else _earliest_project_need_dates(db, product_ids)
    wh_meta = _warehouse_meta(db, [r.warehouse_id for r in rec_rows])
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
        recs = by_product[pid]
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
        row.avg_daily_demand = stats.get(pid)
        row.unit_volume_cbm = _unit_volume_cbm(product) if product else None
        row.spare_lands_at_warehouse_id = spare.get(pid)
        row.project_demand_line_count = agg.get("project_lines", 0)
        row.dealer_outstanding_line_count = agg.get("dealer_lines", 0)
        row.unclassified_line_count = agg.get("unclassified_lines", 0)
        row.max_days_outstanding = agg.get("max_days_outstanding")
        # A run only states a breakdown its recommendations actually froze. That is not
        # the same question as "is the run legacy": a run stamped under the contract but
        # planned by an engine that predates the channel snapshot (the window between two
        # deploys) has a contract version and no `project_need` anywhere, and reading its
        # absent breakdown as zero would suggest ordering nothing for a product the plan
        # said to buy.
        has_channel = any("project_need" in (r.inputs or {}) for r in recs)
        if is_legacy or not has_channel:
            # Rounded UP to a whole unit, which is the conservative direction. Kept
            # verbatim - the BUY rows only, exactly as before channels existed - so
            # re-freezing such a run cannot silently restate a figure somebody already
            # decided against. A `covered` row carries the quantity that WOULD be bought,
            # and summing it here would turn a suggestion into an order.
            row.suggested_qty = float(math.ceil(
                sum(float(r.rounded_qty or 0)
                    for r in recs if r.rec_type == BUY_REC_TYPE)))
        else:
            channel = _channel_freeze(recs, wh_meta,
                                      decimal_places=decimals.get(pid, 0),
                                      constraints=constraints.get(pid) or {})
            row.project_buy_qty = channel["project_buy_qty"]
            row.retail_replenishment_qty = channel["retail_replenishment_qty"]
            row.unclassified_demand_qty = channel["unclassified_demand_qty"]
            row.uom_decimal_places = channel["uom_decimal_places"]
            row.channel_calculation_basis = channel["basis"]
            row.suggested_qty = channel["suggested_qty"]
            # Only when there IS firm Buy to date. NULL says "no confirmed project need",
            # which is a different fact from "needed today".
            row.earliest_project_need_date = (
                need_dates.get(pid) if channel["project_buy_qty"] > 0 else None
            )
        row.computed_at = computed_at
        row.source_system = "scm"
        row.source_ref = _SEED
        if pid not in existing:
            db.add(row)
        written += 1

    db.commit()
    return written


def _quantize_up(qty: float, decimal_places: int) -> float:
    """Round UP to the UOM's divisibility. 0 places means whole units.

    Up, never nearest: rounding down suggests less than the policy says is needed, and the
    figure this produces pre-fills an editable order quantity. A buyer can always type a
    smaller one.
    """
    if qty <= 0:
        return 0.0
    scale = 10 ** max(int(decimal_places or 0), 0)
    return math.ceil(round(float(qty) * scale, 6)) / scale


def _belongs_on_the_book(recs: list) -> bool:
    """Does this product get a Summary Order Report row at all?

    Yes when the run SIZED a purchase for it. Yes, too, when it owes firm Project Buy the
    run could not size: a confirmed unplaced Buy at a location with no linked supplier
    triggers and then emits `exception` with no buy anywhere, and leaving the product off
    the book hides a commitment CS has already made to a customer (AC-E04, AC-E06).

    No for a product whose only outcome was `covered` or `needs_level`. Its actionable
    suggestion is 0 by definition - its own stock is the answer, or nobody has set the
    level it would be planned against - so the Product grain has nothing to decide, and
    on the live catalogue that would put roughly 2,400 undecidable rows on an unpaginated
    report: the information fatigue AC-C2.2a exists to prevent. Those rows remain the
    Location grain's work, where each states its own reason.

    Both kinds still SPEAK on the products that do get a row: a covered group at location
    B contributes its channel readings and its member locations to a product buying at
    location A (`_channel_freeze`). What is scoped here is whose row exists, not what a
    row is allowed to read.
    """
    for r in recs:
        if r.rec_type == BUY_REC_TYPE:
            return True
        basis = (r.inputs or {}).get("plan_basis") or {}
        if float(basis.get("project_need") or 0.0) > 0:
            return True
    return False


def _sizing_groups(recs: list) -> dict:
    """``{group key: frozen plan basis}`` for the rows of one product.

    A plan is made against a GROUP of locations, not against a row: a pool emits one row
    per location that was allocated something, all describing ONE decision, and a network
    buy emits a single row that names no location at all. The engine freezes that group's
    own basis on every row it produced (`reorder_run_service._plan_basis`), so this
    collapses the rows back to the decisions they came from - once per group, however many
    rows carried it, and however many KINDS of row it carried: a group that emitted both a
    buy and a needs_level is still one group and must be counted once.

    Pass whichever rows the question is about. The demand readings want every kind
    (`CHANNEL_REC_TYPES`); the sized figures want the buys alone.
    """
    groups: dict = {}
    for r in recs:
        basis = (r.inputs or {}).get("plan_basis")
        if basis:
            groups.setdefault(basis.get("group") or str(r.warehouse_id), basis)
    return groups


def _channel_freeze(recs: list, wh_meta: dict, *, decimal_places: int,
                    constraints: dict) -> dict:
    """The product row's channel readings, its once-rounded suggestion, and the evidence.

    Reads the SAME frozen basis the engine sized each buy on, so the Product and Location
    views cannot disagree about a number (AC-F03): there is one calculation and two
    presentations of it.

    **The unit is the sizing GROUP, not the recommendation row.** Project need, the sheet
    leg and unclassified demand are additive across locations, so summing rows happened to
    work for them. Netted Retail replenishment is not: a pool and a network buy are netted
    ONCE on the aggregate, and their member cells can each read 0 - individually
    untriggered under their own reorder level - while the group is short 213. Summing the
    rows therefore stated "Suggested 0" for a run that had just sized a 213-unit buy. The
    group states its own netted figure and the freeze reads that.

    **Demand is read from every kind of row, sizing only from the buys.** Project, the
    sheet leg and unclassified demand are statements about the order book, so they come
    from every group the product produced - covered, unsourceable and un-levelled included,
    or a product buying at location A silently loses location B's readings and B itself
    from the evidence. Netted Retail replenishment is the figure a purchase was sized on,
    so it comes only from groups that bought; a covered group's is 0 by definition.

    A run frozen before the basis existed (or a hand-built recommendation) has no group,
    and falls back to the row-wise sum over the BUY rows, which is exactly right for the
    per-warehouse shape it was written for and leaves those runs byte for byte as they
    were.

    `project_buy_qty` is CONFIRMED unplaced Buy only, which is what plan 5.3 and AC-E04
    define it as. The unconfirmed sheet leg was netted by the engine alongside Retail, so
    it is answered inside `retail_replenishment_qty` and cannot be a fourth quantity here
    (the row carries exactly three, per plan 6.4). It is still named - `project_sheet_netted`
    in the basis, and per location below - so the drill can say where it went rather than
    leave a reader to notice a project-class quantity missing from both columns. The open
    project-class order book is separately visible as `project_demand` on the same row.
    """
    buy_recs = [r for r in recs if r.rec_type == BUY_REC_TYPE]
    groups = _sizing_groups(recs)
    if groups:
        sources: list = list(groups.values())
        # Netted Retail is a SIZED figure, so it is read only off the groups that actually
        # bought. A covered group's replenishment is 0 by definition (its stock covers the
        # need), and a group that could not be sourced or is waiting on a level sized no
        # purchase either - while their Project, sheet and unclassified readings above are
        # demand and stay additive across every group.
        retail_sources: list = list(_sizing_groups(buy_recs).values())
        locations = [
            # `warehouse_id` stays inside the recommendation snapshot, where the allocator
            # replay reads it; the product row's basis is addressed by code alone.
            {k: v for k, v in loc.items() if k != "warehouse_id"}
            for g in sources for loc in (g.get("locations") or [])
        ]
    else:
        sources = [
            {
                "project_need": (r.inputs or {}).get("project_need"),
                "retail_need": (r.inputs or {}).get("retail_need"),
                "project_sheet_need": (r.inputs or {}).get("project_sheet_need"),
                "unclassified_need": (r.inputs or {}).get("unclassified_need"),
            }
            for r in buy_recs
        ]
        retail_sources = sources
        locations = []
        for r in buy_recs:
            inp = r.inputs or {}
            code, name = wh_meta.get(str(r.warehouse_id), (None, None))
            locations.append({
                "warehouse_code": code,
                "warehouse_name": name,
                "project_need": _f(inp.get("project_need")) or 0.0,
                "retail_need": _f(inp.get("retail_need")) or 0.0,
                # Netted inside `retail_need` above, never added to it: an unconfirmed
                # sheet-origin project quantity is demand the engine put through ordinary
                # netting, so it is stated for the reader and summed nowhere.
                "project_sheet_need": _f(inp.get("project_sheet_need")) or 0.0,
                "unclassified_need": _f(inp.get("unclassified_need")) or 0.0,
                # Shared facts of the product-location, counted ONCE and carrying no
                # channel dimension (AC-F07).
                "on_hand": _f(inp.get("on_hand")),
                "incoming_spo": _f(inp.get("on_order")),
                "on_order_po": _f(inp.get("po_ordered")),
                "reorder_level": _f(inp.get("reorder_level")),
                "avg_daily_demand": _f(inp.get("demand_rate")),
                "location_suggested_qty": _f(r.rounded_qty) or 0.0,
            })

    project = sum(float(s.get("project_need") or 0.0) for s in sources)
    retail = sum(float(s.get("retail_need") or 0.0) for s in retail_sources)
    unclassified = sum(float(s.get("unclassified_need") or 0.0) for s in sources)
    project_sheet = sum(float(s.get("project_sheet_need") or 0.0) for s in sources)
    raw_need = project + retail
    moq = constraints.get("moq")
    multiple = constraints.get("order_multiple")
    # ONCE: the supplier's terms apply to the product total, never per location and never
    # per channel, and the quantize is the same step's last half rather than a second
    # rounding policy.
    suggested = _quantize_up(
        eng_round_order_qty(raw_need, moq, multiple) if raw_need > 0 else 0.0,
        decimal_places,
    )
    locations.sort(key=lambda x: (x["warehouse_code"] or ""))
    return {
        "project_buy_qty": project,
        "retail_replenishment_qty": retail,
        "unclassified_demand_qty": unclassified,
        "uom_decimal_places": decimal_places,
        "suggested_qty": suggested,
        "basis": {
            "raw_need": raw_need,
            "supplier_moq": moq,
            "supplier_order_multiple": multiple,
            "rounded_qty": suggested,
            "uom_decimal_places": decimal_places,
            # Named rather than merely absent, so the drill can say WHY it is not in the
            # actionable total instead of leaving a reader to notice the gap.
            "unclassified_excluded": unclassified,
            # Inside `retail_replenishment_qty`, not beside it. Named so the drill can
            # explain a project-class quantity that is not in `project_buy_qty` because
            # nobody has confirmed a decision for it yet (plan 4).
            "project_sheet_netted": project_sheet,
            "locations": locations,
        },
    }


def _warehouse_meta(db: Session, warehouse_ids) -> dict:
    """``{warehouse_id: (code, name)}`` for the locations a run touched.

    Resolved once for the whole freeze so no UUID reaches a stored basis or a response.
    """
    ids = list({str(w) for w in warehouse_ids if w})
    if not ids:
        return {}
    return {
        str(w.id): (w.warehouse_code, w.warehouse_name)
        for w in db.query(Warehouse).filter(Warehouse.id.in_(ids)).all()
    }


def _uom_decimal_places(db: Session, product_ids: list[str]) -> dict[str, int]:
    """``{product_id: base UOM decimal_places}``, defaulting to 0.

    Frozen onto the row by the caller: validation and the allocator rerun read the
    SNAPSHOT, so editing the UOM next week cannot change what a finished run accepted
    (AC-F12). A missing value during rollout resolves to 0 - whole units - which is the
    conservative reading of "nobody has said this is divisible".
    """
    rows = (
        db.query(Product.id, UnitOfMeasure.decimal_places)
        .outerjoin(UnitOfMeasure, UnitOfMeasure.id == Product.base_uom_id)
        .filter(Product.id.in_(product_ids))
        .all()
    )
    return {str(pid): int(dp or 0) for pid, dp in rows}


def _supplier_constraints(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """``{product_id: {moq, order_multiple}}`` from the product's supplier link.

    The PRIMARY link wins; any link is used when none is primary, because a constraint
    nobody marked primary is still the supplier's constraint and ignoring it would size an
    order the supplier will not accept.
    """
    rows = (
        db.query(
            ProductSupplier.product_id,
            ProductSupplier.moq,
            ProductSupplier.order_multiple,
            ProductSupplier.is_primary_supplier,
        )
        .filter(ProductSupplier.product_id.in_(product_ids))
        .all()
    )
    out: dict[str, dict] = {}
    for pid, moq, multiple, is_primary in rows:
        key = str(pid)
        current = out.get(key)
        if current is None or (is_primary and not current.get("is_primary")):
            out[key] = {"moq": _f(moq), "order_multiple": _f(multiple),
                        "is_primary": bool(is_primary)}
    return out


def _earliest_project_need_dates(db: Session, product_ids: list[str]) -> dict[str, date]:
    """``{product_id: earliest date a confirmed unplaced Buy is needed}``.

    Read through the same section-4 join path the read model uses, so the date on the row
    describes the very quantity in `project_buy_qty` rather than the order book generally.
    The inquiry row's own delivery date wins; the reconciled core line's required date is
    the fallback, and a Buy nobody has dated contributes no date at all.
    """
    if not product_ids:
        return {}
    rows = db.execute(text("""
        SELECT sol.product_id::text AS pid,
               MIN(COALESCE(oir.delivery_date, sol.required_date)) AS needed
        FROM projects.order_inquiry_rows oir
        JOIN projects.so_supply_decisions d
          ON d.id = oir.supply_decision_id AND d.state = :active
        JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
        JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
        WHERE oir.verb = :buy
          AND oir.state = :unplaced
          AND oir.qty > 0
          AND sol.product_id::text = ANY(:pids)
        GROUP BY 1
    """), {"pids": [str(p) for p in product_ids], "active": ACTIVE_DECISION_STATE,
           "buy": BUY_VERB, "unplaced": UNPLACED_INQUIRY_STATE}).fetchall()
    return {str(r[0]): r[1] for r in rows if r[1] is not None}


def _demand_aggregates(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """Project and retail outstanding quantity, line counts, and the worst retail ageing.

    One query for the whole batch, split on the PERSISTED `sales_orders.demand_class`
    (front planning 5.2 / AC-E01). The class is the semantic owner: it is stamped by the
    import precedence (stored order type, stated order type, customer market segment, then
    sales-agent class) through one shared mapper, so a dealer-looking `order_type` on an
    order the importer classified as project is Project here, full stop. Reading
    `order_type` directly, as this used to, was a second classifier that could disagree
    with the one the rest of planning uses.

    A line whose order carries NO class is unclassified: counted, named, and folded into
    neither aggregate, because a missing class is a data-quality exception rather than a
    third channel (AC-E02).

    The stored columns keep their names (`dealer_*`); the API and the screens say retail,
    which is the user's word.
    """
    rows = (
        db.query(
            SalesOrderLine.product_id,
            SalesOrder.demand_class,
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
        kind = _channel_of(r.demand_class)
        if kind == PROJECT_KIND:
            acc["project_qty"] += qty
            acc["project_lines"] += 1
        elif kind == RETAIL_KIND:
            acc["dealer_qty"] += qty
            acc["dealer_lines"] += 1
            # Ageing is only meaningful on the retail half: AC-C2.4's point is that a small
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
    splits = _location_allocations(db, [str(r.id) for r, _p, _s, _w in rows])
    return {
        "run_id": str(run.id),
        # The run's STAMP, never the live policy setting: a run is read at the grain it was
        # created with (AC-F01/F10). `is_legacy` is the older, pre-contract run whose
        # channel breakdown is unavailable and whose decisions are closed.
        "decision_grain": plan_grain.decision_grain_of(run),
        "is_legacy": plan_grain.is_legacy_run(run),
        # Off the rows, not off `date.today()`: an empty report has no computed date to state,
        # and inventing today's would date a book that was never built.
        "as_of": (rows[0][0].as_of.isoformat() if rows else None),
        "generated_at": (
            rows[0][0].computed_at.isoformat() if rows else None
        ),
        "rows": [_serialise_row(r, p, s, w, splits.get(str(r.id)), run)
                 for r, p, s, w in rows],
    }


def _location_allocations(db: Session, row_ids: list[str]) -> dict[str, list[dict]]:
    """``{order_summary_row_id: [{warehouse_code, warehouse_name, allocated_qty}]}``.

    Read for the whole report in one query rather than per row, and addressed by code: the
    split is what tells a buyer where a product-grain purchase lands, so it travels with
    the row rather than behind another request.
    """
    if not row_ids:
        return {}
    rows = (
        db.query(OrderSummaryLocationAllocation, Warehouse)
        .join(Warehouse, Warehouse.id == OrderSummaryLocationAllocation.warehouse_id)
        .filter(OrderSummaryLocationAllocation.order_summary_row_id.in_(row_ids))
        .all()
    )
    out: dict[str, list[dict]] = {}
    for alloc, wh in rows:
        out.setdefault(str(alloc.order_summary_row_id), []).append({
            "warehouse_code": wh.warehouse_code,
            "warehouse_name": wh.warehouse_name,
            "allocated_qty": _f(alloc.allocated_qty) or 0.0,
        })
    for split in out.values():
        split.sort(key=lambda a: a["warehouse_code"] or "")
    return out


def _serialise_row(row: OrderSummaryRow, product: Product, supplier, pool,
                   allocations: Optional[list[dict]] = None,
                   run: Optional[ReorderRun] = None) -> dict:
    return {
        "product_code": product.product_code,
        # The run's own stamp, repeated on the row so a row is self-describing: whether
        # its channel figures mean anything is a property of the run it belongs to, and a
        # component holding one row should not have to reach back up for it.
        "decision_grain": plan_grain.decision_grain_of(run) if run is not None else None,
        "is_legacy": plan_grain.is_legacy_run(run) if run is not None else True,
        "product_name": product.product_name,
        "uom": getattr(getattr(product, "base_uom", None), "uom_code", None),
        "on_hand": _f(row.on_hand) or 0.0,
        "project_demand": _f(row.project_demand) or 0.0,
        "dealer_outstanding": _f(row.dealer_outstanding) or 0.0,
        # The same stored column under the name every screen uses (AC-E03). The column
        # keeps its name; the wire and the UI say retail, which is the user's word.
        "retail_outstanding": _f(row.dealer_outstanding) or 0.0,
        # Front planning. NULL on a legacy run, and NOT inferred: an unavailable breakdown
        # is what the screen renders, never a guess at one (AC-F10).
        "project_buy_qty": _f(row.project_buy_qty),
        "retail_replenishment_qty": _f(row.retail_replenishment_qty),
        "unclassified_demand_qty": _f(row.unclassified_demand_qty),
        "earliest_project_need_date": (
            row.earliest_project_need_date.isoformat()
            if row.earliest_project_need_date else None
        ),
        "uom_decimal_places": row.uom_decimal_places,
        # `channel_calculation_basis` is deliberately NOT here. It is the row's whole
        # per-location evidence set, the report is returned unpaginated, and on a real run
        # that was 2,043 location entries across 507 rows - shipped to every reader of the
        # book so that a drill nobody had opened yet would already have its data. The drill
        # fetches it per product from `/order-summary/{code}/locations`, which is one row's
        # worth on demand. The column and that endpoint are untouched.
        "location_allocations": allocations or None,
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
        "retail_outstanding_line_count": row.dealer_outstanding_line_count or 0,
        "unclassified_line_count": row.unclassified_line_count or 0,
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
    computed: `retail` comes back worst-first by days outstanding (AC-C2.4), `project` by
    required date with undated lines last, `unclassified` oldest first. A client that
    re-sorted could show a different worst line than the row's own flag.

    Classified by the PERSISTED `demand_class`, the same owner the aggregates use, so a
    drill can never disagree with the figure it opened (AC-E01). `dealer` is accepted as
    the legacy name of `retail`.

    A project line carries what Purchasing needs to trace it back: its human line number,
    its fulfilment location, and the decision revision plus inquiry reference the Buy came
    from - never a UUID (AC-E07). A line whose SO has no confirmed decision says so.
    """
    if kind not in DEMAND_KINDS:
        raise AppException(
            422, "A drill is project, retail or unclassified.")
    if kind == DEALER_ALIAS:
        kind = RETAIL_KIND
    product = _product_by_code(db, product_code)

    rows = (
        db.query(
            SalesOrder.id,
            SalesOrder.so_number,
            SalesOrder.order_date,
            SalesOrder.demand_class,
            SalesOrderLine.id,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
            SalesOrderLine.required_date,
            SalesOrder.requested_delivery_date,
            Customer.customer_name,
            Warehouse.warehouse_code,
        )
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(
            SalesOrderLine.product_id == product.id,
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.qty_ordered > SalesOrderLine.qty_delivered,
        )
        .all()
    )
    today = _today()
    project_lines: list[dict] = []
    retail_lines: list[dict] = []
    unclassified_lines: list[dict] = []
    total = 0.0
    line_ids = [str(r[4]) for r in rows if _channel_of(r[3]) == kind]
    decision_refs = _decision_refs(db, line_ids) if kind != RETAIL_KIND else {}
    for r in rows:
        (_so_id, so_number, order_date, demand_class, line_id, qty_ordered, qty_delivered,
         required_date, requested_delivery_date, customer_name, warehouse_code) = r
        # `public.sales_order_lines` carries no line number - the human one lives on the
        # reconciled PROJECT line, which is also where the decision reference comes from,
        # so both are resolved through the same join, for the project drill and for the
        # unclassified one (an order whose class was never stamped can still have been
        # reconciled). A line with no reconciled project line has no human number, and
        # NULL says so rather than inventing an index.
        traced = decision_refs.get(str(line_id)) or {}
        line_no = traced.get("line_no")
        if _channel_of(demand_class) != kind:
            continue
        qty = float(qty_ordered or 0) - float(qty_delivered or 0)
        total += qty
        if kind == PROJECT_KIND:
            project_lines.append({
                # AC-C2.3 asks for the PROJECT name, and the SCM order book does not carry
                # one: `sales_orders` has customer, type and dates, and the project-sales
                # module's `project_sales_orders` is a separate book with no link to this
                # one. The customer is the closest true label (on a project order it is the
                # main contractor), so it is used and the gap is recorded in the plan rather
                # than filled with a fabricated project name.
                "project_name": customer_name or "",
                "so_number": so_number or "",
                "qty": round(qty, 4),
                "required_date": (
                    required_date.isoformat() if required_date
                    else (requested_delivery_date.isoformat()
                          if requested_delivery_date else None)
                ),
                "line_no": line_no,
                "warehouse_code": warehouse_code,
                "decision_ref": traced.get("ref"),
            })
        elif kind == RETAIL_KIND:
            retail_lines.append({
                "dealer_name": customer_name or "",
                "so_number": so_number or "",
                "qty": round(qty, 4),
                "days_outstanding": (
                    (today - order_date).days if order_date is not None else 0
                ),
                "ordered_date": order_date.isoformat() if order_date else None,
            })
        else:
            unclassified_lines.append({
                "customer_name": customer_name or "",
                "so_number": so_number or "",
                "line_no": line_no,
                "qty": round(qty, 4),
                "ordered_date": order_date.isoformat() if order_date else None,
                # In the words it is recorded with: the import evaluated stored order
                # type, stated order type, market segment and sales agent and none of them
                # said. That is a data-quality job, not a third channel.
                "exception": "No demand class on the sales order",
            })

    # Undated project lines LAST rather than first: `date.min` would put a line nobody has
    # dated at the top of a list ordered by urgency.
    project_lines.sort(key=lambda x: (x["required_date"] is None, x["required_date"] or ""))
    retail_lines.sort(key=lambda x: -x["days_outstanding"])
    unclassified_lines.sort(key=lambda x: (x["ordered_date"] is None,
                                           x["ordered_date"] or ""))

    return {
        "product_code": product.product_code,
        "kind": kind,
        "total_qty": round(total, 4),
        "project_lines": project_lines,
        "retail_lines": retail_lines,
        # The same lines under the old name, so a caller written against the previous
        # payload keeps rendering.
        "dealer_lines": retail_lines,
        "unclassified_lines": unclassified_lines,
    }


def _decision_refs(db: Session, core_line_ids: list[str]) -> dict[str, dict]:
    """``{core sales-order line id: {"ref": "Rev 2 / PSO-0188", "line_no": 3}}``.

    A HUMAN reference, assembled from the decision's revision number and the Project SO's
    AutoCount document (falling back to its provisional reference), because Purchasing has
    to be able to trace a Buy back to the decision that produced it and no UUID may reach a
    screen (AC-E07). The human line number comes from the same reconciled project line -
    `public.sales_order_lines` has none - so a line the AutoCount upload has not reconciled
    yet has neither, and NULL says so rather than inventing an index into a result set.
    """
    if not core_line_ids:
        return {}
    rows = db.execute(text("""
        SELECT psl.core_sales_order_line_id::text AS line_id,
               psl.line_no,
               d.revision_no,
               COALESCE(pso.autocount_doc_no, pso.provisional_ref) AS ref
        FROM projects.sales_order_lines psl
        JOIN projects.sales_orders pso ON pso.id = psl.project_sales_order_id
        LEFT JOIN projects.so_supply_decisions d
          ON d.project_sales_order_id = pso.id AND d.state = :active
        WHERE psl.core_sales_order_line_id::text = ANY(:ids)
    """), {"ids": core_line_ids, "active": ACTIVE_DECISION_STATE}).fetchall()
    out: dict[str, dict] = {}
    for line_id, line_no, revision_no, ref in rows:
        out[str(line_id)] = {
            "line_no": int(line_no) if line_no is not None else None,
            "ref": (f"Rev {revision_no}" + (f" / {ref}" if ref else "")
                    if revision_no is not None else None),
        }
    return out


def locations(db: Session, product_code: str, *, run_id: Optional[str] = None) -> dict:
    """The member locations behind one product row (AC-F08).

    Everything here comes off the row's FROZEN basis, not a live recalculation: it is the
    same evidence the product figure was summed from, so the drill can only ever reconcile
    with the row it opened. Demand is split by channel; stock, incoming SPO, the PO book
    and the reorder level are single shared facts of the product-location and appear ONCE,
    with no channel dimension (AC-F07).

    On a legacy run there is no breakdown to show and none is inferred: the locations come
    back empty and `is_legacy` says why (AC-F10).
    """
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
            404, f"{product.product_code} is not in that plan, so it has no locations.")

    basis = row.channel_calculation_basis or {}
    allocated = {
        a["warehouse_code"]: a["allocated_qty"]
        for a in (_location_allocations(db, [str(row.id)]).get(str(row.id)) or [])
    }
    members = []
    for loc in basis.get("locations") or []:
        members.append({
            "warehouse_code": loc.get("warehouse_code"),
            "warehouse_name": loc.get("warehouse_name"),
            "project_need": loc.get("project_need"),
            "retail_need": loc.get("retail_need"),
            # Absent on a run frozen before the confirmed/sheet split, and NULL there
            # rather than 0: the run never stated it.
            "project_sheet_need": loc.get("project_sheet_need"),
            "unclassified_need": loc.get("unclassified_need"),
            "on_hand": loc.get("on_hand") or 0.0,
            "incoming_spo": loc.get("incoming_spo") or 0.0,
            "on_order_po": loc.get("on_order_po") or 0.0,
            # NULL means nobody has set a level, which is not the same as a level of zero.
            "reorder_level": loc.get("reorder_level"),
            "avg_daily_demand": loc.get("avg_daily_demand"),
            "allocated_qty": allocated.get(loc.get("warehouse_code")),
        })
    return {
        "product_code": product.product_code,
        "decision_grain": plan_grain.decision_grain_of(run),
        "is_legacy": plan_grain.is_legacy_run(run),
        "uom": getattr(getattr(product, "base_uom", None), "uom_code", None),
        "uom_decimal_places": row.uom_decimal_places,
        # Repeated from the row so the drill reconciles against the figure it opened
        # rather than against one it recomputed.
        "suggested_qty": _f(row.suggested_qty) or 0.0,
        "chosen_qty": _f(row.chosen_qty),
        "locations": members,
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
            # The SHIPMENT line's own currency, not the candidate's. `currency` above is the
            # link's or the PO line's, and a CNY pre-loading list price rendered under it
            # reads as MYR 250.00 for CNY 250.00 with nothing on screen disagreeing. Null
            # when the shipment line states none, which the screen shows unlabelled rather
            # than borrowing a code the figure is not in.
            "last_incoming_currency": inc_ccy,
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

    Empty for every row written before G3c, and populated from there: the packing-list ingest
    now persists the `unit_cost` + `currency` it parses instead of discarding them, so a
    shipment loaded from a priced pre-loading list answers here. Rows with no cost still
    read as "no incoming cost recorded" rather than having one invented for them, and the
    currency below is load-bearing now that the value arrives - a CNY price compared against
    an MYR price list is a variance number that means nothing.
    """
    from app.models.procurement import InboundShipment, InboundShipmentLine

    rows = (
        db.query(
            # Whose line this is, else whose container it is: a mixed container has no
            # header supplier, and reading the header alone dropped every one of its
            # lines out of the per-supplier cost.
            func.coalesce(InboundShipmentLine.supplier_id, InboundShipment.supplier_id),
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
        if sid is None:
            # A line nobody has attributed to a factory is not a price from any supplier.
            continue
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
    # Product grain owns this decision. A legacy run owns neither, and a location-grain
    # run owns the recommendation decisions instead (plan 5.4, AC-F09).
    plan_grain.assert_decision_grain(run, plan_grain.PRODUCT_GRAIN)
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

    # The FROZEN precision, never live UOM master data: a UOM edited after the run was
    # calculated must not change what this run will accept (AC-F12).
    _assert_chosen_qty_precision(chosen_qty, row.uom_decimal_places, product.product_code,
                                 uom_code=getattr(getattr(product, "base_uom", None),
                                                  "uom_code", None))

    row.chosen_qty = float(chosen_qty)
    row.chosen_supplier_id = str(supplier.id)
    row.decided_by = actor or "unknown"
    row.decided_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))
    db.flush()
    split = _persist_location_split(db, row)
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
        # Returned with the decision so the split is visible the moment it is recorded,
        # rather than after a refetch nobody triggers.
        "location_allocations": split,
    }


def _fractional_digits(value: float) -> int:
    """How many decimal places a submitted quantity actually carries.

    Through `Decimal(str(...))` on purpose: `Decimal(2.5)` is the binary expansion and
    would report seventeen places for a figure a person typed as one.
    """
    exponent = Decimal(str(value)).normalize().as_tuple().exponent
    return -int(exponent) if isinstance(exponent, int) and exponent < 0 else 0


def _assert_chosen_qty_precision(chosen_qty: float, decimal_places: Optional[int],
                                 product_code: str, *, uom_code: Optional[str]) -> None:
    """Refuse a quantity finer than the UOM divides (AC-F12).

    `2.5 EA` is half a thing nobody can pick, ship or key; `2.5 kg` at three places is an
    ordinary weight. The difference is master data, not a planning knob, and the snapshot
    on the row is what a frozen run is judged against.
    """
    allowed = int(decimal_places or 0)
    if _fractional_digits(chosen_qty) <= allowed:
        return
    unit = f" ({uom_code})" if uom_code else ""
    message = (
        f"{product_code} is ordered in whole units{unit}."
        if allowed == 0
        else f"{product_code} is ordered to {allowed} decimal places{unit}."
    )
    raise AppException(422, message, code="chosen_qty_precision")


def _persist_location_split(db: Session, row: OrderSummaryRow) -> list[dict]:
    """Replay the allocator over the run's frozen location inputs and persist the split.

    The Product grain decides ONE quantity and a purchase order still has to land
    somewhere, so the existing `reorder_engine.allocate` is rerun with the chosen quantity,
    the frozen per-location need, and the row's frozen `uom_decimal_places` - working in
    integer minor units so the children sum EXACTLY to `chosen_qty` (AC-F12).

    A re-decision REPLACES the split rather than rescaling it: rescaling a previous
    apportionment compounds its rounding and would drift away from the parent, and the
    frozen inputs it is derived from have not changed.
    """
    db.query(OrderSummaryLocationAllocation).filter(
        OrderSummaryLocationAllocation.order_summary_row_id == str(row.id)
    ).delete(synchronize_session=False)

    chosen = float(row.chosen_qty or 0)
    all_recs = (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == str(row.run_id),
            ReorderRecommendation.product_id == str(row.product_id),
            ReorderRecommendation.rec_type == "buy",
        )
        .all()
    )
    recs = [r for r in all_recs if r.warehouse_id is not None]
    if chosen <= 0 or not all_recs:
        return []

    inputs = []
    for rec in recs:
        frozen = rec.inputs or {}
        # The location's own frozen need is its deficit: it is what the run said this
        # place was short of, which is the same figure the plan's location view shows.
        deficit = _f(rec.rounded_qty) or 0.0
        if deficit <= 0:
            deficit = max(-(_f(rec.net_position) or 0.0), 0.0)
        inputs.append({
            "warehouse_id": str(rec.warehouse_id),
            "deficit": deficit,
            "demand_rate": _f(rec.forecast_daily_demand) or _f(frozen.get("demand_rate")) or 0.0,
            "recommendation_id": str(rec.id),
        })
    if not inputs:
        # A NETWORK buy names no warehouse, so there is no per-location row to replay
        # over - and a product-grain decision that could not be split would leave the
        # buyer with a quantity and nowhere to put it (AC-F08, AC-F12). The run's own
        # frozen basis carries the member locations and the share the engine gave each,
        # which is exactly the deficit signal the per-location rows would have supplied.
        for g in _sizing_groups(all_recs).values():
            for loc in g.get("locations") or []:
                if not loc.get("warehouse_id"):
                    continue
                inputs.append({
                    "warehouse_id": str(loc["warehouse_id"]),
                    "deficit": float(loc.get("location_suggested_qty") or 0.0),
                    "demand_rate": float(loc.get("avg_daily_demand") or 0.0),
                    "recommendation_id": None,
                })
    if not inputs:
        return []
    rec_by_wid = {i["warehouse_id"]: i["recommendation_id"] for i in inputs}
    allocation = eng_allocate(chosen, inputs,
                              decimal_places=int(row.uom_decimal_places or 0))
    for wid, qty in allocation.items():
        db.add(OrderSummaryLocationAllocation(
            id=_uuid(),
            order_summary_row_id=str(row.id),
            reorder_recommendation_id=rec_by_wid.get(wid),
            warehouse_id=wid,
            allocated_qty=float(qty),
        ))
    db.flush()
    meta = _warehouse_meta(db, list(allocation))
    out = [{
        "warehouse_code": meta.get(wid, (None, None))[0],
        "warehouse_name": meta.get(wid, (None, None))[1],
        "allocated_qty": float(qty),
    } for wid, qty in allocation.items()]
    out.sort(key=lambda a: a["warehouse_code"] or "")
    return out


# =========================================================================== #
# S4: the PO creation worklist over the decisions
# =========================================================================== #

# The keyed-into-AutoCount states (AC-E2.2). Manual, because nothing can detect it: no
# integration exists, so the person keying is the only source of truth. `keying` is
# load-bearing rather than decorative - it is what stops two people keying the same PO.
KEYED_STATUSES = ("not_keyed", "keying", "keyed")


def po_worklist(db: Session, *, run_id: Optional[str] = None) -> dict:
    """What was decided, ready to be keyed (AC-E2.1).

    Rows are the frozen report rows that carry a DECISION, and only those: a product
    nobody has decided on belongs on the report, not on the worklist. A decision of ZERO is
    included and says no PO is needed (AC-E2.5) - filtered out, a use-pool decision would
    be indistinguishable from one nobody made, and the worklist could not be reconciled
    one-for-one against the decisions.

    Need-by comes off the FROZEN shortfall date, because that is what the decision was
    taken against. Place-by is derived LIVE from need-by minus the lead time, because a
    corrected lead time should move the date an order has to be placed by; freezing it
    would leave a stale place-by beside a current lead time.

    **It reads ONE grain: the run's own** (AC-F09). A `product` run lists product rows,
    each carrying the split of its chosen quantity back to locations; a `location` run
    lists the per-location recommendation decisions instead. Merging both would key the
    same requirement twice, which is the whole reason exactly one grain is actionable per
    run. A legacy run has no actionable grain and therefore no worklist, and no row in
    either shape carries a channel key - channel is analysis, never a purchase.
    """
    run = _run_for(db, run_id)
    grain = plan_grain.decision_grain_of(run)
    if plan_grain.is_legacy_run(run):
        return {
            "run_id": str(run.id),
            "as_of": None,
            "decision_grain": None,
            "front_planning_contract_version": None,
            "rows": [],
        }
    if grain == plan_grain.LOCATION_GRAIN:
        return _location_grain_worklist(db, run)
    rows = (
        db.query(OrderSummaryRow, Product, Supplier)
        .join(Product, Product.id == OrderSummaryRow.product_id)
        .outerjoin(Supplier, Supplier.id == OrderSummaryRow.chosen_supplier_id)
        .filter(
            OrderSummaryRow.run_id == run.id,
            OrderSummaryRow.chosen_qty.isnot(None),
        )
        .all()
    )
    leads = _lead_times(
        db,
        [(str(r.product_id), str(r.chosen_supplier_id)) for r, _p, _s in rows
         if r.chosen_supplier_id],
    )
    splits = _location_allocations(db, [str(r.id) for r, _p, _s in rows])
    today = _today()

    out: list[dict] = []
    for row, product, supplier in rows:
        lead = leads.get((str(row.product_id), str(row.chosen_supplier_id or "")))
        need_by = row.shortfall_at
        # No place-by from a GUESSED lead time. A derived date is acted on, so producing
        # one from a figure nobody recorded is worse than reporting that it cannot be
        # derived - which is the same rule the report applies to months of cover.
        place_by = (
            need_by - timedelta(days=int(lead))
            if need_by is not None and lead is not None
            else None
        )
        cost = _f(row.chosen_qty) or 0.0
        unit = leads.get(("cost", str(row.product_id), str(row.chosen_supplier_id or "")))
        out.append({
            "product_code": product.product_code,
            "product_name": product.product_name,
            "uom": getattr(getattr(product, "base_uom", None), "uom_code", None),
            # The run's grain on every row as well as on the response: a row is what gets
            # handed around, and which shape it is (product + split, or location) is not
            # something to infer from which fields happen to be null.
            "decision_grain": plan_grain.PRODUCT_GRAIN,
            # The precision the quantity was DECIDED at, so it is keyed at that precision.
            "uom_decimal_places": row.uom_decimal_places,
            # A product-grain row names no location: where it lands is the split.
            "warehouse_code": None,
            "warehouse_name": None,
            "location_allocations": splits.get(str(row.id)) or [],
            "chosen_qty": _f(row.chosen_qty) or 0.0,
            "suggested_qty": _f(row.suggested_qty) or 0.0,
            "chosen_supplier_code": supplier.supplier_code if supplier else None,
            "chosen_supplier_name": supplier.supplier_name if supplier else None,
            "decided_by": row.decided_by or "unknown",
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "need_by": need_by.isoformat() if need_by else None,
            "place_by": place_by.isoformat() if place_by else None,
            "lead_time_days": int(lead) if lead is not None else None,
            # Flagged rather than silently listed among the ones still in time (AC-C2). An
            # order that had to be placed five weeks ago is a different job.
            "is_late": bool(place_by is not None and place_by < today),
            "last_po_cost": unit,
            "last_po_currency": leads.get(
                ("ccy", str(row.product_id), str(row.chosen_supplier_id or ""))
            ),
            "cash_committed": (round(cost * unit, 2) if unit is not None else None),
            "keyed_status": row.keyed_status or "not_keyed",
            "keyed_by": row.keyed_by,
            "keyed_at": row.keyed_at.isoformat() if row.keyed_at else None,
        })

    # SERVER-owned ordering, worst first: late, then by place-by with nulls last, then by
    # code. Filtering to not-keyed is the primary use of the screen (AC-E2.4), but urgency
    # decides WHICH not-keyed row to do first, and a client free to re-sort could disagree
    # with the late flag beside it.
    out.sort(
        key=lambda r: (
            not r["is_late"],
            r["place_by"] is None,
            r["place_by"] or "",
            r["product_code"],
        )
    )
    return {
        "run_id": str(run.id),
        "as_of": (rows[0][0].as_of.isoformat() if rows else None),
        "decision_grain": plan_grain.decision_grain_of(run),
        "front_planning_contract_version": run.front_planning_contract_version,
        "rows": out,
    }


def _location_grain_worklist(db: Session, run: ReorderRun) -> dict:
    """The worklist of a run decided at LOCATION grain (plan 5.4).

    Its decisions live on `scm.reorder_recommendation` (accepted or adjusted) with the
    quantity on the override when there is one, so each row IS a location and carries no
    `location_allocations`: the two shapes are alternatives, never both, because a row that
    named a location AND a split would invite keying the same units twice.

    The product summary row is a read-only aggregate under this grain, so it supplies the
    frozen need-by date the row is worked against, and never a quantity. The keyed status
    is the recommendation's own: keying is per location here, because each location IS a
    purchase order, and one status shared across a product's locations would key WH-B the
    moment WH-A was.
    """
    from app.models.scm import RecommendationOverride

    recs = (
        db.query(ReorderRecommendation, Product, Warehouse, Supplier)
        .join(Product, Product.id == ReorderRecommendation.product_id)
        .outerjoin(Warehouse, Warehouse.id == ReorderRecommendation.warehouse_id)
        .outerjoin(Supplier, Supplier.id == ReorderRecommendation.supplier_id)
        .filter(
            ReorderRecommendation.run_id == str(run.id),
            ReorderRecommendation.status.in_(("accepted", "adjusted")),
        )
        .all()
    )
    rec_ids = [str(rec.id) for rec, _p, _w, _s in recs]
    overrides: dict[str, RecommendationOverride] = {}
    if rec_ids:
        for ov in (
            db.query(RecommendationOverride)
            .filter(RecommendationOverride.recommendation_id.in_(rec_ids))
            .order_by(RecommendationOverride.overridden_at.asc().nullsfirst())
            .all()
        ):
            overrides[str(ov.recommendation_id)] = ov   # newest wins

    summary = {
        str(r.product_id): r
        for r in db.query(OrderSummaryRow)
        .filter(OrderSummaryRow.run_id == str(run.id))
        .all()
    }
    leads = _lead_times(
        db, [(str(rec.product_id), str(rec.supplier_id)) for rec, _p, _w, _s in recs
             if rec.supplier_id])
    today = _today()
    decimals = _uom_decimal_places(db, list({str(rec.product_id) for rec, *_ in recs}))

    out: list[dict] = []
    for rec, product, warehouse, supplier in recs:
        override = overrides.get(str(rec.id))
        chosen = (_f(override.override_qty) if override is not None
                  and override.override_qty is not None else _f(rec.rounded_qty)) or 0.0
        row = summary.get(str(rec.product_id))
        lead = leads.get((str(rec.product_id), str(rec.supplier_id or "")))
        need_by = row.shortfall_at if row is not None else None
        place_by = (need_by - timedelta(days=int(lead))
                    if need_by is not None and lead is not None else None)
        unit = leads.get(("cost", str(rec.product_id), str(rec.supplier_id or "")))
        out.append({
            "product_code": product.product_code,
            "product_name": product.product_name,
            "uom": getattr(getattr(product, "base_uom", None), "uom_code", None),
            "decision_grain": plan_grain.LOCATION_GRAIN,
            "uom_decimal_places": (row.uom_decimal_places if row is not None
                                   else decimals.get(str(rec.product_id))),
            "warehouse_code": warehouse.warehouse_code if warehouse else None,
            "warehouse_name": warehouse.warehouse_name if warehouse else None,
            "location_allocations": None,
            "chosen_qty": chosen,
            "suggested_qty": _f(rec.rounded_qty) or 0.0,
            "chosen_supplier_code": supplier.supplier_code if supplier else None,
            "chosen_supplier_name": supplier.supplier_name if supplier else None,
            "decided_by": (override.overridden_by if override is not None
                           and override.overridden_by else "unknown"),
            "decided_at": (override.overridden_at.isoformat()
                           if override is not None and override.overridden_at else None),
            "need_by": need_by.isoformat() if need_by else None,
            "place_by": place_by.isoformat() if place_by else None,
            "lead_time_days": int(lead) if lead is not None else None,
            "is_late": bool(place_by is not None and place_by < today),
            "last_po_cost": unit,
            "last_po_currency": leads.get(
                ("ccy", str(rec.product_id), str(rec.supplier_id or ""))),
            "cash_committed": (round(chosen * unit, 2) if unit is not None else None),
            "keyed_status": rec.keyed_status or "not_keyed",
            "keyed_by": rec.keyed_by,
            "keyed_at": rec.keyed_at.isoformat() if rec.keyed_at else None,
        })

    out.sort(
        key=lambda r: (
            not r["is_late"],
            r["place_by"] is None,
            r["place_by"] or "",
            r["product_code"],
            r["warehouse_code"] or "",
        )
    )
    as_of = next((r.as_of.isoformat() for r in summary.values() if r.as_of), None)
    return {
        "run_id": str(run.id),
        "as_of": as_of,
        "decision_grain": plan_grain.LOCATION_GRAIN,
        "front_planning_contract_version": run.front_planning_contract_version,
        "rows": out,
    }


def _lead_times(
    db: Session, pairs: list[tuple[str, str]]
) -> dict:
    """Lead time and last cost per (product, supplier), keyed for `po_worklist`.

    MEASURED lead time wins over the supplier link's standard figure, for the same reason
    it does on the report: what a supplier actually takes is what a place-by date has to be
    derived from, and the link's value is the promise. Cost is the ORDERED cost off the
    newest PO line (AC-C7), falling back to the link's quoted price.

    One query per source rather than one per row: the worklist is as long as the number of
    decisions, and this is called once for all of them.
    """
    if not pairs:
        return {}
    product_ids = list({p for p, _s in pairs})
    supplier_ids = list({s for _p, s in pairs if s})
    out: dict = {}

    for pid, sid, lead, cost, ccy in (
        db.query(
            ProductSupplier.product_id,
            ProductSupplier.supplier_id,
            ProductSupplier.standard_lead_time_days,
            ProductSupplier.unit_cost,
            ProductSupplier.currency,
        )
        .filter(
            ProductSupplier.product_id.in_(product_ids),
            ProductSupplier.supplier_id.in_(supplier_ids),
        )
        .all()
    ):
        key = (str(pid), str(sid))
        if lead is not None:
            out[key] = float(lead)
        if cost is not None:
            out[("cost", str(pid), str(sid))] = float(cost)
            out[("ccy", str(pid), str(sid))] = (ccy or "").upper() or None

    # Measured performance overrides the promise where it exists.
    for sid, pid, avg in (
        db.query(
            SupplierPerformance.supplier_id,
            SupplierPerformance.product_id,
            SupplierPerformance.avg_lead_time_days,
        )
        .filter(
            SupplierPerformance.supplier_id.in_(supplier_ids),
            or_(
                SupplierPerformance.product_id.in_(product_ids),
                SupplierPerformance.product_id.is_(None),
            ),
        )
        .order_by(SupplierPerformance.period_end.desc().nullslast())
        .all()
    ):
        if avg is None:
            continue
        for p in ([str(pid)] if pid else product_ids):
            out[(p, str(sid))] = float(avg)

    # The ordered cost wins over the link's quote (AC-C7 reads it off prior PO lines).
    for pid, sid, cost, ccy in (
        db.query(
            PurchaseOrderLine.product_id,
            PurchaseOrder.supplier_id,
            PurchaseOrderLine.unit_cost,
            PurchaseOrderLine.currency,
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.product_id.in_(product_ids),
            PurchaseOrder.supplier_id.in_(supplier_ids),
            PurchaseOrderLine.unit_cost.isnot(None),
        )
        .order_by(PurchaseOrder.issue_date.desc().nullslast())
        .all()
    ):
        key = ("cost", str(pid), str(sid))
        if key in out and out.get(("po", str(pid), str(sid))):
            continue  # already took this pair's newest PO
        out[key] = float(cost)
        out[("ccy", str(pid), str(sid))] = (ccy or "").upper() or None
        out[("po", str(pid), str(sid))] = True

    return out


def set_keyed_status(
    db: Session,
    product_code: str,
    *,
    run_id: str,
    keyed_status: str,
    actor: Optional[str] = None,
    warehouse_code: Optional[str] = None,
) -> dict:
    """Record that a PO has been keyed into AutoCount, or un-record it (AC-E2.2).

    ANY transition is allowed, including backwards. Somebody who marked a row keyed by
    mistake has to be able to unmark it, and a state machine that only moved forward would
    leave them editing the database by hand.

    A use-pool decision (quantity zero) is refused: there is no purchase order to key, and
    accepting the write would record a fiction the worklist then reports as done.

    The write lands at the run's own grain (AC-F09). A PRODUCT-grain run keys the product
    summary row and names no location. A LOCATION-grain run keys ONE recommendation, so
    `warehouse_code` is required there: each location is its own purchase order, and the
    product row under that grain is an aggregate that owns no decision to key.
    """
    if keyed_status not in KEYED_STATUSES:
        raise AppException(
            422, f"A keyed status is one of {', '.join(KEYED_STATUSES)}."
        )
    run = _run_for(db, run_id)
    product = _product_by_code(db, product_code)
    if plan_grain.decision_grain_of(run) == plan_grain.LOCATION_GRAIN:
        if not (warehouse_code or "").strip():
            raise AppException(
                422,
                f"{product.product_code} was decided per location in that plan, so the "
                "location to key has to be named.",
            )
        return _set_location_keyed_status(
            db, run, product, warehouse_code=warehouse_code,
            keyed_status=keyed_status, actor=actor,
        )
    if (warehouse_code or "").strip():
        raise AppException(
            409,
            f"{product.product_code} was decided as one order for the company in that "
            "plan, so it is keyed as a whole, not per location.",
        )
    row = (
        db.query(OrderSummaryRow)
        .filter(
            OrderSummaryRow.run_id == run.id,
            OrderSummaryRow.product_id == str(product.id),
        )
        .one_or_none()
    )
    if row is None or row.chosen_qty is None:
        raise AppException(
            404,
            f"{product.product_code} has no decision in that plan, so there is nothing to key.",
        )
    if float(row.chosen_qty) <= 0:
        raise AppException(
            422,
            f"{product.product_code} is covered from stock, so there is no purchase order "
            "to key.",
        )

    row.keyed_status = keyed_status
    row.keyed_by = actor or "unknown"
    row.keyed_at = to_naive_datetime(datetime.now(MALAYSIA_TZ))
    db.commit()
    db.refresh(row)
    return {
        "product_code": product.product_code,
        "warehouse_code": None,
        "keyed_status": row.keyed_status,
        "keyed_by": row.keyed_by,
        "keyed_at": row.keyed_at.isoformat(),
    }


def _set_location_keyed_status(
    db: Session,
    run: ReorderRun,
    product: Product,
    *,
    warehouse_code: str,
    keyed_status: str,
    actor: Optional[str],
) -> dict:
    """The LOCATION-grain half of `set_keyed_status`: one recommendation, one status.

    Only an accepted or adjusted recommendation is on the worklist, so only that is
    keyable; a location the run never decided for is a 404, the same answer the product
    path gives a product with no decision.
    """
    from app.models.scm import RecommendationOverride

    warehouse = (
        db.query(Warehouse)
        .filter(func.upper(Warehouse.warehouse_code) == warehouse_code.strip().upper())
        .first()
    )
    if warehouse is None:
        raise AppException(404, f"No location with code {warehouse_code}.")
    recs = (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == str(run.id),
            ReorderRecommendation.product_id == str(product.id),
            ReorderRecommendation.warehouse_id == str(warehouse.id),
            ReorderRecommendation.status.in_(("accepted", "adjusted")),
        )
        .all()
    )
    if not recs:
        raise AppException(
            404,
            f"{product.product_code} has no decision at {warehouse.warehouse_code} in that "
            "plan, so there is nothing to key.",
        )
    override = (
        db.query(RecommendationOverride)
        .filter(RecommendationOverride.recommendation_id.in_([str(r.id) for r in recs]))
        .order_by(RecommendationOverride.overridden_at.desc().nullslast())
        .first()
    )
    chosen = (
        _f(override.override_qty)
        if override is not None and override.override_qty is not None
        else _f(recs[0].rounded_qty)
    ) or 0.0
    if chosen <= 0:
        raise AppException(
            422,
            f"{product.product_code} at {warehouse.warehouse_code} is covered from stock, "
            "so there is no purchase order to key.",
        )
    now = to_naive_datetime(datetime.now(MALAYSIA_TZ))
    for rec in recs:
        rec.keyed_status = keyed_status
        rec.keyed_by = actor or "unknown"
        rec.keyed_at = now
    db.commit()
    rec = recs[0]
    db.refresh(rec)
    return {
        "product_code": product.product_code,
        "warehouse_code": warehouse.warehouse_code,
        "keyed_status": rec.keyed_status,
        "keyed_by": rec.keyed_by,
        "keyed_at": rec.keyed_at.isoformat(),
    }
