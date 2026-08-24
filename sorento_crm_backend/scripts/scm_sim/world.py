"""Deterministic seed builders for the SCM reorder-engine simulation.

Every date here is relative to ``AS_OF``, never to ``date.today()`` - the whole point of
the harness is that re-running it in a month, a year, or on a different machine seeds the
IDENTICAL world. ``runner.py`` patches ``app.services.scm.reorder_run_service.date`` so the
engine also plans as of ``AS_OF``, not the real wall clock.

All rows this module writes carry a ``SIM`` prefix (``SIM-P###`` products, ``SIM-WH-*``
warehouses, ``SIM-SUP-*`` suppliers, ``SIM-CUS-*`` customers, ``SIM-CAT`` / ``SIM-UOM``) so
``runner.reset_sim_db`` can be a blunt TRUNATE without a second thought about what else
might be in the (dedicated, disposable) sim database.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

#: The frozen clock. Every seeded date is AS_OF plus/minus a fixed offset, so the world
#: does not drift as real time passes. ``runner.py`` patches the engine's own clock to
#: this same value before calling ``run_reorder``.
AS_OF = date(2026, 9, 1)

#: The company every sim row is stamped with. Matches the fixed Sorento company id used
#: everywhere else in this codebase (migration 302 / ``_seed_default_company``).
SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

WH_DEALER = "SIM-WH-D"
WH_PROJECT = "SIM-WH-P"

CATEGORY_CODE = "SIM-CAT"
UOM_CODE = "SIM-UOM"

CUSTOMER_DEALER = "SIM-CUS-D"
CUSTOMER_PROJECT = "SIM-CUS-P"

#: code -> (supplier_code, supplier_name, nominal currency). Nominal currency is what a
#: scenario gets unless it names its own ``currency`` override (S35 deliberately overrides
#: supplier A's link to THB to pin the missing-rate path).
SUPPLIERS = {
    "A": ("SIM-SUP-A", "Sim Supplier A", "MYR"),
    "B": ("SIM-SUP-B", "Sim Supplier B", "MYR"),
    "C": ("SIM-SUP-C", "Sim Supplier C", "CNY"),
}

#: CNY has a rate; THB deliberately does NOT (S35 pins the missing-rate path - "a rate we
#: do not have is not a rate of 1").
CNY_RATE_TO_BASE = Decimal("0.606061")

#: Fixed lead time for every sim product_suppliers link. Scenarios vary MOQ / order
#: multiple / cost, never lead time - one fewer axis to hold in your head when reading a
#: diff.
LEAD_TIME_DAYS = 30

#: Fixed sourcing lead-time sample so `standard_lead_time_days` always resolves the same
#: way (declared, never measured - no `scm.supplier_performance` rows are seeded).
_STUDY_MONTHS_START = 3  # matches reorder_level_service.DEFAULT_STUDY_MONTHS


@dataclass(frozen=True)
class ScenarioSpec:
    """One synthetic SKU and the story it is meant to tell the engine.

    ``expected_note`` is documentation only - the harness never asserts against it. The
    snapshot IS the record of what the engine actually did.
    """

    code: str  # also the product_code, e.g. "SIM-P001"
    title: str
    expected_note: str
    segment: str = "dealer"  # "dealer" | "project" -> which sim warehouse
    policy: str = "forecast"  # "forecast" | "reorder_level" | "needs_level"
    on_hand: float = 0.0
    avg_daily_demand: float = 0.0
    demand_cv: float = 0.2
    demand_pattern: str = "steady"  # steady | spiky | declining | rising | none
    sales_volume: Optional[float] = None  # override for the monthly consumption qty
    supplier: str = "A"  # "A" | "B" | "C"
    moq: Optional[float] = None
    order_multiple: Optional[float] = None
    unit_cost: float = 60.0
    currency: Optional[str] = None  # None -> the supplier's own nominal currency
    list_price: Optional[float] = None  # None -> unit_cost * 1.5
    last_purchase_age_days: Optional[int] = None
    last_purchase_cost: Optional[float] = None
    previous_purchase_age_days: Optional[int] = None
    previous_purchase_cost: Optional[float] = None
    reorder_level_value: Optional[float] = None  # only read when policy == "reorder_level"
    spo_incoming_qty: Optional[float] = None
    spo_eta_days: int = 20
    po_open_qty: Optional[float] = None
    po_order_date_days_ago: int = 15
    so_committed_qty: Optional[float] = None
    dead_movement_days_ago: Optional[int] = None  # S7 only: one stale movement, nothing since


def _uid() -> str:
    return str(uuid.uuid4())


def _d(v) -> Decimal:
    return Decimal(str(v))


# ===========================================================================
# shared infra - created once per seed, before any scenario
# ===========================================================================


def build_infra(db) -> dict:
    """Warehouses, suppliers, customers, category/uom, currency rate.

    Returns id lookups keyed by the short codes the scenario table uses
    (``"dealer"``/``"project"``, ``"A"``/``"B"``/``"C"``).
    """
    from sqlalchemy import text

    from app.models.inventory import Warehouse
    from app.models.order import Customer
    from app.models.procurement import Supplier
    from app.models.product import ProductCategory, UnitOfMeasure
    from app.models.scm import CurrencyRate

    # `market_segments` is DATA seeded by migration 263, which `bootstrap_env.py`'s
    # create_all-based bootstrap never runs (same class of gap as `import_field_alias` /
    # `priority_policy`, which bootstrap_env DOES replay). The customer FK needs it.
    db.execute(text(
        "INSERT INTO market_segments (code, name, sort_order, is_active) VALUES "
        "('retail', 'Retail', 1, true), ('project', 'Project', 2, true) "
        "ON CONFLICT (code) DO NOTHING"
    ))

    wh_dealer = Warehouse(
        id=_uid(), warehouse_code=WH_DEALER, warehouse_name="Sim Dealer Warehouse",
        is_active=True, counts_as_available=True, segment="dealer",
    )
    wh_project = Warehouse(
        id=_uid(), warehouse_code=WH_PROJECT, warehouse_name="Sim Project Warehouse",
        is_active=True, counts_as_available=True, segment="project",
    )
    db.add_all([wh_dealer, wh_project])

    suppliers: dict[str, str] = {}
    supplier_rows = []
    for key, (code, name, _currency) in SUPPLIERS.items():
        sid = _uid()
        suppliers[key] = sid
        supplier_rows.append(Supplier(
            id=sid, supplier_code=code, supplier_name=name, is_active=True,
            payment_terms_days=30,
        ))
    db.add_all(supplier_rows)

    cat = ProductCategory(
        id=_uid(), category_code=CATEGORY_CODE, category_name="Sim Category", is_active=True,
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=UOM_CODE, uom_name="Sim Unit", is_active=True)
    db.add_all([cat, uom])

    cust_dealer = Customer(
        id=_uid(), customer_code=CUSTOMER_DEALER, customer_name="Sim Dealer Customer",
        is_active=True, customer_type="company", market_segment_code="retail",
    )
    cust_project = Customer(
        id=_uid(), customer_code=CUSTOMER_PROJECT, customer_name="Sim Project Customer",
        is_active=True, customer_type="company", market_segment_code="project",
    )
    db.add_all([cust_dealer, cust_project])

    db.add(CurrencyRate(
        currency="CNY", rate_to_base=CNY_RATE_TO_BASE, as_of=AS_OF,
        note="scm_sim fixed rate",
    ))
    # Deliberately NO row for THB - S35 pins the missing-rate path.

    db.flush()

    return {
        "warehouses": {"dealer": wh_dealer.id, "project": wh_project.id},
        "suppliers": suppliers,
        "customers": {"dealer": cust_dealer.id, "project": cust_project.id},
        "category_id": cat.id,
        "uom_id": uom.id,
    }


# ===========================================================================
# per-scenario world
# ===========================================================================


def _demand_baseline(spec: ScenarioSpec) -> float:
    """The monthly quantity a scenario's demand distills to - shared by the consumption AND
    trajectory seeders below so the DO book and the sales-order book never imply two
    different demand stories for the same SKU."""
    return (
        float(spec.sales_volume) if spec.sales_volume is not None
        else round(float(spec.avg_daily_demand) * 30, 1)
    )


def _month_shift(d: date, months: int) -> date:
    """Same month arithmetic as ``trajectory_service._month_shift`` - duplicated rather than
    imported so this seeding module stays free of a dependency on the (DB-reading) service;
    only the two window-length constants below are actually shared."""
    total = d.year * 12 + (d.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def _consumption_months(spec: ScenarioSpec) -> list[float]:
    """Three months of DO quantity, oldest first, feeding the level-suggestion's
    ``monthly_movement`` (the study window is the 3 calendar months before AS_OF's month  -
    the same window this returns values for)."""
    baseline = _demand_baseline(spec)
    if spec.demand_pattern == "none" or baseline <= 0:
        return [0.0, 0.0, 0.0]
    if spec.demand_pattern == "rising":
        return [baseline * 0.5, baseline * 1.0, baseline * 1.5]
    if spec.demand_pattern == "declining":
        return [baseline * 1.5, baseline * 1.0, baseline * 0.5]
    if spec.demand_pattern == "spiky":
        return [baseline * 2.0, baseline * 0.2, baseline * 2.0]
    return [baseline, baseline, baseline]  # steady


def _month_start(d: date, months_back: int) -> date:
    total = d.year * 12 + (d.month - 1) - months_back
    return date(total // 12, total % 12 + 1, 1)


def _seed_consumption(db, *, product_id: str, warehouse_id: str, customer_id: str,
                      spec: ScenarioSpec) -> None:
    """Delivery-order history (``orders`` + ``order_lines``) driving both the
    level-suggestion's monthly movement AND (via ``scm.consumption_v``) the
    last-movement-date the disposition check reads.

    S7 (dead stock) is the one exception: it wants a SINGLE stale movement outside the
    3-month study window, never the steady/rising/etc. shape.
    """
    if spec.dead_movement_days_ago is not None:
        day = AS_OF - timedelta(days=spec.dead_movement_days_ago)
        _write_do(db, product_id, warehouse_id, customer_id, day, qty=max(spec.on_hand, 1))
        return

    months = _consumption_months(spec)
    if not any(months):
        return
    for i, qty in enumerate(months):
        if qty <= 0:
            continue
        month_start = _month_start(AS_OF, 3 - i)
        day = month_start + timedelta(days=9)  # the 10th of the month, well inside it
        _write_do(db, product_id, warehouse_id, customer_id, day, qty=qty)


def _write_do(db, product_id, warehouse_id, customer_id, day, *, qty) -> None:
    from app.models.order import Order, OrderLine

    order_id = _uid()
    db.add(Order(
        id=order_id, order_number=f"SIM-DO-{order_id[:8]}", order_date=day,
        customer_id=customer_id, is_cancelled=False, order_type="dealer",
    ))
    db.add(OrderLine(
        id=_uid(), line_sequence=1, order_id=order_id, product_id=product_id,
        warehouse_id=warehouse_id, quantity=_d(qty),
    ))


#: Sourced from ``app.services.scm.trajectory`` (the pure verdict module - no DB import),
#: so the window this seeder targets can never drift from the one the engine reads with.
def _trajectory_window_months(segment: str) -> int:
    from app.services.scm.trajectory import DEFAULT_PROJECT_MONTHS, DEFAULT_RETAIL_MONTHS

    return DEFAULT_PROJECT_MONTHS if segment == "project" else DEFAULT_RETAIL_MONTHS


def _seed_trajectory_history(db, *, product_id: str, warehouse_id: str, customer_id: str,
                             spec: ScenarioSpec) -> None:
    """CLOSED (fully-delivered) sales-order lines - the book ``trajectory_service`` reads to
    judge rising/holding/falling/quiet. Seeded for EVERY demand-bearing scenario (not just
    the two original trend probes), so the Reorder Planning grid's Trend column reads the
    scenario's own story instead of falsely reading "no order history" for every scenario
    that never happened to touch ``sales_order_lines`` (S5/S6's rising/declining shapes are
    untouched here - the story they were built to tell stays exactly as it was).

    ``line_status='closed'`` + ``qty_delivered == qty_ordered`` so these never contribute
    to ``scm.committed_v`` - they are historical evidence of a book rising or falling, not
    outstanding demand.

    P007 (dead stock) and the genuinely zero-demand rows are exempt: the ABSENCE of a
    trajectory book IS their story, not a gap to fill.
    """
    from app.models.order import SalesOrder, SalesOrderLine

    if spec.dead_movement_days_ago is not None:
        return  # P007: one stale DO movement, no order-placement trend to report either.

    baseline = _demand_baseline(spec)
    if spec.demand_pattern == "none" or baseline <= 0:
        return  # genuinely no demand -> genuinely no trend history.

    def _write_so(day: date, qty: float, tag: str) -> None:
        so_id = _uid()
        db.add(SalesOrder(
            id=so_id, so_number=f"SIM-SO-{spec.code}-{tag}", customer_id=customer_id,
            order_date=day, order_type=spec.segment,
            status="closed", source_system="scm_sim", source_ref=spec.code,
        ))
        db.add(SalesOrderLine(
            id=_uid(), sales_order_id=so_id, product_id=product_id,
            warehouse_id=warehouse_id, qty_ordered=_d(qty), qty_delivered=_d(qty),
            line_status="closed", source_system="scm_sim", source_ref=spec.code,
        ))

    if spec.demand_pattern == "rising":
        # Unchanged from the original S5 shape: recent window has orders, the window
        # before it has none at all - "started from nothing" reads as rising regardless of
        # window length, so this needs no window-size awareness.
        for i, (days_ago, qty) in enumerate([(20, 30.0), (45, 30.0)]):
            _write_so(AS_OF - timedelta(days=days_ago), qty, f"T{i}")
        return
    if spec.demand_pattern == "declining":
        # Unchanged from the original S6 shape: one light recent order against two heavier
        # ones in the window before.
        for i, (days_ago, qty) in enumerate([(25, 20.0), (95, 50.0), (140, 50.0)]):
            _write_so(AS_OF - timedelta(days=days_ago), qty, f"T{i}")
        return

    # steady / spiky: monthly buckets across BOTH the recent and previous trend windows so
    # the verdict reads "holding"/a real comparison instead of "no history". Window length
    # is segment-aware (retail 3mo / project 12mo) - the same pair `trajectory_service`
    # itself falls back to when no policy overrides it (none is seeded in this world).
    months = _trajectory_window_months(spec.segment)
    until = _month_shift(AS_OF, 0)
    recent_start = _month_shift(until, -months)
    prev_start = _month_shift(until, -2 * months)
    # A third, older window: the SNAPSHOT reads trajectory pinned at AS_OF, but the live
    # UI endpoint anchors at the real today. When today sits a little before AS_OF, its
    # "previous" window reaches one month further back than AS_OF's does - if that month
    # is unseeded, a steady book falsely reads "rising" in the UI while the snapshot says
    # "holding". Seeding one full extra window behind keeps both anchors on evidence.
    prev2_start = _month_shift(until, -3 * months)

    if spec.demand_pattern == "spiky":
        # Deterministic lumpy shape - one big month, the rest quiet. No randomness: the same
        # shape both windows so a rerun (or a human reading the code) sees the same story.
        shape = [baseline * 2.0] + [baseline * 0.2] * (months - 1)
    else:  # steady
        shape = [baseline] * months

    for window_start, tag in ((recent_start, "R"), (prev_start, "P"), (prev2_start, "Q")):
        for i, qty in enumerate(shape):
            if qty <= 0:
                continue
            month_start = _month_shift(window_start, i)
            _write_so(month_start + timedelta(days=9), qty, f"{tag}{i}")


def _seed_committed_demand(db, *, product_id: str, warehouse_id: str, customer_id: str,
                           spec: ScenarioSpec) -> None:
    """An OPEN sales-order line naming this SKU - the demand ``scm.committed_v`` nets.

    Project-side demand is only counted by the view when it originates from the Order
    Inquiry feed (S13b), so a project scenario is stamped ``demand_class='project'`` +
    ``demand_origin='scm_order_inquiry'``; a dealer scenario is left unclassified, which the
    view counts unconditionally (``demand_class IS DISTINCT FROM 'project'``).
    """
    from app.models.order import SalesOrder, SalesOrderLine

    if not spec.so_committed_qty:
        return
    so_id = _uid()
    is_project = spec.segment == "project"
    db.add(SalesOrder(
        id=so_id, so_number=f"SIM-SO-{spec.code}", customer_id=customer_id,
        order_date=AS_OF - timedelta(days=3), order_type=spec.segment, status="open",
        demand_class=("project" if is_project else None),
        demand_origin=("scm_order_inquiry" if is_project else None),
        source_system="scm_sim", source_ref=spec.code,
    ))
    db.add(SalesOrderLine(
        id=_uid(), sales_order_id=so_id, product_id=product_id, warehouse_id=warehouse_id,
        qty_ordered=_d(spec.so_committed_qty), qty_delivered=_d(0), line_status="open",
        source_system="scm_sim", source_ref=spec.code,
    ))


def _seed_spo_incoming(db, *, product_id: str, warehouse_id: str, supplier_id: str,
                       spec: ScenarioSpec) -> None:
    """An open SPO allocation - this IS the on-order supply ``scm.on_order_v`` nets."""
    from app.models.procurement import InboundShipment, SPOAllocation

    if not spec.spo_incoming_qty:
        return
    ship_id = _uid()
    db.add(InboundShipment(
        id=ship_id, shipment_number=f"SIM-SHP-{spec.code}", supplier_id=supplier_id,
        shipment_date=AS_OF - timedelta(days=10),
        estimated_arrival_date=AS_OF + timedelta(days=spec.spo_eta_days),
        shipment_status="in_transit",
    ))
    db.add(SPOAllocation(
        id=_uid(), spo_number=f"SIM-SPO-{spec.code}", inbound_shipment_id=ship_id,
        warehouse_id=warehouse_id, product_id=product_id,
        allocated_quantity=int(round(spec.spo_incoming_qty)), receipt_status="pending",
        quantity_received=0,
    ))


def _seed_po_open(db, *, product_id: str, warehouse_id: str, supplier_id: str,
                  spec: ScenarioSpec) -> None:
    """An open purchase-order line - INFORMATIONAL only (``scm.po_ordered_v``). Per ADR
    (migration 337), supply is the SPO allocation, never the PO - this line does NOT net
    against demand. Scenarios that name it are pinning exactly that: the buy still fires."""
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    if not spec.po_open_qty:
        return
    po_id = _uid()
    currency = spec.currency or SUPPLIERS[spec.supplier][2]
    db.add(PurchaseOrder(
        id=po_id, po_number=f"SIM-PO-{spec.code}", supplier_id=supplier_id,
        issue_date=AS_OF - timedelta(days=spec.po_order_date_days_ago),
        expected_date=AS_OF + timedelta(days=14), status="active", currency=currency,
        source_system="scm_sim", source_ref=spec.code,
    ))
    db.add(PurchaseOrderLine(
        id=_uid(), purchase_order_id=po_id, product_id=product_id, warehouse_id=warehouse_id,
        qty_ordered=_d(spec.po_open_qty), qty_received=_d(0), unit_cost=_d(spec.unit_cost),
        currency=currency, expected_date=AS_OF + timedelta(days=14), line_status="open",
        source_system="scm_sim", source_ref=spec.code,
    ))


def _seed_price_history(db, *, product_id: str, warehouse_id: str, supplier_id: str,
                        spec: ScenarioSpec) -> None:
    """CLOSED, fully-received PO lines purely as purchase-price evidence (S11-S14).

    ``line_status='closed'`` + fully received so they never register as open PO exposure - 
    isolated from the po_open_qty axis above.
    """
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    currency = spec.currency or SUPPLIERS[spec.supplier][2]

    def _line(tag: str, age_days: int, cost: float) -> None:
        po_id = _uid()
        issue = AS_OF - timedelta(days=age_days)
        db.add(PurchaseOrder(
            id=po_id, po_number=f"SIM-PPO-{spec.code}-{tag}", supplier_id=supplier_id,
            issue_date=issue, expected_date=issue, status="closed", currency=currency,
            source_system="scm_sim", source_ref=spec.code,
        ))
        db.add(PurchaseOrderLine(
            id=_uid(), purchase_order_id=po_id, product_id=product_id,
            warehouse_id=warehouse_id, qty_ordered=_d(50), qty_received=_d(50),
            unit_cost=_d(cost), currency=currency, expected_date=issue,
            line_status="closed", source_system="scm_sim", source_ref=spec.code,
        ))

    if spec.last_purchase_age_days is not None:
        _line("last", spec.last_purchase_age_days,
              spec.last_purchase_cost if spec.last_purchase_cost is not None else spec.unit_cost)
    if spec.previous_purchase_age_days is not None:
        _line("previous", spec.previous_purchase_age_days,
              spec.previous_purchase_cost
              if spec.previous_purchase_cost is not None else spec.unit_cost)


def _seed_policy(db, *, product_id: str, warehouse_id: str, spec: ScenarioSpec) -> None:
    """A per-SKU policy row when the scenario is not on the plain forecast basis, plus a
    ``scm.reorder_level`` row for (almost) every scenario - S2/UAC C1.

    A sku-scope ``reorder_policy`` row pinned to ``reorder_level`` (below) makes a
    scenario manual REGARDLESS of the global toggle - that is only meant for the two
    scenarios whose story IS the reorder-level basis (P031/P032). Every other scenario
    stays on the plain forecast basis and resolves through the GLOBAL row, so seeding it
    a level here is harmless while the global mode is auto and becomes the real trigger
    line the moment somebody flips the global toggle to manual (C3's round-trip needs
    every "forecast" scenario to have a coherent manual-mode answer too, not just P031/
    P032). P033 (``needs_level``) and P038 (genuinely zero demand, zero stock) are the
    deliberate exceptions: an ABSENT level is part of their story, so none is seeded for
    them at all.

    P007 (dead stock) is NOT one of those exceptions, despite having no measurable
    demand: real dead stock still carries a reorder level in AutoCount (nobody deletes
    it just because the SKU stopped moving), and "a level nobody has revisited" is
    exactly the trap manual mode has to be honest about - see ``reorder_level_value``
    on its ``ScenarioSpec``, which bypasses the baseline-demand check below.
    """
    from app.models.scm import ReorderLevel, ReorderPolicy

    if spec.policy in ("reorder_level", "needs_level"):
        db.add(ReorderPolicy(
            id=_uid(), scope_type="sku", scope_ref=str(product_id),
            policy_type="reorder_level", is_active=True, priority=0,
            source_system="scm_sim", source_ref=spec.code,
        ))

    if spec.policy == "needs_level":
        return  # P033: deliberately NO scm.reorder_level row at all.

    if spec.reorder_level_value is not None:
        # P031/P032/P007: the value the story is written around, unchanged - this branch
        # is what lets P007 (zero demand) carry a level at all, bypassing the
        # baseline-demand check below.
        level_value = float(spec.reorder_level_value)
    else:
        baseline = _demand_baseline(spec)
        if baseline <= 0:
            return  # P038: genuinely no demand and no story that needs a level either.
        level_value = round(baseline * 2, 1)

    db.add(ReorderLevel(
        id=_uid(), product_id=product_id, warehouse_id=warehouse_id,
        level=_d(level_value), source="manual",
    ))


def build_scenario(db, spec: ScenarioSpec, infra: dict) -> dict:
    """Write every row one scenario needs. Returns ``{product_id, warehouse_id}``."""
    from app.models.inventory import Stock
    from app.models.product import Product
    from app.models.procurement import ProductSupplier
    from app.models.scm import DemandStat

    warehouse_id = infra["warehouses"][spec.segment]
    supplier_id = infra["suppliers"][spec.supplier]
    customer_id = infra["customers"][spec.segment]
    currency = spec.currency or SUPPLIERS[spec.supplier][2]
    list_price = spec.list_price if spec.list_price is not None else round(spec.unit_cost * 1.5, 2)

    product_id = _uid()
    db.add(Product(
        id=product_id, product_code=spec.code, product_name=spec.title,
        category_id=infra["category_id"], base_uom_id=infra["uom_id"],
        list_price=_d(list_price), cost_price=_d(spec.unit_cost), currency="MYR",
        is_active=True, is_discontinued=False,
    ))
    db.flush()

    db.add(Stock(
        id=_uid(), product_id=product_id, warehouse_id=warehouse_id,
        quantity_on_hand=int(round(spec.on_hand)), quantity_reserved=0,
    ))
    db.add(ProductSupplier(
        id=_uid(), product_id=product_id, supplier_id=supplier_id,
        standard_lead_time_days=LEAD_TIME_DAYS, moq=(int(spec.moq) if spec.moq else None),
        order_multiple=(int(spec.order_multiple) if spec.order_multiple else None),
        unit_cost=_d(spec.unit_cost), currency=currency, is_primary_supplier=True,
    ))
    db.add(DemandStat(
        id=_uid(), product_id=product_id, warehouse_id=warehouse_id,
        avg_daily_demand=_d(spec.avg_daily_demand), baseline_rate=_d(spec.avg_daily_demand),
        demand_cv=_d(spec.demand_cv), sample_days=30, window_days=90, method="scm_sim",
        source_system="scm_sim", source_ref=spec.code,
    ))

    _seed_consumption(db, product_id=product_id, warehouse_id=warehouse_id,
                      customer_id=customer_id, spec=spec)
    _seed_trajectory_history(db, product_id=product_id, warehouse_id=warehouse_id,
                             customer_id=customer_id, spec=spec)
    _seed_committed_demand(db, product_id=product_id, warehouse_id=warehouse_id,
                           customer_id=customer_id, spec=spec)
    _seed_spo_incoming(db, product_id=product_id, warehouse_id=warehouse_id,
                       supplier_id=supplier_id, spec=spec)
    _seed_po_open(db, product_id=product_id, warehouse_id=warehouse_id,
                 supplier_id=supplier_id, spec=spec)
    _seed_price_history(db, product_id=product_id, warehouse_id=warehouse_id,
                        supplier_id=supplier_id, spec=spec)
    _seed_policy(db, product_id=product_id, warehouse_id=warehouse_id, spec=spec)

    return {"product_id": product_id, "warehouse_id": warehouse_id}


def seed_all(db, scenarios: list[ScenarioSpec]) -> dict:
    """Infra once, then every scenario. Returns ``{code: {product_id, warehouse_id}}``."""
    infra = build_infra(db)
    out: dict[str, dict] = {}
    for spec in scenarios:
        out[spec.code] = build_scenario(db, spec, infra)
    db.flush()
    return out
